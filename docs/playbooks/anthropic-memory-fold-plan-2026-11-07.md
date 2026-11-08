# Fold the Anthropic "components of agent memory" article into the harness

CURRENT 2026-11-07. Source: https://www.anthropic.com/research/components-of-agent-memory
(published 2026-11-06, read in full). Targets per operator: ~\.mcp (memory-index server —
the conversational-memory MCP), ~\.harness, ~\.skills, ~\.rules.

## Research summary (verdict first)

The harness ALREADY implements the article's architecture core:
- capture/judgment separation: events_store records without opinion; dream.py decides
  what's worth remembering (its own thesis, verbatim match to the article's
  hippocampus/neocortex split).
- transcript foundation: conversation_store volleys (FTS5) + events_store = the
  "transcript search as foundation" the article ends on.
- salience gate: candidate -> approved state machine, confidence cold-start rule,
  recursion guard, idempotent watermarks.

The article adds THREE dream functions we lack + THREE steering laws:
1. VERIFY — re-check existing memories against their source transcripts (Mt. Moon
   demo: a wrong note read by every future session is the failure; the transcript is
   the ground truth that fixes it). dream.py distills NEW memories but never audits
   old ones.
2. PROMOTE — rebuild a small injected top layer (MEMORY.md index, 200 lines/25KB
   budget, demote detail into links). Today the top layer is hand-maintained
   AGENTS.md/steering; nothing regenerates an index from the store.
3. INSTRUCTIONS — goal-tuned dreaming (--instructions FILE): the contract-page
   lesson (41/57 -> 57/57 facts when instructions said what matters). dream.py's
   EXTRACTION_PROMPT is fixed.
Laws: (a) salience — don't store what can be re-read off the screen (413 files/1 badge
vs 9 files/4 badges); store only what exists solely because you worked it out.
(b) steering — say what memory is FOR, not how; fixed rules ("record only failures")
measurably degrade strong models; weaker models need read-before-answer prompts.
(c) representation — wiki+search beats either alone (61 vs 54 vs 53); prune the
Borges map (a representation larger than its source abstracts nothing).

## Chosen approach

Extend dream.py in place (incumbent — no new server, no new store), modes behind
flags, defaults safe: --verify reports only, corrections need --apply and land as
candidate; --promote writes only MEMORY.md (regenerable); --instructions feeds the
existing prompt. Laws go to ~\.rules (numbered cluster, 145 slots between 140
memory-and-continuity and 150 orchestration). Mapping + article numbers go to the
agent-long-term-memory skill (the gate framework that already owns this decision)
and a reference note in docs\references (ddse.md pattern).

## Waves — 6 remain; expected passes M0 1/1, M1 4/4, M2 1/1, M3 1/1, M4 2/2, M5 3/3

- M0: finish dream.py — VERIFY_PROMPT + GOAL_INSTRUCTIONS already in; add
  iter_memories, parse_verdict, cmd_verify, cmd_promote, argparse modes.
- M1: verify — py_compile, --help shows new flags, --verify --dry-run lists
  verifiable memories (no LLM calls), --promote --dry-run then real --promote on
  ~/memory-bank.
- M2: reference note docs\references\anthropic-agent-memory-components.md (the
  Modes docstring already cites this path).
- M3: ~\.rules\145-memory-steering.md — the three laws + correction + cadence.
- M4: agent-long-term-memory skill dated fold section + sync_skills export.
- M5: SpecsDB req+task; receipts; promote trio at close.

## Rejected

- New dreaming service or scheduler task now (anneal task exists; cadence is an open
  question the article itself leaves open — measure first).
- Auto-approving verify corrections (violates the candidate-gate invariant).
- A second memory store or wiki subsystem (skill-wiki + agentic_kg_memory exist;
  the article's wiki findings are guidance for them, not a new build).

## Acceptance

- dream.py compiles; --help lists --verify/--apply/--promote/--instructions.
- --promote produces MEMORY.md within budget on the real store; --verify --dry-run
  enumerates source-session memories without spending LLM calls.
- Laws present in ~\.rules; skill + reference note + SpecsDB records updated; trio
  promoted to docs/playbooks/anthropic-memory-fold-*.

## Deferred (named)

- Live --verify --apply run (per-memory claude -p cost; cadence TBD).
- Dreaming cadence tuning (article's own open question).
- Wiki-build dreaming for agentic_kg_memory (separate gate per skill doctrine).
