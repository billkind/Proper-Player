from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import tempfile
import os
import subprocess
import nltk
from nltk.stem import WordNetLemmatizer
import uuid
from typing import Dict, Optional
import time

# === Configuration ===
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# Stockage en mémoire des jobs
jobs_storage: Dict[str, dict] = {}

# Variable globale pour le modèle (chargement lazy)
whisper_model: Optional[WhisperModel] = None
model_loading = False

# === Téléchargement des ressources NLTK ===
def download_nltk_data():
    """Télécharge les ressources NLTK nécessaires"""
    resources = [
        ('tokenizers/punkt', 'punkt'),
        ('corpora/wordnet', 'wordnet'),
        ('corpora/omw-1.4', 'omw-1.4')
    ]
    for path, name in resources:
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(name, quiet=True)

download_nltk_data()

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

# === Chargement lazy du modèle ===
def get_whisper_model():
    """Charge le modèle seulement quand nécessaire"""
    global whisper_model, model_loading
    
    if whisper_model is not None:
        return whisper_model
    
    # Éviter les chargements multiples simultanés
    if model_loading:
        # Attendre que le chargement se termine
        max_wait = 60  # 60 secondes max
        waited = 0
        while model_loading and waited < max_wait:
            time.sleep(1)
            waited += 1
        return whisper_model
    
    try:
        model_loading = True
        print("Loading Faster-Whisper model on first use...")
        whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        print("Faster-Whisper model loaded successfully!")
        return whisper_model
    finally:
        model_loading = False

