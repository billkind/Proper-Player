from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import whisper
import tempfile
import shutil
import re
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# === Initialisation de FastAPI ===
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ou précise ton front : ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Chargement des modèles ===
whisper_model = whisper.load_model("base")

tox_model_name = "unitary/toxic-bert"
tox_tokenizer = AutoTokenizer.from_pretrained(tox_model_name)
tox_model = AutoModelForSequenceClassification.from_pretrained(tox_model_name)
tox_model.eval()

tox_labels = ["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]

# === Fonction de détection des mots toxiques ===
def get_toxic_words(text, tokenizer, model, original_score, threshold=0.1):
    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    toxic_words = []

    for i, word in enumerate(words):
        masked_words = words.copy()
        masked_words[i] = tokenizer.mask_token
        masked_text = " ".join(masked_words)

        inputs = tokenizer(masked_text, return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.sigmoid(logits)[0]

        masked_score = probs[0].item()  # score "toxic"
        diff = original_score - masked_score

        if diff > threshold:
            toxic_words.append({"word": word, "impact": round(diff, 3)})

    return toxic_words

# === API POST /analyze ===
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    # Sauvegarde temporaire du fichier audio (quel que soit son nom ou extension)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        # Transcription
        result = whisper_model.transcribe(tmp_path, word_timestamps=False)

        segments = []
        for seg in result.get("segments", []):
            text = seg["text"].strip()

            # Prédiction de toxicité
            inputs = tox_tokenizer(text, return_tensors="pt", truncation=True)
            with torch.no_grad():
                logits = tox_model(**inputs).logits
                probs = torch.sigmoid(logits)[0]  # multi-label classification

            scores = dict(zip(tox_labels, probs.tolist()))
            toxic_score = scores.get("toxic", 0)

            # Si toxique → identifier les mots en cause
            if (
                toxic_score > 0.79 and
                scores.get("severe_toxic", 0) > 0.01 and
                scores.get("obscene", 0) > 0.15
            ):
                toxic_words = get_toxic_words(text, tox_tokenizer, tox_model, toxic_score)
                segments.append({
                    "start": round(seg["start"], 2),
                    "end": round(seg["end"], 2),
                    "text": text,
                    "scores": {k: round(v, 4) for k, v in scores.items()},
                    "toxic_words": toxic_words
                })

        return JSONResponse(content={"segments": segments, "total": len(segments)})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
