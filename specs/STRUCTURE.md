# Specs Structure

> Source of truth: `specs.db` (SQLite). All `.md` files in this tree are **rendered views** —
> never hand-edit them. Mutations go through the `specs` MCP server (CRUD tools),
> which writes to the DB then regenerates markdown in one pass.

## Taxonomy

```
specs/
├── STRUCTURE.md          # this file (manual, not generated)
├── specs.db              # SQLite source of truth
├── requirements.md       # acceptance criteria — what must be true
├── design.md             # architecture decisions — how it's built
├── tasks.md              # current plan — doing / done / blocked / next
├── settings.md           # hyperparameter anchors with provenance citations
├── canon.md              # settled claims (findings + do-not-retry, verdict-first)
└── dispositions/         # per-experiment detailed writeups
    └── <slug>.md         # evidence, samples, root cause — too long for canon
```

## File Semantics

| File | Maps to | Content style |
|------|---------|---------------|
| `requirements.md` | `requirements` table | MUST/SHOULD statements with testable criteria |
| `design.md` | `decisions` table | Decision records: context → options → chosen → rationale |
| `tasks.md` | `tasks` table | Plan.md equivalent: status, owner, ETA, blockers |
| `settings.md` | `settings` table | Key-value with citation/provenance per entry |
| `canon.md` | `canon` table | Verdict-first: claim → YES/NO → discriminating evidence |
| `dispositions/*.md` | `dispositions` table | Long-form experiment writeups with structured metadata |

## Statuses (tasks)

`planned` → `doing` → `done`
`planned` → `blocked` (with blocker reason)
`doing` → `deferred` (with rationale)
Any → `deprecated` (superseded, with pointer to replacement)

## Render Contract

- `specs_db.py render_all()` regenerates every `.md` from the DB
- Called automatically after every CRUD op via the MCP server
- Markdown is deterministic given the same DB state (no timestamps in render, no randomness)
- Dispositions render one file per row: `dispositions/<slug>.md`

## MCP Tools

| Tool | Purpose |
|------|---------|
| `add_requirement(title, criteria, priority)` | Add acceptance criterion |
| `add_decision(title, context, options, chosen, rationale)` | Record architecture decision |
| `add_task(title, status, details, parent_id)` | Add/update plan item |
| `update_task(id, status, details)` | Transition task state |
| `add_setting(key, value, citation)` | Record hyperparameter anchor |
| `add_canon(claim, verdict, evidence)` | Record settled finding |
| `add_disposition(slug, title, body, tags)` | Record experiment writeup |
| `query_specs(type, status, query)` | Search across all tables |
| `list_tasks(status)` | Filtered task view |
| `render()` | Force re-render all markdown |

## Principles

1. **DB is truth.** Markdown is a view. If they diverge, the DB wins.
2. **One render pass.** Never patch markdown — always full regen.
3. **Append-mostly.** Status transitions, not deletions. History preserved.
4. **Verdict-first.** Canon entries lead with YES/NO, then evidence.
5. **Provenance.** Settings and canon cite where the value came from.
