#!/usr/bin/env python3
"""PostToolUse: every Python file written must cite what authorised it.

NO GOVERNING SPEC. Basis: operator instruction 2026-08-29 ("all decisions in code
should have cited spec requirement information (spec # and plain english
description)... anytime we update a python file, we run this check on the file").
Promote to a REQ before anything depends on it.

Thesis
------
`rules/spec-attribution.md` already states this law. Nothing enforced it, so it held
exactly as often as the model remembered it. `task_lineage.py` covers the adjacent
question -- is this FILE claimed by a task -- but only at Stop, and only in a
`.spec/`-armed repo. Neither reads what is written INSIDE the file.

This closes that: at the moment a `.py` file is written, check that its header names
its authority. Three outcomes, all of them acceptable except the last:

  1. `Spec: <path> REQ-xxx (plain english)`  -- cited. The operator can go correct it.
  2. `NO GOVERNING SPEC. Basis: ...`         -- honestly unspec'd. Also fine; it is
                                                a declared debt, not a hidden one.
  3. A REQ id with no plain-english gloss    -- flagged. "REQ-J11" alone tells the
                                                operator where to look but not what
                                                to correct, which is half the point.
  4. Nothing at all                          -- flagged. Indistinguishable from
                                                invention.

Fabricated citations are the worst case (`spec-attribution.md`: "an invented citation
is worse than none"). So when the repo IS spec-armed, the cited id is checked against
the actual requirements -- a citation that resolves to nothing is reported as such.

WARN, NEVER BLOCK. PostToolUse runs after the write, so blocking would be theatre;
the useful move is to put the finding in front of the model while it still has the
file open, and let it add the header.

Contract
--------
Require   - stdin carries the PostToolUse payload with tool_input.file_path.
Guarantee - exit 0 always. Prints one finding to stderr per offending file.
Maintain  - fails OPEN and SILENT on every unexpected condition.
Assert    - read-only. It never edits the file it judges.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# How far into the file provenance may sit. Past this it is not a header, it is a
# comment, and the operator will not find it when they go looking.
HEADER_LINES = 60

# Paths that are Python but never carry a spec citation. Tests are claimed by the
# code they test; throwaway and vendored trees are claimed by nobody on purpose.
EXEMPT = ("test_", "conftest.py", "__init__.py", "setup.py")
EXEMPT_DIRS = ("tests/", "test/", "node_modules/", ".venv/", "venv/", "site-packages/",
               "build/", "dist/", "__pycache__/", "migrations/")

REQ_RE = re.compile(r"\b(REQ[-_][A-Za-z0-9][\w.-]*|#\d+)\b")
SPEC_LINE_RE = re.compile(r"^\s*[#*\s]*(?:Spec|Requirement|Task)\s*:\s*(.+)$", re.M | re.I)
NOSPEC_RE = re.compile(r"NO GOVERNING SPEC", re.I)
# Deliberately unanchored: the idiomatic form runs the two together on one line --
# `NO GOVERNING SPEC. Basis: operator instruction 2026-08-29 (...)`. Anchoring this
# to line-start rejected every correctly-attributed file in the tree.
BASIS_RE = re.compile(r"\bBasis\s*:\s*\S", re.I)

# A gloss is prose, not an identifier: >=3 word-ish tokens that are not the id itself.
GLOSS_RE = re.compile(r"[A-Za-z]{3,}")


def _run(args: list[str], cwd: str) -> str:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=10)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def _exempt(path: str) -> bool:
    norm = path.replace("\\", "/")
    base = os.path.basename(norm)
    if base.startswith("test_") or base in EXEMPT:
        return True
    # Segment match, not substring. `d in norm` looked equivalent and was not: it
    # exempted `spectest/`, `latest/`, and `pytest/` via the "test/" entry, which
    # silently disabled the check for any path containing those.
    parts = set(norm.split("/"))
    return any(d.rstrip("/") in parts for d in EXEMPT_DIRS)


def _spec_corpus(root: str) -> str | None:
    """Every requirement id declared in the repo's active spec, as one blob.

    None when the repo is not spec-armed -- in that case a citation cannot be
    validated, only required, and claiming otherwise would be the fabrication this
    hook exists to catch.
    """
    active = os.path.join(root, ".spec", "ACTIVE")
    if not os.path.isfile(active):
        return None
    try:
        with open(active, encoding="utf-8") as f:
            feature = f.read().strip()
        if not feature:
            return None
        blob = []
        d = os.path.join(root, ".spec", "specs", feature)
        for name in os.listdir(d):
            if name.endswith(".md"):
                with open(os.path.join(d, name), encoding="utf-8", errors="replace") as f:
                    blob.append(f.read())
        return "\n".join(blob) if blob else None
    except Exception:
        return None


def _judge(header: str, corpus: str | None) -> tuple[str, str] | None:
    """(code, detail) when the header is deficient; None when it passes."""
    if NOSPEC_RE.search(header):
        if BASIS_RE.search(header):
            return None                       # declared debt, with its reason
        return ("NOBASIS",
                "declares NO GOVERNING SPEC but names no `Basis:` line. State what "
                "you were actually going on (an operator instruction, a ticket, a "
                "conversation) and date it.")

    m = SPEC_LINE_RE.search(header)
    ids = REQ_RE.findall(header)

    if not m and not ids:
        return ("MISSING",
                "carries no provenance. Add a `Spec: <file> REQ-xxx (plain english "
                "description)` line to the module docstring, or say `NO GOVERNING "
                "SPEC.` with a `Basis:` line. Never invent a requirement id.")

    if not ids:
        return ("NOID",
                "names a spec file but no requirement id. `Spec: requirements.md` "
                "tells the operator where to look; `REQ-J11` tells them what to "
                "correct. Cite the requirement, not just the feature.")

    cite = (m.group(1) if m else header)
    words = [w for w in GLOSS_RE.findall(REQ_RE.sub(" ", cite))
             if w.lower() not in ("spec", "md", "requirements", "tasks", "design", "task")]
    if len(words) < 3:
        return ("NOGLOSS",
                "cites %s with no plain-english description. The id alone does not "
                "say what the code was supposed to do, so a wrong implementation of "
                "the right id reads as correct. Add the gloss in parentheses."
                % ids[0])

    if corpus is not None:
        unknown = [i for i in ids if not i.startswith("#") and i not in corpus]
        if unknown:
            return ("UNKNOWN",
                    "cites %s, which appears in NO requirement of the active spec. An "
                    "invented citation is worse than none -- it defeats the one thing "
                    "attribution exists to enable. Either fix the id or add the "
                    "requirement (Article IX: the spec changes first)."
                    % ", ".join(unknown))
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        ti = payload.get("tool_input") or {}
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if not path.endswith(".py") or _exempt(path):
            return 0
        if not os.path.isfile(path):
            return 0

        with open(path, encoding="utf-8", errors="replace") as f:
            header = "".join(f.readline() for _ in range(HEADER_LINES))
        if not header.strip():
            return 0

        cwd = payload.get("cwd") or os.path.dirname(path) or os.getcwd()
        root = _run(["git", "rev-parse", "--show-toplevel"], cwd).strip() or cwd

        verdict = _judge(header, _spec_corpus(root))
        if not verdict:
            return 0
        code, detail = verdict
        print("SPEC-ATTRIBUTION [%s]: %s %s\n  Law: rules/spec-attribution.md -- no "
              "artifact without a named source of guidance, written INTO the artifact."
              % (code, os.path.basename(path), detail), file=sys.stderr)
    except Exception:
        return 0                              # fail open: never trap a turn
    return 0


if __name__ == "__main__":
    sys.exit(main())
