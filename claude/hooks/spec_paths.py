#!/usr/bin/env python3
"""Shared filesystem contract for the spec-driven gate.

Thesis
------
`spec_gate.py` (the wall) and `spec_state.py` (the reporter and the state
machine) must agree on exactly one thing: where the spec tree is and what it
says. Two copies of that logic would drift, and a gate that disagrees with the
status line it prints is worse than no gate -- you would stop trusting both.
So the resolution lives here once, and both import it.

Layout (flat, two tiers -- Kiro-faithful; there is no epic tier)
---------------------------------------------------------------
    <root>/.spec/
        ACTIVE                  one line: the current feature name
        BYPASS                  presence disarms the gate entirely
        steering/               project-wide tier
            product.md  tech.md  structure.md
        specs/<feature>/
            requirements.md     feature lane (EARS, via the `spec` skill)
            bugfix.md           bugfix lane (current/expected/unchanged)
            design.md
            tasks.md
            state.json          the gate's source of truth

Contract
--------
Require   - nothing. Every function tolerates a missing or malformed tree.
Guarantee - `find_spec_root` returns an existing `.spec` directory or None;
            `load_state` returns a dict or None; never raises on bad input.
Maintain  - no writes. This module is read-only so the gate can never mutate
            the state it is judging.
Assert    - `PHASES` is ordered; `next_phase` and approval checks derive from
            that order rather than restating it, so the sequence is stated once.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from typing import Any

# Ordered. Everything about sequencing derives from this list.
PHASES = ["requirements", "design", "tasks", "implement"]

# The bugfix lane swaps the first artifact only; design/tasks are identical.
FIRST_ARTIFACT = {"feature": "requirements.md", "bugfix": "bugfix.md"}

# The document each phase must leave behind before it may be left. This is what
# makes the canonical spec shape (Kiro's requirements/design/tasks triad) an
# enforced contract rather than a naming convention: `advance` consults it, so a
# phase with a missing or placeholder artifact cannot be walked past.
#
# `implement` is absent deliberately -- it is the terminal phase and its output
# is the code itself, which the gate is busy unlocking rather than demanding.
ARTIFACT_FOR_PHASE = {
    "requirements": "requirements.md",
    "design": "design.md",
    "tasks": "tasks.md",
}

# Paths the gate never blocks. Without these the tree deadlocks: you could not
# write the spec that unlocks the repo. `state.json` is deliberately absent --
# see `is_exempt`.
EXEMPT_GLOBS = [
    "*/.spec/*",
    "*/.claude/*",
    "*/.git/*",
    "*.md",
    "*.txt",
    "*/.gitignore",
]


def norm(path: str) -> str:
    """Forward-slash form, for glob matching that behaves the same on Windows."""
    return str(path).replace("\\", "/")


def find_spec_root(start: str) -> str | None:
    """Walk up from `start` looking for a `.spec` directory.

    Returns the `.spec` path itself, or None if the repo is not armed. Walking
    up (rather than checking only cwd) matters because Claude Code's cwd can be
    a subdirectory of the repo root.
    """
    try:
        current = os.path.abspath(start)
    except Exception:
        return None

    while True:
        candidate = os.path.join(current, ".spec")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def is_bypassed(spec_root: str) -> bool:
    """True when the operator has consciously disarmed the gate.

    Two hatches, both deliberate and both visible: a BYPASS file in the tree, or
    SPEC_GATE=off in the environment. The gate exists to stop drift, not to trap
    someone who has decided to move fast on purpose.
    """
    if os.environ.get("SPEC_GATE", "").strip().lower() in {"off", "0", "false"}:
        return True
    return os.path.isfile(os.path.join(spec_root, "BYPASS"))


def is_exempt(path: str) -> bool:
    """True for paths the gate must never block.

    Two carve-outs from the `.spec/` exemption, both for the same reason: they
    are the gate's own authority, and a wall the model can edit is decorative.

    - `state.json` -- approvals. Writable means the model approves its own phases.
    - `spec.db`    -- the record store. Writable means ids, bindings and gate
      results can be rewritten in place, so `render` would faithfully reproduce a
      forged history. It is *not* covered by the `*.md`/`*.txt` prose exemption
      (it is binary), but it does sit under `*/.spec/*`, so the block must be
      explicit. Every mutation routes through `spec_store.py`.

    Known hole, recorded rather than papered over: `Bash` is not gated for
    writes, so `sqlite3 .spec/spec.db ...` bypasses this. See
    `memory-bank/activeContext.md:3742-3745`.
    """
    if not path:
        return True                      # nothing to judge -> do not block
    p = norm(path)
    if os.path.basename(p) in {"state.json", "spec.db"}:
        return False
    return any(fnmatch.fnmatch(p, g) for g in EXEMPT_GLOBS)


def specs_dir(spec_root: str) -> str:
    return os.path.join(spec_root, "specs")


def list_specs(spec_root: str) -> list[str]:
    """Feature names that have a state.json, sorted. Empty on any error."""
    base = specs_dir(spec_root)
    try:
        return sorted(
            name
            for name in os.listdir(base)
            if os.path.isfile(os.path.join(base, name, "state.json"))
        )
    except OSError:
        return []


def state_path(spec_root: str, feature: str) -> str:
    return os.path.join(specs_dir(spec_root), feature, "state.json")


def load_state(spec_root: str, feature: str) -> dict[str, Any] | None:
    """Parse one spec's state.json, or None if missing/corrupt."""
    try:
        with open(state_path(spec_root, feature), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def read_active(spec_root: str) -> str | None:
    """The feature named in ACTIVE, if that spec actually exists."""
    try:
        with open(os.path.join(spec_root, "ACTIVE"), encoding="utf-8") as fh:
            name = fh.read().strip()
    except OSError:
        return None
    if not name:
        return None
    return name if load_state(spec_root, name) else None


def resolve_active(spec_root: str) -> tuple[str | None, str | None]:
    """Determine which spec governs this edit.

    Returns (feature, error). Falls back to sole-candidate inference when ACTIVE
    is absent but exactly one spec has reached `implement` -- the unambiguous
    case, where refusing would be pedantry. Two or more implementable specs is
    genuinely ambiguous and must not be guessed: picking one would silently
    authorize edits against the wrong scope.
    """
    active = read_active(spec_root)
    if active:
        return active, None

    names = list_specs(spec_root)
    if not names:
        return None, "no specs exist yet"

    ready = [n for n in names if (load_state(spec_root, n) or {}).get("phase") == "implement"]
    if len(ready) == 1:
        return ready[0], None
    if len(ready) > 1:
        return None, "ACTIVE is unset and several specs are implementable: " + ", ".join(ready)
    return None, "ACTIVE is unset and no spec has reached the implement phase"


def approved_through(state: dict[str, Any]) -> list[str]:
    """Phases with a truthy approval stamp, in PHASES order."""
    approvals = state.get("approvals") or {}
    if not isinstance(approvals, dict):
        return []
    return [p for p in PHASES if approvals.get(p)]


def next_phase(current: str) -> str | None:
    """The phase after `current`, or None at the end of the sequence."""
    try:
        return PHASES[PHASES.index(current) + 1]
    except (ValueError, IndexError):
        return None


def artifact_for(phase: str, kind: str = "feature") -> str | None:
    """The document `phase` owes, honouring the bugfix lane's first-artifact swap.

    Returns None for phases that owe nothing (`implement`, or anything unknown).
    """
    if phase == PHASES[0]:
        return FIRST_ARTIFACT.get(kind or "feature", FIRST_ARTIFACT["feature"])
    return ARTIFACT_FOR_PHASE.get(phase)


def missing_artifacts(spec_root: str, feature: str, state: dict[str, Any]) -> list[str]:
    """Artifacts the spec owes for every phase up to and including its current one.

    Checks the whole prefix rather than just the current phase: a spec advanced
    while the gate was bypassed can otherwise sit at `tasks` with no
    requirements.md and nothing would ever notice. A file that exists but is
    empty or still placeholder boilerplate counts as missing -- `advance` must
    not be satisfiable by `touch`.

    For the DB-backed artifacts the row count is authoritative, not the text:
    `requirements.md` is a rendered view, so hand-written prose in it proves
    nothing about whether any requirement was actually recorded.
    """
    phase = state.get("phase") or PHASES[0]
    kind = state.get("kind") or "feature"
    try:
        upto = PHASES.index(phase)
    except ValueError:
        return []

    missing: list[str] = []
    for p in PHASES[: upto + 1]:
        name = artifact_for(p, kind)
        if not name:
            continue
        path = os.path.join(specs_dir(spec_root), feature, name)
        try:
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
        except OSError:
            missing.append(name)
            continue
        if is_stub_artifact(body):
            missing.append(name)
            continue
        table = _ROW_BACKED.get(name)
        if table and _row_count(spec_root, feature, table) == 0:
            missing.append(name)
    return missing


# Artifacts that are rendered views of a DB table rather than authored prose.
_ROW_BACKED = {"requirements.md": "requirements", "tasks.md": "tasks"}


def _row_count(spec_root: str, feature: str, table: str) -> int:
    """Rows recorded for `feature` in `table`, or -1 when unknowable.

    Returns -1 rather than 0 when the DB is absent or unreadable so a missing
    store degrades to the text check instead of declaring every artifact
    missing and wedging every spec on the machine.

    `spec_store` is imported lazily: it imports this module at load time, so a
    module-level import here would be circular.
    """
    try:
        import spec_store  # noqa: PLC0415 -- circular at module scope
        conn = spec_store.connect(spec_root, create=False)
        if conn is None:
            return -1
        with conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE feature = ?",  # noqa: S608 -- fixed literals
                (feature,),
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return -1


# EARS (Easy Approach to Requirements Syntax). The value is not the ceremony --
# it is that "the system should be fast" cannot be written in it, so the shape
# itself rejects the unfalsifiable requirements that cause circular rework.
EARS_PATTERNS = [
    # WHEN <trigger>, THE <system> SHALL <response>   (and IF/WHILE/WHERE)
    re.compile(r"^\s*(WHEN|IF|WHILE|WHERE)\b.+?\bTHE\b.+?\bSHALL\b.+", re.IGNORECASE),
    # Ubiquitous: THE <system> SHALL <response>
    re.compile(r"^\s*THE\b.+?\bSHALL\b.+", re.IGNORECASE),
]


def ears_violations(text: str) -> list[str]:
    """Requirement lines in `text` that are not valid EARS, in file order.

    Only bullet/numbered lines are judged: prose, headings, code fences and
    tables are scaffolding, not requirements. Returns the offending lines
    verbatim so the caller can quote them back.
    """
    bullet = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
    out: list[str] = []
    fenced = False
    for raw in (text or "").splitlines():
        if raw.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = bullet.match(raw)
        if not m:
            continue
        claim = m.group(1).strip()
        if not claim or claim.startswith("["):  # checklist scaffolding
            continue
        if not any(p.match(claim) for p in EARS_PATTERNS):
            out.append(claim)
    return out


# ---------------------------------------------------------------- steering
#
# Steering is the project-wide tier: context every spec inherits. Kiro loads it
# into every interaction by default, and that default is the whole point -- a
# steering doc nobody reads is just a file. Scaffolding it without loading it is
# the same "prose instead of enforcement" failure the gate exists to fix.
#
# Inclusion modes follow Kiro's, declared in YAML front matter that must be the
# very first thing in the file:
#
#     always     (default) injected every turn
#     fileMatch  injected when a file matching `fileMatchPattern` is read
#     manual     injected only when the prompt names it as #<stem>
#
# Kiro's fourth mode, `auto` (description-matched), is NOT implemented: it needs
# a model judgement call, and a mode that silently behaves like `manual` would be
# worse than one that is absent. It is treated as `manual` and reported as such.

STEERING_MODES = {"always", "fileMatch", "manual", "auto"}

# Injecting steering costs tokens on every single turn. Cap the total so a
# runaway steering doc degrades context instead of destroying it.
STEERING_BUDGET = 8000


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split leading `---` YAML front matter from the body.

    Deliberately a tiny parser rather than a yaml dependency: it handles the
    scalar and inline-list forms these files use, and anything more exotic is a
    sign the steering doc is doing too much. Returns ({}, text) when absent.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text

    meta: dict[str, Any] = {}
    for raw in lines[1:end]:
        if ":" not in raw or raw.strip().startswith("#"):
            continue
        key, _, value = raw.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value.strip("\"'")
    return meta, "\n".join(lines[end + 1:]).lstrip("\n")


def is_placeholder(body: str) -> bool:
    """True when a steering doc has no prose a model could act on.

    Strips headings and HTML comments and asks whether anything survives. The
    naive version -- "does the body start with a comment" -- missed the exact
    shape `init` writes (`# Product` then a hint comment), so untouched stubs
    were injected into every turn. Steering that is mostly filler teaches the
    model to skim the steering block, which is worse than shipping none.
    """
    stripped = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    stripped = re.sub(r"^\s*#+.*$", "", stripped, flags=re.MULTILINE)
    return not stripped.strip()


_FILLER = re.compile(
    r"^[\s>*\-+\d.)\[\]xX]*\(?(todo|tbd|t\.b\.d\.|fixme|xxx|placeholder|n/?a|none|fill in|coming soon)\b[\s\S]{0,40}?\)?[.!]*$",
    re.IGNORECASE,
)

# What `spec_store.render_*` emits for an empty table. These carry no filler
# token, so `_FILLER` reads them as genuine prose and a spec with zero rows
# advanced. The authoritative check is the row count in `missing_artifacts`;
# this is the fallback for when the artifact is judged from its body alone.
_EMPTY_REGION = re.compile(
    r"^_No (requirements|tasks|properties) recorded\._$",
    re.IGNORECASE,
)


def is_stub_artifact(body: str) -> bool:
    """True when a spec artifact has no content an approver could review.

    Distinct from `is_placeholder`, which answers a narrower question for
    steering injection (headings + comments only). Artifacts fail a different
    way: `init` and models alike leave `TODO` / `TBD` / `(placeholder)` under a
    real heading, which survives the steering test and advanced the phase.

    Only *lines that are entirely filler* are dropped, so a genuine document
    that happens to contain one TODO among real prose still counts as content.

    Generated regions are also dropped when empty: `requirements.md` and
    `tasks.md` are read-views of the DB, and their empty rendering
    (`_No requirements recorded._`) contains no filler token, so without this
    a spec with zero rows read as reviewable content.
    """
    stripped = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    stripped = re.sub(r"^\s*#+.*$", "", stripped, flags=re.MULTILINE)
    survivors = [
        ln for ln in stripped.splitlines()
        if ln.strip()
        and not _FILLER.match(ln.strip())
        and not _EMPTY_REGION.match(ln.strip())
    ]
    return not survivors


def load_steering(spec_root: str) -> list[dict[str, Any]]:
    """Every steering doc with its inclusion mode resolved.

    Order is alphabetical by filename so injection is deterministic: the same
    tree must produce the same context every time, or debugging what the model
    saw becomes guesswork.
    """
    base = os.path.join(spec_root, "steering")
    try:
        names = sorted(n for n in os.listdir(base) if n.endswith(".md"))
    except OSError:
        return []

    docs = []
    for name in names:
        try:
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            continue
        meta, body = parse_frontmatter(raw)

        # `always` stays the default for a doc that declares nothing. Defaulting
        # to `manual` instead would silently stop injecting every doc written
        # before frontmatter existed -- no error, no diff, just a model that
        # quietly knows less. Injecting too much is visible and correctable;
        # injecting nothing is neither. What we owe the caller is not a
        # different default but an audible one, so record whether the mode was
        # actually chosen or merely fallen into.
        raw_mode = meta.get("inclusion")
        declared = isinstance(raw_mode, str) and raw_mode.strip() != ""
        mode = raw_mode.strip() if declared else "always"
        unknown = mode if declared and mode not in STEERING_MODES else None
        if mode not in STEERING_MODES:
            mode = "always"
        patterns = meta.get("fileMatchPattern") or []
        if isinstance(patterns, str):
            patterns = [patterns]
        docs.append({
            "name": name,
            "stem": name[:-3],
            "inclusion": mode,
            "declared": declared,
            "unknown_mode": unknown,
            "patterns": [p for p in patterns if isinstance(p, str)],
            "body": body.strip(),
            "empty": is_placeholder(body),
        })
    return docs


def glob_variants(g: str) -> list[str]:
    """Forms of `g` to try, so `**/` can span zero directories.

    fnmatch has no `**`: it reads the stars as ordinary wildcards and leaves the
    surrounding slashes as hard requirements, so `src/api/**/*.py` demanded a
    subdirectory and missed `src/api/users.py`. Emitting a `/**/`-collapsed
    variant restores the meaning people expect from the pattern.
    """
    forms = {g}
    if "/**/" in g:
        forms.add(g.replace("/**/", "/"))
    if g.startswith("**/"):
        forms.add(g[3:])
    return sorted(forms)


def steering_matches_path(doc: dict[str, Any], path: str) -> bool:
    """True when a fileMatch doc's patterns cover `path`.

    Patterns are relative to the project, paths arriving from hooks are
    absolute, so each form is also tried with a `*/` prefix.
    """
    if doc.get("inclusion") != "fileMatch" or not doc.get("patterns"):
        return False
    p = norm(path)
    for raw in doc["patterns"]:
        for g in glob_variants(norm(raw)):
            if fnmatch.fnmatch(p, g) or fnmatch.fnmatch(p, "*/" + g.lstrip("/")):
                return True
    return False


def render_steering(docs: list[dict[str, Any]], budget: int = STEERING_BUDGET) -> str:
    """Concatenate steering bodies under a hard character budget.

    Truncation is reported inline rather than silently, because steering the
    model half-read is worse than steering it knows was cut.
    """
    out, used = [], 0
    for d in docs:
        if d["empty"]:
            continue
        block = f"### {d['stem']}\n{d['body']}"
        if used + len(block) > budget:
            out.append(f"[steering truncated: {d['stem']} and later docs omitted, "
                       f"{budget}-char budget reached]")
            break
        out.append(block)
        used += len(block)
    return "\n\n".join(out)


def in_scope(path: str, state: dict[str, Any]) -> bool:
    """True when `path` falls inside the spec's declared scope.

    An absent or empty `scope` means unrestricted -- scope is opt-in tightening,
    because you rarely know every file up front. Matching is attempted against
    both the absolute path and its basename so a scope of `src/**/*.py` behaves
    the way it reads.
    """
    scope = state.get("scope")
    if not scope or not isinstance(scope, list):
        return True

    p = norm(path)
    for pattern in scope:
        if not isinstance(pattern, str):
            continue
        g = norm(pattern)
        if fnmatch.fnmatch(p, g) or fnmatch.fnmatch(p, "*/" + g.lstrip("/")):
            return True
    return False
