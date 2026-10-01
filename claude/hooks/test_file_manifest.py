#!/usr/bin/env python3
"""Synthetic battery for `file_manifest.py`. No live session, no network.

Spec: .specs/file-manifest.md
Task: harness change 2026-08-31 (file table gate)

Follows `test_spec_gate.py`: build a throwaway project tree per case, hand
`decide()` a hand-rolled payload, assert blocked/allowed. Every branch that can
trap a session gets a fail-open case, because fail-open is the one property whose
regression is silent.

Run: python hooks/test_file_manifest.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import file_manifest as fm  # noqa: E402

MANIFEST = """# Project files

| Path | Type | Intent |
|---|---|---|
| hooks/*.py | code | Enforcement hooks |
| docs/**/*.md | docs | Design notes |
| settings.json | config | Harness settings |
| src/ | code | Application source |
"""


def make_project(manifest_text=MANIFEST, spec_dir=".specs", bypass=False):
    root = tempfile.mkdtemp(prefix="fmtest_")
    d = os.path.join(root, spec_dir)
    os.makedirs(d)
    if manifest_text is not None:
        with open(os.path.join(d, fm.MANIFEST_NAME), "w", encoding="utf-8") as fh:
            fh.write(manifest_text)
    if bypass:
        open(os.path.join(d, "NOMANIFEST"), "w").close()
    return root


def payload(root, path, tool="Write"):
    return {"cwd": root, "tool_name": tool,
            "tool_input": {"file_path": os.path.join(root, path)}}


DISCIPLINED = """# Project files

