#!/usr/bin/env python3
"""Three modes over one file table: no file enters a project without a row.

    (default)    PreToolUse -- denies a write whose path has no row
    --audit      Stop       -- names changed files no row claims (catches Bash)
    --coverage   by hand    -- names files in the repo no row covers
                              (add --all to include gitignored files)

Spec: .specs/file-manifest.md (the manifest itself is the governing artifact)
Task: harness change 2026-08-31 -- operator instruction, two features:
      (1) project scratch space is `./.tmp`, (2) a project file table that every
      write is checked against.

Thesis
------
`spec_gate.py` answers "have the phases been approved?" and `task_lineage.py`
warns after the fact about files no task claims. Neither answers the question the
operator actually asks before a write lands: *is this file supposed to exist at
all, and what is it for?* A repo accretes files nobody chose; the manifest makes
choosing them the precondition for writing them.

The rule
--------
Deny a file-mutating tool call when ALL of these hold:

  1. The project is armed        (a `.spec/` or `.specs/` dir above cwd holds
                                  `file-manifest.md`)
  2. The gate is not bypassed    (no `NOMANIFEST` file, no FILE_MANIFEST=off)
  3. The target is not exempt    (`.tmp/`, `.git/`, the spec tree itself, or a
                                  path outside the project root)
  4. No manifest row matches the target. A row is `Name | Location | Type |
     Discipline | Intent` (REQ #37) and the glob it matches on is Location
     joined to Name; the legacy `Path | Type | Intent` shape still parses.

Two Discipline values are enforced rather than reported. A row marked `read-only`
denies every file-mutating tool (the operator edits such files by hand); a row
marked `append-only` denies Write/NotebookEdit and denies an Edit whose
`new_string` does not begin with its `old_string`. Everything else in DISCIPLINES
is advisory, as before.

Scratch has one address
-----------------------
`.tmp/` at the project root is the ONE always-writable location, and that is the
whole of feature (1). Making the exemption a single directory is what stops the
gate from being annoying: anything genuinely throwaway has an obvious home that
costs nothing, so the only writes that hit the wall are the ones that were about
to become permanent without anyone deciding.

Why deny and not warn
---------------------
The operator asked for confirmation *before* the write. A warning after the fact
is `task_lineage.py`, which already exists; duplicating it would add noise and
close nothing. `--audit` mode covers the Bash-mediated hole the same way
task_lineage does -- filesystem, not tool calls -- and warns there, because at
Stop time the file already exists and blocking cannot un-write it.

Why `--coverage` is a third mode and not a flag on the audit
-----------------------------------------------------------
They answer different questions, and conflating them produces a false negative
that reads like success. `--audit` asks "did anything unclaimed change THIS TURN?"
and is silent on a quiet tree -- which looks identical to "the table covers
everything" when the table may cover almost nothing. `--coverage` asks "what in
the WHOLE repo has no row?" and is the only one that finds a section nobody knew
was there. Run it after authoring or editing a manifest -- a clean audit is not
coverage. It is deliberately not wired to any hook event: it is a whole-repo
question, and asking it every turn would be noise.

What neither mode can see
-------------------------
Both read git. In a whitelist-style repo -- a `.gitignore` of `/*` followed by
exceptions, which is exactly `~/.claude` -- that means they see only the vaulted
surface. A file outside the whitelist is invisible to both, so the audit's
silence there means "nothing git can see", NOT "nothing unclaimed". Measured
2026-08-31: `~/.claude` reported 326 files / 0 uncovered while 7696 files
actually existed, 6986 of them with no row.

`--coverage --all` drops `--exclude-standard` and reports the truth. Use it when
authoring the manifest; use the default when you only care about what ships.

The PreToolUse gate has no such limit -- it judges every path it is handed,
gitignored or not, which is why the gate and not the audit is the wall.

Contract
--------
Require   - stdin carries a PreToolUse payload (gate mode), a Stop payload
            (`--audit`), or any object with a `cwd` (`--coverage`); git on PATH
            for the two filesystem modes.
Guarantee - exits 0 always. Gate mode prints a deny decision when the rule fires;
            `--audit` prints unclaimed paths to stderr; `--coverage` prints a
            one-line tally to stdout, plus the uncovered paths when there are
            any.
Maintain  - fails OPEN and SILENT on every unexpected condition. A manifest gate
            that traps the session on a parse error gets switched off, taking the
            real check with it.
Assert    - never writes anything. A gate that can edit the table it judges
            against is not a gate.
"""
from __future__ import annotations


