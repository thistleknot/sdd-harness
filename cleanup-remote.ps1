# Cleanup the mess on 192.168.3.17 and re-sync only what's needed
# Run from Windows

$remote = "root@192.168.3.17"

Write-Host "Removing everything we just dumped..."
ssh $remote "rm -rf ~/.harness ~/.mcp ~/.skills ~/memory-bank"

Write-Host "Done. Remote is clean."
Write-Host ""
Write-Host "To re-sync properly, use sync-to-remote.ps1 (now fixed)."
