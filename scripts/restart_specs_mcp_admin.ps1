<#
| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| GUARD | Require elevation and verify the registered Specs MCP executable, source, and directory | [mandatory] | R1 |
| RESTART | Restart only the existing `specs-mcp` service | [mandatory] | R1-R2 |
| HEALTH | Poll service state and HTTP health endpoint with a fixed timeout | [mandatory] | R2 |
| PROBE | Call the live `cross_analyze` MCP tool with prefix-negative and exact/task-local cases | [mandatory] | R3 |
| RECEIPT | Save timestamped service, source hash, and probe results as JSON | [contract] | R4 |

R1: WHEN the service registration differs from the verified install, THEN stop before restarting.
R2: WHEN the service fails to become healthy within 45 seconds, THEN report failure and do not claim verification.
R3: WHEN live prefix or task-block results differ from expected values, THEN exit nonzero.
R4: WHEN every probe passes, THEN write a timestamped receipt under `.tmp/satna-feature-review`.
CLOSED: Reinstalling/re-registering NSSM was rejected because it removes and recreates the service; restarting the verified registration is sufficient.
Preconditions: Run from an elevated PowerShell session; installed service, source, Python environment, and FastMCP client exist at the fixed paths below.
Failure modes: elevation, registration mismatch, service startup, health, MCP call, or assertion failure exits nonzero with the failing stage.
#>
$ErrorActionPreference = 'Stop'

$serviceName = 'specs-mcp'
$serviceExe = 'C:\Users\user\.pi\bin\nssm.exe'
$pythonExe = 'F:\Python\mcp\specs\Scripts\python.exe'
$sourcePath = 'C:\Users\user\.mcp\specs\specs_mcp.py'
$workingDirectory = 'C:\Users\user\.mcp\specs'
$healthUrl = 'http://127.0.0.1:8057/health'
$mcpUrl = 'http://127.0.0.1:8057/mcp'
$receiptDirectory = 'C:\Users\user\.harness\.tmp\satna-feature-review'

# Spec layer: behavioral; the script restarts one registered service, then verifies its live MCP contract.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from PowerShell opened with Run as administrator.'
}

foreach ($requiredPath in @($serviceExe, $pythonExe, $sourcePath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file is missing: $requiredPath"
    }
}
if (-not (Test-Path -LiteralPath $workingDirectory -PathType Container)) {
    throw "Registered working directory is missing: $workingDirectory"
}

$service = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
if (-not $service -or $service.PathName -notlike '*nssm.exe*') {
    throw "Expected the existing NSSM service '$serviceName'; registration was not changed."
}
$parametersKey = "HKLM:\SYSTEM\CurrentControlSet\Services\$serviceName\Parameters"
$registered = Get-ItemProperty -LiteralPath $parametersKey
if ($registered.Application -ne $pythonExe -or
    $registered.AppParameters -ne $sourcePath -or
    $registered.AppDirectory -ne $workingDirectory) {
    throw "Service registration does not match the verified install; refusing to restart '$serviceName'."
}

$sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
Write-Host "Restarting $serviceName (registered source SHA256 $sourceHash)..."
Restart-Service -Name $serviceName -Force

$deadline = [DateTime]::UtcNow.AddSeconds(45)
$health = $null
while ([DateTime]::UtcNow -lt $deadline) {
    $service = Get-Service -Name $serviceName
    if ($service.Status -eq 'Running') {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($health -and $health.status -eq 'ok') { break }
    }
    Start-Sleep -Milliseconds 750
}
if (-not $health -or $health.status -ne 'ok') {
    throw "Service did not pass $healthUrl health check within 45 seconds."
}

$probeScript = @'
import asyncio, json
from fastmcp import Client

URL = "http://127.0.0.1:8057/mcp"
CASES = [
    {
        "name": "prefix IDs do not count",
        "arguments": {"spec_text": "REQ-10", "design_text": "REQ-100", "tasks_text": "Task #14: REQ-100"},
        "expected": {"design_coverage": "0/1", "task_coverage": "0/1", "orphaned_tasks": ["Task #14"]},
    },
    {
        "name": "exact IDs count only inside task blocks",
        "arguments": {"spec_text": "REQ-10 REQ-20", "design_text": "REQ-10 REQ-20", "tasks_text": "Task #14: REQ-10\nTask #15: no requirement\nTask #16: REQ-20"},
        "expected": {"design_coverage": "2/2", "task_coverage": "2/2", "orphaned_tasks": ["Task #15"]},
    },
]

async def main():
    output = []
    async with Client(URL) as client:
        tools = await client.list_tools()
        if "cross_analyze" not in {tool.name for tool in tools}:
            raise AssertionError("live MCP catalog does not expose cross_analyze")
        for case in CASES:
            response = await client.call_tool("cross_analyze", case["arguments"])
            text_blocks = [item.text for item in response.content if hasattr(item, "text")]
            if len(text_blocks) != 1:
                raise AssertionError(f"{case['name']}: expected one text result, got {len(text_blocks)}")
            actual = json.loads(text_blocks[0])
            for key, expected in case["expected"].items():
                if actual.get(key) != expected:
                    raise AssertionError(f"{case['name']}: {key} expected {expected!r}, got {actual.get(key)!r}")
            output.append({"name": case["name"], "result": actual, "passed": True})
    print(json.dumps({"probes": output}, separators=(",", ":")))

asyncio.run(main())
'@
$probePath = Join-Path $env:TEMP ("specs-mcp-probe-{0}.py" -f [guid]::NewGuid().ToString('N'))
Set-Content -LiteralPath $probePath -Value $probeScript -Encoding utf8
$probeOutput = & $pythonExe $probePath
if ($LASTEXITCODE -ne 0) {
    throw "Live MCP behavior probes failed with exit code $LASTEXITCODE."
}
$probeReport = ($probeOutput -join "`n") | ConvertFrom-Json
Remove-Item -LiteralPath $probePath -Force

$service = Get-Service -Name $serviceName
$serviceDetails = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
$receipt = [ordered]@{
    verifiedAt = (Get-Date).ToString('o')
    service = $serviceName
    status = $service.Status.ToString()
    processId = $serviceDetails.ProcessId
    health = $health
    source = $sourcePath
    sourceSha256 = $sourceHash
    probes = $probeReport.probes
}
New-Item -ItemType Directory -Path $receiptDirectory -Force | Out-Null
$receiptPath = Join-Path $receiptDirectory ("admin-restart-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding utf8

Write-Host "PASS: service healthy and both live MCP probes passed."
Write-Host "Receipt: $receiptPath"
