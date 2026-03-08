$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$apiPort = 4321
$webPort = 1234
$databaseDir = Join-Path $root "data"
$databasePath = ((Join-Path $databaseDir "app.db") -replace "\\", "/")
$databaseUrl = "sqlite:///$databasePath"

function Get-ListeningPids($port) {
  return (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
}

function Ensure-Started($name, $port, $cmd, $url) {
  $pids = Get-ListeningPids $port
  if ($pids) {
    Start-Sleep -Milliseconds 800
    $pids = Get-ListeningPids $port
  }

  if ($pids) {
    Write-Host "${name} already running on port $port"
    return
  }

  Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd | Out-Null
  Write-Host "${name} starting on $url"
  Start-Sleep -Seconds 1

  if (-not (Get-ListeningPids $port)) {
    Write-Host "${name} failed to bind port $port (check the new window for errors)"
  }
}

$apiPython = Join-Path $root "api\\.venv\\Scripts\\python.exe"
$webNodeModules = Join-Path $root "web\\node_modules"

if (-not (Test-Path $apiPython)) {
  Write-Host "Missing API venv. Run: cd api; python -m venv .venv; .venv\\Scripts\\Activate.ps1; pip install -r requirements-dev.txt"
  exit 1
}

if (-not (Test-Path $webNodeModules)) {
  Write-Host "Missing web dependencies. Run: cd web; npm install"
  exit 1
}

if (-not (Test-Path $databaseDir)) {
  New-Item -ItemType Directory -Path $databaseDir | Out-Null
}

Ensure-Started "API" $apiPort "`$env:DATABASE_URL = '$databaseUrl'; cd `"$root\\api`"; `"$apiPython`" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 4321" "http://127.0.0.1:4321"

Ensure-Started "Web" $webPort "cd `"$root\\web`"; npm run dev" "http://localhost:1234"
