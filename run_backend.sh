#!/usr/bin/env bash
# ==============================================================================
# GovBank Assistant - Backend Server Runner (macOS / Linux)
# ==============================================================================

# Ensure execution from the repository root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ANSI Color codes for clean terminal output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}==========================================================${NC}"
echo -e "${GREEN} GovBank Assistant - Starting Backend API Server (macOS)${NC}"
echo -e "${CYAN}==========================================================${NC}"
echo ""

# 1. Detect Python executable (python3 or python)
PY_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
else
    echo -e "${RED}[ERROR] Python 3 was not found in your system PATH.${NC}"
    echo "Please install Python 3.10+ using Homebrew: brew install python"
    echo "or download directly from https://www.python.org/"
    exit 1
fi

echo -e "${YELLOW}[INFO]${NC} Detected Python: $($PY_CMD --version 2>&1)"

# 2. Auto-activate virtual environment if present
if [ -f "venv/bin/activate" ]; then
    echo -e "${YELLOW}[INFO]${NC} Activating virtual environment (venv)..."
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    echo -e "${YELLOW}[INFO]${NC} Activating virtual environment (.venv)..."
    source .venv/bin/activate
fi

# 3. Export environment variables
export PYTHONIOENCODING="utf-8"
export RAG_ENABLED="${RAG_ENABLED:-true}"
export RAG_VECTOR_ENABLED="${RAG_VECTOR_ENABLED:-true}"
export TRANSLATION_ENABLED="${TRANSLATION_ENABLED:-true}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo -e "${YELLOW}[INFO]${NC} Configuration:"
echo "       - Host: $HOST"
echo "       - Port: $PORT"
echo "       - Hybrid RAG: $RAG_ENABLED"
echo "       - Qdrant Vector Store: $RAG_VECTOR_ENABLED"
echo "       - Indic Translation: $TRANSLATION_ENABLED"
echo ""

# 4. Verify backend module dependencies
if ! $PY_CMD -c "import backend.main" >/dev/null 2>&1; then
    echo -e "${YELLOW}[WARNING]${NC} Dependencies may be missing. Installing from requirements..."
    if [ -f "backend/requirements.txt" ]; then
        $PY_CMD -m pip install -r backend/requirements.txt
    elif [ -f "requirements.txt" ]; then
        $PY_CMD -m pip install -r requirements.txt
    fi
fi

echo -e "${CYAN}==========================================================${NC}"
echo -e "${GREEN} Backend Server Running!${NC}"
echo -e " - API Root:      ${CYAN}http://$HOST:$PORT/${NC}"
echo -e " - Swagger Docs:  ${CYAN}http://$HOST:$PORT/docs${NC}"
echo -e " - ReDoc:         ${CYAN}http://$HOST:$PORT/redoc${NC}"
echo -e " - Health Check:  ${CYAN}http://$HOST:$PORT/api/health${NC}"
echo -e " - Metrics:       ${CYAN}http://$HOST:$PORT/api/metrics${NC}"
echo -e "${CYAN}==========================================================${NC}"
echo "Press Ctrl+C to stop the server."
echo ""

# 5. Launch uvicorn
exec $PY_CMD -m uvicorn backend.main:app --host "$HOST" --port "$PORT" --reload
