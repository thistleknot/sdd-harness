<#
Pipeline:
| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| PREFLIGHT | Verify administrator token, F: interpreters, NSSM settings, and task action | [mandatory] | R1 |
| BACKUP | Save current service Application values and probe action beside this script | [mandatory] | R2 |
| CONFIGURE | Change only NSSM Application values and the probe task executable | [mandatory] | R3 |
| RESTART | Restart existing services one at a time and wait for health endpoints | [mandatory] | R4 |

R1: WHEN the script runs, the caller MUST use an elevated Windows PowerShell session.
R2: BEFORE any changes, the script MUST persist a rollback record and preserve all other service/task settings.
R3: WHEN configuring a service, only its NSSM Application value may change; task arguments and working directory MUST be preserved.
R4: WHEN a service restarts, the script MUST wait for its existing health endpoint before proceeding.

CLOSED: Creating new supervisors is rejected because existing NSSM services and the scheduled task already own these processes.

Preconditions: All listed F: interpreters exist and the four existing Windows services plus probe task are registered.
Failure modes: Preflight or backup failures stop before mutation; service failures report the affected service and rollback file.
#>
[CmdletBinding()]
param(
    [ValidateRange(30, 300)]
    [int]$HealthTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell window (Run as administrator). No changes were made.'
}

$nssm = 'C:\Users\user\.pi\bin\nssm.exe'
$serviceTargets = [ordered]@{
    'skill-router' = [pscustomobject]@{ Python = 'F:\Python\mcp\retrieve-skills\Scripts\python.exe'; Health = 'http://127.0.0.1:8765/health' }
    'mem-server'   = [pscustomobject]@{ Python = 'F:\Python\mcp\memory-index\Scripts\python.exe'; Health = 'http://127.0.0.1:8055/health' }
    'todo-mcp'     = [pscustomobject]@{ Python = 'F:\Python\mcp\todo\Scripts\python.exe'; Health = 'http://127.0.0.1:8056/health' }
    'specs-mcp'    = [pscustomobject]@{ Python = 'F:\Python\mcp\specs\Scripts\python.exe'; Health = 'http://127.0.0.1:8057/health' }
}
$taskName = 'skill-router-probe'
$taskPython = 'F:\Python\mcp\retrieve-skills\Scripts\pythonw.exe'

if (-not (Test-Path -LiteralPath $nssm -PathType Leaf)) { throw "NSSM executable is missing: $nssm" }
foreach ($name in $serviceTargets.Keys) {
    if (-not (Test-Path -LiteralPath $serviceTargets[$name].Python -PathType Leaf)) {
        throw "F: interpreter is missing for ${name}: $($serviceTargets[$name].Python)"
    }
    if (-not (Get-Service -Name $name -ErrorAction SilentlyContinue)) { throw "Service is missing: $name" }
}
if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) { throw "Probe interpreter is missing: $taskPython" }
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if ($task.Actions.Count -ne 1) { throw "Expected one action on $taskName; found $($task.Actions.Count). No changes were made." }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupPath = Join-Path $PSScriptRoot "mcp-cutover-rollback-$stamp.json"
$oldApplications = [ordered]@{}
foreach ($name in $serviceTargets.Keys) {
    $key = "HKLM:\SYSTEM\CurrentControlSet\Services\$name\Parameters"
    $oldApplications[$name] = (Get-ItemProperty -LiteralPath $key -Name Application -ErrorAction Stop).Application
}
$oldAction = $task.Actions[0]
$backup = [ordered]@{
    CreatedAt = (Get-Date).ToString('o')
    Services = $oldApplications
    Task = [ordered]@{
        Name = $taskName
        Execute = $oldAction.Execute
        Arguments = $oldAction.Arguments
        WorkingDirectory = $oldAction.WorkingDirectory
    }
}
$backup | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $backupPath -Encoding UTF8
Write-Host "Rollback record: $backupPath" -ForegroundColor Cyan

foreach ($name in $serviceTargets.Keys) {
    & $nssm set $name Application $serviceTargets[$name].Python
    if ($LASTEXITCODE -ne 0) { throw "NSSM failed to update Application for $name (exit $LASTEXITCODE). Rollback record: $backupPath" }
    $key = "HKLM:\SYSTEM\CurrentControlSet\Services\$name\Parameters"
    $actual = (Get-ItemProperty -LiteralPath $key -Name Application -ErrorAction Stop).Application
    if ($actual -ne $serviceTargets[$name].Python) { throw "Application verification failed for ${name}: $actual. Rollback record: $backupPath" }
    Write-Host "Configured $name -> $actual" -ForegroundColor Green
}

$actionParameters = @{ Execute = $taskPython; Argument = $oldAction.Arguments }
if (-not [string]::IsNullOrWhiteSpace($oldAction.WorkingDirectory)) {
    $actionParameters.WorkingDirectory = $oldAction.WorkingDirectory
}
$newAction = New-ScheduledTaskAction @actionParameters
Set-ScheduledTask -TaskName $taskName -Action $newAction | Out-Null
$actualTask = (Get-ScheduledTask -TaskName $taskName).Actions[0]
if ($actualTask.Execute -ne $taskPython -or $actualTask.Arguments -ne $oldAction.Arguments -or $actualTask.WorkingDirectory -ne $oldAction.WorkingDirectory) {
    throw "Probe task verification failed. Rollback record: $backupPath"
}
Write-Host "Configured $taskName -> $($actualTask.Execute); arguments and working directory preserved" -ForegroundColor Green

foreach ($name in $serviceTargets.Keys) {
    Write-Host "Restarting $name..." -ForegroundColor Cyan
    $service = Get-Service -Name $name
    if ($service.Status -ne 'Stopped') {
        Stop-Service -Name $name -Force -ErrorAction Stop
        (Get-Service -Name $name).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
    }
    Start-Service -Name $name -ErrorAction Stop
    (Get-Service -Name $name).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))

    $deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $serviceTargets[$name].Health -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $healthy) { throw "$name did not become healthy at $($serviceTargets[$name].Health). Rollback record: $backupPath" }
    Write-Host "$name healthy at $($serviceTargets[$name].Health)" -ForegroundColor Green
}

Write-Host 'Cutover complete. MCP initialize/tool-list checks should now be run from the harness clients.' -ForegroundColor Green