# === Fonctions utilitaires ===
def convert_to_wav(input_file, output_file="audio.wav"):
    """Convertit un fichier audio en WAV"""
    command = [
        "ffmpeg", "-y", "-i", input_file,
        "-ac", "1", "-ar", "16000", output_file
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# === Traitement en arrière-plan ===
def process_audio(job_id: str, file_path: str, filename: str):
    """Traite l'audio en arrière-plan"""
    wav_path = None
    start_time = time.time()
    MAX_PROCESSING_TIME = 60  # 60 secondes max (limite Render gratuit)
    
    try:
        # Mise à jour du statut
        jobs_storage[job_id]["status"] = "processing"
        jobs_storage[job_id]["progress"] = 10
        
        # Vérifier le timeout
        if time.time() - start_time > MAX_PROCESSING_TIME:
            raise Exception("Processing timeout exceeded")
        
        # Conversion audio
        wav_path = file_path if file_path.endswith(".wav") else file_path + ".wav"
        if not file_path.endswith(".wav"):
            jobs_storage[job_id]["message"] = "Converting audio..."
            jobs_storage[job_id]["progress"] = 20
            convert_to_wav(file_path, wav_path)
        
        # Vérifier le timeout
        if time.time() - start_time > MAX_PROCESSING_TIME:
            raise Exception("Processing timeout exceeded")
        
        # Charger le modèle (lazy loading)
        jobs_storage[job_id]["message"] = "Loading AI model..."
        jobs_storage[job_id]["progress"] = 30
        model = get_whisper_model()
        
        # Transcription
        jobs_storage[job_id]["message"] = "Transcribing audio..."
        jobs_storage[job_id]["progress"] = 40
        
        segments, info = model.transcribe(wav_path, word_timestamps=True)
        
        # Vérifier le timeout
        if time.time() - start_time > MAX_PROCESSING_TIME:
            raise Exception("Processing timeout exceeded")
        
        jobs_storage[job_id]["progress"] = 70
        jobs_storage[job_id]["message"] = "Detecting offensive words..."
        
        toxic_words = []
        segments_list = list(segments)
        total_segments = len(segments_list)
        
        for idx, segment in enumerate(segments_list):
            # Vérifier le timeout périodiquement
            if idx % 10 == 0:
                if time.time() - start_time > MAX_PROCESSING_TIME:
                    raise Exception("Processing timeout exceeded")
                
                # Mise à jour du progrès
                if total_segments > 0:
                    progress = 70 + int((idx / total_segments) * 25)
                    jobs_storage[job_id]["progress"] = min(progress, 95)
            
            if not hasattr(segment, 'words') or not segment.words:
                continue
                
            for word_data in segment.words:
                try:
                    word = word_data.word.strip()
                    if not word:
                        continue
                        
                    start = round(word_data.start, 2)
                    end = round(word_data.end, 2)
                    
                    # Normalisation rapide
                    norm_word = word.lower().strip(".,!?()[]{};:\"'")
                    
                    # Vérification directe
                    if norm_word in offensive_lexicon:
                        toxic_words.append({
                            "word": word,
                            "start": start,
                            "end": end
                        })
                except Exception as e:
                    print(f"Error processing word: {e}")
                    continue
        
        # Terminé
        jobs_storage[job_id]["status"] = "completed"
        jobs_storage[job_id]["progress"] = 100
        jobs_storage[job_id]["message"] = "Analysis complete!"
        jobs_storage[job_id]["result"] = {
            "total": len(toxic_words),
            "toxic_words": toxic_words,
            "processing_time": round(time.time() - start_time, 2)
        }
        
        print(f"Job {job_id} completed in {round(time.time() - start_time, 2)}s: {len(toxic_words)} toxic words")
        
    except Exception as e:
        jobs_storage[job_id]["status"] = "failed"
        jobs_storage[job_id]["error"] = str(e)
        jobs_storage[job_id]["progress"] = 0
        print(f"Job {job_id} failed: {str(e)}")
    
    finally:
        # Nettoyage
        for path in [file_path, wav_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception as e:
                    print(f"Error deleting {path}: {e}")

# === Cleanup des vieux jobs (évite l'accumulation en mémoire) ===
def cleanup_old_jobs():
    """Supprime les jobs de plus de 1 heure"""
    current_time = time.time()
    to_delete = []
    
    for job_id, job in jobs_storage.items():
        # Si le job a un timestamp et qu'il est vieux
        if "created_at" in job:
            age = current_time - job["created_at"]
            if age > 3600:  # 1 heure
                to_delete.append(job_id)
    
    for job_id in to_delete:
        del jobs_storage[job_id]
    
    if to_delete:
        print(f"Cleaned up {len(to_delete)} old jobs")

# === Endpoints ===
@app.get("/")
async def root():
    return {
        "status": "online", 
        "message": "Proper Player API v2.0 - Async Processing",
        "version": "2.0.0",
        "model_loaded": whisper_model is not None,
        "active_jobs": len(jobs_storage)
    }

@app.get("/health")
@app.head("/health")
async def health():
    """Health check rapide - ne charge PAS le modèle"""
    return {
        "status": "healthy",
        "service": "Proper-Player",
        "model_loaded": whisper_model is not None
    }

@app.post("/analyze")
async def analyze(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """Démarre l'analyse en arrière-plan et retourne un job_id"""
    
    # Nettoyage périodique
    cleanup_old_jobs()
    
    # Limite de taille (50 MB pour le plan gratuit)
    MAX_FILE_SIZE = 50 * 1024 * 1024
    
    try:
        # Lire le fichier
        contents = await file.read()
        
        # Vérifier la taille
        if len(contents) > MAX_FILE_SIZE:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "File too large. Maximum 50MB allowed on free plan",
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
            "error": None,
            "created_at": time.time()
        }
        
        # Lancer le traitement en arrière-plan
        background_tasks.add_task(process_audio, job_id, tmp_path, file.filename)
        
        return JSONResponse(content={
            "job_id": job_id,
            "status": "queued",
            "message": "Analysis started. Use /status/{job_id} to check progress.",
            "estimate": "Processing typically takes 10-60 seconds"
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
                "error": "Job not found or expired",
                "status": "not_found",
                "message": "Jobs expire after 1 hour"
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

@app.get("/stats")
async def stats():
    """Statistiques de l'API"""
    return {
        "model_loaded": whisper_model is not None,
        "active_jobs": len(jobs_storage),
        "jobs_by_status": {
            "queued": sum(1 for j in jobs_storage.values() if j["status"] == "queued"),
            "processing": sum(1 for j in jobs_storage.values() if j["status"] == "processing"),
            "completed": sum(1 for j in jobs_storage.values() if j["status"] == "completed"),
            "failed": sum(1 for j in jobs_storage.values() if j["status"] == "failed")
        }
    }

# Point d'entrée
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
