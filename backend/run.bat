@echo off
REM Backend launcher for Windows.
REM Usage: run.bat

cd /d "%~dp0"

REM Create venv on first run
if not exist ".venv" (
    echo Creating Python 3.11 virtual env...
    py -3.11 -m venv .venv
    if errorlevel 1 (
        echo ERROR: Python 3.11 not found. Install from python.org, tick "Add Python to PATH".
        exit /b 1
    )
)

REM Activate and install
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM Create .env from example if missing
if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo !!! Created backend\.env from template.
    echo !!! Edit backend\.env and paste your ANTHROPIC_API_KEY before running again.
    echo.
    exit /b 1
)

set PYTHONPATH=.
echo Starting backend on http://127.0.0.1:8000 ...
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
