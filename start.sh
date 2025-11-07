#!/bin/bash

# Installer les dépendances système
apt-get update && apt-get install -y ffmpeg

# Démarrer l'application
exec uvicorn forapitest:app --host 0.0.0.0 --port ${PORT:-8000}