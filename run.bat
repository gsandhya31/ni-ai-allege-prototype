@echo off
REM Starts backend and frontend in two separate windows.
REM Usage: run.bat

set "HERE=%~dp0"

echo Starting backend in a new window...
start "Allege Backend" cmd /k "cd /d %HERE%backend && run.bat"

timeout /t 3 /nobreak >nul

echo Starting frontend in a new window...
start "Allege Frontend" cmd /k "cd /d %HERE%github_ni-ai-fx-otc-settlements && npm run dev"

echo.
echo Both services launched.
echo   Backend:  http://127.0.0.1:8000/docs
echo   Frontend: http://localhost:8080
echo.
echo Close the two new windows to stop.
