$root = Split-Path -Parent $PSScriptRoot
$apiPort = 8000
$webPort = 3000

function Get-ListeningPids($port) {
  return (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
}

function Get-ProcessInfo($procId) {
  return Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
}

function Get-ChildPids($parentProcId) {
  return (Get-CimInstance Win32_Process -Filter "ParentProcessId=$parentProcId" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty ProcessId)
}

function Stop-ProcessTree($procId) {
  foreach ($childPid in (Get-ChildPids $procId)) {
    Stop-ProcessTree $childPid
  }

  try {
    Stop-Process -Id $procId -Force -ErrorAction Stop
    return $true
  } catch {
    return $false
  }
}

function Get-RepoRootPid($procId, $rootPath) {
  $current = Get-ProcessInfo $procId
  $candidatePid = $null

  while ($current) {
    if ($current.CommandLine -and $current.CommandLine -like "*$rootPath*") {
      $candidatePid = $current.ProcessId
    }

    if (-not $current.ParentProcessId -or $current.ParentProcessId -eq 0) {
      break
    }

    $current = Get-ProcessInfo $current.ParentProcessId
  }

  return $candidatePid
}

function Stop-ByPort($name, $port) {
  $pids = Get-ListeningPids $port
  if (-not $pids) {
    Write-Host "${name}: not running on port $port"
    return
  }

  foreach ($procId in $pids) {
    $targetPid = Get-RepoRootPid $procId $root
    if (-not $targetPid) {
      $targetPid = $procId
    }

    if (Stop-ProcessTree $targetPid) {
      Write-Host "${name}: stopped PID $targetPid (port $port)"
    } else {
      Write-Host "${name}: failed to stop PID $targetPid (port $port)"
    }
  }
}

Stop-ByPort "API" $apiPort
Stop-ByPort "Web" $webPort
