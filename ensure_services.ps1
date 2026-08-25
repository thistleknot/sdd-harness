<#
.SYNOPSIS
    Idempotent pre-setup: ensure all harness MCP services are running.
    Safe to call every session, every time. Skips anything already healthy.

.DESCRIPTION
    For each HTTP-transport MCP service, probes the /health endpoint.
    If healthy: SKIP. If not: attempts to start via Scheduled Task or
    direct launch, then re-probes. Reports per-service status.

    Stdio services (todo, data-science-skills) are started per-session
    by the harness client and are not managed here.

.USAGE
    powershell -NoProfile -ExecutionPolicy Bypass -File ensure_services.ps1
#>
param(
    [int]$TimeoutSec = 10,
    [switch]$Verbose
)

$ErrorActionPreference = "Continue"

# --- Service inventory (HTTP-transport only) --------------------------------

$services = @(
    @{
        Name     = "retrieve-skills"
        Port     = 8765
        Health   = "http://127.0.0.1:8765/health"
        Task     = "retrieve-skills"
        Launch   = "C:\Users\user\.skills\retrieve-skills\launch.ps1"
        WorkDir  = "C:\Users\user\.skills\retrieve-skills"
    },
    @{
        Name     = "memory-index"
        Port     = 8055
        Health   = "http://127.0.0.1:8055/health"
        Task     = $null  # NSSM service 'mem-server'
        Service  = "mem-server"
        Launch   = $null
        WorkDir  = "C:\Users\user\.skills\memory-index"
    },
    @{
        Name     = "todo"
        Port     = 8056
        Health   = "http://127.0.0.1:8056/health"
        Task     = "todo-mcp"
        Launch   = "C:\Users\user\.skills\todo\launch.ps1"
        WorkDir  = "C:\Users\user\.skills\todo"
    },
    @{
        Name     = "specs"
        Port     = 8057
        Health   = "http://127.0.0.1:8057/health"
        Task     = "specs-mcp"
        Launch   = $null
        WorkDir  = "C:\Users\user\.harness\specs"
    }
)

# --- Helpers ----------------------------------------------------------------

function Test-Health {
    param([string]$Url, [int]$Timeout = 5)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $Timeout -ErrorAction Stop
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-PortListening {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        return $conn.Count -gt 0
    } catch {
        return $false
    }
}

function Start-ViaScheduledTask {
    param([string]$TaskName)
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        if ($task.State -ne "Running") {
            Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
            Start-Sleep -Seconds 3
        }
        return $true
    } catch {
        return $false
    }
}

function Start-ViaLaunchScript {
    param([string]$Script, [string]$WorkDir)
    if (-not (Test-Path $Script)) { return $false }
    try {
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Script `
            -WorkingDirectory $WorkDir `
            -WindowStyle Hidden
        Start-Sleep -Seconds 5
        return $true
    } catch {
        return $false
    }
}

function Start-ViaNSSM {
    param([string]$ServiceName)
    try {
        $svc = Get-Service -Name $ServiceName -ErrorAction Stop
        if ($svc.Status -ne "Running") {
            Start-Service -Name $ServiceName -ErrorAction Stop
            Start-Sleep -Seconds 3
        }
        return $true
    } catch {
        return $false
    }
}

# --- Main loop --------------------------------------------------------------

Write-Host "=== SDD Harness: ensure_services ===" -ForegroundColor Cyan
Write-Host "  Checking $($services.Count) HTTP MCP services..."
Write-Host ""

$results = @()

foreach ($svc in $services) {
    $name = $svc.Name
    $healthy = Test-Health -Url $svc.Health -Timeout $TimeoutSec

    if ($healthy) {
        Write-Host "  [SKIP] $name - already healthy on :$($svc.Port)" -ForegroundColor Green
        $results += @{ Name = $name; Status = "SKIP" }
        continue
    }

    Write-Host "  [....] $name - not responding, attempting start..." -ForegroundColor Yellow

    $started = $false

    # Try NSSM service first (memory-index)
    if ($svc.Service) {
        $started = Start-ViaNSSM -ServiceName $svc.Service
        if ($Verbose -and $started) { Write-Host "         started via NSSM service '$($svc.Service)'" }
    }

    # Try Scheduled Task
    if (-not $started -and $svc.Task) {
        $started = Start-ViaScheduledTask -TaskName $svc.Task
        if ($Verbose -and $started) { Write-Host "         started via Scheduled Task '$($svc.Task)'" }
    }

    # Try launch script
    if (-not $started -and $svc.Launch) {
        $started = Start-ViaLaunchScript -Script $svc.Launch -WorkDir $svc.WorkDir
        if ($Verbose -and $started) { Write-Host "         started via launch script" }
    }

    # Re-probe health after start attempt
    if ($started) {
        Start-Sleep -Seconds 2
        $healthy = Test-Health -Url $svc.Health -Timeout $TimeoutSec
    }

    if ($healthy) {
        Write-Host "  [DONE] $name - now healthy on :$($svc.Port)" -ForegroundColor Green
        $results += @{ Name = $name; Status = "STARTED" }
    } else {
        Write-Host "  [FAIL] $name - could not start or health check failed" -ForegroundColor Red
        $results += @{ Name = $name; Status = "FAIL" }
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan

$skipped  = ($results | Where-Object { $_.Status -eq "SKIP" }).Count
$started  = ($results | Where-Object { $_.Status -eq "STARTED" }).Count
$failed   = ($results | Where-Object { $_.Status -eq "FAIL" }).Count

Write-Host "  SKIP: $skipped  |  STARTED: $started  |  FAIL: $failed"

if ($failed -gt 0) {
    Write-Host ""
    Write-Host "  Failed services need manual intervention:" -ForegroundColor Red
    $results | Where-Object { $_.Status -eq "FAIL" } | ForEach-Object {
        Write-Host "    - $($_.Name)" -ForegroundColor Red
    }
    exit 1
}

exit 0
