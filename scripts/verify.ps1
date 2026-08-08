# verify.ps1 — Health check for the cross-harness SDD system
# Run: powershell -File ~/.harness/scripts/verify.ps1
# Checks: MCP services, hooks, memory, skills, settings

$ErrorActionPreference = "Continue"
$pass = 0; $fail = 0; $skip = 0

function Check($name, $test) {
    try {
        $result = & $test
        if ($result) { Write-Host "  PASS  $name" -ForegroundColor Green; $script:pass++ }
        else { Write-Host "  FAIL  $name" -ForegroundColor Red; $script:fail++ }
    } catch {
        Write-Host "  FAIL  $name ($($_.Exception.Message))" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "=== Cross-Harness SDD Health Check ===" -ForegroundColor Cyan
Write-Host ""

# 1. MCP Services
Write-Host "--- MCP Services ---"
Check "retrieve-skills (:8765)" { (Invoke-WebRequest "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 }
Check "memory-index (:8055)" { (Invoke-WebRequest "http://127.0.0.1:8055/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 }

# 2. Windows Services
Write-Host "--- Windows Services ---"
Check "mem-server service" { (Get-Service mem-server -ErrorAction SilentlyContinue).Status -eq "Running" }

# 3. Skill Store
Write-Host "--- Skill Store ---"
Check "skill store exists" { Test-Path "$HOME\.claude\skills\.skills" }
$skillCount = (Get-ChildItem "$HOME\.claude\skills\.skills" -Directory).Count
Check "skill store populated ($skillCount skills)" { $skillCount -gt 100 }
Check "index.db exists" { Test-Path "$HOME\.claude\skills\retrieve-skills\index.db" }

# 4. Memory Bank
Write-Host "--- Memory Bank ---"
Check "memory-bank dir exists" { Test-Path "$HOME\memory-bank" }
Check "activeContext.md exists" { Test-Path "$HOME\memory-bank\activeContext.md" }
Check "chroma store exists" { Test-Path "$HOME\memory-bank\.chroma" }

# 5. Claude Code Config
Write-Host "--- Claude Code ---"
Check "settings.json exists" { Test-Path "$HOME\.claude\settings.json" }
Check ".claude.json has MCP servers" { (Get-Content "$HOME\.claude.json" -Raw) -match "retrieve-skills" }
Check "hook.py wired" { (Get-Content "$HOME\.claude\settings.json" -Raw) -match "hook.py" }
Check "spec_gate.py exists" { Test-Path "$HOME\.claude\hooks\spec_gate.py" }

# 6. Kiro Config
Write-Host "--- Kiro ---"
Check "kiro mcp.json exists" { Test-Path "$HOME\.kiro\settings\mcp.json" }
Check "kiro steering exists" { Test-Path "$HOME\.kiro\steering\testing.md" }

# 7. opencode Config
Write-Host "--- opencode ---"
Check "opencode.json exists" { Test-Path "$HOME\.config\opencode\opencode.json" }
Check "opencode has MCP" { (Get-Content "$HOME\.config\opencode\opencode.json" -Raw) -match "retrieve-skills" }

# 8. Harness Spec
Write-Host "--- Harness Spec ---"
Check "requirements.md" { Test-Path "$HOME\.harness\requirements.md" }
Check "design.md" { Test-Path "$HOME\.harness\design.md" }
Check "inspirations.md" { Test-Path "$HOME\.harness\inspirations.md" }

Write-Host ""
Write-Host "=== Results: $pass passed, $fail failed, $skip skipped ===" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Yellow" })