import json
import os
import re
import subprocess
import sys

MANIFEST_NAME = "file-manifest.md"

# Both spellings, because `spec_paths.py` standardised on `.spec/` while this
# repo already carries `.specs/`. Resolving both costs one loop and avoids a
# migration whose only product would be a rename.
SPEC_DIRS = (".spec", ".specs")

# The scratch address. Feature (1) in one constant.
SCRATCH = ".tmp"

# Never gated, regardless of the manifest. Everything here is either the gate's
# own authority, machine-managed state, or the declared scratch space.
EXEMPT_PREFIXES = (SCRATCH + "/", ".git/", ".spec/", ".specs/", ".playbook/",
                   ".agentpackets/")

# Derived directories: nobody authors a file in one, so demanding a row for it is
# noise that buries the real finding. Matched at any depth, unlike the prefixes
# above -- `specs/__pycache__/x.pyc` is as derived as a top-level one. Without
# this, `--coverage --all` reported 53 "uncovered" files in one subtree that were
# all bytecode.
EXEMPT_SEGMENTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
                   ".benchmarks", "node_modules", ".venv", "venv", ".egg-info"}

# Recognised `Type` values. Not enforced -- an unknown type is reported in the
# deny message rather than rejected, because inventing a category is a cheaper
# error to correct than a blocked session.
TYPES = ("code", "test", "docs", "config", "data", "asset", "scratch")

# Recognised `Discipline` values (REQ #37) ... The first two are ENFORCED by the
# gate, not merely reported: see `discipline_reason`. Everything after them is
# advisory in the same way as TYPES.
DISCIPLINES = ("read-only", "append-only",
               "hook-contract", "spec-attribution", "mirror-from-vault",
               "vault-source", "generated", "named-for-intent", "machine-state",
               "scratch", "none")

# Tools that mutate a file's bytes. A discipline only has an opinion about these.
MUTATING_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# Header vocabulary. The table shape is read off its own header row rather than
# guessed from cell count, so a five-column table and a legacy three-column one
# can sit in the same document (REQ #37).
HEAD_PATH = {"path", "file", "glob"}
HEAD_NAME = {"name", "filename"}
HEAD_LOCATION = {"location", "where", "dir", "directory", "folder"}

# A location cell meaning "the project root", which contributes no path segment.
ROOT_LOCATIONS = {"", "/", ".", "./", "root", "(root)", "-"}


# ------------------------------------------------------------------ locating

def norm(path: str) -> str:
    """Forward-slash form, so glob matching behaves the same on Windows."""
    return str(path).replace("\\", "/")


def find_manifest(start: str):
    """Walk up from `start` for a spec dir containing the manifest.

    Returns (project_root, manifest_path), or None when the project is unarmed.
    Walking up matters because cwd is often a subdirectory of the root.
    """
    try:
        current = os.path.abspath(start)
    except Exception:
        return None
    while True:
        for d in SPEC_DIRS:
            candidate = os.path.join(current, d, MANIFEST_NAME)
            if os.path.isfile(candidate):
                return current, candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def is_bypassed(root: str) -> bool:
    """True when the operator has consciously disarmed the gate.

    Two visible hatches, matching `spec_paths.is_bypassed`: a NOMANIFEST file in
    either spec dir, or FILE_MANIFEST=off in the environment.
    """
    if os.environ.get("FILE_MANIFEST", "").strip().lower() in {"off", "0", "false"}:
        return True
    return any(os.path.isfile(os.path.join(root, d, "NOMANIFEST")) for d in SPEC_DIRS)


