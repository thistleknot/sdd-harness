<#
.SYNOPSIS
    Dispatch a task to Claude Code as a fresh-context executor.

.DESCRIPTION
    Sends a one-shot task to Claude Code CLI, captures output,
    and returns the result for audit. Part of the MEA loop:
    Kiro (Manager) → Claude Code (Executor) → Kiro (Auditor).

.PARAMETER Task
    The task description to send to Claude Code.

.PARAMETER Cwd
    Working directory for the task. Defaults to .harness root.

.PARAMETER MaxTurns
    Maximum agent turns before stopping. Default: 10.

.PARAMETER Label
    Short label for the output file (for tracking). Default: "task".

.PARAMETER AllowEdit
    If set, allows Claude to edit files without permission prompts.

.EXAMPLE
    .\dispatch_claude.ps1 -Task "Add tests for specs_db.py failures table" -Label "test-failures"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$Task,

    [string]$Cwd = (Split-Path -Parent $PSScriptRoot),

    [int]$MaxTurns = 10,

    [string]$Label = "task",

    [switch]$AllowEdit
)

$ErrorActionPreference = "Stop"
$HarnessRoot = Split-Path -Parent $PSScriptRoot
$eventsDir = if ($env:HARNESS_EVENTS_DIR) {
    Join-Path $env:HARNESS_EVENTS_DIR "claude-dispatch"
} else {
    Join-Path $HarnessRoot "events\claude-dispatch"
}
if (-not (Test-Path $eventsDir)) { New-Item -ItemType Directory -Path $eventsDir -Force | Out-Null }

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$outFile = Join-Path $eventsDir "${timestamp}_${Label}_out.txt"
$errFile = Join-Path $eventsDir "${timestamp}_${Label}_err.txt"
$metaFile = Join-Path $eventsDir "${timestamp}_${Label}_meta.json"
$promptFile = Join-Path $eventsDir "${timestamp}_${Label}_prompt.txt"

# Frame the task for fresh execution — written to a temp file to avoid quoting issues
$framedTask = @"
FRESH TASK — execute only what follows, do not resume prior session context.
Do not summarize repo state. Do not propose candidates. Execute THIS task:

$Task

Report what you did and what verification you performed.
"@

Set-Content -Path $promptFile -Value $framedTask -Encoding UTF8

# Build arguments — use stdin for the prompt to avoid PowerShell quoting hell
$argList = @("--print", "--max-turns", $MaxTurns.ToString(), "--output-format", "text", "--no-session-persistence")
if ($AllowEdit) { $argList += "--dangerously-skip-permissions" }

# Log dispatch metadata
$meta = @{
    timestamp = $timestamp
    label = $Label
    task = $Task
    cwd = $Cwd
    max_turns = $MaxTurns
    allow_edit = $AllowEdit.IsPresent
    out_file = $outFile
    err_file = $errFile
    prompt_file = $promptFile
} | ConvertTo-Json
Set-Content -Path $metaFile -Value $meta -Encoding UTF8

Write-Host "Dispatching to Claude Code..." -ForegroundColor Cyan
Write-Host "  Label: $Label" -ForegroundColor Gray
Write-Host "  CWD: $Cwd" -ForegroundColor Gray
Write-Host "  Max turns: $MaxTurns" -ForegroundColor Gray
Write-Host "  Output: $outFile" -ForegroundColor Gray
Write-Host ""

# Execute using piped input from prompt file
$startTime = Get-Date
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "claude"
$psi.Arguments = $argList -join " "
$psi.WorkingDirectory = $Cwd
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true

$process = [System.Diagnostics.Process]::Start($psi)
$process.StandardInput.Write($framedTask)
$process.StandardInput.Close()

$stdout = $process.StandardOutput.ReadToEnd()
$stderr = $process.StandardError.ReadToEnd()
$process.WaitForExit()

$elapsed = (Get-Date) - $startTime

# Write outputs
Set-Content -Path $outFile -Value $stdout -Encoding UTF8
Set-Content -Path $errFile -Value $stderr -Encoding UTF8

# Report
Write-Host ""
Write-Host "Claude Code returned (exit: $($process.ExitCode), elapsed: $($elapsed.ToString('mm\:ss')))" -ForegroundColor $(if ($process.ExitCode -eq 0) { "Green" } else { "Red" })
Write-Host ""

if ($stdout) {
    Write-Host "--- OUTPUT ---" -ForegroundColor Yellow
    # Show first 50 lines to avoid flooding
    $lines = $stdout -split "`n"
    if ($lines.Count -le 50) {
        Write-Host $stdout
    } else {
        Write-Host ($lines[0..49] -join "`n")
        Write-Host "`n... ($($lines.Count - 50) more lines, see $outFile)" -ForegroundColor Gray
    }
    Write-Host "--- END ---" -ForegroundColor Yellow
}

if ($stderr) {
    Write-Host "--- ERRORS ---" -ForegroundColor Red
    Write-Host $stderr
    Write-Host "--- END ERRORS ---" -ForegroundColor Red
}

# Update meta with result
$metaObj = Get-Content $metaFile | ConvertFrom-Json
$metaObj | Add-Member -NotePropertyName "exit_code" -NotePropertyValue $process.ExitCode -Force
$metaObj | Add-Member -NotePropertyName "elapsed_seconds" -NotePropertyValue $elapsed.TotalSeconds -Force
$metaObj | Add-Member -NotePropertyName "output_bytes" -NotePropertyValue ([System.Text.Encoding]::UTF8.GetByteCount($stdout)) -Force
$metaObj | ConvertTo-Json | Set-Content -Path $metaFile -Encoding UTF8

return @{
    ExitCode = $process.ExitCode
    Output = $stdout
    Errors = $stderr
    Elapsed = $elapsed
    MetaFile = $metaFile
}
