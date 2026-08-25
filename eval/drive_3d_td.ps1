param(
    [Parameter(Mandatory)][ValidateSet("pi","opencode","claude")][string]$Harness,
    [int]$MaxSteps = 30
)

$ErrorActionPreference = "Stop"
$evalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workDir = Join-Path $evalRoot "worktrees\3d-td-$Harness"
$logFile = Join-Path $evalRoot "results\3d-td\$Harness-log.jsonl"
$prompt = Get-Content (Join-Path $evalRoot "prompts\3d-td.md") -Raw

function Send-Prompt {
    param([string]$Text, [string]$Harness, [string]$WorkDir, [bool]$Continue = $false)
    
    switch ($Harness) {
        "claude" {
            $args = @("-p", $Text, "--dangerously-skip-permissions")
            if ($Continue) { $args += "--continue" }
            $result = & claude @args 2>&1 | Out-String
        }
        "pi" {
            $args = @("-p", $Text)
            if ($Continue) { $args += "--continue" }
            $result = & pi @args 2>&1 | Out-String
        }
        "opencode" {
            $args = @("run", $Text)
            if ($Continue) { $args += "--continue" }
            $result = & opencode @args 2>&1 | Out-String
        }
    }
    return $result
}

function Log-Step {
    param([int]$Step, [string]$Prompt, [string]$Response, [string]$CompileResult, [string]$Gates)
    $entry = @{
        step = $Step
        timestamp = (Get-Date -Format "o")
        prompt_len = $Prompt.Length
        response_len = $Response.Length
        compile = $CompileResult
        gates = $Gates
    } | ConvertTo-Json -Compress
    Add-Content -Path $logFile -Value $entry
}

function Try-Build {
    param([string]$Dir)
    $cmake = Join-Path $Dir "CMakeLists.txt"
    $buildDir = Join-Path $Dir "build"
    if (-not (Test-Path $cmake)) { return "no_cmake" }
    
    New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
    $genResult = cmd /c "cd /d $buildDir && cmake .. -G ""Visual Studio 18 2026"" -A x64 2>&1"
    if ($LASTEXITCODE -ne 0) { return "cmake_fail: $($genResult | Select-Object -Last 3)" }
    
    $buildResult = cmd /c "cd /d $buildDir && cmake --build . --config Release 2>&1"
    if ($LASTEXITCODE -ne 0) { return "build_fail: $($buildResult | Select-Object -Last 5)" }
    
    return "ok"
}

function Check-Gates {
    param([string]$Dir)
    $exe = Get-ChildItem $Dir -Recurse -Filter "*.exe" -ErrorAction SilentlyContinue | 
           Where-Object { $_.Name -notmatch "cmake|vcvars" } | Select-Object -First 1
    if (-not $exe) { return "no_exe" }
    
    $proc = Start-Process -FilePath $exe.FullName -WorkingDirectory $Dir -PassThru
    Start-Sleep 5
    if ($proc.HasExited) { return "gate1_fail:crashed" }
    
    Stop-Process $proc.Id -Force -ErrorAction SilentlyContinue
    return "gate1_pass"
}

# --- Main Loop ---
Write-Host "=== 3D TD Eval: $Harness ==="
Write-Host "WorkDir: $workDir"
Write-Host "MaxSteps: $MaxSteps"
Write-Host ""

Set-Location $workDir
$step = 0
$currentPrompt = $prompt
$continue = $false

while ($step -lt $MaxSteps) {
    $step++
    Write-Host "--- Step $step ---"
    Write-Host "Sending prompt ($($currentPrompt.Length) chars)..."
    
    $response = Send-Prompt -Text $currentPrompt -Harness $Harness -WorkDir $workDir -Continue $continue
    $continue = $true
    
    # Check if files were created
    $files = Get-ChildItem $workDir -Recurse -File -ErrorAction SilentlyContinue | 
             Where-Object { $_.Extension -in ".cpp",".h",".c",".cmake",".txt" -and $_.FullName -notmatch "build" }
    Write-Host "  Files: $($files.Count)"
    
    # Try to build
    $buildResult = Try-Build -Dir $workDir
    Write-Host "  Build: $buildResult"
    
    # Check gates if build succeeded
    $gates = "not_checked"
    if ($buildResult -eq "ok") {
        $gates = Check-Gates -Dir $workDir
        Write-Host "  Gates: $gates"
    }
    
    Log-Step -Step $step -Prompt $currentPrompt -Response $response -CompileResult $buildResult -Gates $gates
    
    # Prepare next prompt based on result
    if ($gates -match "gate1_pass") {
        $currentPrompt = "Gate 1 passed (window opens, doesn't crash). Continue to next gate: enemies spawning and pathfinding."
    } elseif ($buildResult -eq "ok") {
        $currentPrompt = "Build succeeded but the exe crashed on launch. Check for null pointers or missing initialization."
    } elseif ($buildResult -match "build_fail") {
        $errors = $buildResult -replace "build_fail: ", ""
        $currentPrompt = "Build failed with: $errors"
    } elseif ($buildResult -match "cmake_fail") {
        $errors = $buildResult -replace "cmake_fail: ", ""
        $currentPrompt = "CMake configuration failed: $errors"
    } elseif ($buildResult -eq "no_cmake") {
        $currentPrompt = "No CMakeLists.txt found. Please create the build system."
    } else {
        $currentPrompt = "Continue building. Current state: $buildResult"
    }
    
    Write-Host ""
}

Write-Host "=== Eval complete: $Harness reached step $step ==="