def relative_to(root: str, path: str):
    """`path` expressed relative to `root`, or None when it falls outside.

    Outside the project is outside the gate's jurisdiction: a manifest for this
    repo has nothing to say about a file in another one.
    """
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except Exception:
        return None
    rel = norm(rel)
    return None if rel.startswith("../") or rel == ".." else rel


def strip_lead(rel: str) -> str:
    """Drop a leading `./` only.

    NOT `lstrip("./")` -- that strips a *character set*, so `.tmp/x` became
    `tmp/x` and the scratch exemption silently stopped firing on the one
    directory it exists to protect. Every dotted top-level path had the same bug.
    """
    r = norm(rel)
    while r.startswith("./"):
        r = r[2:]
    return r


def is_exempt(rel: str) -> bool:
    """True for project-relative paths the gate never judges."""
    r = strip_lead(rel)
    if r == SCRATCH or any(r.startswith(p) for p in EXEMPT_PREFIXES):
        return True
    return any(seg in EXEMPT_SEGMENTS for seg in r.split("/")[:-1])


# ------------------------------------------------------------------- parsing

_ROW = re.compile(r"^\s*\|(?P<cells>.+)\|\s*$")
_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def join_location(location: str, name: str) -> str:
    """`Location` + `Name` -> the glob the gate matches against (REQ #37).

    A root location contributes no segment, so `| CLAUDE.md | / |` is `CLAUDE.md`
    and not `//CLAUDE.md`. Splitting the two is what makes the table sortable by
    area; the matcher only ever sees the join.
    """
    loc = norm(location or "").strip().strip("`").strip()
    if loc.lower() in ROOT_LOCATIONS:
        return norm(name)
    return norm(loc.rstrip("/") + "/" + name.lstrip("/"))


def parse_manifest(text: str):
    """Every data row of every markdown table in the manifest.

    Two shapes, and the header row says which (REQ #37):

        | Name | Location | Type | Discipline | Intent |    <- current
        | Path | Type | Intent |                            <- legacy, still gated

    Read the shape rather than guess it from cell count, so both can sit in one
    document and an old project keeps working untouched. Otherwise deliberately
    format-tolerant: a manifest is a document a human edits by hand, and a parser
    that rejects a stray column is a parser that gets the whole feature abandoned.
    """
    rows = []
    fenced = False
    five = False                          # shape of the table currently being read
    for raw in (text or "").splitlines():
        if raw.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or _SEP.match(raw):
            continue
        m = _ROW.match(raw)
        if not m:
            continue
        cells = [c.strip().strip("`") for c in m.group("cells").split("|")]
        if len(cells) < 3:
            continue
        first = cells[0].lower()
        if not cells[0] or first in HEAD_PATH or first in HEAD_NAME:
            # Header row: it declares the shape of every row beneath it.
            five = first in HEAD_NAME and cells[1].lower() in HEAD_LOCATION
            continue
        if five and len(cells) >= 4:
            names, location, kind = cells[0], cells[1], cells[2]
            discipline = cells[3]
            intent = cells[4] if len(cells) > 4 else ""
        else:
            names, location, kind = cells[0], "", cells[1]
            discipline, intent = "", cells[2]
        # One cell may carry several globs that share an intent. Authors write
        # `cache/**, image-cache/**` by reflex -- I did it myself -- and without
        # this split the whole cell is one pattern that matches nothing at all.
        # A silent no-match is the worst failure this tool has: the row LOOKS
        # like coverage and provides none.
        for g in (p.strip().strip("`") for p in names.split(",")):
            if g:
                rows.append({"path": join_location(location, g),
                             "name": g, "location": location,
                             "type": kind.lower(),
                             "discipline": discipline.lower(), "intent": intent})
    return rows


