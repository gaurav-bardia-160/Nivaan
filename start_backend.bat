@echo off
echo Starting GovBank Assistant Backend...
cd /d "%~dp0backend"
py -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
pause
