# Project file table — `~/.harness`

<!-- Spec: this file IS the governing artifact for file existence in this repo.
     Task: harness change 2026-08-31 (operator: scratch to .tmp + file table).
     Enforced by: ~/.claude/hooks/file_manifest.py -->

Every file in this project is declared here before it is written. A path with no
row does not get created — `~/.claude/hooks/file_manifest.py` denies the write.

`~/.harness` is the cross-harness layer: the substrate `~/.claude` and the Codex /
opencode / pi adapters all sit on. Rows here are deliberately **broader** than in
`~/.claude`, because most of this tree is one coherent system rather than a
collection of individually-chosen files. A row per subsystem, not per file.

Rows carry the file's name, where it lives, what kind of file it is, what
discipline applies to it, and what it is for. `Name` and `Location` join to form
the glob, with path semantics: `*` stops at a directory separator, `**/` spans
directories, a trailing `/` covers the whole tree. `Discipline` is the rule that
governs how the file is maintained — `hook-contract`, `spec-attribution`,
`vault-source`, `generated`, `named-for-intent`, `machine-state`, `scratch`, or
`none`. Deleting a file deletes
its row — a table describing files that no longer exist protects nothing.

**Scratch is `./.tmp/`** — ungated, gitignored, disposable. Everything that is not
a deliverable goes there. The `.obj` and `chess-deep-q-*.txt` files at the root are
exactly what should have gone there and did not; they carry a `scratch` row so the
gate does not fire on them, and they should be deleted, not preserved.

## The authority layer

| Name | Location | Type | Discipline | Intent |
|---|---|---|---|---|
| constitution.md | / | docs | none | Immutable articles. Amended only by the process it names. |
| harness.json | / | config | none | Which adapters exist and where their surfaces land. |
| manifest.toml | / | config | none | Package manifest for distributing the harness. |
| tiers.toml | / | config | none | Model ladder: which tier gets which role. |
| prompt-rules.md | / | docs | none | Rules injected into the prompt across all harnesses. |
| prompt.md | / | docs | none | Working prompt scratchpad the operator edits by hand. |
| prompt.txt | / | docs | none | Plain-text mirror of `prompt.md`. |
| *.md | policy/ | docs | none | Named policies referenced by rules (plan mode, and later siblings). |
| ** | instructions/ | docs | none | Per-harness instruction fragments emitted by the adapters. |
| README.md | / | docs | none | What this tree is, for a reader who has never seen it. |

## Spec surface — requirements, design, and the record store

| Name | Location | Type | Discipline | Intent |
|---|---|---|---|---|
| *.md | .specs/ | docs | none | Spec artifacts, including this table. Never gated. |
| requirements.md | / | docs | none | EARS requirements for the harness itself. |
| design.md | / | docs | none | Structural and behavioural design of the harness. |
| tasks.md | / | docs | none | Numbered task catalog; every changed file traces to one. |
| test-plan.md | / | docs | none | What each gate is tested against, and what is deliberately untested. |
| *.py | specs/ | code | spec-attribution | The specs MCP server, its SQLite store, and the renderers. |
| *.md | specs/ | docs | generated | Rendered views of the spec DB. Generated — edit the DB, not these. |
| ** | specs/validators/ | code | spec-attribution | Per-artifact validators the gate runner calls. |
| *.py | specs/adapters/ | code | spec-attribution | Spec-layer adapters: Codex and Copilot front ends of the spec store. |
| .gitignore | specs/ | config | none | Keeps the spec DB's working files out of the vault. |
| ** | specs/dispositions/ | data | generated | Recorded dispositions: what was decided and why. |
| test_*.py | specs/ | test | spec-attribution | Battery for the spec store, gates, and renderers. |
| specs.db | specs/ | data | none | Source of truth for requirements and tasks. Markdown is the view. |
| register-specs-service.cmd | specs/ | config | none | Installs the specs MCP as a service. |
| index.db | / | data | machine-state | Codebase index backing `hooks/codebase_map.py`. |

## Hooks — the part that actually holds

