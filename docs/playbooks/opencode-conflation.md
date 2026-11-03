# OpenCode task conflation

CURRENT 2026-10-25: Harness memory/autoresearch is live; `mem-server` serves the
130-record SQLite store and its scoped HTTP MCP search passes. OpenCode remains on the
weakest served model (`qwen3.5-oc:2b`). Existing no-tool diagnostics completed 3/3
captures, with P2 missing its two-sentence constraint; a full-tools run timed out with
zero recorded tokens. No OpenCode memory-tool arm or conflation verdict exists. The
capture/checker rig is ported under `~/.harness/eval/opencode` and its fixture suite
passed 20/20. Two bounded 2B memory-tool captures timed out at 94s with zero answer
text/tool calls; shared SQLite logical hash matched before/after both. The first logged
33 tools and duplicate external skill names; the second suppressed those scans and
removed the duplicate warnings, but still timed out. A pre-existing OpenCode process
(PID 1309988) remains live, with `qwen3.5-oc:2b` loaded and GPU utilization observed
between 25% and 39%; it was left untouched. No further model run should compete with
that active backend. The private stdio `search_memory` call also timed out at 30s while
tool listing and `audit_memory` succeeded; direct lexical search took 0.44s. Source
handoff: `~/.claude/.tmp/{plan,critique,critique-todo}.md`.

| Stage | Mechanism | Contract |
|---|---|---|
| START | Close stdin and explicitly select the model | [mandatory] R1 |
| SOURCES | Measure context origins without changing shared memory | [mandatory] R2-R3 |
| ISOLATE | Test the weakest served model before adding tool context | [mandatory] R10 |
| PRIVATE-MCP | Exercise memory tools only against a private SQLite snapshot | [mandatory] R11 |
| CAPTURE | Persist native JSON stdout and separate stderr | [mandatory] R4 |
| COMPARE | Codex drives matched plugin/context arms | [mandatory] R5-R6 |
| FIX | Change the earliest evidenced source with backup | [mandatory] R7 |
| RECHECK | Repeat matched configurations in one window | [mandatory] R8 |
| PROMOTE | Port validated artifacts and export through adapter | [mandatory] R9 |

## Requirements

- R1: When starting OpenCode, the driver MUST close stdin before waiting.
  - Given the OpenRouter startup control, When run five times, Then five PONG runs MUST finish.
- R2: When probing memory, the rig MUST leave the shared store unchanged.
  - Given a copied index and source hashes, When three queries run, Then source hashes MUST match.
- R3: When memory embeds queries, its canonical runtime MUST provide its imported dependencies.
  - Given the existing client version, When syncing its lock, Then ollama Client MUST import.
  - The memory-index manifest MUST pin ollama 0.6.1; other runtime manifests MUST remain unchanged.
- R4: If exit, parsing, text, completion, or timeout checks fail, the run MUST be invalid.
  - Given clean/foreign/reasoning/tool fixtures, When parsed, Then only answer text MUST score conflation.
  - Native capture MUST request --thinking and supply neutral session-title metadata.
- R5: When comparing arms, Codex MUST dispatch OpenCode and independently verify outputs.
  - Given arm A, When run, Then memory/todo tool calls MUST be absent.
  - Given arm B, When run, Then at least one memory/todo call MUST establish the axis.
- R6: If source or instruction probes identify a different mechanism, the rig MUST record that attribution.
  - Model/provider transitions and compaction MUST remain visible in historical receipts.
- R7: When changing a component, the change MUST have a mechanism, falsifier and rollback.
  - Shared MCP transport repair MUST preserve tools and database content.
  - Memory dependency installation MUST NOT reindex or promote shared memories.
- R8: When judging improvement, the rig MUST compare interleaved pre/post configurations.
  - Invalid runs MUST NOT count as clean results or model failures.
- R9: When promoting results, the harness MUST preserve raw receipts and validate skill structure.
  - Export MUST use the incumbent adapter; missing adapter support MUST remain explicit work.
- R10: When validating model routing, the driver MUST select the weakest ID in the live LiteLLM model list and record any tool-permission overlay. A no-tool diagnostic MUST NOT count as memory activation or conflation evidence.
- R11: When testing memory-tool delivery without the live SQLite service, the driver MUST use a private SQLite snapshot and a private MCP endpoint; the shared database and service MUST remain unchanged.
  - Given a private snapshot and three tool queries, When the check completes, Then before/after hashes of the shared database MUST match.
- R12: The maintained capture/checker source, their specs and checker fixtures MUST live under `~/.harness/eval/opencode`; scratch copies under `~/.claude/.tmp` are handoff evidence only.
  - Given the ported checker fixtures, When the acceptance suite runs, Then all existing fixture verdicts MUST pass.

## CLOSED

- Port pinning as a startup fix: falsified by RC-04 and the matched RC-24 controls.
- Upstream stream leakage on this battery: six completed streams are clean, RC-25.
- Historical CTP2 drift as 4B proof: quoted drift occurs on 2B, RC-27.
- Successful shared search_memory as read-only: counters/promotions mutate state, RC-29.

## Preconditions and failure modes

Local LiteLLM/Ollama, installed OpenCode/Codex, isolated runtime and writable executor state.
Each test MUST stay below 15 minutes; stop only captured process trees on timeout.
Missing dependency, malformed transport, unproven arm activation and empty output block the next gate.
Validated against spec skill: conditional grammar, atomic requirements, nested acceptance,
ordered stages, closed alternatives, failure paths, source ownership and explicit completion limits.
