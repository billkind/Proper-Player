from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import whisper
import tempfile
import shutil
import re
import os
import subprocess
import json
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet

# === Téléchargement des ressources NLTK ===
nltk.download('punkt')
nltk.download('wordnet')
nltk.download('omw-1.4')

# === Initialisation ===
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

lemmatizer = WordNetLemmatizer()

# === Chargement du modèle Whisper ===
whisper_model = whisper.load_model("base")

# === Dictionnaire de gros mots étendu ===
offensive_lexicon = set([
    "fuck", "fucking", "fucker","fucked","shit","shitty", "asshole","bitch",
    "bastard","dick","dumb","dumb bitch","idiot", "retard", "slut","cunt","whore",
    "motherfucker", "pussy", "crap", "bollocks", "damn", "cock", "nigger",
    "nigga", "spic", "kike", "fag", "faggot", "twat", "wanker", "douche",
    "prick", "arse", "arsehole", "bloody", "bugger", "bullshit", "jackass",
    "moron", "nuts", "piss", "screw", "screwed","suck","sucks","sex","shitball",
    "shitballs","ass","butthog","douchebag","titty","titties","ass-lick","ass-licker","puzzie","atto",
    "ass lick","ass licker","retarded","shithead","penis","penises"
])

# === Fonction de normalisation ===
def normalize(word):
    word = word.lower().strip(".,!?()[]{};:\"'")
    lemma = lemmatizer.lemmatize(word)
    return lemma

# === Conversion automatique en .wav mono 16kHz ===
def convert_to_wav(input_file, output_file="audio.wav"):
    command = [
        "ffmpeg", "-y", "-i", input_file,
        "-ac", "1", "-ar", "16000", output_file
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)





# === Point d'API ===
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    # Conversion audio
    wav_path = tmp_path if tmp_path.endswith(".wav") else tmp_path + ".wav"
    if not tmp_path.endswith(".wav"):
        convert_to_wav(tmp_path, wav_path)

    try:
        result = whisper_model.transcribe(wav_path, word_timestamps=True)
        toxic_words = []

        for segment in result.get("segments", []):
            for word_data in segment.get("words", []):
                word = word_data["word"].strip()
                start = round(word_data["start"], 2)
                end = round(word_data["end"], 2)
                
                norm_word = normalize(word)
                if norm_word in offensive_lexicon:
                    toxic_words.append({
                        "word": word,
                        "start": start,
                        "end": end
                    })

        # Sauvegarde
        with open("toxic_words_output.json", "w", encoding="utf-8") as f:
            json.dump(toxic_words, f, indent=2)

        return JSONResponse(content={
            "total": len(toxic_words),
            "toxic_words": toxic_words
        })
    

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        os.unlink(tmp_path)
        if wav_path != tmp_path and os.path.exists(wav_path):
            os.unlink(wav_path)
