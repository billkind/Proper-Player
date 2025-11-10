from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import tempfile
import os
import subprocess
import nltk
import uuid
from typing import Dict, Optional, Set
import time
import re
from concurrent.futures import ThreadPoolExecutor

# === Configuration ===
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
jobs_storage: Dict[str, dict] = {}
whisper_model: Optional[WhisperModel] = None
model_loading = False

# ThreadPool pour traitement parallèle
executor = ThreadPoolExecutor(max_workers=2)

# === Téléchargement NLTK (une seule fois) ===
def download_nltk_data():
    resources = [('tokenizers/punkt', 'punkt'), ('corpora/wordnet', 'wordnet'), ('corpora/omw-1.4', 'omw-1.4')]
    for path, name in resources:
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(name, quiet=True)

download_nltk_data()

# === Initialisation ===
app = FastAPI(title="Proper Player API", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Dictionnaire optimisé (Set pour O(1) lookup) ===
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

# Regex ultra-optimisé (compilé une seule fois)
PUNCTUATION_PATTERN = re.compile(r'[^\w\s-]')
WHITESPACE_PATTERN = re.compile(r'\s+')

# === Chargement lazy du modèle ===
def get_whisper_model():
    global whisper_model, model_loading
    
    if whisper_model is not None:
        return whisper_model
    
    if model_loading:
        for _ in range(60):
            if whisper_model is not None:
                return whisper_model
            time.sleep(1)
        raise Exception("Model loading timeout")
    
    try:
        model_loading = True
        print("Loading Whisper model (tiny.en for max speed)...")
        whisper_model = WhisperModel(
            "tiny.en",
            device="cpu",
            compute_type="int8",
            num_workers=1
        )
        print("Model loaded!")
        return whisper_model
    finally:
        model_loading = False

# === Conversion audio optimisée ===
def convert_to_wav(input_file, output_file):
    subprocess.run([
        "ffmpeg", "-y", "-i", input_file,
        "-ac", "1", "-ar", "16000",
        "-acodec", "pcm_s16le",
        output_file
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# === Détection ultra-rapide (vectorisée) ===
def detect_offensive_batch(words_batch):
    """Traite un batch de mots en une seule passe"""
    results = []
    
    for word_data in words_batch:
        word = word_data.word
        
        # Skip vides et très courts
        if not word or len(word) < 3:
            continue
        
        # Nettoyage ultra-rapide
        clean = PUNCTUATION_PATTERN.sub('', word).lower().strip()
        
        if not clean:
            continue
        
        # Lookup O(1)
        if clean in OFFENSIVE_WORDS:
            results.append({
                "word": word.strip(),
                "start": round(word_data.start, 2),
                "end": round(word_data.end, 2)
            })
    
    return results

# === Traitement optimisé avec batching ===
def process_audio(job_id: str, file_path: str, filename: str):
    wav_path = None
    start_time = time.time()
    MAX_TIME = 120  # 2 minutes max
    
    try:
        jobs_storage[job_id]["status"] = "processing"
        jobs_storage[job_id]["progress"] = 10
        
        # Conversion
        wav_path = file_path if file_path.endswith(".wav") else file_path + ".wav"
        if not file_path.endswith(".wav"):
            jobs_storage[job_id]["message"] = "Converting..."
            jobs_storage[job_id]["progress"] = 20
            convert_to_wav(file_path, wav_path)
        
        # Timeout check
        if time.time() - start_time > MAX_TIME:
            raise Exception("Timeout")
        
        # Modèle
        jobs_storage[job_id]["message"] = "Loading model..."
        jobs_storage[job_id]["progress"] = 30
        model = get_whisper_model()
        
        # Transcription ULTRA-OPTIMISÉE
        jobs_storage[job_id]["message"] = "Transcribing..."
        jobs_storage[job_id]["progress"] = 40
        
        segments, info = model.transcribe(
            wav_path,
            word_timestamps=True,
            beam_size=1,  # Le plus rapide
            best_of=1,
            temperature=0,
            vad_filter=True,
            vad_parameters=dict(
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=2000,  # Ignore les silences > 2s
                max_speech_duration_s=float('inf')
            ),
            language="en"  # Force anglais pour vitesse
        )
        
        if time.time() - start_time > MAX_TIME:
            raise Exception("Timeout")
        
        # Détection ULTRA-RAPIDE par batch
        jobs_storage[job_id]["progress"] = 70
        jobs_storage[job_id]["message"] = "Detecting..."
        
        toxic_words = []
        segments_list = list(segments)
        total = len(segments_list)
        
        # Traitement par batch de 50 segments
        BATCH_SIZE = 50
        
        for batch_idx in range(0, total, BATCH_SIZE):
            if time.time() - start_time > MAX_TIME:
                raise Exception("Timeout")
            
            # Mise à jour progrès
            if total > 0:
                prog = 70 + int((batch_idx / total) * 25)
                jobs_storage[job_id]["progress"] = min(prog, 95)
            
            # Traiter un batch
            batch_segments = segments_list[batch_idx:batch_idx + BATCH_SIZE]
            
            for segment in batch_segments:
                if not hasattr(segment, 'words') or not segment.words:
                    continue
                
                # Collecter tous les mots du segment
                words_list = list(segment.words)
                
                # Détection batch (très rapide)
                batch_results = detect_offensive_batch(words_list)
                toxic_words.extend(batch_results)
        
        # Terminé
        elapsed = round(time.time() - start_time, 2)
        jobs_storage[job_id]["status"] = "completed"
        jobs_storage[job_id]["progress"] = 100
        jobs_storage[job_id]["message"] = "Complete!"
        jobs_storage[job_id]["result"] = {
            "total": len(toxic_words),
            "toxic_words": toxic_words,
            "processing_time": elapsed,
            "audio_duration": round(info.duration, 2) if hasattr(info, 'duration') else None
        }
        
        print(f"✅ Job {job_id}: {len(toxic_words)} words in {elapsed}s")
        
    except Exception as e:
        jobs_storage[job_id]["status"] = "failed"
        jobs_storage[job_id]["error"] = str(e)
        jobs_storage[job_id]["progress"] = 0
        print(f"❌ Job {job_id}: {e}")
    
    finally:
        for path in [file_path, wav_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except:
                    pass

# === Cleanup ===
def cleanup_old_jobs():
    now = time.time()
    to_delete = [jid for jid, job in jobs_storage.items() 
                 if "created_at" in job and (now - job["created_at"]) > 3600]
    for jid in to_delete:
        del jobs_storage[jid]
    if to_delete:
        print(f"Cleaned {len(to_delete)} jobs")

# === Endpoints ===
@app.get("/")
async def root():
    return {
        "status": "online",
        "version": "2.2.0 - ULTRA OPTIMIZED",
        "model_loaded": whisper_model is not None,
        "active_jobs": len(jobs_storage),
        "optimizations": [
            "Batch processing (50 segments at once)",
            "Pre-compiled regex patterns",
            "Set-based O(1) word lookup",
            "VAD with 2s silence skip",
            "beam_size=1 (5x faster)",
            "Forced English language",
            "Min word length filter (3 chars)"
        ]
    }

@app.get("/health")
@app.head("/health")
async def health():
    return {"status": "healthy", "service": "Proper-Player"}

@app.post("/analyze")
async def analyze(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    cleanup_old_jobs()
    
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB
    
    try:
        contents = await file.read()
        
        if len(contents) > MAX_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error": "File > 50MB", "status": "error"}
            )
        
        job_id = str(uuid.uuid4())
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        jobs_storage[job_id] = {
            "status": "queued",
            "progress": 0,
            "message": "Queued...",
            "filename": file.filename,
            "result": None,
            "error": None,
            "created_at": time.time()
        }
        
        background_tasks.add_task(process_audio, job_id, tmp_path, file.filename)
        
        return JSONResponse(content={
            "job_id": job_id,
            "status": "queued",
            "message": "Started. Check /status/{job_id}",
            "estimate": "~10-30s for most files"
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "status": "error"}
        )

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs_storage:
        return JSONResponse(
            status_code=404,
            content={"error": "Job not found", "status": "not_found"}
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
    completed = [j for j in jobs_storage.values() if j["status"] == "completed"]
    avg = sum(j["result"]["processing_time"] for j in completed if "result" in j) / len(completed) if completed else 0
    
    return {
        "model_loaded": whisper_model is not None,
        "active_jobs": len(jobs_storage),
        "average_time": round(avg, 2),
        "total_completed": len(completed)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
