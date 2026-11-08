# Anthropic memory-article fold — work log — CLOSED 2026-11-07

Spec: REQ #74 + task #96. Plan: anthropic-memory-fold-plan-2026-11-07.md (same folder).
Receipts: anthropic-memory-fold-receipts-2026-11-07.md.

- [DONE] M0: dream.py finished — iter_memories, parse_verdict, cmd_verify (25/run bound,
  report-only default, --apply corrections land as candidate), cmd_promote (MEMORY.md,
  200-line/25KB budget, goals section preserved), argparse --verify/--apply/--promote/
  --instructions. Verify: py_compile rc=0, --help shows all four flags.
- [DONE] M1: live checks on ~/memory-bank — verify --dry-run (0 eligible / 45 skipped,
  named as finding), promote --dry-run + real (45/45, 55 lines, 6370 bytes, MEMORY.md
  written).
- [DONE] M2: docs\references\anthropic-agent-memory-components.md — article summary,
  all numbers [empirical:cited], mapping table to the harness stack.
- [DONE] M3: ~\.rules\145-memory-steering.md — salience, steering, prediction,
  correction, hierarchy, representation (6 laws).
- [DONE] M4: agent-long-term-memory skill dated fold section + sync export + mirror
  hash check.
- [DONE] M5: SpecsDB #74/#96; trio promoted to docs/playbooks/anthropic-memory-fold-*;
  .tmp stub left; memory logged.

## Deferred (named, not silent)

- Live --verify --apply run — needs memories carrying source_session (next dream pass)
  and per-memory LLM budget; cadence TBD (article leaves it open too).
- Effectiveness gate: control arms (no-memory / full-context / BM25) before any
  recall/precision claim upgrades the skill from draft.
- Wiki-build dreaming for agentic_kg_memory — separate gate per skill doctrine.
