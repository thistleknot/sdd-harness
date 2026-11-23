# Pipeline
# | Stage | Mechanism | Contract |
# |---|---|---|
# | CONNECT | Authenticate to the shared SSH host and verify selected remote CLIs | [mandatory] R22 |
# | VALIDATE | Check selected harness sources and Codex skill packages | [mandatory] R22, R43-R49 |
# | PACK | Build every selected archive before creating remote staging | [mandatory] R22 |
# | UPLOAD | Upload all selected archives into a unique remote staging directory | [mandatory] R22 |
# | PLACE | Additively extract selected payloads and merge the managed Claude hook | [mandatory] R22, R43-R49 |
# | VERIFY | Read back instructions, skills, and the managed hook registration; remove staging | [mandatory] R22, R48 |
#
# EARS guards
# R1: The caller selects claude, codex, or both; omitted selection means both.
# R2: If SSH, source, CLI, pack, or upload validation fails, stop before destination extraction and remove this run's remote staging directory.
# R3: Preserve remote client configuration, credentials, and hooks not managed by this sync; never copy local settings or credentials.
# R4: Credentials are requested once only when SSH key login needs bootstrapping.
# R5: The shared remote target is root@192.168.3.17; an SSH alias or per-harness target is not supported.
#
# CLOSED
# - A separate Codex SSH script is rejected by R47; one script owns selection and transport.
# - Copying local client settings or credentials is rejected by R46; selected hook registration is merged from a minimal managed fragment.
# Preconditions: Windows PowerShell, Git for Windows tar.exe, ssh/scp, key or password access, and complete selected sources.
# Failure modes: Missing selected CLI/source, archive creation failure, or upload failure stops before extraction; remote extraction/readback failures report failure.

[CmdletBinding()]
param(
    [ValidateSet("claude", "codex")]
    [string[]]$Harness = @("claude", "codex")
)

$ErrorActionPreference = "Stop"
$remote = "root@192.168.3.17"
$selected = @($Harness | ForEach-Object { $_.ToLowerInvariant() } | Select-Object -Unique)
$sshOpts = @("-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=8")
$runId = [guid]::NewGuid().ToString("N")
$stage = "/root/.sync-stage-$runId"
$localStage = Join-Path $env:TEMP "harness-sync-$runId"
$archives = [System.Collections.Generic.List[string]]::new()
$stageCreated = $false
$userRoot = $env:USERPROFILE
$harnessRoot = Join-Path $userRoot ".harness"
$gitUsrBin = "C:\Program Files\Git\usr\bin"
$tar = Join-Path $gitUsrBin "tar.exe"
$env:PATH = "$gitUsrBin;$env:PATH"
$excludes = @("--exclude=.git", "--exclude=__pycache__", "--exclude=.pytest_cache", "--exclude=*.pyc", "--exclude=*.log")

function Pack-Archive {
    <#
    Require: Root and every relative entry exist; tar.exe is available.
    Guarantee: Returns a nonempty archive in the current run's temporary directory.
    Maintain: Never includes paths outside Root or uses a shared archive filename.
    Assert: tar exits successfully and the produced archive is nonempty.
    #>
    param([string]$Name, [string]$Root, [string[]]$Entries)

    $out = Join-Path $localStage $Name
    Write-Host "Packing $Name..."
    & $tar -czf $out --force-local @excludes -C $Root @Entries
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $out) -or (Get-Item -LiteralPath $out).Length -eq 0) {
        throw "tar failed for $Name (exit $LASTEXITCODE); remote destinations unchanged"
    }
    return $out
}

