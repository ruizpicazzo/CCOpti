@echo off
REM CardMax MX — daily scraper. Runs the token-optimized scraper.
cd /d "%~dp0backend"
set PYTHONIOENCODING=utf-8
venv\Scripts\python.exe -m app.scraper >> "%~dp0scraper_log.txt" 2>&1
