#!/usr/bin/env python3
"""Battery for spec_gate.decide().

Builds a real temporary tree per case rather than mocking the filesystem, so the
path-walking and glob matching are exercised as they actually run.

Half the cases are false-positive probes. A gate that fires on an unarmed repo,
on the spec artifacts themselves, or on markdown would be worse than no gate --
it would make the tree unwritable and get switched off within a day. "Must
ALLOW" therefore carries as much weight here as "must DENY".

Entities and paths vary across cases (payments, auth, parser, ingest, ...) so the
battery tests the RULE and not a memorized string. Per CLAUDE.md, no fixture is
seeded from a single observed failing case.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spec_gate import decide  # noqa: E402
from spec_paths import PHASES  # noqa: E402


def build(root: str, tree: dict | None) -> None:
    """Materialize a .spec tree.

    `tree` is None for an unarmed repo. Otherwise each key is a spec name mapping
    to its state dict; the special keys `_active`, `_bypass`, and `_files` cover
    the ACTIVE pointer, the escape hatch, and extra artifact files.
    """
    os.makedirs(os.path.join(root, "src"), exist_ok=True)
    if tree is None:
        return

    spec_root = os.path.join(root, ".spec")
    os.makedirs(os.path.join(spec_root, "specs"), exist_ok=True)

    if tree.get("_bypass"):
        open(os.path.join(spec_root, "BYPASS"), "w").close()

    if tree.get("_active"):
        with open(os.path.join(spec_root, "ACTIVE"), "w", encoding="utf-8") as fh:
            fh.write(tree["_active"])

    for rel in tree.get("_files", []):
        path = os.path.join(spec_root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()

    for name, state in tree.items():
        if name.startswith("_"):
            continue
        d = os.path.join(spec_root, "specs", name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as fh:
            json.dump(state, fh)


def spec(phase="requirements", kind="feature", approved=(), scope=None):
    """A state.json body. Approvals derive from PHASES so order is stated once."""
    return {
        "feature": "x",
        "kind": kind,
        "phase": phase,
        "approvals": {p: ("2026-08-04T00:00:00Z" if p in approved else None)
                      for p in PHASES[:-1]},
        "scope": scope or [],
        "created": "2026-08-04T00:00:00Z",
    }


def payload(root: str, rel: str, tool="Edit"):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": os.path.join(root, rel)},
        "cwd": root,
    }


IMPL = "implement"

CASES = [
    # ---- must ALLOW: repo not armed ---------------------------------------
    ("unarmed repo, ordinary source edit", None, "src/payments.py", "Edit", False),
    ("unarmed repo, Write of a new module", None, "src/auth/session.go", "Write", False),
    ("unarmed repo, notebook edit", None, "analysis/eda.ipynb", "NotebookEdit", False),

    # ---- must ALLOW: escape hatch -----------------------------------------
    ("BYPASS present, unapproved spec", {"_bypass": True, "parser": spec()},
     "src/parser.rs", "Edit", False),
    ("BYPASS present, no specs at all", {"_bypass": True}, "lib/util.ts", "Write", False),

    # ---- must ALLOW: exempt paths -----------------------------------------
    ("spec artifact itself is writable", {"ingest": spec()},
     ".spec/specs/ingest/requirements.md", "Write", False),
    ("steering doc is writable", {"ingest": spec()},
     ".spec/steering/tech.md", "Write", False),
    ("markdown anywhere is exempt", {"ingest": spec()}, "docs/architecture.md", "Edit", False),
    ("dot-claude config is exempt", {"ingest": spec()}, ".claude/settings.json", "Edit", False),
    ("README at root is exempt", {"ingest": spec()}, "README.md", "Write", False),

    # ---- must ALLOW: fully approved and in scope --------------------------
    ("implement phase, no scope declared",
     {"_active": "billing", "billing": spec(IMPL, approved=("requirements", "design", "tasks"))},
     "src/billing/invoice.py", "Edit", False),
    ("implement phase, path inside declared scope",
     {"_active": "search", "search": spec(IMPL, approved=("requirements", "design", "tasks"),
                                          scope=["src/search/*.py"])},
     "src/search/index.py", "Write", False),
    ("sole implementable spec inferred without ACTIVE",
     {"solo": spec(IMPL, approved=("requirements", "design", "tasks"))},
     "src/solo.py", "Edit", False),

    # ---- must ALLOW: non-mutating or unparseable ---------------------------
    # Confusion fails open. state.json is unwritable by Edit/Write, so denying on
    # a malformed phase would brick the repo with no in-tool route back.
    ("null phase fails open",
     {"_active": "broken", "broken": {"phase": None, "approvals": "not-a-dict"}},
     "src/thing.py", "Edit", False),
    ("unrecognized phase string fails open",
     {"_active": "weird", "weird": spec("shipped")},
     "src/thing.py", "Edit", False),
    # Unreadable state means no spec can be IDENTIFIED, which is the same
    # situation as an armed repo with no specs -- deny, with an actionable
    # message. That differs from the two cases above, where a spec is identified
    # but its state is uninterpretable, so the gate declines to guess.
    ("state.json that is not a dict denies as un-identifiable",
     {"_active": "listy", "listy": ["not", "a", "dict"]},
     "src/thing.py", "Write", True),

    # ---- must DENY: armed but no governing spec ---------------------------
    ("armed, zero specs exist", {}, "src/main.py", "Edit", True),
    ("armed, spec exists but none implementable", {"draft": spec()}, "src/api.py", "Write", True),
    ("armed, two implementable specs and no ACTIVE",
     {"alpha": spec(IMPL, approved=("requirements", "design", "tasks")),
      "beta": spec(IMPL, approved=("requirements", "design", "tasks"))},
     "src/ambiguous.py", "Edit", True),

    # ---- must DENY: phase not reached -------------------------------------
    ("phase requirements, nothing approved",
     {"_active": "checkout", "checkout": spec("requirements")},
     "src/checkout.py", "Edit", True),
    ("phase design, requirements approved only",
     {"_active": "upload", "upload": spec("design", approved=("requirements",))},
     "src/upload.py", "Write", True),
    ("phase tasks, design approved but tasks not",
     {"_active": "report", "report": spec("tasks", approved=("requirements", "design"))},
     "src/report.py", "Edit", True),
    ("bugfix lane blocks the same way",
     {"_active": "npe-crash", "npe-crash": spec("requirements", kind="bugfix")},
     "src/crash.py", "Edit", True),

    # ---- must DENY: scope violation ---------------------------------------
    ("implement phase but path outside scope",
     {"_active": "search", "search": spec(IMPL, approved=("requirements", "design", "tasks"),
                                          scope=["src/search/*.py"])},
     "src/billing/charge.py", "Edit", True),
    ("scope violation via Write on a new file",
     {"_active": "narrow", "narrow": spec(IMPL, approved=("requirements", "design", "tasks"),
                                          scope=["lib/*.ts"])},
     "src/server.ts", "Write", True),

    # ---- must DENY: state.json is not self-approvable ---------------------
    ("state.json cannot be written by Edit",
     {"_active": "guard", "guard": spec("requirements")},
     ".spec/specs/guard/state.json", "Edit", True),
    ("state.json cannot be written even in implement phase",
     {"_active": "guard", "guard": spec(IMPL, approved=("requirements", "design", "tasks"),
                                        scope=["src/*.py"])},
     ".spec/specs/guard/state.json", "Write", True),
]


# --------------------------------------------------------------------------
# Shell cases. `Edit`/`Write` carry a `file_path` the gate can inspect; a shell
# carries only a command string, so it reaches the filesystem by a route
# `target_path` cannot see. These probe that second route.
#
# The ALLOW half matters more than the DENY half. A gate that blocks `cat
# state.json` or a read-only `SELECT` would make the store un-inspectable from
# inside a blocked state, which is exactly the deadlock the module contract
# forbids.
# --------------------------------------------------------------------------
ARMED = {"_active": "ledger", "ledger": spec("requirements")}
DONE = {"_active": "ledger",
        "ledger": spec(IMPL, approved=("requirements", "design", "tasks"))}

SHELL_CASES = [
    # ---- must ALLOW: reads never block ------------------------------------
    ("shell read of state.json", ARMED,
     "cat .spec/specs/ledger/state.json", "Bash", False),
    ("shell read piped elsewhere", ARMED,
     "grep phase .spec/specs/auth/state.json | head -5", "Bash", False),
    ("read of state.json redirected to a scratch file", ARMED,
     "cat .spec/specs/ingest/state.json > /tmp/notes.txt", "Bash", False),
    ("read-only SELECT against the store", ARMED,
     'sqlite3 .spec/spec.db "SELECT id FROM requirements"', "Bash", False),

    # ---- must ALLOW: the sanctioned mutation route ------------------------
    # The store is how legitimate writes happen. Denying it would block the
    # command that unlocks the repo.
    ("store invocation may write", ARMED,
     "python spec_store.py approve requirements --feature ledger", "Bash", False),
    ("slash command may write", ARMED, "/spec-approve design", "Bash", False),

    # ---- must ALLOW: unrelated shell work ---------------------------------
    ("ordinary command naming neither file", ARMED, "git status --short", "Bash", False),
    ("redirect into an unrelated file", ARMED, "echo hello > build/out.txt", "Bash", False),

    # ---- must ALLOW: not this gate's business -----------------------------
    ("unarmed repo, shell write to a state.json", None,
     "echo {} > .spec/specs/x/state.json", "Bash", False),
    ("BYPASS present, shell write to the store",
     {"_bypass": True, "parser": spec()},
     'sqlite3 .spec/spec.db "UPDATE gates SET passed=1"', "Bash", False),

    # ---- must DENY: redirection into the gate's own record ----------------
    ("truncating redirect into state.json", ARMED,
     "echo {} > .spec/specs/ledger/state.json", "Bash", True),
    ("appending redirect into state.json", ARMED,
     'echo \'"approved"\' >> .spec/specs/payments/state.json', "Bash", True),

    # ---- must DENY: mutating SQL against the store ------------------------
    ("UPDATE against the store", ARMED,
     'sqlite3 .spec/spec.db "UPDATE gates SET passed=1"', "Bash", True),
    ("DELETE against the store", DONE,
     'sqlite3 .spec/spec.db "DELETE FROM requirements WHERE id=3"', "Bash", True),

    # ---- must DENY: clobbering file operations ----------------------------
    ("removing the store outright", ARMED, "rm -f .spec/spec.db", "Bash", True),
    ("moving a file over state.json", ARMED,
     "mv /tmp/forged.json .spec/specs/upload/state.json", "Bash", True),

    # ---- must DENY: the PowerShell route ----------------------------------
    # PowerShell is the primary shell on this machine. Gating only Bash would
    # leave the hole open by the more convenient route.
    ("PowerShell Set-Content on state.json", ARMED,
     "Set-Content -Path .spec/specs/ledger/state.json -Value '{}'", "PowerShell", True),
    ("PowerShell Remove-Item on the store", ARMED,
     "Remove-Item .spec/spec.db -Force", "PowerShell", True),

    # ---- must DENY: inline interpreter write ------------------------------
    ("python -c write to state.json", DONE,
     "python -c \"open('.spec/specs/ledger/state.json','w').write('{}')\"", "Bash", True),

    # ---- must DENY: approved phase is not a licence to forge --------------
    # There is no phase or scope question for these files. Rewriting approvals
    # is wrong in `implement` too, which is why the shell branch runs before
    # the phase checks.
    ("implement phase does not license a shell write", DONE,
     "echo {} > .spec/specs/ledger/state.json", "Bash", True),
]


def run_case(tree, rel, tool):
    root = tempfile.mkdtemp(prefix="specgate-")
    try:
        build(root, tree)
        return decide(payload(root, rel, tool))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_shell_case(tree, command, tool):
    """Same as `run_case`, but the payload carries a command instead of a path."""
    root = tempfile.mkdtemp(prefix="specgate-")
    try:
        build(root, tree)
        return decide({
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": {"command": command},
            "cwd": root,
        })
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    failures = 0
    for name, tree, rel, tool, should_deny in CASES:
        try:
            reason = run_case(tree, rel, tool)
            denied = reason is not None
            ok = denied == should_deny
        except Exception as exc:                     # a crash is a failure, not a pass
            denied, ok, reason = None, False, f"EXCEPTION {exc!r}"
        if not ok:
            failures += 1
        print(
            f"{'PASS' if ok else 'FAIL'}  "
            f"{'DENY ' if should_deny else 'ALLOW'}  {name}"
            + ("" if ok else f"   <-- got {'DENY' if denied else 'ALLOW'}: {reason}")
        )

    for name, tree, command, tool, should_deny in SHELL_CASES:
        try:
            reason = run_shell_case(tree, command, tool)
            denied = reason is not None
            ok = denied == should_deny
        except Exception as exc:                     # a crash is a failure, not a pass
            denied, ok, reason = None, False, f"EXCEPTION {exc!r}"
        if not ok:
            failures += 1
        print(
            f"{'PASS' if ok else 'FAIL'}  "
            f"{'DENY ' if should_deny else 'ALLOW'}  shell: {name}"
            + ("" if ok else f"   <-- got {'DENY' if denied else 'ALLOW'}: {reason}")
        )

    # A read-only tool must never be judged, whatever the tree looks like.
    # `Bash` is deliberately NOT in this list any more: since the shell branch
    # landed it is a judged tool, and asserting otherwise here would state a
    # falsehood that happens to pass (these payloads carry no `command` key).
    root = tempfile.mkdtemp(prefix="specgate-")
    try:
        build(root, {"_active": "x", "x": spec("requirements")})
        for tool in ("Read", "Grep", "Glob"):
            reason = decide({"tool_name": tool, "tool_input": {"file_path": f"{root}/src/a.py"},
                             "cwd": root})
            ok = reason is None
            failures += 0 if ok else 1
            print(f"{'PASS' if ok else 'FAIL'}  ALLOW  read-only tool {tool} is never gated")

        # A shell payload with no command key must fail open, not crash.
        for tool in ("Bash", "PowerShell"):
            reason = decide({"tool_name": tool, "tool_input": {}, "cwd": root})
            ok = reason is None
            failures += 0 if ok else 1
            print(f"{'PASS' if ok else 'FAIL'}  ALLOW  {tool} with no command fails open")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    total = len(CASES) + len(SHELL_CASES) + 5
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
