#!/bin/bash
# ==============================================================
#  NEURAL:IO LABS - STANDALONE PUBLIC EVALUATION SUITE (LINUX)
# ==============================================================

# Colors for terminal
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}==============================================================${NC}"
echo -e "${CYAN} NEURAL:IO LABS - STANDALONE PUBLIC EVALUATION SUITE (LINUX)${NC}"
echo -e "${CYAN}==============================================================${NC}"
echo -e "[System] Initializing local environment checks..."

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] python3 was not found on your system PATH.${NC}"
    echo -e "Please install Python 3.10 or 3.11 and try again."
    exit 1
fi

PY_VER=$(python3 -V 2>&1 | awk '{print $2}')
echo -e "[System] Detected Python version: ${GREEN}${PY_VER}${NC}"

# Setup local virtual environment
if [ ! -d "venv" ]; then
    echo -e "[System] Creating local virtual environment (venv)..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to create virtual environment.${NC}"
        exit 1
    fi
fi

echo -e "[System] Activating local virtual environment..."
source venv/bin/activate

echo -e "[System] Upgrading pip..."
python3 -m pip install --upgrade pip &> /dev/null

echo -e "[System] Installing dashboard telemetry dependencies (fastapi, uvicorn, pydantic)..."
pip install fastapi uvicorn pydantic
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}[WARNING] Dependency installation encountered issues. Checking fallback...${NC}"
fi

# Detect Python version and install correct wheel
PY_MAJOR_MINOR=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

if [ "$PY_MAJOR_MINOR" == "3.11" ]; then
    echo -e "${CYAN}[System] Installing pre-compiled C++ accelerated wheel for Python 3.11 (Linux x86_64)...${NC}"
    pip install bin/linux/neuralio-2.2.5-cp311-cp311-linux_x86_64.whl
elif [ "$PY_MAJOR_MINOR" == "3.10" ]; then
    echo -e "${CYAN}[System] Installing pre-compiled AMD ROCm wheel for Python 3.10 (Linux x86_64)...${NC}"
    pip install bin/linux/neuralio_amd-2.3.0+amd-cp310-cp310-linux_x86_64.whl
else
    echo -e "${YELLOW}[WARNING] No exact match wheel found for Python $PY_VER (requires 3.10 or 3.11 for C++ acceleration).${NC}"
    echo -e "Evaluating pure Python safe-mode fallback."
fi

# Attempt to install PyTorch for true GPU benchmarks
echo -e "[System] Attempting to install PyTorch for hardware collective benchmark..."
pip install torch
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}[INFO] PyTorch not installed. Running benchmark in safe-mode (simulated GPU training).${NC}"
fi

# Verify import
python3 -c "import neuralio; print('[System] Neural:IO import check: PASSED')" &> /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[System] Core library verified successfully!${NC}"
else
    echo -e "${YELLOW}[WARNING] Core acceleration was not loaded; safe-mode active.${NC}"
fi

echo -e "${CYAN}==============================================================${NC}"
echo -e "${GREEN} PRE-FLIGHT CHECKS COMPLETED SUCCESSFULLY${NC}"
echo -e "${CYAN}==============================================================${NC}"
echo -e "[Launch] 1. Starting Local Hardware Performance Benchmark Loop..."
echo -e "[Launch] 2. Starting visual telemetry dashboard on http://localhost:8000"
echo.
echo -e "Press [Enter] to start the Neural:IO suite..."
read

# Attempt to open browser (Linux-friendly open)
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:8000 &
elif command -v gnome-open &> /dev/null; then
    gnome-open http://localhost:8000 &
fi

# Run uvicorn server
python3 -m uvicorn dashboard.main:app --port 8000
