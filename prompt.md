# Correction: your ~/.skills topology model is stale

You described this layout:

```
~/.skills/                 <- repo root
├── .skills/               <- 159 skill dirs (the corpus)
├── retrieve-skills/
└── AGENTS.md, README.md, ...
```

**That nested `.skills/` directory does not exist on disk.** Verified just now
from `~/.skills`:

```
$ ls -d .skills
ls: cannot access '.skills': No such file or directory

$ ls -d */ | head
active-inference/
adjacent-surface-scan/
agent-governance/
agent-identity/
agentic-design-patterns/
...
```

The corpus has been **flattened one level up**. Skill dirs now live directly at
repo root (`~/.skills/active-inference/SKILL.md`), not at
`~/.skills/.skills/active-inference/SKILL.md`.

## What git currently sees

```
## main...origin/main
 D .skills/active-inference/SKILL.md
 D .skills/adjacent-surface-scan/SKILL.md
 D .skills/agent-governance/SKILL.md
 ... (386 tracked files staged as deleted)
?? active-inference/
?? adjacent-surface-scan/
?? agent-governance/
 ... (161 untracked entries)
?? .mcp.json
?? AGENTS.md.conflict
```

386 deletions + 161 untracked additions = **the same files, moved**. Nothing is
lost. But git has only recorded the delete half, because the new top-level paths
were never `git add`ed.

## Why this matters before anything else

`git push` from `~/.skills` right now would publish a commit that **deletes the
entire skill corpus** from `github.com/thistleknot/skills.git`. The additions
aren't staged, so only the removals go up. Do not push until the tree is
reconciled.

## Requested from you

1. **Confirm which layout is intended** — flat (corpus at repo root, matches
   disk) or nested (`.skills/` subfolder, matches git index). Disk says flat;
   your writeup assumed nested. One of the two has to move.
2. **State how the flattening happened** and whether it was deliberate. If a
   script or a `retrieve-skills` reindex did it, that's the actual root cause
   and it needs naming before we commit the result.
3. **Reconcile before push** — `git add -A` so git pairs the deletes with the
   adds and records renames rather than 386 deletions. Then diff
   `git status --short` to verify the rename count matches.
4. **Explain `AGENTS.md.conflict`** — untracked, sitting next to a tracked
   `AGENTS.md`. Merge artifact? Which one is live?

## Downstream of the correction

Your Option 3 (collapse `~/.claude/skills/retrieve-skills/` and run the router
from the repo copy) may still be right, but the reasoning that got you there was
built on the nested layout and the `discover_skills` exclusion of a `skills/`
subfolder. With the corpus flat at repo root, re-derive: what does
`SKILL_STORE=~/.skills` actually enumerate now, and does the `skills/`/`disabled/`
exclusion still do what you think? Recheck before recommending a CWD change to
the watcher or NSSM service.

One related fix already applied on this side: `~/.skills/gstack/SKILL.md` had
four `~/.claude/skills/gstack/...` references (lines 22, 28, 35, 134) that
silently disabled gstack's self-update check. Those now point at
`~/.skills/gstack/...`. The repo-local `$_ROOT/.claude/skills/...` reference on
line 133 and the relative fallback on line 22 were left alone.
