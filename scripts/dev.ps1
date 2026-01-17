$root = Split-Path -Parent $PSScriptRoot

$apiPython = Join-Path $root "api\\.venv\\Scripts\\python.exe"
$webNodeModules = Join-Path $root "web\\node_modules"

if (-not (Test-Path $apiPython)) {
  Write-Host "Missing API venv. Run: cd api; python -m venv .venv; .venv\\Scripts\\Activate.ps1; pip install -r requirements.txt"
  exit 1
}

if (-not (Test-Path $webNodeModules)) {
  Write-Host "Missing web dependencies. Run: cd web; npm install"
  exit 1
}

$apiCmd = "cd `"$root\\api`"; `"$apiPython`" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 4321"
$webCmd = "cd `"$root\\web`"; npm run dev"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd | Out-Null
Start-Process powershell -ArgumentList "-NoExit", "-Command", $webCmd | Out-Null

Write-Host "Started API (http://localhost:4321) and Web (http://localhost:1234)."