try {
    Write-Host "=== Checking SSH access ==="
    $ErrorActionPreference = "Continue"
    ssh @sshOpts -o BatchMode=yes $remote "exit" 2>&1 | Out-Null
    $keyOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = "Stop"
    if (-not $keyOk) {
        $key = Join-Path $userRoot ".ssh\id_ed25519"
        if (-not (Test-Path -LiteralPath $key)) {
            New-Item -ItemType Directory -Force (Split-Path $key) | Out-Null
            ssh-keygen -t ed25519 -N '""' -f $key -q
            if ($LASTEXITCODE -ne 0) { throw "ssh-keygen failed (exit $LASTEXITCODE)" }
        }
        $pub = (Get-Content "$key.pub" -Raw).Trim()
        Write-Host "Key login not set up. Enter the remote password ONCE to install the key."
        $ErrorActionPreference = "Continue"
        ssh @sshOpts $remote "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; grep -qxF '$pub' ~/.ssh/authorized_keys || echo '$pub' >> ~/.ssh/authorized_keys"
        $ErrorActionPreference = "Stop"
        if ($LASTEXITCODE -ne 0) { throw "key install failed (exit $LASTEXITCODE); destinations unchanged" }
        $ErrorActionPreference = "Continue"
        ssh @sshOpts -o BatchMode=yes $remote "exit" 2>&1 | Out-Null
        $keyOk = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = "Stop"
        if (-not $keyOk) { throw "key login still rejected after install; destinations unchanged" }
    }

    foreach ($client in $selected) {
        $ErrorActionPreference = "Continue"
        ssh @sshOpts $remote "command -v $client >/dev/null 2>&1"
        $cliOk = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = "Stop"
        if (-not $cliOk) { throw "Selected remote CLI '$client' is unavailable; destinations unchanged" }
    }

    $requiredSources = [System.Collections.Generic.List[string]]::new()
    $claudeSourceEntries = @("CLAUDE.md", "SOUL.md", "AGENTS.md", "agents", "rules", "docs", "hooks")
    if ($selected -contains "claude") {
        foreach ($entry in $claudeSourceEntries) { $requiredSources.Add((Join-Path (Join-Path $harnessRoot "claude") $entry)) }
        $requiredSources.Add((Join-Path $userRoot ".claude\hooks\route_instructions.py"))
        foreach ($entry in @(".rules", ".skills\GLOSSARY.md", ".skills\plan-do\SKILL.md", ".skills\task-breakdown\SKILL.md", ".tessl\RULES.md", ".harness\constitution.md", ".harness\rules", ".harness\hooks\plan_do_route.py", ".harness\hooks\_common.py")) {
            $requiredSources.Add((Join-Path $userRoot $entry))
        }
        foreach ($entry in @(".skills\plan-do", ".skills\task-breakdown")) { $requiredSources.Add((Join-Path $userRoot $entry)) }
    }
    $codexSkillDirs = @()
    if ($selected -contains "codex") {
        $requiredSources.Add((Join-Path $userRoot ".codex\AGENTS.md"))
        $requiredSources.Add((Join-Path $userRoot ".tessl\RULES.md"))
        $skillRoot = Join-Path $userRoot ".agents\skills"
        $requiredSources.Add($skillRoot)
        $codexSkillDirs = @(Get-ChildItem -LiteralPath $skillRoot -Directory -ErrorAction SilentlyContinue)
        if ($codexSkillDirs.Count -eq 0) { throw "No selected Codex skill packages found at $skillRoot; destinations unchanged" }
        foreach ($skillDir in $codexSkillDirs) {
            $requiredSources.Add((Join-Path $skillDir.FullName "SKILL.md"))
        }
    }
    $missingSources = @($requiredSources | Where-Object { -not (Test-Path -LiteralPath $_) })
    if ($missingSources.Count -gt 0) {
        throw "Required selected runtime source is missing; destinations unchanged:`n$($missingSources -join "`n")"
    }

    if (-not (Test-Path -LiteralPath $tar)) { throw "Git for Windows tar.exe is missing at $tar; destinations unchanged" }

    Write-Host ""
    Write-Host "=== Packing selected harnesses: $($selected -join ', ') ==="
    New-Item -ItemType Directory -Path $localStage | Out-Null
    if ($selected -contains "claude") {
        $archives.Add((Pack-Archive "claude.tar.gz" (Join-Path $harnessRoot "claude") $claudeSourceEntries))
        $archives.Add((Pack-Archive "claude-support.tar.gz" $userRoot @(".rules", ".skills/GLOSSARY.md", ".skills/plan-do", ".skills/task-breakdown", ".tessl/RULES.md", ".harness/constitution.md", ".harness/rules", ".harness/hooks/plan_do_route.py", ".harness/hooks/_common.py")))
        $archives.Add((Pack-Archive "claude-skills.tar.gz" (Join-Path $userRoot ".skills") @("plan-do", "task-breakdown")))
        # Ship only the managed handler fragment; the local global settings file contains machine-specific hooks.
        $routePayloadRoot = Join-Path $localStage "route-payload"
        $routeHookDir = Join-Path $routePayloadRoot ".claude\hooks"
        New-Item -ItemType Directory -Path $routeHookDir -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $userRoot ".claude\hooks\route_instructions.py") -Destination (Join-Path $routeHookDir "route_instructions.py")
        $routeSettings = @{
            hooks = @{
                UserPromptSubmit = @(
                    @{
                        hooks = @(
                            @{
                                type = "command"
                                shell = "bash"
                                command = 'python "$HOME/.claude/hooks/route_instructions.py"'
                                timeout = 10
                            }
                        )
                    }
                )
            }
        }
        $routeSettingsPath = Join-Path $routePayloadRoot ".claude\route-hook-fragment.json"
        [System.IO.File]::WriteAllText($routeSettingsPath, ($routeSettings | ConvertTo-Json -Depth 10), [System.Text.UTF8Encoding]::new($false))
        $mergeScript = @'
import copy
import datetime
import json
import os
import shutil
import stat
import tempfile

home = os.path.expanduser("~")
settings_path = os.path.join(home, ".claude", "settings.json")
fragment_path = os.path.join(home, ".claude", "route-hook-fragment.json")
with open(fragment_path, encoding="utf-8") as stream:
    managed = json.load(stream)["hooks"]["UserPromptSubmit"][0]["hooks"][0]
if os.path.exists(settings_path):
    with open(settings_path, encoding="utf-8") as stream:
        original = json.load(stream)
    settings = copy.deepcopy(original)
    mode = stat.S_IMODE(os.stat(settings_path).st_mode)
else:
    original = {}
    settings = {}
    mode = 0o600
hooks = settings.setdefault("hooks", {})
groups = hooks.setdefault("UserPromptSubmit", [])
if not isinstance(groups, list):
    raise TypeError("hooks.UserPromptSubmit must be a list")
for group in groups:
    group["hooks"] = [
        item for item in group.get("hooks", [])
        if "route_instructions.py" not in item.get("command", "")
        and not any("route_instructions.py" in arg for arg in item.get("args", []))
    ]
groups[:] = [group for group in groups if group.get("hooks")]
groups.append({"hooks": [managed]})
if settings != original:
    if os.path.exists(settings_path):
        os.makedirs(os.path.join(home, ".claude", "backups"), exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = os.path.join(home, ".claude", "backups", "settings.json.before-route-" + stamp)
        shutil.copy2(settings_path, backup)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".settings-route-", suffix=".tmp", dir=os.path.dirname(settings_path))
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(settings, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    os.chmod(temporary_path, mode)
    os.replace(temporary_path, settings_path)
with open(settings_path, encoding="utf-8") as stream:
    verified = json.load(stream)
matches = [
    item for group in verified.get("hooks", {}).get("UserPromptSubmit", [])
    for item in group.get("hooks", [])
    if "route_instructions.py" in item.get("command", "")
    or any("route_instructions.py" in arg for arg in item.get("args", []))
]
if len(matches) != 1 or matches[0] != managed:
    raise RuntimeError("managed Claude route hook readback failed")
print("CLAUDE_ROUTE_HOOK_MERGED")
'@
        $mergeScriptPath = Join-Path $routePayloadRoot ".claude\merge-route-hook.py"
        [System.IO.File]::WriteAllText($mergeScriptPath, $mergeScript, [System.Text.UTF8Encoding]::new($false))
        $archives.Add((Pack-Archive "claude-route-hook.tar.gz" $routePayloadRoot @(".claude/hooks/route_instructions.py", ".claude/route-hook-fragment.json", ".claude/merge-route-hook.py")))
    }
    if ($selected -contains "codex") {
        $archives.Add((Pack-Archive "codex-home.tar.gz" $userRoot @(".codex/AGENTS.md", ".tessl/RULES.md")))
        $skillEntries = @($codexSkillDirs | ForEach-Object { ".agents/skills/$($_.Name)" })
        $archives.Add((Pack-Archive "codex-skills.tar.gz" $userRoot $skillEntries))
    }
    $totalBytes = ($archives | ForEach-Object { (Get-Item -LiteralPath $_).Length } | Measure-Object -Sum).Sum
    Write-Host ("  payload {0:N0} KB" -f ($totalBytes / 1KB))

    Write-Host ""
    Write-Host "=== Uploading ==="
    $ErrorActionPreference = "Continue"
    $stageCreated = $true
    ssh @sshOpts $remote "mkdir -m 700 '$stage'"
    $ok = ($LASTEXITCODE -eq 0)
    if ($ok) {
        foreach ($archive in $archives) {
            scp @sshOpts $archive "${remote}:$stage/"
            if ($LASTEXITCODE -ne 0) { $ok = $false; break }
        }
    }
    $ErrorActionPreference = "Stop"
    if (-not $ok) { throw "Upload failed; remote destinations unchanged" }

    Write-Host ""
    Write-Host "=== Placing files ==="
    $commands = @("set -e")
    if ($selected -contains "claude") {
        $commands += @(
            "mkdir -p ~/.claude ~/.claude/skills ~/.claude/hooks",
            "tar xzf $stage/claude.tar.gz -C ~/.claude",
            "tar xzf $stage/claude-support.tar.gz -C ~",
            "tar xzf $stage/claude-skills.tar.gz -C ~/.claude/skills",
            "tar xzf $stage/claude-route-hook.tar.gz -C ~",
            "python3 ~/.claude/merge-route-hook.py",
            "rm -f ~/.claude/route-hook-fragment.json ~/.claude/merge-route-hook.py",
            "test -r ~/.claude/CLAUDE.md",
            "test -r ~/.claude/hooks/route_instructions.py",
            "test -r ~/.harness/constitution.md",
            "test -r ~/.skills/GLOSSARY.md",
            "test -r ~/.tessl/RULES.md",
            "test -r ~/.skills/plan-do/SKILL.md",
            "test -r ~/.skills/task-breakdown/SKILL.md",
            "test -r ~/.claude/skills/plan-do/SKILL.md",
            "test -r ~/.claude/skills/task-breakdown/SKILL.md",
            "test -r ~/.rules/010-operating-core.md",
            "test -r ~/.harness/rules/approval-scope.md",
            "test -r ~/.harness/hooks/plan_do_route.py"
        )
    }
    if ($selected -contains "codex") {
        $commands += @("mkdir -p ~/.codex ~/.agents/skills", "tar xzf $stage/codex-home.tar.gz -C ~", "tar xzf $stage/codex-skills.tar.gz -C ~", "test -r ~/.codex/AGENTS.md", "test -r ~/.tessl/RULES.md")
        foreach ($skillDir in $codexSkillDirs) { $commands += "test -r ~/.agents/skills/$($skillDir.Name)/SKILL.md" }
    }
    if ($selected -contains "claude") { $commands += "ls -ld ~/.claude ~/.claude/skills/plan-do ~/.claude/skills/task-breakdown ~/.rules ~/.skills/plan-do ~/.skills/task-breakdown ~/.harness/rules ~/.harness/hooks" }
    if ($selected -contains "codex") { $commands += "ls -ld ~/.codex/AGENTS.md ~/.agents/skills" }
    $commands += "rm -rf '$stage'"
    $commands += "echo SYNC_READBACK_OK"
    $ErrorActionPreference = "Continue"
    ssh @sshOpts $remote ($commands -join "; ")
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = "Stop"
    if (-not $ok) { throw "Remote extraction or selected destination readback failed" }
    $stageCreated = $false
    Write-Host ""
    Write-Host "=== Done ==="
    Write-Host "Verified selected harnesses on ${remote}: $($selected -join ', '). Client config and credentials were preserved."
    if ($selected -contains "claude") { Write-Host "Claude's managed route hook was merged additively." }
}
finally {
    if ($stageCreated) {
        $ErrorActionPreference = "Continue"
        ssh @sshOpts $remote "rm -rf '$stage'" 2>&1 | Out-Null
        $ErrorActionPreference = "Stop"
    }
    if ($archives.Count -gt 0) { Remove-Item -LiteralPath $archives.ToArray() -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $localStage) {
        $resolvedLocalStage = [System.IO.Path]::GetFullPath($localStage)
        $resolvedTempRoot = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
        if (-not $resolvedLocalStage.StartsWith($resolvedTempRoot, [System.StringComparison]::OrdinalIgnoreCase) -or (Split-Path -Leaf $resolvedLocalStage) -ne "harness-sync-$runId") {
            throw "Refusing to remove unexpected local staging path: $resolvedLocalStage"
        }
        Remove-Item -LiteralPath $resolvedLocalStage -Recurse -Force -ErrorAction SilentlyContinue
    }
}
