# Pipeline stages (execution order):
# | Stage | Mechanism | Tag | Requirement |
# | PROMPT | Read one prompt file and preserve its full text | [mandatory] | R1 |
# | LAUNCH | Feed Claude/Pi on stdin; pass OpenCode one quoted positional argument | [mandatory] | R1 |
# | WAIT | Wait 30 minutes per arm, then kill and report timeout | [mandatory] | R2 |
# | REPORT | Print process status and generated C/C++ file and LOC counts | [mandatory] | R3 |
# R1: When an arm starts, its harness MUST receive the complete prompt in its declared input channel.
# R2: If an arm exceeds 30 minutes, then the runner MUST terminate it and report the timeout.
# R3: When all arms finish, the runner MUST report exit status and output counts per arm.
# CLOSED: OpenCode stdin was rejected because its run command expects the message as a positional argument.
# Preconditions: PromptNum identifies an existing prompt and all six worktrees exist.
# Failure modes: Missing prompt/worktree or missing harness executable stops that launch; timeout kills that arm.
param(
    [Parameter(Mandatory)][int]$PromptNum
)

function ConvertTo-WindowsArgument {
    <#
    .SYNOPSIS
    Quotes one value for the Windows native process command line.
    .DESCRIPTION
    Preserves spaces, quotes, trailing backslashes, and newlines as one argv value.
    .PARAMETER Value
    The argument value to quote.
    .OUTPUTS
    System.String. The encoded command-line argument.
    .NOTES
    Called by the OpenCode launch branch; follows the Windows CRT backslash/quote rules.
    Failure mode: invalid input type is rejected by PowerShell parameter binding.
    Require: Value is the complete prompt for one OpenCode run.
    Guarantee: The returned string parses as exactly one Windows command-line argument.
    Maintain: Backslashes and quotes remain associated with their original prompt text.
    Assert: Callers pass one prompt value and do not append other arguments inside it.
    #>
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Value)

    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.Append('"')
    $backslashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') {
            $backslashes++
            continue
        }
        if ($character -eq '"') {
            [void]$builder.Append(('\' * (2 * $backslashes + 1)))
            [void]$builder.Append('"')
            $backslashes = 0
            continue
        }
        if ($backslashes -gt 0) {
            [void]$builder.Append(('\' * $backslashes))
            $backslashes = 0
        }
        [void]$builder.Append($character)
    }
    if ($backslashes -gt 0) {
        [void]$builder.Append(('\' * (2 * $backslashes)))
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

$evalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$worktreeRoot = Join-Path $evalRoot "worktrees"
$resultsRoot = Join-Path $evalRoot "results\3d-td"
$promptFile = Join-Path $evalRoot "prompts\td-p$PromptNum.md"
$prompt = Get-Content $promptFile -Raw

New-Item -ItemType Directory -Path $resultsRoot -Force | Out-Null

$runs = @(
    @{ Harness = "claude"; Arm = "gates-on" },
    @{ Harness = "claude"; Arm = "gates-off" },
    @{ Harness = "pi"; Arm = "gates-on" },
    @{ Harness = "pi"; Arm = "gates-off" },
    @{ Harness = "opencode"; Arm = "gates-on" },
    @{ Harness = "opencode"; Arm = "gates-off" }
)

$jobs = @()
foreach ($run in $runs) {
    $dir = Join-Path $worktreeRoot "td-$($run.Harness)-$($run.Arm)-p$PromptNum"
    $log = Join-Path $resultsRoot "$($run.Harness)-$($run.Arm)-p$PromptNum.log"
    
    Write-Host "Starting: $($run.Harness) [$($run.Arm)] prompt $PromptNum in $dir"
    
    # Keep stdin-based harnesses on a file; pass OpenCode's prompt as one argv value.
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
            $promptArgument = ConvertTo-WindowsArgument -Value $prompt
            $arguments = @("run", "-m", "nvidia/nemotron-3.5-lightning-30b-a3b", $promptArgument) -join " "
            $job = Start-Process -FilePath "opencode" -ArgumentList $arguments -WorkingDirectory $dir -NoNewWindow -PassThru -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
        }
    }
    $jobs += @{ Name = "$($run.Harness)-$($run.Arm)"; Proc = $job; Dir = $dir; Log = $log }
}

Write-Host ""
Write-Host "All 6 runs launched. Waiting..."
Write-Host ""

# Wait up to 30 minutes for each arm.
foreach ($job in $jobs) {
    $done = $job.Proc.WaitForExit(1800000)
    if ($done) {
        Write-Host "[DONE] $($job.Name): exit=$($job.Proc.ExitCode)"
    } else {
        $job.Proc.Kill()
        Write-Host "[TIMEOUT] $($job.Name): killed after 30 min"
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
