#!/usr/bin/env bash
# Run the backend API server.
# Usage: ./run.sh
set -e

cd "$(dirname "$0")"

# Create venv on first run
if [ ! -d ".venv" ]; then
  echo "Creating Python 3.11 virtual env..."
  python3.11 -m venv .venv
fi

# Activate and install
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Create .env from example if missing
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "!!! Created backend/.env from template."
  echo "!!! Edit backend/.env and paste your ANTHROPIC_API_KEY before running again."
  echo ""
  exit 1
fi

# Start FastAPI
export PYTHONPATH=.
echo "Starting backend on http://127.0.0.1:8000 ..."
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
