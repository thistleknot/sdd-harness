# Session Handoff — `~/.rules` cross-harness canonical instruction source

Repo: `C:\Users\user\.harness` · Mode: handoff

## Objective

Build `~/.rules`: one canonical, harness-agnostic body of agent instructions,
authored once and **projected** into each installed harness's native instruction
surface by a deterministic, idempotent, verifiable sync.

## Why — the finding that shapes everything

Do not re-derive this. It is measured and recorded as Canon #8 / #9.

**1. The two existing instruction files are essentially disjoint.**

| file | lines | bytes |
|---|---|---|
| `C:\Users\user\.claude\CLAUDE.md` | 393 | 21070 |
| `C:\Users\user\.config\opencode\AGENTS.md` | 464 | 28763 |

Sorted-unique line comparison: **3 lines in common**, 295 only-in-CLAUDE,
340 only-in-AGENTS. Zero shared H2 headings.

The obvious confound was checked: both files are uniformly CRLF (CR counts 393
and 465), so the raw comparison was already like-for-like; re-running with CR
stripped, trailing whitespace trimmed and blank lines dropped still yields 3.

**Consequence:** these are not drifted copies of one rule set — they are two
independently authored documents. "Factor out the shared core and project it"
would yield a ~3-line core. **Migration is a human adjudication problem, not an
automated merge.** They *will* contradict each other, and those contradictions
are the real deliverable: they encode undocumented per-harness behaviour.

**2. Four of seven harnesses currently get nothing.**

Config roots present: `.claude`, `.codex`, `.config\opencode`, `.gemini`,
`.pi`, `.kiro`, `.copilot`. Instruction surfaces that actually exist: only the
two above, plus `.gemini\GEMINI.md` at **0 bytes**. Absent entirely:
`.codex\AGENTS.md`, `.pi\AGENTS.md`, `.github\copilot-instructions.md`.

So the majority of this project's value is **coverage extension**, not dedup.
Frame it that way.

## Where the spec lives

All of it is in the specs MCP database — read it there, don't reconstruct it:

- **Requirements #30–#35** — `query_specs(type="requirement")`
- **Decisions #16–#20** — the design
- **Canon #8, #9** — the measurements above
- **Tasks #37–#58** — five phases, `list_tasks(status="planned")`

Rendered Markdown mirrors: `specs/requirements.md`, `specs/design.md`,
`specs/tasks.md`, `specs/canon.md`.

## Design decisions already settled — do not reopen without new evidence

- **#16** Canonical format: `~/.rules/*.md`, one topic per file, YAML
  frontmatter `harnesses: [...]` for scoping and `order: NN` for stable
  concatenation. Matches the 7 existing `.kiro/steering/*.md` files.
- **#17** Projection is render-and-write with hash-skip. **Not** symlinks or
  junctions — each harness gets a *different* subset and filename, so a link
  cannot express it, and Windows symlinks need elevation this repo avoids.
- **#18** A generated banner in each target carries the canonical source hash,
  letting `--check` distinguish clean / stale / hand-edited. Banner must be
  excluded from the hash it carries.
- **#19** Migration is a human-adjudicated disposition ledger. Not auto-merge.
- **#20** Each adapter declares its newline policy; default CRLF for these
  Windows surfaces, because forcing LF would rewrite every line of every target
  and reproduce this repo's recurring whole-file CRLF diffs.

## Start here

Phase 0 (tasks **#42**, **#43**) — cheap, and makes the rest reversible:

1. **#42** Back up the three live surfaces to a timestamped dir; record SHA256
   of each. These hashes prove no content was lost in Phase 1.
2. **#43** Confirm clean git state and commit the baseline first. This repo has
   documented CRLF churn; without a clean baseline the migration diff is
   unreadable.

Then Phase 1 (#44–#47) is the critical path and gates everything downstream.
Extract ledger rows **grouped by enclosing heading, not raw lines** — a bare
line is not a reviewable unit. Exit criterion: zero UNCLASSIFIED rows across all
635 source units.

## Constraints and traps

- **Do not auto-merge CLAUDE.md and AGENTS.md.** Naive concatenation of two
  contradictory documents is the specific failure Req #34 exists to prevent.
- **Do not discard either file** to seed from the other — that silently drops
  ~300 lines of working instruction.
- **Reuse the proven fan-out** in `install.py` / `sync-to-claude.ps1` rather
  than introducing a parallel mechanism.
- **`.kiro` is multi-file** (`steering/*.md`) — it needs its own emit strategy,
  not one concatenated document like the other six.
- **Absent harness config root ⇒ skip, not error** (Req #31).
- **Unknown harness name in frontmatter ⇒ hard error**, so a typo cannot
  quietly drop a rule from every target.
- Verify claims against the filesystem before acting on them. A suspiciously
  clean null result usually means a confound — check for one, as with the CRLF
  test above.

## Definition of done

All seven targets exist, are non-empty, and are byte-stable across two
consecutive syncs; a hand-edited target is reported rather than clobbered; a
scoped rule reaches only its declared harnesses; every one of the 635 source
units is accounted for; and `--check` runs in the hook/CI path so the seven
surfaces cannot drift back apart into the state Canon #8 measured.
