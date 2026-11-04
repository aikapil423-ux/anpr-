@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PY_BIN=.venv\Scripts\python.exe"
) else (
    set "PY_BIN=python"
)
echo ================================================================
echo  Haryana Police ANPR ^& FRS - AI Model Downloader / Verifier
echo ================================================================
"%PY_BIN%" scripts/download_models.py %*
echo.
pause
