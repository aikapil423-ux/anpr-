@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PY_BIN=.venv\Scripts\python.exe"
) else (
    set "PY_BIN=python"
)
echo Starting Smart ANPR & FRS Surveillance System on http://localhost:8000 ...
"%PY_BIN%" -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
