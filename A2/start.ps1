# One-command start (Windows PowerShell): builds the frontend if needed and
# serves the whole app from FastAPI at http://localhost:8000
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path "$root\backend\.env")) {
    Copy-Item "$root\backend\.env.example" "$root\backend\.env"
    Write-Host "Created backend\.env from the template - add your OPENROUTER_API_KEY to it." -ForegroundColor Yellow
}
if (-not (Test-Path "$root\frontend\dist\index.html")) {
    Push-Location "$root\frontend"
    npm install
    npm run build
    Pop-Location
}
Push-Location "$root\backend"
Write-Host "Open http://localhost:8000" -ForegroundColor Green
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