def load_manifest(manifest_path: str):
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            return parse_manifest(fh.read())
    except OSError:
        return []


# ------------------------------------------------------------------ matching

def glob_regex(g: str):
    """Compile a manifest glob to a full-match regex with pathlib semantics.

    `fnmatch` is not usable here and the difference is not cosmetic: its `*`
    happily crosses `/`, so a row of `hooks/*.py` silently authorised
    `hooks/nested/deep.py` -- the gate would have claimed to cover a directory it
    had never been told about. So the separator is respected explicitly:

        **/   spans zero or more directories
        **    spans anything, separators included
        *     anything within one segment
        ?     one character within one segment
        trailing `/`  a bare directory row covers its whole tree
    """
    g = strip_lead(g)
    if g.endswith("/"):
        g += "**"
    out, i = [], 0
    while i < len(g):
        c = g[i]
        if g.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif g.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out) + r"\Z")


_REGEX_CACHE: dict = {}


def match_row(rel: str, rows):
    """The first manifest row whose glob covers `rel`, or None."""
    p = strip_lead(rel)
    for row in rows:
        pattern = row["path"]
        rx = _REGEX_CACHE.get(pattern)
        if rx is None:
            rx = _REGEX_CACHE[pattern] = glob_regex(pattern)
        if rx.match(p):
            return row
    return None


# -------------------------------------------------------------------- decide

def targets(tool_input: dict):
    """Every path a file-mutating tool call would touch."""
    out = []
    for key in ("file_path", "notebook_path", "path"):
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            out.append(v)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if isinstance(e, dict) and isinstance(e.get("file_path"), str):
                out.append(e["file_path"])
    return out


def edits_for(tool_input: dict, root: str, rel: str):
    """(old, new) pairs this call would apply to `rel`.

    A single Edit carries the pair at the top level; MultiEdit carries a list,
    and in a list an entry may name a different file, so only entries pointing
    at `rel` (or naming no file at all) count.
    """
    pairs = []
    top_old, top_new = tool_input.get("old_string"), tool_input.get("new_string")
    if isinstance(top_old, str) and isinstance(top_new, str):
        pairs.append((top_old, top_new))
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if not isinstance(e, dict):
                continue
            fp = e.get("file_path")
            if isinstance(fp, str) and fp:
                if relative_to(root, fp) != rel:
                    continue
            o, n = e.get("old_string"), e.get("new_string")
            if isinstance(o, str) and isinstance(n, str):
                pairs.append((o, n))
    return pairs


def discipline_reason(rel, row, tool, tool_input, root, rel_manifest):
    """Deny reason when the matched row's discipline forbids this call, else None.

    Two disciplines are enforced rather than reported. Both name the matched row
    and both escape hatches, because a gate the operator cannot get past is a gate
    that gets switched off.
    """
    d = (row.get("discipline") or "").strip().lower()
    if tool not in MUTATING_TOOLS or d not in ("read-only", "append-only"):
        return None
    shown = "| {} | {} | {} | {} | {} |".format(
        row["name"] or row["path"], row["location"] or "/", row["type"],
        row["discipline"], row["intent"])

    if d == "read-only":
        return (
            "BLOCKED: `{}` is declared `read-only` in the project file table "
            "(`{}`).\n\nMatched row:\n  {}\n\n"
            "The operator edits this file by hand; an agent write to it is a "
            "defect, not a step. Do one of:\n"
            "  1. Tell the operator what change it needs and let them make it.\n"
            "  2. If it genuinely should be agent-writable, change that row's "
            "Discipline in `{}` first, then retry.\n"
            "  3. If the content is scratch, write it under `{}/` instead."
            .format(rel, rel_manifest, shown, rel_manifest, SCRATCH))

    # append-only
    if tool in ("Write", "NotebookEdit"):
        return (
            "BLOCKED: `{}` is declared `append-only` in the project file table "
            "(`{}`).\n\nMatched row:\n  {}\n\n"
            "`{}` replaces the file wholesale; this file may only grow. Do one "
            "of:\n"
            "  1. Use Edit with `new_string` starting with the exact "
            "`old_string`, adding your text after it.\n"
            "  2. If existing content must change, the operator edits the file "
            "directly, or changes that row's Discipline in `{}`."
            .format(rel, rel_manifest, shown, tool, rel_manifest))

    pairs = edits_for(tool_input, root, rel)
    if not pairs:
        return None                       # nothing to judge -- fail open
    for old, new in pairs:
        if not new.startswith(old):
            return (
                "BLOCKED: `{}` is declared `append-only` in the project file "
                "table (`{}`).\n\nMatched row:\n  {}\n\n"
                "An edit here must be a pure append: `new_string` has to begin "
                "with the whole of `old_string` and add after it. This one "
                "rewrites existing content. Do one of:\n"
                "  1. Re-issue the edit as an append.\n"
                "  2. If existing content must change, the operator edits the "
                "file directly, or changes that row's Discipline in `{}`."
                .format(rel, rel_manifest, shown, rel_manifest))
    return None


