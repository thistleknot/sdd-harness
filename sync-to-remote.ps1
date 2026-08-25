# Sync harness to 192.168.3.17
# Copies ~/.harness, ~/.mcp, ~/.skills — excludes .git, __pycache__, node_modules, .chroma, *.db-wal, *.db-shm, mlruns

$remote = "root@192.168.3.17"

Write-Host "=== Cleanup remote ==="
ssh $remote "rm -rf ~/.harness ~/.mcp ~/.skills"

Write-Host ""
Write-Host "=== Creating tar archives (excludes junk) ==="

$excludes = "--exclude=.git --exclude=__pycache__ --exclude=node_modules --exclude=.chroma --exclude=*.db-wal --exclude=*.db-shm --exclude=mlruns --exclude=.pytest_cache --exclude=.benchmarks --exclude=.ruff_cache --exclude=*.egg-info --exclude=*.pyc --exclude=service_stdout.log --exclude=service_stderr.log --exclude=*.log"

# Use tar via Git Bash (tar is available there)
$gitBash = "C:\Program Files\Git\usr\bin\tar.exe"

Write-Host "Packing .harness..."
& $gitBash -czf "$env:TEMP\harness.tar.gz" $excludes.Split(" ") -C "C:\Users\user" .harness

Write-Host "Packing .mcp..."
& $gitBash -czf "$env:TEMP\mcp.tar.gz" $excludes.Split(" ") -C "C:\Users\user" .mcp

Write-Host "Packing .skills..."
& $gitBash -czf "$env:TEMP\skills.tar.gz" $excludes.Split(" ") -C "C:\Users\user" .skills

Write-Host ""
Write-Host "=== Uploading ==="
scp "$env:TEMP\harness.tar.gz" "${remote}:/tmp/"
scp "$env:TEMP\mcp.tar.gz" "${remote}:/tmp/"
scp "$env:TEMP\skills.tar.gz" "${remote}:/tmp/"

Write-Host ""
Write-Host "=== Extracting on remote ==="
ssh $remote "cd ~; tar xzf /tmp/harness.tar.gz; tar xzf /tmp/mcp.tar.gz; tar xzf /tmp/skills.tar.gz; rm /tmp/harness.tar.gz /tmp/mcp.tar.gz /tmp/skills.tar.gz"

Write-Host ""
Write-Host "=== Done ==="
Write-Host "SSH in and run:"
Write-Host "  ssh $remote"
Write-Host "  pip install fastmcp httpx sentence-transformers"
Write-Host "  cd ~/.harness; python3 plugin/install.py --target claude"

# Cleanup local temp
Remove-Item "$env:TEMP\harness.tar.gz","$env:TEMP\mcp.tar.gz","$env:TEMP\skills.tar.gz" -Force -EA 0
