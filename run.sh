#!/usr/bin/env bash
# Start both backend and frontend.
# Usage: ./run.sh
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"

# Start backend in background
echo ">>> Starting backend (http://127.0.0.1:8000)..."
(cd "$HERE/backend" && ./run.sh) &
BACKEND_PID=$!

# Trap to kill backend on exit
trap "echo 'Stopping backend...'; kill $BACKEND_PID 2>/dev/null || true" EXIT

# Give backend a few seconds to boot
sleep 3

# Start frontend in foreground
echo ">>> Starting frontend (http://localhost:8080)..."
cd "$HERE/github_ni-ai-fx-otc-settlements"
npm run dev
