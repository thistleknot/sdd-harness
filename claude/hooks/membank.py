#!/usr/bin/env python3
"""SessionStart hook: inject the memory-bank read layer as session context.

Thesis
------
The memory-bank read protocol only works if it fires deterministically. A prose
instruction in CLAUDE.md is model-discretionary and gets skipped; a harness hook
does not. This script owns the READ side; CLAUDE.md owns the WRITE policy.

Why Python and not PowerShell
-----------------------------
Claude Code runs hook command strings through a POSIX-ish shell on this box.
That chain ate two dependencies in a row: Windows backslashes in the command
path were stripped (`C:\\Users\\...` -> `C:Usersuser...`, so the script was never
found), and `pwsh` resolves to a WindowsApps execution-alias stub that is
unreliable from non-interactive contexts. `python` is a real executable on PATH.
Invoke as: `python C:/Users/user/.claude/hooks/membank.py` (forward slashes).

Contract
--------
Require   - nothing. A missing memory bank is a valid state, not an error.
Guarantee - writes a bounded context block to stdout: MEMORY.md index, the
            global six-file layer, and the repo-local layer + last_session.md
            when cwd resolves to a git repo that has a bank under projects/.
Maintain  - total output stays under TOTAL; section ceilings sit below it to
            leave room for the unbudgeted headers. Ceilings are cumulative, so
            the global layer can never
            starve the repo layer (the more actionable half). Volatile logs are
            excerpted tail-first so the newest entries survive; stable docs
            head-first so the thesis survives. This hook must never re-create
            the context bloat it was written to replace.
Assert    - missing canonical files are named MISSING, never silently dropped.
            A non-repo cwd says so rather than implying a global-only bank is
            the whole picture.

Failure modes
-------------
- No memory-bank dir -> one NOTE line, exit 0. Never blocks a session.
- git absent / not a repo -> global layer only, stated explicitly.
- Repo has no bank -> foreign-repo guard message, no bank created.
- Any unexpected exception -> one NOTE line, exit 0. A broken hook must not
  break the session.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Memory-bank content contains non-cp1252 characters (>=, arrows, em dashes) and
# Windows consoles default to cp1252, which raises UnicodeEncodeError mid-write.
# Reconfigure before any output; errors='replace' so an exotic glyph degrades to
# '?' rather than aborting the whole injection.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# TOTAL is the real contract. Fixed headers and the foreign-repo guard print
# outside the budgeted path, so the section ceilings are set below TOTAL to leave
# room for them -- otherwise the script overruns the cap it advertises.
TOTAL = 6000
HEADER_RESERVE = 450
BUDGET = TOTAL - HEADER_RESERVE

CEIL_INDEX = 900
CEIL_GLOBAL = 3000
CEIL_REPO = BUDGET

CANON = [
    "projectbrief",
    "productContext",
    "activeContext",
    "systemPatterns",
    "techContext",
    "progress",
]
# Append-only logs: the newest entries are the load-bearing ones.
VOLATILE = {"activeContext", "progress", "last_session"}

_spent = 0
_ceiling = BUDGET


def emit(text: str) -> None:
    """Write to stdout, charged against the current section ceiling.

    Ceilings are cumulative caps on total spend, not independent pools -- a
    single shared pool let the global layer consume everything before the repo
    layer was reached.
    """
    global _spent
    if _spent >= _ceiling:
        return
    room = _ceiling - _spent
    if len(text) > room:
        text = text[:room] + "\n[...truncated at budget]"
    _spent += len(text)
    sys.stdout.write(text + "\n")


def excerpt(path: Path, max_chars: int, tail_biased: bool) -> str | None:
    """Bounded excerpt of one file, or None when the file is absent.

    None is distinct from '' so the caller can report MISSING rather than
    silently emitting an empty section.
    """
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(unreadable)"
    if not raw.strip():
        return "(empty)"
    raw = raw.rstrip()
    if len(raw) <= max_chars:
        return raw
    if tail_biased:
        return "[...earlier entries omitted]\n" + raw[-max_chars:].lstrip()
    return raw[:max_chars].rstrip() + "\n[...truncated]"


def emit_layer(directory: Path, names: list[str], label: str) -> None:
    """Emit one six-file layer, dividing remaining room across files still due."""
    emit(f"\n### {label}")
    remaining = len(names)
    for name in names:
        share = max(200, (_ceiling - _spent) // max(1, remaining))
        per_file = min(share, 900)
        body = excerpt(directory / f"{name}.md", per_file, name in VOLATILE)
        if body is None:
            emit(f"\n**{name}.md** - MISSING ({directory / (name + '.md')})")
        else:
            emit(f"\n**{name}.md**\n{body}")
        remaining -= 1


def git_root() -> str | None:
    """Repo root for cwd, or None when git is absent or cwd is not a repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    root = out.stdout.strip()
    return root if out.returncode == 0 and root else None


def main() -> int:
    global _ceiling

    root = Path(os.path.expanduser("~")) / "memory-bank"
    if not root.is_dir():
        print(f"NOTE: no memory bank at {root} - skipping memory-bank bootstrap.")
        return 0

    print("## Memory bank (SessionStart, read layer)")
    print("Write policy lives in CLAUDE.md. Full protocol: skill `memory-bank`.")

    _ceiling = CEIL_INDEX
    index = excerpt(root / "MEMORY.md", 1200, tail_biased=False)
    if index is not None:
        emit(f"\n### Topical index (MEMORY.md)\n{index}")

    _ceiling = CEIL_GLOBAL
    emit_layer(root, CANON, f"Global layer ({root})")

    _ceiling = CEIL_REPO
    repo = git_root()
    if repo is None:
        print("\n### Repo layer\nNot inside a git repository - global layer only.")
    else:
        name = Path(repo).name
        local = root / "projects" / name
        if local.is_dir():
            emit_layer(local, CANON + ["last_session"], f"Repo layer: {name} ({local})")
        else:
            # Foreign-repo guard: absence of a project dir is the signal NOT to
            # apply the skills-repo protocol here. Do not create one unprompted.
            print("\n### Repo layer")
            print(f"Repo `{name}` has no memory bank at {local}.")
            print(
                "Foreign-repo guard: use this workspace's own instructions. "
                "Do not create a bank unless asked."
            )

    if _spent >= BUDGET:
        print(f"\n[TRUNCATED at {BUDGET}-char budget - read files directly if more is needed.]")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a broken hook must never break the session
        print(f"NOTE: memory-bank hook failed ({type(exc).__name__}: {exc}) - continuing.")
        sys.exit(0)
