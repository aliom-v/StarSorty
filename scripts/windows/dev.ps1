$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$apiPython = Join-Path $root ".venv\\Scripts\\python.exe"
$webNextCmd = Join-Path $root "web\\node_modules\\.bin\\next.cmd"
$databaseDir = Join-Path $root "data"
$databasePath = ((Join-Path $databaseDir "app.db") -replace "\\", "/")
$databaseUrl = "sqlite:///$databasePath"

if (-not (Test-Path $apiPython)) {
  Write-Host "Missing root Python venv. Run: cd $root; python -m venv .venv; .\\.venv\\Scripts\\Activate.ps1; pip install -r api\\requirements-dev.txt"
  exit 1
}

if (-not (Test-Path $webNextCmd)) {
  Write-Host "Missing or incomplete web dependencies. Run: npm --prefix web install"
  exit 1
}

if (-not (Test-Path $databaseDir)) {
  New-Item -ItemType Directory -Path $databaseDir | Out-Null
}

$apiCmd = "`$env:DATABASE_URL = '$databaseUrl'; cd `"$root\\api`"; `"$apiPython`" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 4321"
$webCmd = "cd `"$root`"; npm run web:dev"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd | Out-Null
Start-Process powershell -ArgumentList "-NoExit", "-Command", $webCmd | Out-Null

Write-Host "Started API (http://localhost:4321) and Web (http://localhost:1234)."
