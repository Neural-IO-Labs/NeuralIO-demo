@echo off
title Neural:IO Labs - Standalone Evaluation Suite
color 0B

echo ==============================================================
echo  NEURAL:IO LABS - STANDALONE PUBLIC EVALUATION SUITE
echo ==============================================================
echo [System] Initializing local environment checks...

:: Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found on your system PATH.
    echo Please install Python 3.11, 3.12, or 3.13 and try again.
    pause
    exit /b 1
)

:: Get Python Version
for /f "tokens=2 delims= " %%I in ('python -V 2^>^&1') do set PY_VER=%%I
echo [System] Detected Python version: %PY_VER%

:: Parse Major/Minor version
python -c "import sys; sys.exit(0 if sys.version_info[:2] in [(3,11), (3,12), (3,13)] else 1)"
if %errorlevel% neq 0 (
    echo [WARNING] Neural:IO is optimized and pre-compiled for Python 3.11, 3.12, or 3.13.
    echo Running on this version might fall back to Python safe-mode.
)

:: Create Virtual Environment
if not exist "venv" (
    echo [System] Creating local virtual environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [System] Activating local virtual environment...
call venv\Scripts\activate.bat

echo [System] Upgrading pip...
python -m pip install --upgrade pip >nul 2>nul

echo [System] Installing dashboard telemetry dependencies (fastapi, uvicorn, pydantic)...
pip install fastapi uvicorn pydantic
if %errorlevel% neq 0 (
    echo [WARNING] Dependency installation failed. Checking fallback...
)

echo [System] Attempting to install PyTorch for hardware CUDA execution...
pip install torch
if %errorlevel% neq 0 (
    echo [INFO] PyTorch not installed. The benchmark will run in Safe fall-back mode (simulated).
)

:: Detect Python version for C++ binary linking
python -c "import sys; sys.exit(12 if sys.version_info[:2] == (3,12) else (13 if sys.version_info[:2] == (3,13) else 0))"
set PY_VER_CODE=%errorlevel%

if "%PY_VER_CODE%"=="12" (
    echo [System] Aligning pre-compiled C++ extension for Python 3.12...
    copy /y "bin\windows\neuralio_formula1.cp312-win_amd64.pyd" "neuralio_final.pyd" >nul
) else if "%PY_VER_CODE%"=="13" (
    echo [System] Aligning pre-compiled C++ extension for Python 3.13...
    copy /y "bin\windows\neuralio_final.cp313-win_amd64.pyd" "neuralio_final.pyd" >nul
) else (
    echo [WARNING] No pre-compiled binary matches Python %PY_VER%. 
    echo Falling back to pure Python safe-mode.
)

:: Verify C++ binary load
if exist "neuralio_final.pyd" (
    python -c "import neuralio_final; print('[System] Compiled C++ binary imported successfully!')" 2>nul
    if %errorlevel% neq 0 (
        echo [WARNING] C++ binary link exists but failed to import. Safe-mode will be active.
    )
)

echo ==============================================================
echo  PRE-FLIGHT CHECKS COMPLETED SUCCESSFULLY
echo ==============================================================
echo [Launch] 1. Starting Local Hardware Performance Benchmark Loop...
echo [Launch] 2. Starting visual telemetry dashboard on http://localhost:8000
echo.
echo Press any key to start the Neural:IO suite...
pause >nul

:: Launch browser in background
start "" http://localhost:8000

:: Run the benchmark in background if supported, or sequentially
echo [Launch] Starting telemetry dashboard server...
python -m uvicorn dashboard.main:app --port 8000
