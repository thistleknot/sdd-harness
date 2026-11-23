# Superseded context export and remote sync states — 2026-11-21

## Superseded Claude-only remote sync interpretation

The earlier decision extended `sync-to-remote.ps1` to include `.rules/`,
`.skills/GLOSSARY.md`, `plan-do`, `task-breakdown`, `.harness/constitution.md`,
`.harness/rules/`, and plan-router hook files while leaving `.claude/settings.json`
out because it held Windows paths. That decision was based on remote Claude
missing the plan-do skill and router hook, and on avoiding the 5.3 GB full skill
library. It is superseded by the selected multi-harness contract in R22 and
R43-R46.

## Superseded local context-export preview state — 2026-11-21

The initial preview confirmed `055-context-assembly.md` in all seven declared
client views. The later Codex and Claude apply request exposed prior-owner
drift: Codex expected `043cfe8b…`, current `d01ef946…`; Claude expected
`b60b9115…`, current `1b3ac78d…`. Baseline transfer refused both, preserving
the targets. The remote sync succeeded and delivered the context rule.

## Prior remote Claude sync contract

The prior R22 copied only Claude's vault files plus `constitution.md` and
`GLOSSARY.md`, and explicitly excluded `.rules`, skill packages, and the harness
runtime. The remote check showed `/root/.skills/plan-do/SKILL.md` and
`/root/.claude/hooks/plan_do_route.py` were absent. The operator clarified that
the sync must carry the support files referenced by the Claude setup. R22 now
copies the complete `.rules` set and only the selected runtime dependencies,
including `task-breakdown`, which the `plan-do` skill references;
the 5.3 GB skill store and Windows-specific `settings.json` remain excluded.
