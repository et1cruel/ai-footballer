@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
)
.venv\Scripts\python.exe -m pip install -r api\requirements.txt
set PYTHONPATH=api
start "" "http://127.0.0.1:8000"
.venv\Scripts\python.exe -m uvicorn football_ai.api:app --host 127.0.0.1 --port 8000
pause
