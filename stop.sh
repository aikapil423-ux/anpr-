#!/bin/bash
# ==============================================================================
# Smart ANPR & FRS - Native Stop Script
# Stops any running ANPR/FRS uvicorn process on host
# ==============================================================================

PORT="${PORT:-8000}"
echo "Searching for process listening on port $PORT..."

PID=$(lsof -ti :$PORT 2>/dev/null || fuser $PORT/tcp 2>/dev/null || true)

if [ -n "$PID" ]; then
    echo "Stopping process $PID..."
    kill -15 $PID 2>/dev/null || true
    sleep 2
    kill -9 $PID 2>/dev/null || true
    echo "[SUCCESS] Process stopped on port $PORT."
else
    echo "No process was running on port $PORT."
fi

# Also ensure any lingering app.py processes are stopped cleanly
pkill -f "uvicorn app:app" 2>/dev/null || true
