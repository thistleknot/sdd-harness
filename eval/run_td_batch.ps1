param(
    [Parameter(Mandatory)][int]$PromptNum
)

$evalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$worktreeRoot = Join-Path $evalRoot "worktrees"
$resultsRoot = Join-Path $evalRoot "results\3d-td"
$promptFile = Join-Path $evalRoot "prompts\td-p$PromptNum.md"
$prompt = Get-Content $promptFile -Raw

New-Item -ItemType Directory -Path $resultsRoot -Force | Out-Null

$runs = @(
    @{ Harness = "claude"; Arm = "gates-on"; Cmd = "cmd"; Args = @("/c", "claude -p `"$prompt`" --dangerously-skip-permissions --add-dir .") },
    @{ Harness = "claude"; Arm = "gates-off"; Cmd = "cmd"; Args = @("/c", "claude -p `"$prompt`" --dangerously-skip-permissions --add-dir .") },
    @{ Harness = "pi"; Arm = "gates-on"; Cmd = "cmd"; Args = @("/c", "pi -p `"$prompt`"") },
    @{ Harness = "pi"; Arm = "gates-off"; Cmd = "cmd"; Args = @("/c", "pi -p `"$prompt`"") },
    @{ Harness = "opencode"; Arm = "gates-on"; Cmd = "cmd"; Args = @("/c", "opencode run -m nvidia/nemotron-3.5-lightning-30b-a3b `"$prompt`"") },
    @{ Harness = "opencode"; Arm = "gates-off"; Cmd = "cmd"; Args = @("/c", "opencode run -m nvidia/nemotron-3.5-lightning-30b-a3b `"$prompt`"") }
)

$jobs = @()
foreach ($run in $runs) {
    $dir = Join-Path $worktreeRoot "td-$($run.Harness)-$($run.Arm)-p$PromptNum"
    $log = Join-Path $resultsRoot "$($run.Harness)-$($run.Arm)-p$PromptNum.log"
    
    Write-Host "Starting: $($run.Harness) [$($run.Arm)] prompt $PromptNum in $dir"
    
    # Write prompt to a temp file in the worktree to avoid quoting issues
    $promptTmp = Join-Path $dir "_prompt_input.txt"
    Set-Content -Path $promptTmp -Value $prompt -Encoding UTF8
    
    switch ($run.Harness) {
        "claude" {
            $job = Start-Process -FilePath "cmd" -ArgumentList "/c", "type _prompt_input.txt | claude -p --dangerously-skip-permissions --add-dir ." -WorkingDirectory $dir -NoNewWindow -PassThru -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
        }
        "pi" {
            $job = Start-Process -FilePath "cmd" -ArgumentList "/c", "type _prompt_input.txt | pi -p" -WorkingDirectory $dir -NoNewWindow -PassThru -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
        }
        "opencode" {
            $job = Start-Process -FilePath "cmd" -ArgumentList "/c", "type _prompt_input.txt | opencode run -m nvidia/nemotron-3.5-lightning-30b-a3b" -WorkingDirectory $dir -NoNewWindow -PassThru -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
        }
    }
    $jobs += @{ Name = "$($run.Harness)-$($run.Arm)"; Proc = $job; Dir = $dir; Log = $log }
}

Write-Host ""
Write-Host "All 6 runs launched. Waiting..."
Write-Host ""

# Wait for all to finish (timeout 10 min per run)
foreach ($job in $jobs) {
    $done = $job.Proc.WaitForExit(1800000)
    if ($done) {
        Write-Host "[DONE] $($job.Name): exit=$($job.Proc.ExitCode)"
    } else {
        $job.Proc.Kill()
        Write-Host "[TIMEOUT] $($job.Name): killed after 10 min"
    }
}

Write-Host ""
Write-Host "=== Results for Prompt $PromptNum ==="
foreach ($job in $jobs) {
    $dir = $job.Dir
    $files = Get-ChildItem $dir -Recurse -File | Where-Object { $_.Extension -in ".cpp",".h",".c" }
    $loc = 0
    foreach ($f in $files) { $loc += (Get-Content $f.FullName | Measure-Object -Line).Lines }
    Write-Host "$($job.Name): files=$($files.Count) loc=$loc log_size=$((Get-Item $job.Log -EA SilentlyContinue).Length)"
}
