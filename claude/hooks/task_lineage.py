#!/usr/bin/env python3
"""Stop hook: flag source changes that no task in the active spec claims.

Thesis
------
`spec_gate.py` answers "have the phases been approved?" and stops at `implement`.
It does NOT answer "is THIS file in scope?" -- once a spec reaches `implement`,
every write passes, forever, on any file. That is the hole this closes.

The other half of the hole is the tool used. The PreToolUse matcher watches
Edit/Write/NotebookEdit, so a change made by `python patch.py`, `sed -i`, or a
heredoc is invisible to it. This hook reads the FILESYSTEM (`git status`), not the
tool calls, so it sees a change regardless of how it was made.

The rule
--------
Warn when ALL of these hold:

  1. The repo has a `.spec/` with an ACTIVE feature
  2. That feature's state is `implement`
  3. Source files are modified in the working tree
  4. One or more of those files is named by NO task in the feature's `tasks.md`

WARN, NOT BLOCK -- and that asymmetry is deliberate. An empty or fileless task
catalog is the common case in a repo mid-migration, and a hook that made the
session unrecoverable over a missing `_Files:` line would be turned off within the
hour, taking the real signal with it. Exit 0 with the finding on stderr puts the
list in front of the model without trapping the turn.

Deliberately NOT flagged
------------------------
- Repos with no `.spec/`            (ungated, same as spec_gate)
- Specs before `implement`          (spec_gate already owns that case)
- Non-source files: docs, specs, data, notebooks, lockfiles, logs
- Deleted files -- removing dead code is Law 10, not an unspec'd feature

Contract
--------
Require   - stdin carries the Stop payload; git is on PATH.
Guarantee - exit 0 always. Prints a lineage finding to stderr when the rule fires.
Maintain  - fails OPEN and SILENT on every unexpected condition. A lineage checker
            that cries wolf on a parse error trains the reader to ignore it, which
            costs more than the check is worth.
Assert    - never reads or writes anything under .spec/ (a hook that could edit the
            catalog it checks against is not a check).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# Only these extensions are "source" for lineage purposes. Docs and data change for
# a hundred legitimate reasons that no task will ever name, and flagging them is how
# a useful gate becomes noise.
SOURCE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb",
              ".c", ".h", ".cpp", ".hpp", ".cs", ".sh", ".ps1"}

# Paths that are source by extension but never owned by a feature task.
EXEMPT_DIRS = ("tests/", "test/", ".spec/", ".kiro/", "scripts/", "node_modules/",
               ".venv/", "venv/", "build/", "dist/")


def _run(args: list[str], cwd: str) -> str:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=10)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def _repo_root(start: str) -> str | None:
    out = _run(["git", "rev-parse", "--show-toplevel"], start).strip()
    return out or None


def _active_feature(root: str) -> tuple[str, dict] | None:
    """The feature named by .spec/ACTIVE, plus its state. None if not gated."""
    active = os.path.join(root, ".spec", "ACTIVE")
    if not os.path.isfile(active):
        return None
    try:
        with open(active, encoding="utf-8") as f:
            feature = f.read().strip()
        if not feature:
            return None
        with open(os.path.join(root, ".spec", "specs", feature, "state.json"),
                  encoding="utf-8") as f:
            return feature, json.load(f)
    except Exception:
        return None


def _changed_source(root: str) -> list[str]:
    """Modified/added source files in the working tree. Deletions are excluded."""
    # -uall is load-bearing: plain --porcelain collapses an untracked directory to a
    # single '?? src/' entry, so an entire NEW module reads as zero changed files --
    # silently exempting the exact case (fresh unspec'd code) this hook exists for.
    out = _run(["git", "status", "--porcelain", "--untracked-files=all"], root)
    files: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        status, path = line[:2], line[3:].strip().strip('"')
        if "D" in status:
            continue
        if " -> " in path:                      # rename: judge the destination
            path = path.split(" -> ", 1)[1]
        if os.path.splitext(path)[1] not in SOURCE_EXT:
            continue
        if any(path.startswith(d) or ("/" + d) in path for d in EXEMPT_DIRS):
            continue
        files.append(path)
    return files


def _claimed_paths(root: str, feature: str) -> set[str]:
    """Every path token appearing anywhere in the feature's tasks.md.

    Deliberately generous: any path-shaped string counts as a claim, whether it sits
    in a `_Files:` line or in prose. A strict parser would reject real catalogs over
    formatting and teach everyone to distrust the hook.
    """
    p = os.path.join(root, ".spec", "specs", feature, "tasks.md")
    try:
        with open(p, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return set()
    return set(re.findall(r"[\w./\\-]+\.[A-Za-z0-9]{1,4}", text))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    root = _repo_root(cwd)
    if not root:
        return 0

    found = _active_feature(root)
    if not found:
        return 0
    feature, state = found
    if state.get("phase") != "implement":
        return 0                                # spec_gate owns the earlier phases

    changed = _changed_source(root)
    if not changed:
        return 0

    claimed = _claimed_paths(root, feature)
    unclaimed = [f for f in changed
                 if not any(f == c or f.endswith("/" + c) or c.endswith("/" + f)
                            or os.path.basename(f) == os.path.basename(c)
                            for c in claimed)]
    if not unclaimed:
        return 0

    head = ("LINEAGE: %d changed source file(s) are claimed by no task in spec '%s'."
            % (len(unclaimed), feature))
    if not claimed:
        head += ("\n  Its tasks.md names NO files at all -- the spec-to-file catalog is "
                 "empty, so nothing in this repo is traceable to a task. Populating it "
                 "is the next step, not more code.")
    body = "\n".join("    %s" % f for f in sorted(unclaimed)[:25])
    tail = ("\n  Either add the task that owns these (amend the spec first, Article IX), "
            "or say plainly in the reply that they are unclaimed. Do not fold them "
            "silently into the summary.")
    print("%s\n%s%s" % (head, body, tail), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
