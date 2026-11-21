# Sync the Claude downstream of the meta-harness to 192.168.3.17.
# Places the vault's Claude files (~/.harness/claude) into remote ~/.claude and the selected runtime
# dependencies referenced by those files at their matching home paths, including native-discovery skills.
# The full 5.3 GB skill library and unrelated harness framework are not copied. Old full-framework copies are removed by cleanup-remote.ps1.
#
# Pipeline: SSH check -> source check -> pack all archives -> upload all -> additive extract -> readback.
# Spec: docs/playbooks/memory-and-harness-integration.md R22.
# Nothing on the remote is replaced until all payload archives are packed and have reached it; extraction only
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

$userRoot = $env:USERPROFILE
$harnessRoot = Join-Path $userRoot ".harness"
$requiredSources = @(
    (Join-Path $userRoot ".rules"),
    (Join-Path $userRoot ".skills\GLOSSARY.md"),
    (Join-Path $userRoot ".skills\plan-do\SKILL.md"),
    (Join-Path $userRoot ".skills\task-breakdown\SKILL.md"),
    (Join-Path $harnessRoot "constitution.md"),
    (Join-Path $harnessRoot "rules"),
    (Join-Path $harnessRoot "hooks\plan_do_route.py"),
    (Join-Path $harnessRoot "hooks\_common.py")
)
$missingSources = @($requiredSources | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missingSources.Count -gt 0) {
    throw "Required Claude runtime source is missing; remote untouched:`n$($missingSources -join "`n")"
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
    (Pack-Archive "claude.tar.gz"  (Join-Path $harnessRoot "claude") @("CLAUDE.md", "SOUL.md", "AGENTS.md", "agents", "rules", "docs", "hooks")),
    (Pack-Archive "support.tar.gz" $userRoot @(".rules", ".skills/GLOSSARY.md", ".skills/plan-do", ".skills/task-breakdown", ".harness/constitution.md", ".harness/rules", ".harness/hooks/plan_do_route.py", ".harness/hooks/_common.py")),
    (Pack-Archive "native-skills.tar.gz" (Join-Path $userRoot ".skills") @("plan-do", "task-breakdown"))
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
ssh @sshOpts $remote "set -e; mkdir -p ~/.claude ~/.claude/skills; tar xzf $stage/claude.tar.gz -C ~/.claude; tar xzf $stage/support.tar.gz -C ~; tar xzf $stage/native-skills.tar.gz -C ~/.claude/skills; rm -rf $stage; test -r ~/.claude/CLAUDE.md; test -r ~/.harness/constitution.md; test -r ~/.skills/GLOSSARY.md; test -r ~/.skills/plan-do/SKILL.md; test -r ~/.skills/task-breakdown/SKILL.md; test -r ~/.claude/skills/plan-do/SKILL.md; test -r ~/.claude/skills/task-breakdown/SKILL.md; test -r ~/.rules/010-operating-core.md; test -r ~/.harness/rules/approval-scope.md; test -r ~/.harness/hooks/plan_do_route.py; ls -ld ~/.claude ~/.claude/skills/plan-do ~/.claude/skills/task-breakdown ~/.rules ~/.skills/plan-do ~/.skills/task-breakdown ~/.harness/rules ~/.harness/hooks"
$ok = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $ok) { throw "remote extract failed" }

Write-Host ""
Write-Host "=== Done ==="
Write-Host "Claude files and selected runtime dependencies are in the remote home on $remote. Hooks stay unwired until a path-translated settings.json merge exists (R22 OPEN)."

Remove-Item $archives -Force -ErrorAction SilentlyContinue
