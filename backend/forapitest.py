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
import re

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
app = FastAPI(title="Proper Player API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

lemmatizer = WordNetLemmatizer()

# === Dictionnaire de gros mots optimisé ===
# Tous en minuscules pour éviter la conversion à chaque fois
offensive_lexicon = {
    "fuck", "fucking", "fucker", "fucked", "shit", "shitty", "asshole", "bitch",
    "bastard", "dick", "dumb", "idiot", "retard", "slut", "cunt", "whore",
    "motherfucker", "pussy", "crap", "bollocks", "damn", "cock", "nigger",
    "nigga", "spic", "kike", "fag", "faggot", "twat", "wanker", "douche",
    "prick", "arse", "arsehole", "bloody", "bugger", "bullshit", "jackass",
    "moron", "nuts", "piss", "screw", "screwed", "suck", "sucks", "sex", "shitball",
    "shitballs", "ass", "butthog", "douchebag", "titty", "titties", "puzzie", 
    "atto", "retarded", "shithead", "penis", "penises"
}

# Variantes avec tirets/espaces
offensive_variations = {
    "dumb bitch", "ass-lick", "ass-licker", "ass lick", "ass licker"
}

# Regex pré-compilé pour nettoyer les mots (beaucoup plus rapide)
WORD_CLEANER = re.compile(r'[.,!?(){}\[\];:"\']')

# === Chargement lazy du modèle ===
def get_whisper_model():
    """Charge le modèle seulement quand nécessaire"""
    global whisper_model, model_loading
    
    if whisper_model is not None:
        return whisper_model
    
    if model_loading:
        max_wait = 60
        waited = 0
        while model_loading and waited < max_wait:
            time.sleep(1)
            waited += 1
        return whisper_model
    
    try:
        model_loading = True
        print("Loading Faster-Whisper model on first use...")
        # Options optimisées pour vitesse maximale
        whisper_model = WhisperModel(
            "tiny",  # Le plus rapide
            device="cpu",
            compute_type="int8",
            num_workers=1,  # Évite les conflits
            download_root=None
        )
        print("Faster-Whisper model loaded successfully!")
        return whisper_model
    finally:
        model_loading = False

# === Fonctions utilitaires optimisées ===
def convert_to_wav(input_file, output_file="audio.wav"):
    """Convertit un fichier audio en WAV - version optimisée"""
    command = [
        "ffmpeg", "-y", "-i", input_file,
        "-ac", "1",  # Mono
        "-ar", "16000",  # 16kHz suffisant pour la parole
        "-acodec", "pcm_s16le",  # Codec rapide
        output_file
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def is_offensive_fast(word: str) -> bool:
    """Détection ultra-rapide sans lemmatization"""
    # Nettoyer avec regex (plus rapide que strip multiple)
    clean_word = WORD_CLEANER.sub('', word).lower()
    
    if not clean_word:
        return False
    
    # Vérification directe (O(1) avec set)
    if clean_word in offensive_lexicon:
        return True
    
    # Vérifier les variations avec espaces/tirets
    if clean_word in offensive_variations:
        return True
    
    return False

# === Traitement en arrière-plan optimisé ===
def process_audio(job_id: str, file_path: str, filename: str):
    """Traite l'audio en arrière-plan - version optimisée"""
    wav_path = None
    start_time = time.time()
    MAX_PROCESSING_TIME = 60
    
    try:
        jobs_storage[job_id]["status"] = "processing"
        jobs_storage[job_id]["progress"] = 10
        
        # Conversion audio
        wav_path = file_path if file_path.endswith(".wav") else file_path + ".wav"
        if not file_path.endswith(".wav"):
            jobs_storage[job_id]["message"] = "Converting audio..."
            jobs_storage[job_id]["progress"] = 20
            convert_to_wav(file_path, wav_path)
        
        if time.time() - start_time > MAX_PROCESSING_TIME:
            raise Exception("Processing timeout exceeded")
        
        # Charger le modèle
        jobs_storage[job_id]["message"] = "Loading AI model..."
        jobs_storage[job_id]["progress"] = 30
        model = get_whisper_model()
        
        # Transcription avec options optimisées
        jobs_storage[job_id]["message"] = "Transcribing audio..."
        jobs_storage[job_id]["progress"] = 40
        
        # Options optimisées pour vitesse
        segments, info = model.transcribe(
            wav_path,
            word_timestamps=True,
            beam_size=1,  # Plus rapide (5 par défaut)
            best_of=1,    # Plus rapide (5 par défaut)
            temperature=0,  # Déterministe et plus rapide
            vad_filter=True,  # Filtre les silences (économise du temps)
            vad_parameters=dict(
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=100
            )
        )
        
        if time.time() - start_time > MAX_PROCESSING_TIME:
            raise Exception("Processing timeout exceeded")
        
        jobs_storage[job_id]["progress"] = 70
        jobs_storage[job_id]["message"] = "Detecting offensive words..."
        
        # Liste pré-allouée (évite les reallocations)
        toxic_words = []
        
        # Convertir en liste une seule fois
        segments_list = list(segments)
        total_segments = len(segments_list)
        
        # Traitement batch optimisé
        for idx, segment in enumerate(segments_list):
            # Update moins fréquent (économise du temps)
            if idx % 20 == 0:
                if time.time() - start_time > MAX_PROCESSING_TIME:
                    raise Exception("Processing timeout exceeded")
                
                if total_segments > 0:
                    progress = 70 + int((idx / total_segments) * 25)
                    jobs_storage[job_id]["progress"] = min(progress, 95)
            
            if not hasattr(segment, 'words') or not segment.words:
                continue
            
            # Traiter tous les mots d'un segment en une passe
            for word_data in segment.words:
                word = word_data.word
                if not word or len(word) < 2:  # Ignorer mots trop courts
                    continue
                
                # Détection ultra-rapide
                if is_offensive_fast(word):
                    toxic_words.append({
                        "word": word.strip(),
                        "start": round(word_data.start, 2),
                        "end": round(word_data.end, 2)
                    })
        
        # Terminé
        processing_time = round(time.time() - start_time, 2)
        jobs_storage[job_id]["status"] = "completed"
        jobs_storage[job_id]["progress"] = 100
        jobs_storage[job_id]["message"] = "Analysis complete!"
        jobs_storage[job_id]["result"] = {
            "total": len(toxic_words),
            "toxic_words": toxic_words,
            "processing_time": processing_time,
            "audio_duration": round(info.duration, 2) if hasattr(info, 'duration') else None,
            "speed_ratio": round(info.duration / processing_time, 2) if hasattr(info, 'duration') and processing_time > 0 else None
        }
        
        print(f"Job {job_id} completed in {processing_time}s: {len(toxic_words)} toxic words found")
        
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

# === Cleanup des vieux jobs ===
def cleanup_old_jobs():
    """Supprime les jobs de plus de 1 heure"""
    current_time = time.time()
    to_delete = [
        job_id for job_id, job in jobs_storage.items()
        if "created_at" in job and (current_time - job["created_at"]) > 3600
    ]
    
    for job_id in to_delete:
        del jobs_storage[job_id]
    
    if to_delete:
        print(f"Cleaned up {len(to_delete)} old jobs")

# === Endpoints ===
@app.get("/")
async def root():
    return {
        "status": "online", 
        "message": "Proper Player API v2.1 - Optimized",
        "version": "2.1.0",
        "model_loaded": whisper_model is not None,
        "active_jobs": len(jobs_storage),
        "optimizations": [
            "Lazy model loading",
            "VAD filtering for silence removal",
            "Beam size 1 for faster transcription",
            "Regex-based word cleaning",
            "Set-based O(1) lookups"
        ]
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
    
    cleanup_old_jobs()
    
    # Limite de taille (30 MB pour traitement rapide)
    MAX_FILE_SIZE = 30 * 1024 * 1024
    
    try:
        contents = await file.read()
        
        if len(contents) > MAX_FILE_SIZE:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "File too large. Maximum 30MB for optimal performance",
                    "status": "error"
                }
            )
        
        job_id = str(uuid.uuid4())
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        jobs_storage[job_id] = {
            "status": "queued",
            "progress": 0,
            "message": "Job queued...",
            "filename": file.filename,
            "result": None,
            "error": None,
            "created_at": time.time()
        }
        
        background_tasks.add_task(process_audio, job_id, tmp_path, file.filename)
        
        return JSONResponse(content={
            "job_id": job_id,
            "status": "queued",
            "message": "Analysis started. Use /status/{job_id} to check progress.",
            "estimate": "Processing typically takes 5-30 seconds (optimized)"
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
    completed_jobs = [j for j in jobs_storage.values() if j["status"] == "completed"]
    avg_time = sum(j["result"]["processing_time"] for j in completed_jobs if "result" in j) / len(completed_jobs) if completed_jobs else 0
    
    return {
        "model_loaded": whisper_model is not None,
        "active_jobs": len(jobs_storage),
        "jobs_by_status": {
            "queued": sum(1 for j in jobs_storage.values() if j["status"] == "queued"),
            "processing": sum(1 for j in jobs_storage.values() if j["status"] == "processing"),
            "completed": sum(1 for j in jobs_storage.values() if j["status"] == "completed"),
            "failed": sum(1 for j in jobs_storage.values() if j["status"] == "failed")
        },
        "performance": {
            "average_processing_time": round(avg_time, 2),
            "total_completed": len(completed_jobs)
        }
    }

@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Supprime un job manuellement"""
    if job_id in jobs_storage:
        del jobs_storage[job_id]
        return {"message": "Job deleted", "job_id": job_id}
    return JSONResponse(
        status_code=404,
        content={"error": "Job not found"}
    )

# Point d'entrée
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
