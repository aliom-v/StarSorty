$apiPort = 4321
$webPort = 1234

function Get-ListeningPids($port) {
  return (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
}

function Show-Status($name, $port) {
  $pids = Get-ListeningPids $port
  if (-not $pids) {
    Write-Host "${name}: stopped (port $port)"
    return
  }

  foreach ($procId in $pids) {
    try {
      $proc = Get-Process -Id $procId -ErrorAction Stop
      Write-Host "${name}: running (port $port, PID $procId, $($proc.ProcessName))"
    } catch {
      Write-Host "${name}: running (port $port, PID $procId)"
    }
  }
}

Show-Status "API" $apiPort
Show-Status "Web" $webPort
