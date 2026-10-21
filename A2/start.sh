#!/usr/bin/env bash
# One-command start (macOS/Linux/Git Bash): builds the frontend if needed and
# serves the whole app from FastAPI at http://localhost:8000
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
[ -f "$root/backend/.env" ] || { cp "$root/backend/.env.example" "$root/backend/.env"; echo "Created backend/.env - add your OPENROUTER_API_KEY."; }
if [ ! -f "$root/frontend/dist/index.html" ]; then (cd "$root/frontend" && npm install && npm run build); fi
cd "$root/backend"
echo "Open http://localhost:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
