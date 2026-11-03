# Remove what the old full-framework sync left on 192.168.3.17.
# Run from Windows:  powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\user\.harness\cleanup-remote.ps1
#
# Removes: ~/.harness ~/.mcp ~/.skills (copied by the old sync), ~/.sync-stage and /tmp/*.tar.gz (upload
# partials from the failed runs of 2026-10-26/27). Leaves ~/.claude alone: that is the target of the
# current sync. Leaves ~/memory-bank alone: no sync script ever wrote it, so it is the remote's own.
# Needs key login (sync-to-remote.ps1 installs the key on its first run).

$remote = "root@192.168.3.17"
$sshOpts = @("-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=8")
$targets = "~/.harness ~/.mcp ~/.skills ~/.sync-stage /tmp/harness.tar.gz /tmp/mcp.tar.gz /tmp/skills.tar.gz /tmp/claude.tar.gz"

# Native stderr is a terminating error under "Stop" in Windows PowerShell 5.1, so leave the default.
Write-Host "=== On the remote now ==="
ssh @sshOpts $remote "du -sh $targets 2>/dev/null; true"
if ($LASTEXITCODE -ne 0) { Write-Host "ssh failed (exit $LASTEXITCODE); nothing removed"; exit 1 }

Write-Host ""
Write-Host "=== Removing ==="
ssh @sshOpts $remote "rm -rf $targets; du -sh $targets 2>/dev/null; echo remaining-check-done"
if ($LASTEXITCODE -ne 0) { Write-Host "removal failed (exit $LASTEXITCODE)"; exit 1 }
Write-Host "Done. ~/.claude was not touched."
