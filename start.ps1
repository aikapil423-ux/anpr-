Set-Location -Path $PSScriptRoot
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
Write-Host "Starting Smart ANPR & FRS Surveillance System on http://localhost:8000 ..." -ForegroundColor Cyan
& $py -m uvicorn app:app --host 0.0.0.0 --port 8000
