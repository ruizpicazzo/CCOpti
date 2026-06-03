@echo off
echo Starting CardMax MX...

start "CardMax Backend" cmd /k "cd /d "%~dp0backend" && venv\Scripts\uvicorn app.main:app --reload --port 8000"

timeout /t 2 /nobreak >nul

start "CardMax Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.
timeout /t 3 /nobreak >nul
start http://localhost:5173
