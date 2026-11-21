# Superseded remote Claude sync contract — 2026-11-21

The prior R22 copied only Claude's vault files plus `constitution.md` and
`GLOSSARY.md`, and explicitly excluded `.rules`, skill packages, and the harness
runtime. The remote check showed `/root/.skills/plan-do/SKILL.md` and
`/root/.claude/hooks/plan_do_route.py` were absent. The operator clarified that
the sync must carry the support files referenced by the Claude setup. R22 now
copies the complete `.rules` set and only the selected runtime dependencies,
including `task-breakdown`, which the `plan-do` skill references;
the 5.3 GB skill store and Windows-specific `settings.json` remain excluded.
