#!/usr/bin/env pwsh
# RUN-ALL.ps1 — Fire all 6 eval runs for prompt 1, collect results.
# Run this in a REAL terminal (not inside Kiro). Takes ~10 min.

$ErrorActionPreference = "Continue"
$evalRoot = $PSScriptRoot
$worktrees = Join-Path $evalRoot "worktrees"
$results = Join-Path $evalRoot "results\3d-td"
$promptFile = Join-Path $evalRoot "prompts\td-p1.md"

New-Item -ItemType Directory -Path $results -Force | Out-Null

Write-Host "=== 3D TD Eval: Prompt 1 ===" -ForegroundColor Cyan
Write-Host "Prompt: $promptFile"
Write-Host ""

# --- Run 1: Claude gates-on ---
Write-Host "[1/6] Claude gates-on..." -ForegroundColor Yellow
$dir = "$worktrees\td-claude-gates-on-p1"
$log = "$results\claude-gates-on-p1.log"
Push-Location $dir
Get-Content $promptFile | claude -p --dangerously-skip-permissions --add-dir . > $log 2>&1
Pop-Location
Write-Host "  Done. Log: $log ($('{0:N0}' -f (Get-Item $log).Length) bytes)"

# --- Run 2: Claude gates-off ---
Write-Host "[2/6] Claude gates-off..." -ForegroundColor Yellow
$dir = "$worktrees\td-claude-gates-off-p1"
$log = "$results\claude-gates-off-p1.log"
Push-Location $dir
Get-Content $promptFile | claude -p --dangerously-skip-permissions --add-dir . > $log 2>&1
Pop-Location
Write-Host "  Done. Log: $log ($('{0:N0}' -f (Get-Item $log).Length) bytes)"

# --- Run 3: OpenCode gates-on ---
Write-Host "[3/6] OpenCode gates-on..." -ForegroundColor Yellow
$dir = "$worktrees\td-opencode-gates-on-p1"
$log = "$results\opencode-gates-on-p1.log"
Push-Location $dir
$p = Get-Content $promptFile -Raw
opencode run -m "openrouter/anthropic/claude-sonnet-4" $p > $log 2>&1
Pop-Location
Write-Host "  Done. Log: $log ($('{0:N0}' -f (Get-Item $log).Length) bytes)"

# --- Run 4: OpenCode gates-off ---
Write-Host "[4/6] OpenCode gates-off..." -ForegroundColor Yellow
$dir = "$worktrees\td-opencode-gates-off-p1"
$log = "$results\opencode-gates-off-p1.log"
Push-Location $dir
opencode run -m "openrouter/anthropic/claude-sonnet-4" $p > $log 2>&1
Pop-Location
Write-Host "  Done. Log: $log ($('{0:N0}' -f (Get-Item $log).Length) bytes)"

# --- Run 5: Pi gates-on ---
Write-Host "[5/6] Pi gates-on..." -ForegroundColor Yellow
$dir = "$worktrees\td-pi-gates-on-p1"
$log = "$results\pi-gates-on-p1.log"
Push-Location $dir
pi -p $p --provider openrouter --model "anthropic/claude-sonnet-4" > $log 2>&1
Pop-Location
Write-Host "  Done. Log: $log ($('{0:N0}' -f (Get-Item $log).Length) bytes)"

# --- Run 6: Pi gates-off ---
Write-Host "[6/6] Pi gates-off..." -ForegroundColor Yellow
$dir = "$worktrees\td-pi-gates-off-p1"
$log = "$results\pi-gates-off-p1.log"
Push-Location $dir
pi -p $p --provider openrouter --model "anthropic/claude-sonnet-4" > $log 2>&1
Pop-Location
Write-Host "  Done. Log: $log ($('{0:N0}' -f (Get-Item $log).Length) bytes)"

# --- Summary ---
Write-Host ""
Write-Host "=== RESULTS ===" -ForegroundColor Cyan
Get-ChildItem "$worktrees\td-*-p1" -Directory | ForEach-Object {
    $src = Get-ChildItem $_.FullName -Recurse -File -EA SilentlyContinue | Where-Object { $_.Extension -in ".cpp",".h",".c" -and $_.FullName -notmatch "\\SDL2\\|\\build\\" }
    $loc = 0; $src | ForEach-Object { $loc += (Get-Content $_.FullName -EA SilentlyContinue | Measure-Object -Line).Lines }
    Write-Host "$($_.Name): $($src.Count) files, $loc LOC"
}
Write-Host ""
Write-Host "Logs in: $results"
Write-Host "Show me these results and I will analyze them."
