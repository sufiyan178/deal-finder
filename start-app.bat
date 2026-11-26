@echo off
title Deal Finder Launcher
echo Starting Deal Finder Backend and Frontend...

:: Start FastAPI Backend in a new Command Prompt window
start "Deal Finder Backend (FastAPI)" cmd /k "cd /d %~dp0 && (if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat) else if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat)) && uvicorn main:app --reload"

:: Wait 4 seconds for backend initialization
timeout /t 4 /nobreak > nul

:: Start Next.js Frontend in a new Command Prompt window
start "Deal Finder Frontend (Next.js)" cmd /k "cd /d %~dp0deal-finder-frontend && npm run dev"

:: Wait 6 seconds and open the web app in the default browser
timeout /t 6 /nobreak > nul
start http://localhost:3000

echo Both servers are launching in separate Command Prompt windows!