def decide(payload: dict):
    """Deny reason, or None to allow. Pure over the payload -- testable offline."""
    cwd = payload.get("cwd") or os.getcwd()
    found = find_manifest(cwd)
    if not found:
        return None                       # unarmed project
    root, manifest_path = found
    if is_bypassed(root):
        return None

    rows = load_manifest(manifest_path)
    if not rows:
        return None                       # empty table gates nothing; see --audit

    tool_input = payload.get("tool_input") or {}
    tool = payload.get("tool_name") or ""
    rel_manifest = relative_to(root, manifest_path) or manifest_path
    for target in targets(tool_input):
        rel = relative_to(root, target)
        if rel is None or is_exempt(rel):
            continue
        row = match_row(rel, rows)
        if row is None:
            return unclaimed_reason(rel, manifest_path, root, rows)
        reason = discipline_reason(rel, row, tool, tool_input, root, rel_manifest)
        if reason:
            return reason
    return None


def unclaimed_reason(rel: str, manifest_path: str, root: str, rows) -> str:
    """The deny message. Names the fix, not just the failure."""
    rel_manifest = relative_to(root, manifest_path) or manifest_path
    nearby = [r for r in rows if r["path"].split("/")[0] == rel.split("/")[0]][:3]
    hint = ""
    if nearby:
        hint = "\n\nNearest rows in that section:\n" + "\n".join(
            "  | {} | {} | {} | {} | {} |".format(
                r["name"] or r["path"], r["location"] or "/", r["type"],
                r["discipline"] or "-", r["intent"])
            for r in nearby)
    name = rel.rsplit("/", 1)[-1]
    where = rel[:-len(name)].rstrip("/") or "/"
    return (
        "BLOCKED: `{}` has no row in the project file table (`{}`).\n\n"
        "Every file in this project is declared before it is written. Do one of:\n"
        "  1. If it is permanent -- add a row to `{}`:\n"
        "       | Name | Location | Type | Discipline | Intent |\n"
        "       | {} | {} | <{}> | <{}> | <what it is for, one line> |\n"
        "     Then retry the write. Say out loud which row authorises it.\n"
        "  2. If it is scratch -- write it under `{}/` instead, which is ungated "
        "and gitignored.\n"
        "  3. If an existing file already does this job -- extend that one "
        "(anti-sprawl Gate A).".format(
            rel, rel_manifest, rel_manifest, name, where,
            "|".join(TYPES), "|".join(DISCIPLINES), SCRATCH)
        + hint
    )


# --------------------------------------------------------------------- audit

SOURCE_SKIP = {".lock", ".log", ".pyc"}


