#!/usr/bin/env bash
# ==============================================================================
# GovBank Assistant - Full-Stack Launcher (macOS / Linux)
# Starts Frontend (port 5500), Backend (port 8000), and opens the web app
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}==========================================================${NC}"
echo -e "${GREEN} Starting GovBank Assistant Full-Stack System (macOS)...${NC}"
echo -e "${CYAN}==========================================================${NC}"

# Detect Python
PY_CMD=""
if [ -n "$PYTHON" ]; then
    PY_CMD="$PYTHON"
elif command -v python3.11 >/dev/null 2>&1; then
    PY_CMD="python3.11"
elif command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
else
    echo -e "${RED}[ERROR] Python was not found in system PATH.${NC}"
    echo "Please install Python 3.11+ using Homebrew: brew install python@3.11"
    exit 1
fi

# Activate venv if present
if [ -f "venv/bin/activate" ]; then
    echo -e "${YELLOW}[INFO]${NC} Activating virtual environment (venv)..."
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    echo -e "${YELLOW}[INFO]${NC} Activating virtual environment (.venv)..."
    source .venv/bin/activate
fi

export PYTHONIOENCODING="utf-8"
export RAG_ENABLED="true"
export RAG_VECTOR_ENABLED="true"
export TRANSLATION_ENABLED="true"

echo -e "${YELLOW}[0/3] Checking local vector index readiness...${NC}"
if ! $PY_CMD -m backend.offline.ensure_vector_db; then
    echo -e "${YELLOW}[WARNING]${NC} Vector index is unavailable. Continuing with lexical RAG fallback."
fi

# 1. Start Frontend static server on port 5500 in the background
echo -e "${YELLOW}[1/3] Starting Frontend static server on port 5500...${NC}"
$PY_CMD -m http.server 5500 --directory frontend >/dev/null 2>&1 &
FRONTEND_PID=$!

# Ensure background frontend is cleaned up on script exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping all services...${NC}"
    kill "$FRONTEND_PID" 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 2. Open Web Browser
echo -e "${YELLOW}[2/3] Opening Web App in default browser...${NC}"
sleep 1
if command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:5500"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://127.0.0.1:5500"
fi

# 3. Start Backend server
echo -e "${GREEN}[3/3] Starting Backend API on http://127.0.0.1:8000 (Ctrl+C to stop)...${NC}"
echo -e " - Swagger Docs: ${CYAN}http://127.0.0.1:8000/docs${NC}"
echo -e " - Health Check: ${CYAN}http://127.0.0.1:8000/api/health${NC}"
echo -e " - Metrics API:  ${CYAN}http://127.0.0.1:8000/api/metrics${NC}"
echo "----------------------------------------------------------"

$PY_CMD -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
