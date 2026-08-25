param(
    [switch]$Setup,
    [switch]$Verify,
    [string]$Harness,
    [int]$Step,
    [string]$Result,
    [string]$Dir
)

$ErrorActionPreference = "Stop"
$evalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$worktreeRoot = Join-Path $evalRoot "worktrees"
$resultsRoot = Join-Path $evalRoot "results\3d-td"
$promptFile = Join-Path $evalRoot "prompts\3d-td.md"

$sdl2Path = "H:\Games\civctp2\ctp2_code\libs\SDL2-2.30.12"

if ($Setup) {
    Write-Host "=== 3D TD Eval Setup ==="
    Write-Host ""
    Write-Host "SDL2 path: $sdl2Path"
    Write-Host "SDL2 exists: $(Test-Path $sdl2Path)"
    Write-Host ""
    Write-Host "Worktrees:"
    foreach ($h in @("pi", "opencode", "claude")) {
        $wt = Join-Path $worktreeRoot "3d-td-$h"
        Write-Host "  $h : $wt"
    }
    Write-Host ""
    Write-Host "--- Launch Protocol ---"
    Write-Host ""
    Write-Host "For pi:       cd $worktreeRoot\3d-td-pi && pi -p"
    Write-Host "For opencode: cd $worktreeRoot\3d-td-opencode && opencode"
    Write-Host "For claude:   cd $worktreeRoot\3d-td-claude && claude"
    Write-Host ""
    Write-Host "Prompt:"
    Write-Host "---"
    Get-Content $promptFile
    Write-Host "---"
    return
}

if ($Verify) {
    if (-not $Dir) { Write-Host "Usage: -Verify -Dir [path]"; return }
    Write-Host "=== Gate Verification: $Dir ==="
    $exe = Get-ChildItem $Dir -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $exe) { Write-Host "[FAIL] No exe found"; return }

    $proc = Start-Process -FilePath $exe.FullName -WorkingDirectory $Dir -PassThru
    Start-Sleep 5
    if ($proc.HasExited) {
        Write-Host "[FAIL] Gate 1: crashed (exit $($proc.ExitCode))"
    } else {
        Write-Host "[PASS] Gate 1: running after 5s (PID $($proc.Id))"
        Write-Host "[INFO] Check gates 2-6 visually. Kill: Stop-Process -Id $($proc.Id)"
    }
    return
}

if ($Harness -and $Step) {
    $logFile = Join-Path $resultsRoot "$Harness-log.jsonl"
    $entry = @{ step = $Step; timestamp = (Get-Date -Format "o"); result = $Result } | ConvertTo-Json -Compress
    Add-Content -Path $logFile -Value $entry
    Write-Host "Logged step $Step for $Harness"
    return
}

Write-Host "Usage: -Setup | -Verify -Dir [path] | -Harness [name] -Step [N] -Result [text]"
