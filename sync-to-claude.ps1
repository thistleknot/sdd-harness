# Sync the harness claude vault <-> the live ~/.claude tree.
#
# Merged from the old sync.ps1 (param surface, setup.py delegation, -Push) and
# the sync-to-remote.ps1 format.
#
# SAFETY MODEL: no backup copies are made. Both trees are git repositories
# (~/.claude and ~/.harness), so history IS the backup -- see `git -C ~/.claude log`.
# Nothing is ever deleted or mirrored: every write is a targeted single-file
# copy, so a stale vault cannot remove live state.
#
# DIRECTION MATTERS. Reductions must never be regressed. Files that have been
# through a slop cut (see slop-review/findings.md) are newer and *smaller* in
# the live tree; pushing the vault over them re-inflates the system prompt,
# which is the exact failure "Delete your CLAUDE.md" warns about. -Pull moves
# the reduced artifact back into the vault instead.
#
#   .\sync-to-claude.ps1 -DryRun     # show what would change, touch nothing
#   .\sync-to-claude.ps1 -Push       # vault -> live
#   .\sync-to-claude.ps1 -Pull       # live  -> vault (capture reductions)
#   .\sync-to-claude.ps1 -Install    # delegate to setup.py (canonical convergence)

[CmdletBinding()]
param(
    [string]$HarnessRoot = "C:\Users\user\.harness",
    [string]$ClaudeRoot  = "C:\Users\user\.claude",
    [switch]$Push,
    [switch]$Pull,
    [switch]$Install,
    [switch]$DryRun
)

$src = Join-Path $HarnessRoot "claude"
$dst = $ClaudeRoot

if (-not (Test-Path $src)) { Write-Host "FATAL: vault not found: $src" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $dst)) { Write-Host "FATAL: live tree not found: $dst" -ForegroundColor Red; exit 1 }
if ($Push -and $Pull)      { Write-Host "FATAL: -Push and -Pull are mutually exclusive" -ForegroundColor Red; exit 1 }
if (-not ($Push -or $Pull -or $Install)) { $DryRun = $true }

# Files that carry reductions. Pushing the vault over a newer live copy of these
# re-inflates the system prompt, so it requires an explicit override.
$reduced = @("CLAUDE.md", "AGENTS.md", "SOUL.md")

$script:changed = 0
$script:same    = 0
$script:held    = 0

function Sync-One {
    param([string]$From, [string]$To, [string]$Rel, [string]$Arrow)

    if (-not (Test-Path $From)) { return }

    if (Test-Path $To) {
        if ((Get-FileHash $From -Algorithm SHA256).Hash -eq (Get-FileHash $To -Algorithm SHA256).Hash) {
            $script:same++; return
        }
    }

    # guard: never let a bigger, older file overwrite a smaller, newer one
    if ($Rel -in $reduced -and (Test-Path $To)) {
        $f = Get-Item $From; $t = Get-Item $To
        if ($t.LastWriteTime -gt $f.LastWriteTime -and $t.Length -lt $f.Length) {
            $delta = $f.Length - $t.Length
            Write-Host ("  HOLD   {0}  (live is newer and {1}b smaller - looks like a reduction)" -f $Rel, $delta) -ForegroundColor Magenta
            $script:held++
            return
        }
    }

    $verb = if (Test-Path $To) { "update" } else { "create" }

    if ($DryRun) {
        Write-Host ("  {0,-6} {1} {2}" -f $verb, $Arrow, $Rel) -ForegroundColor Yellow
        $script:changed++; return
    }

    $tdir = Split-Path $To -Parent
    if (-not (Test-Path $tdir)) { New-Item -ItemType Directory -Path $tdir -Force | Out-Null }

    Copy-Item $From $To -Force
    Write-Host ("  {0,-6} {1} {2}" -f $verb, $Arrow, $Rel) -ForegroundColor Green
    $script:changed++
}

function Sync-Tree {
    param([string]$Name, [string]$From, [string]$To, [string]$Arrow)

    $root = Join-Path $From $Name
    if (-not (Test-Path $root)) { return }

    # Build artifacts are not vault material. Without this filter -Pull walks the
    # live tree and permanently vaults compiled bytecode -- observed 2026-08-24:
    # a pull of one reduced AGENTS.md wanted to bring 8 __pycache__/*.pyc with it.
    Get-ChildItem $root -Recurse -File |
        Where-Object {
            $_.FullName -notmatch '\\__pycache__\\' -and
            $_.Extension -notin @('.pyc', '.pyo')
        } |
        ForEach-Object {
            $rel = $_.FullName.Substring($From.Length).TrimStart('\')
            Sync-One -From $_.FullName -To (Join-Path $To $rel) -Rel $rel -Arrow $Arrow
        }
}

# --- canonical convergence ----------------------------------------------------

if ($Install) {
    Write-Host "=== Delegating to setup.py (design.md 13: single convergence command) ==="
    if ($DryRun) {
        Write-Host "  would run: python plugin/install.py --target claude" -ForegroundColor Yellow
    } else {
        Push-Location $HarnessRoot
        python plugin/install.py --target claude
        Pop-Location
    }
    exit $LASTEXITCODE
}

# --- direction ----------------------------------------------------------------

if ($Pull) { $from, $to, $arrow, $label = $dst, $src, "<-", "live -> vault (capturing reductions)" }
else       { $from, $to, $arrow, $label = $src, $dst, "->", "vault -> live" }

Write-Host "=== $label ==="
if ($DryRun) { Write-Host "    (dry run - nothing will be written; pass -Push or -Pull to apply)" -ForegroundColor Yellow }

Write-Host ""
Write-Host "=== Root instructions ==="
foreach ($f in @("CLAUDE.md", "SOUL.md", "AGENTS.md")) {
    Sync-One -From (Join-Path $from $f) -To (Join-Path $to $f) -Rel $f -Arrow $arrow
}

Write-Host ""
Write-Host "=== Agents / rules / docs / hooks ==="
foreach ($d in @("agents", "rules", "docs", "hooks")) {
    Sync-Tree -Name $d -From $from -To $to -Arrow $arrow
}

# settings.json is a merge target: the manifest points four cells at it
# (adapter, lifecycle, test_gen, skills_router). A flat copy drops whatever
# setup.py merged in later, so it is never copied here.
Write-Host ""
Write-Host "=== settings.json ==="
Write-Host "  skipped (merge target - use -Install)" -ForegroundColor DarkGray

Write-Host ""
Write-Host "=== Done ==="
Write-Host "  changed: $script:changed   unchanged: $script:same   held: $script:held"
if ($script:held -gt 0) {
    Write-Host "  $script:held file(s) held back to protect a reduction - use -Pull to capture them instead" -ForegroundColor Magenta
}
if ($DryRun) { Write-Host "  re-run with -Push or -Pull to apply" -ForegroundColor Yellow }
Write-Host "  recovery: git -C $dst log   (no backup copies are kept by design)" -ForegroundColor DarkGray
