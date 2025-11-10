from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
import uuid
from typing import Dict, Set
import time
import re
import httpx
import asyncio

# === Configuration ===
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")

jobs_storage: Dict[str, dict] = {}

app = FastAPI(title="Proper Player API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Dictionnaire de mots offensants ===
OFFENSIVE_WORDS: Set[str] = {
    "fuck", "fucking", "fucker", "fucked", "fucks",
    "shit", "shitty", "shits",
    "asshole", "assholes",
    "bitch", "bitches", "bitching",
    "bastard", "bastards",
    "dick", "dicks",
    "dumb",
    "idiot", "idiots", "idiotic",
    "retard", "retarded", "retards",
    "slut", "sluts",
    "cunt", "cunts",
    "whore", "whores",
    "motherfucker", "motherfuckers",
    "pussy", "pussies",
    "crap", "crappy",
    "bollocks",
    "damn", "damned",
    "cock", "cocks",
    "nigger", "niggers", "nigga", "niggas",
    "spic", "spics",
    "kike", "kikes",
    "fag", "fags", "faggot", "faggots",
    "twat", "twats",
    "wanker", "wankers",
    "douche", "douchebag", "douchebags",
    "prick", "pricks",
    "arse", "arses", "arsehole", "arseholes",
    "bloody",
    "bugger", "buggers",
    "bullshit",
    "jackass", "jackasses",
    "moron", "morons",
    "nuts",
    "piss", "pissed", "pissing",
    "screw", "screwed", "screwing",
    "suck", "sucks", "sucking",
    "sex",
    "shitball", "shitballs",
    "ass", "asses",
    "butthog",
    "titty", "titties",
    "puzzie",
    "atto",
    "shithead", "shitheads",
    "penis", "penises"
}

PUNCTUATION_PATTERN = re.compile(r'[^\w\s-]')

# === AssemblyAI Functions ===
async def upload_to_assemblyai(file_path: str) -> str:
    """Upload le fichier audio sur AssemblyAI"""
    if not ASSEMBLYAI_API_KEY:
        raise Exception("AssemblyAI API key not configured")
    
    headers = {"authorization": ASSEMBLYAI_API_KEY}
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    "https://api.assemblyai.com/v2/upload",
                    headers=headers,
                    content=f.read()
                )
            
            response.raise_for_status()
            return response.json()["upload_url"]
    except httpx.HTTPStatusError as e:
        raise Exception(f"Upload failed: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        raise Exception(f"Upload error: {str(e)}")

async def start_transcription(audio_url: str) -> str:
    """Démarre la transcription et retourne le transcript_id"""
    headers = {
        "authorization": ASSEMBLYAI_API_KEY,
        "content-type": "application/json"
    }
    
    # Configuration optimale pour la vitesse
    data = {
        "audio_url": audio_url,
        "speech_model": "nano"  # Modèle le plus rapide
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.assemblyai.com/v2/transcript",
                headers=headers,
                json=data
            )
            
            response.raise_for_status()
            return response.json()["id"]
    except httpx.HTTPStatusError as e:
        raise Exception(f"Transcription request failed: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        raise Exception(f"Transcription error: {str(e)}")

async def poll_transcription(transcript_id: str, job_id: str) -> dict:
    """Poll le statut de la transcription avec updates du job"""
    headers = {"authorization": ASSEMBLYAI_API_KEY}
    url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    
    poll_count = 0
    max_polls = 180  # 180 polls * 2s = 6 minutes max
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            while poll_count < max_polls:
                poll_count += 1
                
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                result = response.json()
                
                status = result["status"]
                
                # Mise à jour du progrès
                if status == "processing" or status == "queued":
                    progress = min(50 + (poll_count * 2), 75)
                    jobs_storage[job_id]["progress"] = progress
                    jobs_storage[job_id]["message"] = f"Transcribing... ({status})"
                
                if status == "completed":
                    return result
                elif status == "error":
                    error_msg = result.get("error", "Unknown error")
                    raise Exception(f"Transcription failed: {error_msg}")
                
                # Attendre avant le prochain poll
                await asyncio.sleep(2)
            
            raise Exception("Transcription timeout (6 minutes)")
    except httpx.HTTPStatusError as e:
        raise Exception(f"Poll failed: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        if "Transcription" not in str(e):
            raise Exception(f"Poll error: {str(e)}")
        raise

def detect_offensive_words(words: list) -> list:
    """Détecte les mots offensants dans la transcription"""
    toxic_words = []
    
    if not words:
        return toxic_words
    
    for word_data in words:
        word = word_data.get("text", "")
        
        if not word or len(word) < 3:
            continue
        
        # Nettoyage
        clean = PUNCTUATION_PATTERN.sub('', word).lower().strip()
        
        if not clean:
            continue
        
        if clean in OFFENSIVE_WORDS:
            toxic_words.append({
                "word": word,
                "start": round(word_data["start"] / 1000.0, 2),  # ms → seconds
                "end": round(word_data["end"] / 1000.0, 2)
            })
    
    return toxic_words

# === Traitement principal ===
async def process_audio_async(job_id: str, file_path: str, filename: str):
    """Traite l'audio avec AssemblyAI"""
    start_time = time.time()
    
    try:
        # Update: Uploading
        jobs_storage[job_id]["status"] = "processing"
        jobs_storage[job_id]["progress"] = 10
        jobs_storage[job_id]["message"] = "Uploading audio..."
        
        # Upload
        audio_url = await upload_to_assemblyai(file_path)
        
        # Update: Starting transcription
        jobs_storage[job_id]["progress"] = 30
        jobs_storage[job_id]["message"] = "Starting transcription..."
        
        # Démarrer transcription
        transcript_id = await start_transcription(audio_url)
        
        # Update: Transcribing
        jobs_storage[job_id]["progress"] = 50
        jobs_storage[job_id]["message"] = "Transcribing audio..."
        
        # Poll jusqu'à completion
        result = await poll_transcription(transcript_id, job_id)
        
        # Update: Detecting
        jobs_storage[job_id]["progress"] = 80
        jobs_storage[job_id]["message"] = "Detecting offensive words..."
        
        # Détection
        words = result.get("words", [])
        toxic_words = detect_offensive_words(words)
        
        # Terminé
        elapsed = round(time.time() - start_time, 2)
        audio_duration = result.get("audio_duration", 0)
        
        jobs_storage[job_id]["status"] = "completed"
        jobs_storage[job_id]["progress"] = 100
        jobs_storage[job_id]["message"] = "Analysis complete!"
        jobs_storage[job_id]["result"] = {
            "total": len(toxic_words),
            "toxic_words": toxic_words,
            "processing_time": elapsed,
            "audio_duration": round(audio_duration, 2) if audio_duration else None,
            "transcript_id": transcript_id
        }
        
        print(f"✅ Job {job_id}: {len(toxic_words)} toxic words found in {elapsed}s (audio: {audio_duration}s)")
        
    except Exception as e:
        error_msg = str(e)
        jobs_storage[job_id]["status"] = "failed"
        jobs_storage[job_id]["error"] = error_msg
        jobs_storage[job_id]["progress"] = 0
        print(f"❌ Job {job_id} failed: {error_msg}")
    
    finally:
        # Nettoyage du fichier temporaire
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except Exception as e:
                print(f"Warning: Could not delete temp file: {e}")

def process_audio_wrapper(job_id: str, file_path: str, filename: str):
    """Wrapper synchrone pour BackgroundTasks"""
    asyncio.run(process_audio_async(job_id, file_path, filename))

# === Cleanup ===
def cleanup_old_jobs():
    """Supprime les jobs de plus d'une heure"""
    now = time.time()
    to_delete = [
        jid for jid, job in jobs_storage.items()
        if "created_at" in job and (now - job["created_at"]) > 3600
    ]
    
    for jid in to_delete:
        del jobs_storage[jid]
    
    if to_delete:
        print(f"🧹 Cleaned up {len(to_delete)} old jobs")

# === Endpoints ===
# === MODIFICATION 1 : Dans l'endpoint "/" (ligne ~319) ===
@app.get("/")
async def root():
    return {
        "status": "online",
        "version": "3.0.0",
        "message": "Proper Player API - Powered by AssemblyAI",
        "active_jobs": len(jobs_storage),
        "api_configured": bool(ASSEMBLYAI_API_KEY),
        "features": [
            "Ultra-fast transcription (10-30s for any length)",
            "No timeout issues",
            "Professional accuracy",
            "Supports files up to 500MB"  # ← CHANGÉ DE 200MB À 500MB
        ]
    }

# === MODIFICATION 2 : Dans l'endpoint "/analyze" (ligne ~342) ===
@app.post("/analyze")
async def analyze(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """Analyse un fichier audio pour détecter les mots offensants"""
    
    cleanup_old_jobs()
    
    # Vérifier la configuration
    if not ASSEMBLYAI_API_KEY:
        return JSONResponse(
            status_code=500,
            content={
                "error": "AssemblyAI API key not configured. Please add ASSEMBLYAI_API_KEY to environment variables.",
                "status": "error"
            }
        )
    
    # Limite de taille (500 MB) - CHANGÉ DE 200 À 500
    MAX_SIZE = 500 * 1024 * 1024  # ← MODIFIÉ ICI
    
    try:
        # Lire le fichier
        contents = await file.read()
        
        if len(contents) > MAX_SIZE:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "File too large. Maximum 500MB allowed.",  # ← MODIFIÉ ICI
                    "status": "error"
                }
            )
        
        # ... reste du code inchangé ...
        
        if len(contents) == 0:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Empty file",
                    "status": "error"
                }
            )
        
        # Créer job ID
        job_id = str(uuid.uuid4())
        
        # Sauvegarder temporairement
        suffix = os.path.splitext(file.filename)[-1] or ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        # Initialiser le job
        jobs_storage[job_id] = {
            "status": "queued",
            "progress": 0,
            "message": "Job queued...",
            "filename": file.filename,
            "file_size": len(contents),
            "result": None,
            "error": None,
            "created_at": time.time()
        }
        
        # Lancer le traitement en arrière-plan
        background_tasks.add_task(process_audio_wrapper, job_id, tmp_path, file.filename)
        
        return JSONResponse(content={
            "job_id": job_id,
            "status": "queued",
            "message": "Analysis started. Use GET /status/{job_id} to check progress.",
            "filename": file.filename,
            "estimate": "Usually completes in 10-30 seconds"
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
                "error": "Job not found or expired (jobs expire after 1 hour)",
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

@app.get("/stats")
async def stats():
    """Statistiques de l'API"""
    completed = [j for j in jobs_storage.values() if j["status"] == "completed"]
    failed = [j for j in jobs_storage.values() if j["status"] == "failed"]
    
    avg_time = 0
    if completed:
        times = [j["result"]["processing_time"] for j in completed if "result" in j and "processing_time" in j["result"]]
        avg_time = sum(times) / len(times) if times else 0
    
    return {
        "api_configured": bool(ASSEMBLYAI_API_KEY),
        "active_jobs": len(jobs_storage),
        "jobs_by_status": {
            "queued": sum(1 for j in jobs_storage.values() if j["status"] == "queued"),
            "processing": sum(1 for j in jobs_storage.values() if j["status"] == "processing"),
            "completed": len(completed),
            "failed": len(failed)
        },
        "performance": {
            "average_processing_time": round(avg_time, 2),
            "total_completed": len(completed),
            "total_failed": len(failed),
            "success_rate": round(len(completed) / (len(completed) + len(failed)) * 100, 1) if (len(completed) + len(failed)) > 0 else 0
        },
        "api_provider": "AssemblyAI"
    }

@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Supprime un job manuellement"""
    if job_id in jobs_storage:
        del jobs_storage[job_id]
        return {"message": "Job deleted successfully", "job_id": job_id}
    
    return JSONResponse(
        status_code=404,
        content={"error": "Job not found"}
    )

# Point d'entrée
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

