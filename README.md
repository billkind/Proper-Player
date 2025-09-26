![Logo](file:///C:/Users/DC/web-censor-app/public/Headphones.png)

## Badges

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)

[![GPLv3 License](https://img.shields.io/badge/License-GPL%20v3-yellow.svg)](https://opensource.org/licenses/)

[![AGPL License](https://img.shields.io/badge/license-AGPL-blue.svg)](http://www.gnu.org/licenses/agpl-3.0)

# Proper Player

This project aims to create a protected environment, where anyone can listen to any content from their browser without fear of what they might be listening to.

This web application uses a playback mode with file preprocessing. This means you must download the downloaded audio or video in your browser.

## Features

- Audio and video uploading
- Analysis and censorship with mute or beep options
- Preview playback
- Fullscreen mode

## How it works

    1. File format conversion to .WAV with FFmpeg
    2. Audio Transcription via Whisper
    3. Offensive Word Detection using self-made dictionary
    4. Censorship at each segment with swear words

## Main dependencies

pip install openai-whisper

pip install whisper torch ffmpeg-python pydub streamlit

pip install nltk fastapi

## Swear Words Overview

offensive_lexicon =

set([
"fuck", "fucking", "fucker","fucked","shit","shitty", "asshole","bitch",
"bastard","dick","dumb","dumb bitch","idiot", "retard", "slut","cunt","whore",
"motherfucker", "pussy", "crap", "bollocks", "damn", "cock", "nigger",
"nigga", "spic", "kike", "fag", "faggot", "twat", "wanker", "douche",
"prick", "arse", "arsehole", "bloody", "bugger", "bullshit", "jackass",
"moron", "nuts", "piss", "screw", "screwed","suck","sucks","sex","shitball",
"shitballs","ass","butthog","douchebag","titty","titties","ass-lick","ass-licker","puzzie","atto",
"ass lick","ass licker","retarded","shithead","penis","penises"
])
