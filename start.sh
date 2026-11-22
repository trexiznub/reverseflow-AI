#!/usr/bin/env bash
# Starts the REVERSEFLOW AI backend (port 8040) and frontend (port 3000).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -x "$ROOT/backend/.venv/bin/uvicorn" ]; then
  echo "Setting up backend virtualenv…"
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing frontend dependencies…"
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund)
fi

(cd "$ROOT/backend" && .venv/bin/uvicorn app.main:app --port 8040) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

echo "Backend starting on http://localhost:8040 (first run generates data and trains models, ~40s)"
cd "$ROOT/frontend" && npm run dev
