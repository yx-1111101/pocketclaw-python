#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

cleanup() {
    echo "Stopping services..."
    kill "$APP_PID" "$LLM_PID" 2>/dev/null
    wait "$APP_PID" "$LLM_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "Starting app/main.py (port ${PORT:-8764})..."
python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8764}" &
APP_PID=$!

echo "Starting llm_proxy/main.py (port ${LLM_PROXY_PORT:-8765})..."
python -m uvicorn llm_proxy.main:app --host 0.0.0.0 --port "${LLM_PROXY_PORT:-8765}" &
LLM_PID=$!

echo "Both services started. app PID=$APP_PID, llm_proxy PID=$LLM_PID"
wait "$APP_PID" "$LLM_PID"