| Name | Location | Type | Discipline | Intent |
|---|---|---|---|---|
| _common.py | hooks/ | code | hook-contract | Payload parsing and fail-open helpers every hook shares. |
| session_resume.py | hooks/ | code | hook-contract | SessionStart: replays the prior session's handoff. |
| session_handoff.py | hooks/ | code | hook-contract | Stop: writes the handoff the next session resumes from. |
| session_end.py | hooks/ | code | hook-contract | SessionEnd: closes the log and stamps the memory bank. |
| pre_compact.py | hooks/ | code | hook-contract | PreCompact: preserves state the summary would drop. |
| codebase_map.py | hooks/ | code | hook-contract | UserPromptSubmit: injects a map of the repo being worked on. |
| security_scan.py | hooks/ | code | hook-contract | PreToolUse: refuses writes that leak secrets. |
| self_review.py | hooks/ | code | hook-contract | Stop: catches TODOs, placeholders, mocks, empty bodies. |
| review_changes.py | hooks/ | code | hook-contract | Stop: summarises the turn's diff for the operator. |
| turn_write_log.py | hooks/ | code | hook-contract | PostToolUse: records every write for the Stop-time audits. |
| test_gen.py | hooks/ | code | hook-contract | PostToolUse: proposes a test for source that shipped without one. |
| convergence.py | hooks/ | code | hook-contract | Detects the same class of error repeating (Law 6). |

## Adapters — one harness, several front ends

| Name | Location | Type | Discipline | Intent |
|---|---|---|---|---|
| adapter.py | / | code | spec-attribution | The adapter interface every front end implements. |
| ** | adapters/ | code | spec-attribution | Per-harness adapters (opencode plugin, pi extension). |
| *.md | .kiro/steering/ | docs | none | Kiro steering: the always-injected context for the Kiro front end. |
| *.json | .kiro/hooks/ | config | none | Kiro hook wiring — the Kiro equivalent of `settings.json`. |
| mcp.json | .copilot/ | config | none | MCP server registrations for the Copilot CLI front end. |
| ** | claude/ | config | vault-source | Rendered `~/.claude` surface. Generated by `sync-to-claude.ps1`. |
| ** | plugin/ | code | spec-attribution | Distributable Claude Code plugin: hooks and skills. |
| ** | agents/ | config | none | Agent definitions rendered into each harness's roster. |
| ** | mcp/ | code | spec-attribution | MCP servers this harness registers. |
| render_agents.py | / | code | spec-attribution | Renders `agents/` into per-harness frontmatter. |
| migrate_rules.py | / | code | spec-attribution | One-shot migration of rules between layouts. |
| setup.py | / | code | spec-attribution | Installs the harness onto a new machine. |

## Evaluation and conformance

| Name | Location | Type | Discipline | Intent |
|---|---|---|---|---|
| ** | eval/ | code | spec-attribution | Harness evals: prompts, configs, scoring, and run drivers. |
| ** | conformance/ | test | spec-attribution | Cross-harness conformance suite: same rule, every front end. |
| *.py | tests/ | test | spec-attribution | Headless conformance runs driving each front end via its own CLI. |
| test_*.py | / | test | spec-attribution | Root-level batteries for the adapter, setup, and CPU router. |
| start_router_cpu.py | / | code | spec-attribution | Starts the local skill-retrieval router on CPU. |

## Operations

| Name | Location | Type | Discipline | Intent |
|---|---|---|---|---|
| *.ps1 | / | config | none | Sync, service, and cleanup scripts. Run by hand, not by hooks. |
| ** | scripts/ | code | spec-attribution | Dispatch and verification helpers called by the scripts above. |
| ** | events/ | data | machine-state | Captured lifecycle events. Machine-managed, never hand-edited. |
| ** | slop-review/ | docs | none | Findings from instruction-surface audits. |
| inspirations.md | / | docs | none | Sources the harness borrowed from, with what was taken. |
| ** | inspirations/ | docs | none | Longer notes behind `inspirations.md`. |
| .gitignore | / | config | none | What never enters the vault. |

## Scratch and detritus

| Name | Location | Type | Discipline | Intent |
|---|---|---|---|---|
| ** | .tmp/ | scratch | scratch | Ungated scratch space. Disposable by definition. |
| *.log | specs/ | data | none | Service logs from the specs MCP. Rotate freely. |
| ** | .staging/ | data | none | Rendered artifacts awaiting review before they land. |
| todos.db | .todo/ | data | none | Todo MCP store. Machine-managed. |
| settings.local.json | .claude/ | config | none | Machine-local Claude Code overrides for this repo. |
| .env | / | config | none | Local secrets for the MCP services. Never committed. |
| delete claude-md.md, sync.ps1.retired-bak | / | scratch | scratch | Retired files kept for reference. Delete. |
| *.obj | / | scratch | scratch | Build detritus from a vendored parser. Delete; do not preserve. |
| chess-deep-q-*.txt | / | scratch | scratch | Stray run output. Belongs in `.tmp/`. Delete. |
| ** | references/ | data | none | Cloned reference repos. Large, not ours, gitignored. |
| ** | hookhub-reference/ | data | none | Cloned hook reference. Not ours, gitignored. |
| *.png | / | asset | none | Diagrams referenced from the docs above. |
