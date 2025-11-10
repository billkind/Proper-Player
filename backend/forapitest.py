from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import tempfile
import shutil
import os
import subprocess
import json
import nltk
from nltk.stem import WordNetLemmatizer
import uuid
from typing import Dict
import asyncio

# === Configuration ===
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# Stockage en mémoire des jobs (pour le plan gratuit)
# En production, utilisez Redis ou une base de données
jobs_storage: Dict[str, dict] = {}

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
app = FastAPI(title="Proper Player API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

lemmatizer = WordNetLemmatizer()

# === Chargement du modèle Whisper ===
print("Loading Faster-Whisper model...")
whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
print("Faster-Whisper model loaded successfully!")

# === Dictionnaire de gros mots ===
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

# === Fonctions utilitaires ===
def normalize(word):
    word = word.lower().strip(".,!?()[]{};:\"'")
    lemma = lemmatizer.lemmatize(word)
    return lemma

def convert_to_wav(input_file, output_file="audio.wav"):
    command = [
        "ffmpeg", "-y", "-i", input_file,
        "-ac", "1", "-ar", "16000", output_file
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# === Traitement en arrière-plan ===
def process_audio(job_id: str, file_path: str, filename: str):
    """Traite l'audio en arrière-plan"""
    wav_path = None
    
    try:
        # Mise à jour du statut
        jobs_storage[job_id]["status"] = "processing"
        jobs_storage[job_id]["progress"] = 10
        
        # Conversion audio
        wav_path = file_path if file_path.endswith(".wav") else file_path + ".wav"
        if not file_path.endswith(".wav"):
            jobs_storage[job_id]["message"] = "Converting audio..."
            jobs_storage[job_id]["progress"] = 20
            convert_to_wav(file_path, wav_path)
        
        # Transcription
        jobs_storage[job_id]["message"] = "Transcribing audio..."
        jobs_storage[job_id]["progress"] = 40
        
        segments, info = whisper_model.transcribe(wav_path, word_timestamps=True)
        
        jobs_storage[job_id]["progress"] = 70
        jobs_storage[job_id]["message"] = "Detecting offensive words..."
        
        toxic_words = []
        for segment in segments:
            for word_data in segment.words:
                word = word_data.word.strip()
                start = round(word_data.start, 2)
                end = round(word_data.end, 2)
                
                norm_word = normalize(word)
                if norm_word in offensive_lexicon:
                    toxic_words.append({
                        "word": word,
                        "start": start,
                        "end": end
                    })
        
        # Terminé
        jobs_storage[job_id]["status"] = "completed"
        jobs_storage[job_id]["progress"] = 100
        jobs_storage[job_id]["message"] = "Analysis complete!"
        jobs_storage[job_id]["result"] = {
            "total": len(toxic_words),
            "toxic_words": toxic_words
        }
        
        print(f"Job {job_id} completed: {len(toxic_words)} toxic words found")
        
    except Exception as e:
        jobs_storage[job_id]["status"] = "failed"
        jobs_storage[job_id]["error"] = str(e)
        print(f"Job {job_id} failed: {str(e)}")
    
    finally:
        # Nettoyage
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except:
                pass
        if wav_path and wav_path != file_path and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except:
                pass

# === Endpoints ===
@app.get("/")
async def root():
    return {
        "status": "online", 
        "message": "Proper Player API v2.0 - Async Processing",
        "version": "2.0.0"
    }

@app.get("/health")
@app.head("/health")
async def health():
    return {
        "status": "healthy",
        "service": "Proper-Player"
    }

@app.post("/analyze")
async def analyze(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """Démarre l'analyse en arrière-plan et retourne un job_id"""
    
    # Limite de taille (100 MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024
    
    try:
        # Lire le fichier
        contents = await file.read()
        
        # Vérifier la taille
        if len(contents) > MAX_FILE_SIZE:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "File too large. Maximum 100MB allowed",
                    "status": "error"
                }
            )
        
        # Créer un job ID unique
        job_id = str(uuid.uuid4())
        
        # Sauvegarder temporairement
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        # Initialiser le job
        jobs_storage[job_id] = {
            "status": "queued",
            "progress": 0,
            "message": "Job queued...",
            "filename": file.filename,
            "result": None,
            "error": None
        }
        
        # Lancer le traitement en arrière-plan
        background_tasks.add_task(process_audio, job_id, tmp_path, file.filename)
        
        return JSONResponse(content={
            "job_id": job_id,
            "status": "queued",
            "message": "Analysis started. Use /status/{job_id} to check progress."
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "status": "error"
            }
        )

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Récupère le statut d'un job"""
    
    if job_id not in jobs_storage:
        return JSONResponse(
            status_code=404,
            content={
                "error": "Job not found",
                "status": "not_found"
            }
        )
    
    job = jobs_storage[job_id]
    
    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "filename": job["filename"]
    }
    
    if job["status"] == "completed":
        response["result"] = job["result"]
    elif job["status"] == "failed":
        response["error"] = job["error"]
    
    return response

# Point d'entrée
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
