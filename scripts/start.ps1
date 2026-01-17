$root = Split-Path -Parent $PSScriptRoot
$apiPort = 4321
$webPort = 1234

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
  Write-Host "Missing API venv. Run: cd api; python -m venv .venv; .venv\\Scripts\\Activate.ps1; pip install -r requirements.txt"
  exit 1
}

if (-not (Test-Path $webNodeModules)) {
  Write-Host "Missing web dependencies. Run: cd web; npm install"
  exit 1
}

Ensure-Started "API" $apiPort "cd `"$root\\api`"; `"$apiPython`" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 4321" "http://127.0.0.1:4321"

Ensure-Started "Web" $webPort "cd `"$root\\web`"; npm run dev" "http://localhost:1234"
