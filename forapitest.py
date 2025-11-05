from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import whisper
import tempfile
import shutil
import os
import subprocess
import json
import nltk
from nltk.stem import WordNetLemmatizer

# === Configuration ===
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# === Téléchargement des ressources NLTK ===
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)
    
try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet', quiet=True)
    
try:
    nltk.data.find('corpora/omw-1.4')
except LookupError:
    nltk.download('omw-1.4', quiet=True)

# === Initialisation ===
app = FastAPI(title="Proper Player API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

lemmatizer = WordNetLemmatizer()

# === Chargement du modèle Whisper ===
print("Loading Whisper model...")
whisper_model = whisper.load_model("base")
print("Whisper model loaded successfully!")

# === Dictionnaire de gros mots étendu ===
offensive_lexicon = set([
    "fuck", "fucking", "fucker", "fucked", "shit", "shitty", "asshole", "bitch",
    "bastard", "dick", "dumb", "dumb bitch", "idiot", "retard", "slut", "cunt", "whore",
    "motherfucker", "pussy", "crap", "bollocks", "damn", "cock", "nigger",
    "nigga", "spic", "kike", "fag", "faggot", "twat", "wanker", "douche",
    "prick", "arse", "arsehole", "bloody", "bugger", "bullshit", "jackass",
    "moron", "nuts", "piss", "screw", "screwed", "suck", "sucks", "sex", "shitball",
    "shitballs", "ass", "butthog", "douchebag", "titty", "titties", "ass-lick", "ass-licker", 
    "puzzie", "atto", "ass lick", "ass licker", "retarded", "shithead", "penis", "penises"
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
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# === Health check endpoint ===
@app.get("/")
async def root():
    return {
        "status": "online", 
        "message": "Proper Player API is running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "proper-player-api"
    }

# === Point d'API ===
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    tmp_path = None
    wav_path = None
    
    try:
        # Sauvegarde temporaire du fichier
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        
        # Conversion audio
        wav_path = tmp_path if tmp_path.endswith(".wav") else tmp_path + ".wav"
        if not tmp_path.endswith(".wav"):
            convert_to_wav(tmp_path, wav_path)
        
        # Transcription avec Whisper
        print(f"Transcribing {file.filename}...")
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
        
        print(f"Found {len(toxic_words)} offensive words")
        
        return JSONResponse(content={
            "total": len(toxic_words),
            "toxic_words": toxic_words,
            "status": "success"
        })
    
    except Exception as e:
        print(f"Error processing file: {str(e)}")
        return JSONResponse(
            status_code=500, 
            content={
                "error": str(e),
                "status": "error"
            }
        )
    
    finally:
        # Nettoyage des fichiers temporaires
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass
        if wav_path and wav_path != tmp_path and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except:
                pass

# Point d'entrée pour uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
