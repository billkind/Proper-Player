import whisper
import os
import tempfile
import subprocess
from nltk.stem import WordNetLemmatizer
import json

lemmatizer = WordNetLemmatizer()

offensive_lexicon = set([
    "fuck", "fucking", "fucker", "fucked", "shit", "shitty", "asshole", "bitch",
    "bastard", "dick", "dumb", "dumb bitch", "idiot", "retard", "slut", "cunt",
    "whore", "motherfucker", "pussy", "crap", "bollocks", "damn", "cock", "nigger",
    "nigga", "spic", "kike", "fag", "faggot", "twat", "wanker", "douche", "prick",
    "arse", "arsehole", "bloody", "bugger", "bullshit", "jackass", "moron", "nuts",
    "piss", "screw", "screwed", "suck", "sucks", "sex", "shitball", "shitballs",
    "ass", "butthog", "douchebag", "titty", "titties", "ass-lick", "ass-licker",
    "puzzie", "atto", "ass lick", "ass licker", "retarded", "shithead"
])

model = whisper.load_model("base")

def normalize(word):
    word = word.lower().strip(".,!?()[]{};:\"'")
    return lemmatizer.lemmatize(word)

def convert_to_wav(input_file, output_file="audio.wav"):
    command = [
        "ffmpeg", "-y", "-i", input_file,
        "-ac", "1", "-ar", "16000", output_file
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def split_audio(wav_path, segment_duration=60):
    output_paths = []
    command = [
        "ffmpeg", "-i", wav_path,
        "-f", "segment", "-segment_time", str(segment_duration),
        "-c", "copy", f"{wav_path}_segment_%03d.wav"
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    folder = os.path.dirname(wav_path)
    base = os.path.basename(wav_path)
    base_prefix = os.path.splitext(base)[0]
    for file in os.listdir(folder):
        if file.startswith(f"{base_prefix}_segment_") and file.endswith(".wav"):
            output_paths.append(os.path.join(folder, file))
    return sorted(output_paths)

def analyze_segments(wav_path):
    toxic_words = []
    segments = split_audio(wav_path)
    offset = 0.0  # to track global timing

    for segment_path in segments:
        result = model.transcribe(segment_path, word_timestamps=True)
        for segment in result.get("segments", []):
            for word_data in segment.get("words", []):
                word = word_data["word"].strip()
                norm_word = normalize(word)
                if norm_word in offensive_lexicon:
                    toxic_words.append({
                        "word": word,
                        "start": round(word_data["start"] + offset, 2),
                        "end": round(word_data["end"] + offset, 2)
                    })
        duration = result["segments"][-1]["end"] if result["segments"] else 0
        offset += duration
        os.remove(segment_path)

    return toxic_words
