@echo off
echo === Starting Xeokit Demo Setup ===

:: Step 1 - Check Docker
docker --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker is not installed or not in PATH.
    pause
    exit /b
)

:: Step 2 - Create virtual environment if it doesn't exist
IF NOT EXIST .venv (
    echo [INFO] Creating Python virtual environment...
    python -m venv .venv
)

:: Step 3 - Activate virtual environment and install dependencies
echo [INFO] Installing Python dependencies...
call .venv\Scripts\activate
pip install -r requirements.txt

:: Step 4 - Start MongoDB, Mongo Express and Xeokit via Docker Compose
echo [INFO] Starting Docker containers...
docker compose up -d

:: Step 5 - Launch FastAPI app using uvicorn
echo [INFO] Starting FastAPI with Uvicorn...
start cmd /k ".venv\Scripts\activate && uvicorn app.main:app --reload"

echo [INFO] Setup complete.
echo Visit http://127.0.0.1:8000 and http://127.0.0.1:8000/docs
pause
