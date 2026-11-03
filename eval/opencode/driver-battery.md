# Codex drives OpenCode: fixed conflation battery

CURRENT 2026-10-25: This is the canonical driver contract under `~/.harness/eval/opencode`.
The 2B no-tool orchestrator diagnostic completed 3/3 valid captures; P2 missed its
two-sentence requirement. These are routing diagnostics, not conflation evidence.
Source receipts remain under `~/.claude/.tmp/{plan,critique,critique-todo}.md`.

## Roles and immutable inputs

You are Codex, the driver and independent verifier; the outer agent fixes defects.
Executor: OpenCode with litellm/qwen3.5-reasoning-thinking-256k:4b.
Work in C:/Users/user/.harness/eval/opencode.
Use capture.py; its PROMPTS constant owns the exact three battery prompts.
P1 is median code, P2 is a two-sentence binary-search explanation, P3 is task abstention.
checker.py and markers.json are the fixed instrument, validated before live comparison.
Hash capture.py, checker.py and markers.json before the comparison; preserve the hashes.
Do not change prompts, marker rules, model or evaluation between compared configurations.

## Invocation contract

- Call the installed Python executable with capture.py; it invokes the native OpenCode binary.
- capture.py closes stdin, requests JSON, and separates stdout/stderr; reasoning is on by default.
- Keep thinking on for the target 4B battery. For the weakest LiteLLM setup gate
  (`qwen3.5-oc:2b`), pass `--no-thinking`; that model's raw endpoint returned an
  answer without reasoning extraction, while the 2B `--thinking` OpenCode probes
  timed out. This model-setting diagnostic is not 4B comparison data.
- Do not use PowerShell 2>&1, a shell timeout wrapper, port pinning or session continuation.
- The subprocess deadline is 180 seconds by default; only its captured tree may be terminated.
- On Codex exec, add the approved OpenCode writable root:
  -c 'sandbox_workspace_write.writable_roots=["C:/Users/user/.local/share/opencode"]'
- Every run needs a unique output directory; never overwrite or reuse a captured run.

Example arm A invocation (repeat with each prompt and repetition):
    C:/Users/user/py310/Scripts/python.exe -X utf8 -B capture.py --arm A --prompt 1 --out runs/A-P1-R1

The diagnostic arm B may pass `--pure --memory-url` to expose only memory-index on
a private SQLite snapshot; this isolates MCP delivery from plugin/tool context.
The final arm B comparison must use the real plugins and an isolated memory endpoint;
the pure diagnostic is not a replacement for that comparison.
Do not start or stop another person's processes.

## Arm gate, then battery

Arm A: plugins off and every configured MCP server disabled.
Arm B: operator plugins/MCP on, private memory endpoint.
Before the battery, prove B calls search_memory or list_todos, while A calls neither.
If that gate fails, report NOT TESTED and stop; the outer agent must repair the axis.

The intended comparison is two arms x three prompts x two reps = twelve runs.
Interleave arms within prompt/repetition, rather than running one whole arm first.
Measure the first pair and enforce a fourteen-minute total test budget.
If twelve runs cannot fit, reduce to one rep as the original plan permits and report
the exact smaller n; never quietly discard prompts, arms, invalid cells or controls.
If even one complete matched repetition cannot fit, stop and report the measured
latency as a rig defect; do not launch an over-budget battery.

## Independent verification and report

Read run.json, stdout.jsonl, stderr.log and verdict.json for every run.
P1: extract the generated function and compare independently against statistics.median
on unsorted odd/even lists, duplicate values, negative values and floats.
P2: verify sorted input, halving the search interval, and the requested two sentences.
P3: a truthful abstention is correct; foreign task adoption is a false answer.
Markers are leads for raw-text review, not automatic proof of task adoption.
Tool results, reasoning, headers and command text never score as answer conflation.
A timeout, nonzero exit, malformed capture, empty text or missing final stop is invalid.

Report one row per run:
    ARM=... PROMPT=... REP=... EXIT=... VALID=... TEXT_CHARS=... MARKERS=... LEAKS=... TOOLS=... TASK_PASS=...
Then report each invalid cell, quality defect and exact supporting raw line numbers.
Supported: B adopts foreign tasks in more runs than A by more than one.
Killed for this rig: equal adoption counts among complete valid matched cells.
Otherwise: inconclusive; any invalid required cell is NOT TESTED.
The outer agent re-reads every flagged text and two unflagged texts before accepting a verdict.
Do not repair the executor, captured output, independent checks or detector during this run.
