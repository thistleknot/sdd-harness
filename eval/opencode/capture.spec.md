# OpenCode native capture

CURRENT 2026-10-25: The scratch capture instrument is being maintained here. The
default fixed three-prompt battery is unchanged; explicit pure and custom-message
modes are diagnostic-only and must be recorded in each run receipt.

## Structural

def main() -> None: coordinate one bounded subprocess and persist its evidence; CLI owns invocation state.
Constant: PROMPTS — fixed code, explanation and task-abstention battery.
Config: model — explicit provider/model string, varies by run.
Config: agent — optional explicit OpenCode agent, varies by routing diagnostic.
Config: thinking — whether to request reasoning extraction, defaults to true.
Config: timeout — positive seconds below fifteen minutes, varies by run.
Config: overlay — optional OpenCode JSON overlay, varies by arm/configuration.
Config: memory_url — optional isolated HTTP endpoint; a private local MCP command may instead come from overlay.
Config: pure — whether to disable external plugins for an isolated diagnostic; defaults false for arm B.
Config: message — optional one-off diagnostic prompt; fixed PROMPTS remain the default battery.
Constant: PROBE_TITLE — neutral session metadata that avoids automatic title inference.

## Behavioral

Uses: subprocess.Popen — native child handle with closed stdin and separate file streams.
Uses: child.wait — exit code or TimeoutExpired.
Uses: taskkill — captured child-tree termination with diagnostic output.
Uses: checker.check_events — separated answer, reasoning and tool evidence or parse failure.
Input: arm — A or B, string.
Input: prompt — exact battery prompt, integer 1..3.
Initialize: run directory ← caller-supplied unique path.
Load optional overlay; identify any private memory-index command before disabling servers.
Disable every configured MCP server in arm A or an explicitly pure run, except the private memory-index configuration in arm B.
When arm B: use memory_url when supplied; otherwise require the overlay's private local memory-index command.
Select the indexed battery prompt unless a diagnostic message is supplied.
Persist command, model, prompt, pure mode, effective overlay and start time.
When agent is supplied: append `--agent` and its name; when omitted: preserve OpenCode's normal agent routing.
Launch child with stdin DEVNULL and stdout/stderr to different native file handles.
The invocation supplies a fixed title so the model does not also generate session metadata.
When thinking is true: include `--thinking`; when false: omit it.
Persist child PID before waiting.
If deadline expires: taskkill only that captured tree and wait for its exit.
Persist exit, elapsed time and timeout before parsing output.
Run the checker; persist full separated verdict; classify timeouts/nonzero exits invalid.
Print one machine-readable summary row and return a nonzero status for invalid runs.

## Requirements

- R1: Capture MUST NOT use a PowerShell combined-stream redirector.
  - By default, the command MUST request `--thinking` so reasoning events are retained.
- R2: A nonzero exit or timeout MUST NOT be counted as clean output.
- R3: A run MUST NOT resume an existing session or pin its server port.
- R4: Arm A MUST disable plugins and every configured MCP server.
- R5: Arm B MUST preserve the operator's plugins and use a private memory store.
- R6: Native stdout MUST parse with non-empty answer text before this instrument is accepted.
- R7: The source command, PID, raw streams and checker output MUST survive interruption.
- R8: The caller MUST be able to disable thinking per run with `--no-thinking`; the default MUST remain enabled, and the command recorded in `run.json` MUST match the selected mode.
- R9: The caller MAY select an explicit OpenCode agent; when supplied, the command and run metadata MUST record it, and when omitted the default routing MUST remain unchanged.
- R10: When `--pure` is supplied, the command MUST include `--pure`; arm A MUST remain pure by default. For arm B in pure mode, all configured MCP servers except its private memory-index configuration MUST be disabled.
- R11: When `--message` is supplied, the exact text MUST replace the selected prompt and appear in `run.json`; when omitted, the numbered fixed battery prompt MUST be used.
- R12: When arm B omits `--memory-url`, the overlay MUST define `memory-index` as a local MCP command; otherwise capture MUST fail before launching OpenCode.

Validated: explicit external operations, sequential persistence, error exits,
single owned process handle, arm contracts, selectable thinking mode/agent/purity,
and fixed-battery versus diagnostic-message traceability.
CLOSED: inherited stdin (RC-24), combined PowerShell streams (RC-10), random-port theory (RC-04).