| Name | Location | Type | Discipline | Intent |
|---|---|---|---|---|
| CLAUDE.md | / | docs | read-only | Operator edits this by hand. |
| journal.md | logs/ | docs | append-only | Entries only ever get added. |
| *.py | src/ | code | none | Ordinary source. |
"""


def dpayload(root, path, tool, **tool_input):
    ti = {"file_path": os.path.join(root, path)}
    ti.update(tool_input)
    return {"cwd": root, "tool_name": tool, "tool_input": ti}


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


# ------------------------------------------------------------------ blocking

@case("unlisted file at root is blocked")
def _():
    root = make_project()
    assert fm.decide(payload(root, "random_helper.py")) is not None


@case("unlisted file in a listed directory is blocked")
def _():
    root = make_project()
    assert fm.decide(payload(root, "hooks/nested/deep.py")) is not None


@case("deny message names the manifest and the scratch escape")
def _():
    root = make_project()
    msg = fm.decide(payload(root, "random_helper.py"))
    assert fm.MANIFEST_NAME in msg and ".tmp/" in msg, msg


@case("MultiEdit is judged on every edit target")
def _():
    root = make_project()
    p = {"cwd": root, "tool_name": "MultiEdit", "tool_input": {"edits": [
        {"file_path": os.path.join(root, "hooks/ok.py")},
        {"file_path": os.path.join(root, "nope.py")},
    ]}}
    assert fm.decide(p) is not None


@case("NotebookEdit target is judged")
def _():
    root = make_project()
    p = {"cwd": root, "tool_name": "NotebookEdit",
         "tool_input": {"notebook_path": os.path.join(root, "analysis.ipynb")}}
    assert fm.decide(p) is not None


# ------------------------------------------------------------------ allowing

@case("listed glob allows")
def _():
    root = make_project()
    assert fm.decide(payload(root, "hooks/spec_gate.py")) is None


@case("recursive glob spans zero directories")
def _():
    root = make_project()
    assert fm.decide(payload(root, "docs/notes.md")) is None


@case("recursive glob spans one directory")
def _():
    root = make_project()
    assert fm.decide(payload(root, "docs/adr/0001.md")) is None


@case("exact path row allows")
def _():
    root = make_project()
    assert fm.decide(payload(root, "settings.json")) is None


@case("bare directory row covers its whole tree")
def _():
    root = make_project()
    assert fm.decide(payload(root, "src/api/users.py")) is None


@case("scratch under .tmp is always allowed")
def _():
    root = make_project()
    assert fm.decide(payload(root, ".tmp/scratch.py")) is None
    assert fm.decide(payload(root, ".tmp/deep/nested/thing.json")) is None


@case("the spec tree itself is never gated")
def _():
    root = make_project()
    assert fm.decide(payload(root, ".specs/file-manifest.md")) is None
    assert fm.decide(payload(root, ".spec/specs/x/requirements.md")) is None


@case("a path outside the project root is outside jurisdiction")
def _():
    root = make_project()
    p = {"cwd": root, "tool_name": "Write",
         "tool_input": {"file_path": os.path.join(tempfile.gettempdir(), "elsewhere.py")}}
    assert fm.decide(p) is None


@case("cwd in a subdirectory still finds the manifest")
def _():
    root = make_project()
    sub = os.path.join(root, "hooks")
    os.makedirs(sub, exist_ok=True)
    p = {"cwd": sub, "tool_name": "Write",
         "tool_input": {"file_path": os.path.join(root, "unlisted.py")}}
    assert fm.decide(p) is not None
    p["tool_input"]["file_path"] = os.path.join(root, "hooks", "x.py")
    assert fm.decide(p) is None


@case("the .spec spelling works as well as .specs")
def _():
    root = make_project(spec_dir=".spec")
    assert fm.decide(payload(root, "unlisted.py")) is not None
    assert fm.decide(payload(root, "hooks/x.py")) is None


# ------------------------------ discipline enforcement

@case("a read-only row denies Edit and Write")
def _():
    root = make_project(manifest_text=DISCIPLINED)
    for tool in ("Edit", "Write", "NotebookEdit"):
        msg = fm.decide(dpayload(root, "CLAUDE.md", tool,
                                 old_string="a", new_string="ab"))
        assert msg is not None, tool
        assert "read-only" in msg and "CLAUDE.md" in msg, msg


@case("a read-only deny names the row and the escape hatch")
def _():
    root = make_project(manifest_text=DISCIPLINED)
    msg = fm.decide(dpayload(root, "CLAUDE.md", "Write"))
    assert "| CLAUDE.md | / | docs | read-only |" in msg, msg
    assert "operator" in msg.lower() and "Discipline" in msg, msg


@case("an append-only row denies Write and a rewriting Edit")
def _():
    root = make_project(manifest_text=DISCIPLINED)
    assert fm.decide(dpayload(root, "logs/journal.md", "Write",
                              content="all new")) is not None
    msg = fm.decide(dpayload(root, "logs/journal.md", "Edit",
                             old_string="line one\n", new_string="LINE ONE\n"))
    assert msg is not None and "append-only" in msg, msg


@case("an append-only row allows an edit that is a pure append")
def _():
    root = make_project(manifest_text=DISCIPLINED)
    assert fm.decide(dpayload(root, "logs/journal.md", "Edit",
                              old_string="line one\n",
                              new_string="line one\nline two\n")) is None


@case("append-only judges every edit of a MultiEdit on that file")
def _():
    root = make_project(manifest_text=DISCIPLINED)
    j = os.path.join(root, "logs/journal.md")
    good = {"cwd": root, "tool_name": "MultiEdit", "tool_input": {"edits": [
        {"file_path": j, "old_string": "a", "new_string": "ab"},
        {"file_path": j, "old_string": "b", "new_string": "bc"}]}}
    assert fm.decide(good) is None
    bad = {"cwd": root, "tool_name": "MultiEdit", "tool_input": {"edits": [
        {"file_path": j, "old_string": "a", "new_string": "ab"},
        {"file_path": j, "old_string": "b", "new_string": "XX"}]}}
    assert fm.decide(bad) is not None


@case("a row with an ordinary discipline is unaffected")
def _():
    root = make_project(manifest_text=DISCIPLINED)
    assert fm.decide(dpayload(root, "src/thing.py", "Write")) is None
    assert fm.decide(dpayload(root, "src/thing.py", "Edit",
                              old_string="x", new_string="y")) is None
    assert fm.decide(dpayload(root, "unlisted.py", "Write")) is not None


@case("a discipline row does not fire for a non-mutating tool")
def _():
    root = make_project(manifest_text=DISCIPLINED)
    assert fm.decide({"cwd": root, "tool_name": "Read",
                      "tool_input": {"file_path":
                                     os.path.join(root, "CLAUDE.md")}}) is None


@case("discipline enforcement fails open on a malformed payload")
def _():
    root = make_project(manifest_text=DISCIPLINED)
    # no tool_name at all
    assert fm.decide({"cwd": root, "tool_input": {
        "file_path": os.path.join(root, "CLAUDE.md")}}) is None
    # append-only Edit with no strings to compare -> nothing to judge
    assert fm.decide({"cwd": root, "tool_name": "Edit", "tool_input": {
        "file_path": os.path.join(root, "logs/journal.md")}}) is None
    # non-string edit members do not raise
    assert fm.decide({"cwd": root, "tool_name": "MultiEdit", "tool_input": {
        "edits": [None, {"file_path": 3}, {"old_string": 1, "new_string": 2}]}}) is None


# -------------------------------------------------------------- fail open

@case("a project with no manifest is ungated")
def _():
    root = tempfile.mkdtemp(prefix="fmtest_bare_")
    assert fm.decide(payload(root, "anything.py")) is None


@case("NOMANIFEST disarms the gate")
def _():
    root = make_project(bypass=True)
    assert fm.decide(payload(root, "unlisted.py")) is None


@case("FILE_MANIFEST=off disarms the gate")
def _():
    root = make_project()
    os.environ["FILE_MANIFEST"] = "off"
    try:
        assert fm.decide(payload(root, "unlisted.py")) is None
    finally:
        del os.environ["FILE_MANIFEST"]


@case("an empty table gates nothing")
def _():
    root = make_project(manifest_text="# Project files\n\nNothing yet.\n")
    assert fm.decide(payload(root, "unlisted.py")) is None


@case("a malformed payload does not raise")
def _():
    assert fm.decide({}) is None or True
    assert fm.decide({"cwd": None, "tool_input": None}) is None or True


@case("a tool call with no file target allows")
def _():
    root = make_project()
    assert fm.decide({"cwd": root, "tool_name": "Bash",
                      "tool_input": {"command": "ls"}}) is None


# ---------------------------------------------------------------- parsing

@case("parser skips headers, separators and fenced examples")
def _():
    rows = fm.parse_manifest(
        "| Path | Type | Intent |\n|---|---|---|\n"
        "| a.py | code | thing |\n"
        "```\n| fake.py | code | in a fence |\n```\n"
        "| b.md | docs | other |\n")
    assert [r["path"] for r in rows] == ["a.py", "b.md"], rows


@case("one cell may carry several comma-separated globs")
def _():
    rows = fm.parse_manifest("| `a/**`, b/**, c.py | data | shared intent |\n")
    assert [r["path"] for r in rows] == ["a/**", "b/**", "c.py"], rows
    assert all(r["intent"] == "shared intent" for r in rows)
    root = make_project(manifest_text="| x/**, y/** | data | caches |\n")
    assert fm.decide(payload(root, "y/deep/thing.bin")) is None
    assert fm.decide(payload(root, "z/thing.bin")) is not None


@case("derived directories are exempt at any depth")
def _():
    assert fm.is_exempt("specs/__pycache__/x.pyc")
    assert fm.is_exempt("a/b/node_modules/c/d.js")
    assert fm.is_exempt(".ruff_cache/x")
    assert not fm.is_exempt("src/cache_manager.py")   # substring, not a segment


@case("parser tolerates extra columns and backticks")
def _():
    rows = fm.parse_manifest("| `a.py` | code | thing | owner | 2026 |\n")
    assert rows == [{"path": "a.py", "name": "a.py", "location": "", "type": "code",
                     "discipline": "", "intent": "thing"}], rows


FIVE = ("| Name | Location | Type | Discipline | Intent |\n"
        "|---|---|---|---|---|\n"
        "| playbook.py | hooks/ | code | hook-contract | offers the pivot |\n"
        "| CLAUDE.md | / | docs | mirror-from-vault | the brief |\n"
        "| *.md, *.txt | plans/ | docs | named-for-intent | plans |\n")

LEGACY = ("| Path | Type | Intent |\n"
          "|---|---|---|\n"
          "| hooks/*.py | code | the gates |\n")


@case("five-column rows join Location to Name and carry the discipline")
def _():
    rows = fm.parse_manifest(FIVE)
    assert [(r["path"], r["discipline"]) for r in rows] == [
        ("hooks/playbook.py", "hook-contract"),
        ("CLAUDE.md", "mirror-from-vault"),
        ("plans/*.md", "named-for-intent"),
        ("plans/*.txt", "named-for-intent")], rows


@case("both table shapes parse in one document, in either order")
def _():
    for text in (LEGACY + "\nprose\n\n" + FIVE, FIVE + "\nprose\n\n" + LEGACY):
        paths = [r["path"] for r in fm.parse_manifest(text)]
        assert len(paths) == 5, paths
        assert "hooks/*.py" in paths and "hooks/playbook.py" in paths, paths


@case("a root location contributes no path segment")
def _():
    for loc in ("/", "", ".", "./", "root", "-"):
        assert fm.join_location(loc, "a.md") == "a.md", loc
    assert fm.join_location("hooks", "*.py") == "hooks/*.py"
    assert fm.join_location("hooks/", "*.py") == "hooks/*.py"


@case("the deny message shows the five-column row template")
def _():
    msg = fm.unclaimed_reason("hooks/new.py", ".specs/file-manifest.md",
                              os.getcwd(), fm.parse_manifest(FIVE))
    assert "| Name | Location | Type | Discipline | Intent |" in msg, msg
    assert "| new.py | hooks |" in msg, msg
    assert "hook-contract" in msg, msg


# --------------------------------------------------------------- coverage

@case("coverage names uncovered files and stays quiet when there are none")
def _():
    import subprocess
    root = make_project()
    for rel in ("hooks/gated.py", "stray.py"):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").close()
    for cmd in (["init"], ["add", "-A"]):
        subprocess.run(["git"] + cmd, cwd=root, capture_output=True)

    out = fm.coverage(root)
    assert "stray.py" in out, out            # unlisted -> named
    assert "hooks/gated.py" not in out, out  # listed    -> silent
    assert "UNCOVERED" in out, out


@case("coverage reports a project with no manifest rather than raising")
def _():
    root = tempfile.mkdtemp(prefix="fmtest_nocov_")
    assert "no manifest" in fm.coverage(root)


# ------------------------------------------------------------------ runner

# pytest bridge. Every case above is a closure named `_`, so pytest collects
# nothing without this; `_Verify:` runs under pytest, the `__main__` runner is the
# same battery without the dependency.
try:
    import pytest as _pytest
except Exception:                          # pytest absent -> plain runner only
    _pytest = None

if _pytest is not None:
    @_pytest.mark.parametrize("fn", [c[1] for c in CASES],
                              ids=[c[0] for c in CASES])
    def test_case(fn):
        fn()


def run():
    failed = []
    for name, fn in CASES:
        try:
            fn()
            print("  PASS  " + name)
        except AssertionError as exc:
            failed.append((name, exc))
            print("  FAIL  " + name + "  " + str(exc))
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print("  ERROR " + name + "  " + repr(exc))
    print("\n{}/{} passed".format(len(CASES) - len(failed), len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
