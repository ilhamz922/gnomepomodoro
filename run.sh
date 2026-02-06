#!/usr/bin/env bash
set -e

APP_DIR="$HOME/Projects/pomodoro"
cd "$APP_DIR"

# kalau lo pakai venv:
if [ -f ".venv/bin/python" ]; then
  exec "$APP_DIR/.venv/bin/python" app.py
else
  exec python3 app.py
fi