def changed_files(root: str):
    """Working-tree paths git reports as added or modified, project-relative."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root, capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return []
    files = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:].strip().strip('"')
        if "D" in code:                    # deletion is Law 10, not an unspec'd file
            continue
        if " -> " in path:                 # rename: judge the destination
            path = path.split(" -> ", 1)[1]
        files.append(norm(path))
    return files


def audit(cwd: str):
    """Unclaimed working-tree files, or None when clean/unarmed.

    Exists because the PreToolUse matcher only sees Edit/Write; `sed -i`, a
    heredoc, and `python patch.py` are invisible to it. This reads the
    filesystem, so it sees the change regardless of how it was made.
    """
    found = find_manifest(cwd)
    if not found:
        return None
    root, manifest_path = found
    if is_bypassed(root):
        return None
    rows = load_manifest(manifest_path)

    unclaimed = [
        f for f in changed_files(root)
        if not is_exempt(f)
        and os.path.splitext(f)[1] not in SOURCE_SKIP
        and not match_row(f, rows)
    ]
    if not unclaimed:
        return None
    rel_manifest = relative_to(root, manifest_path) or manifest_path
    listing = "\n".join("  " + f for f in unclaimed[:20])
    more = "\n  ... and {} more".format(len(unclaimed) - 20) if len(unclaimed) > 20 else ""
    return (
        "UNCLAIMED FILES -- changed in the working tree (git-visible), no row in "
        "`{}`:\n{}{}\n\n"
        "Report these to the operator AS UNCLAIMED. Either add a row naming what "
        "each is for, move it under `{}/`, or delete it. Do not fold them silently "
        "into 'and I also changed...'.".format(rel_manifest, listing, more, SCRATCH)
    )


# ------------------------------------------------------------------ coverage

def coverage(cwd: str, include_ignored: bool = False):
    """Every tracked-or-untracked file in the project with no row. Not a hook.

    `--audit` answers "did anything UNCLAIMED change this turn?" and goes quiet on
    a clean tree -- which reads exactly like "the table covers everything" when it
    may cover almost nothing. This asks the other question, over the whole repo at
    once, and it is the one that catches a section you never knew was there.

    Written after the `~/.harness` table missed `.kiro/` and `.copilot/` entirely:
    the tree was surveyed with a `*` glob, hidden directories never appeared, and
    the audit stayed silent because none of those files had changed. Run this after
    authoring or editing a manifest -- a clean audit is not coverage.

    Run: echo '{"cwd":"<path>"}' | python hooks/file_manifest.py --coverage
    """
    found = find_manifest(cwd)
    if not found:
        return "no manifest found above " + cwd
    root, manifest_path = found
    rows = load_manifest(manifest_path)
    cmd = ["git", "ls-files", "--cached", "--others"]
    if not include_ignored:
        cmd.append("--exclude-standard")
    try:
        out = subprocess.run(cmd, cwd=root, capture_output=True,
                             text=True, timeout=60).stdout
    except Exception:
        return "git ls-files failed in " + root
    files = [norm(f) for f in out.splitlines() if f.strip()]
    missing = [f for f in files if not is_exempt(f) and not match_row(f, rows)]
    scope = "all files incl. gitignored" if include_ignored else "git-visible only"
    head = "{}: {} files ({}), {} rows, {} UNCOVERED".format(
        root, len(files), scope, len(rows), len(missing))
    if not missing:
        return head
    return head + "\n" + "\n".join("    " + f for f in sorted(missing)[:60])


# ---------------------------------------------------------------------- main

def main(argv) -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                          # fail open

    if "--coverage" in argv:              # operator-run, not wired to any event
        try:
            print(coverage(payload.get("cwd") or os.getcwd(),
                           include_ignored="--all" in argv))
        except Exception as exc:          # noqa: BLE001 -- a manual tool may speak up
            print("coverage failed: " + repr(exc), file=sys.stderr)
        return 0

    if "--audit" in argv:
        try:
            finding = audit(payload.get("cwd") or os.getcwd())
        except Exception:
            return 0
        if finding:
            print(finding, file=sys.stderr)
        return 0

    try:
        reason = decide(payload)
    except Exception:
        return 0                          # a confused gate must not trap the session

    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        sys.exit(0)
