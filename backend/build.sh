#!/usr/bin/env bash
# exit on error
set -o errexit

# Installer FFmpeg
apt-get update && apt-get install -y ffmpeg

# Installer les dépendances Python
pip install --upgrade pip
pip install -r requirements.txt