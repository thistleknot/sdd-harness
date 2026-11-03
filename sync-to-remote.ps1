# Sync the Claude downstream of the meta-harness to 192.168.3.17.
# Places the vault's Claude files (~/.harness/claude) into the remote ~/.claude, additively, plus the two
# files CLAUDE.md @-imports (~/.harness/constitution.md, ~/.skills/GLOSSARY.md) at the paths it names.
# The remote runs only Claude, so the framework itself (.harness, .mcp, .skills) is NOT copied.
# Old full-framework copies on the remote are removed by cleanup-remote.ps1.
#
# Spec: docs/playbooks/memory-and-harness-integration.md R22.
# Nothing on the remote is replaced until both archives are packed and have reached it; extraction only
# adds or overwrites files, it deletes nothing. settings.json is never sent (see R22 OPEN item).

$ErrorActionPreference = "Stop"
$remote = "root@192.168.3.17"

# Credentials are asked for ONCE. If key login does not work yet, the first password prompt installs
# this machine's public key on the remote; every later ssh/scp call then runs without a prompt.
$sshOpts = @("-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=8")

Write-Host "=== Checking SSH access ==="
# Windows PowerShell 5.1 turns native stderr into a terminating error under "Stop"; relax it around ssh probes.
$ErrorActionPreference = "Continue"
ssh @sshOpts -o BatchMode=yes $remote "exit" 2>&1 | Out-Null
$keyOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $keyOk) {
    $key = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
    if (-not (Test-Path $key)) {
        New-Item -ItemType Directory -Force (Split-Path $key) | Out-Null
        ssh-keygen -t ed25519 -N '""' -f $key -q
        if ($LASTEXITCODE -ne 0) { throw "ssh-keygen failed (exit $LASTEXITCODE)" }
    }
    $pub = (Get-Content "$key.pub" -Raw).Trim()
    Write-Host "Key login not set up. Enter the remote password ONCE to install the key."
    $ErrorActionPreference = "Continue"
    ssh @sshOpts $remote "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; grep -qxF '$pub' ~/.ssh/authorized_keys || echo '$pub' >> ~/.ssh/authorized_keys"
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0) { throw "key install failed (exit $LASTEXITCODE); remote untouched" }
    $ErrorActionPreference = "Continue"
    ssh @sshOpts -o BatchMode=yes $remote "exit" 2>&1 | Out-Null
    $keyOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = "Stop"
    if (-not $keyOk) { throw "key login still rejected after install (exit $LASTEXITCODE); remote untouched" }
}

# tar.exe from Git for Windows shells out to gzip; PowerShell/cmd PATH does not include it.
$gitUsrBin = "C:\Program Files\Git\usr\bin"
$tar = Join-Path $gitUsrBin "tar.exe"
$env:PATH = "$gitUsrBin;$env:PATH"

$excludes = "--exclude=.git --exclude=__pycache__ --exclude=.pytest_cache --exclude=*.pyc --exclude=*.log"

function Pack-Archive {
    param([string]$Name, [string]$Root, [string[]]$Entries)
    $out = Join-Path $env:TEMP $Name
    Write-Host "Packing $Name..."
    # --force-local: GNU tar reads "C:" in an archive path as a remote host otherwise.
    & $tar -czf $out --force-local $excludes.Split(" ") -C $Root @Entries
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out) -or (Get-Item $out).Length -eq 0) {
        throw "tar failed for $Name (exit $LASTEXITCODE); remote untouched"
    }
    return $out
}

Write-Host ""
Write-Host "=== Packing ==="
$archives = @(
    # settings.json is deliberately left out: it is a merge target full of Windows paths.
    (Pack-Archive "claude.tar.gz"  "C:\Users\user\.harness\claude" @("CLAUDE.md", "SOUL.md", "AGENTS.md", "agents", "rules", "docs", "hooks")),
    (Pack-Archive "imports.tar.gz" "C:\Users\user" @(".harness/constitution.md", ".skills/GLOSSARY.md"))
)
Write-Host ("  payload {0:N0} KB" -f ((($archives | ForEach-Object { (Get-Item $_).Length } | Measure-Object -Sum).Sum) / 1KB))

Write-Host ""
Write-Host "=== Uploading ==="
$stage = "~/.sync-stage"
$ErrorActionPreference = "Continue"
ssh @sshOpts $remote "rm -rf $stage; mkdir -p $stage"
$ok = ($LASTEXITCODE -eq 0)
if ($ok) { scp @sshOpts @archives "${remote}:$stage/"; $ok = ($LASTEXITCODE -eq 0) }
$ErrorActionPreference = "Stop"
if (-not $ok) { throw "upload failed; remote untouched" }

Write-Host ""
Write-Host "=== Placing files ==="
$ErrorActionPreference = "Continue"
ssh @sshOpts $remote "set -e; mkdir -p ~/.claude; tar xzf $stage/claude.tar.gz -C ~/.claude; tar xzf $stage/imports.tar.gz -C ~; rm -rf $stage; ls ~/.claude/CLAUDE.md ~/.harness/constitution.md ~/.skills/GLOSSARY.md"
$ok = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $ok) { throw "remote extract failed" }

Write-Host ""
Write-Host "=== Done ==="
Write-Host "Claude files are in ~/.claude on $remote. Hooks stay unwired until a path-translated settings.json merge exists (R22 OPEN)."

Remove-Item $archives -Force -ErrorAction SilentlyContinue
