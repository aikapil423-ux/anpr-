#!/bin/bash
# ==============================================================================
# Smart ANPR & FRS Surveillance Intelligence Hub - Native Python Startup Script
# Runs directly on host without Docker, preserving 100% of pipeline capabilities.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

echo "=========================================================="
echo " Starting Smart ANPR & FRS System (Native Python Mode)"
echo " Project Directory: $DIR"
echo " Listening on:      http://${HOST}:${PORT}"
echo "=========================================================="

# 1. Ensure required runtime storage directories exist
mkdir -p "$DIR/outputs" \
         "$DIR/data/vehicle_photos" \
         "$DIR/data/captured_crops" \
         "$DIR/data/trail_photos" \
         "$DIR/data/frs/enrolled" \
         "$DIR/data/frs/captured_face_crops" \
         "$DIR/data/frs/captured_face_scenes" \
         "$DIR/data/frs/detections/crops" \
         "$DIR/data/frs/detections/scenes" \
         "$DIR/models/yolo" \
         "$DIR/models/frs" \
         "$DIR/models/awiros_anpr"

# 2. Auto-activate virtual environment if one exists
if [ -f "$DIR/venv/bin/activate" ]; then
    echo "[Native] Activating virtual environment: $DIR/venv"
    source "$DIR/venv/bin/activate"
elif [ -f "$DIR/.venv/bin/activate" ]; then
    echo "[Native] Activating virtual environment: $DIR/.venv"
    source "$DIR/.venv/bin/activate"
fi

# 3. Detect Python binary
if command -v python3 &>/dev/null; then
    PY_BIN="python3"
elif command -v python &>/dev/null; then
    PY_BIN="python"
else
    echo "[ERROR] Python interpreter not found in PATH." >&2
    exit 1
fi

echo "[Native] Using Python: $($PY_BIN --version) at $(which $PY_BIN)"

# 3.5 Auto-heal: Ensure Awiros OCR dependencies and weights are present
if ! $PY_BIN -c "import paddle, safetensors" &>/dev/null; then
    echo "[Auto-Heal] Installing PaddlePaddle & Safetensors for Awiros OCR..."
    $PY_BIN -m pip install --no-cache-dir paddlepaddle>=2.6.0 safetensors>=0.4.0 || true
fi

if [ ! -f "$DIR/models/awiros_anpr/model.safetensors" ]; then
    echo "[Auto-Heal] Awiros model weights missing. Auto-downloading..."
    $PY_BIN scripts/download_models.py || true
fi

# 4. Launch Uvicorn FastAPI server directly
export PYTHONUNBUFFERED=1
exec $PY_BIN -m uvicorn app:app --host "$HOST" --port "$PORT"
