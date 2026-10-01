#!/usr/bin/env python3
"""Spec-driven state machine, and the UserPromptSubmit line that reports it.

Thesis
------
Two jobs, one file, because they are the same knowledge viewed twice: what phase
the active spec is in. Splitting them would mean two places to change when the
phase model changes, and a status line that disagrees with the gate is worse
than no status line -- you would stop trusting both.

  As a HOOK (no argv)   reads a UserPromptSubmit payload on stdin and emits one
                        compact `additionalContext` line: active spec, phase,
                        next unchecked task, bypass status. Silent when the repo
                        is not armed, so it costs nothing in ordinary sessions.

  As a CLI (with argv)  `init | new | approve | advance | status` -- the only
                        supported way state.json changes. Routing every mutation
                        through one code path is what lets the gate trust the
                        file: hand-edited state is possible but never the
                        documented route, and Edit/Write on state.json is denied
                        by spec_gate.py.

Why the injected line is phrased as fact
----------------------------------------
The hooks documentation warns that `additionalContext` written as an imperative
("you must now...") reads as an out-of-band instruction and can trip prompt-
injection defenses. So the line states the situation and lets the model draw the
conclusion, which the gate enforces anyway.

Contract
--------
Require   - CLI mutations run from inside a repo containing `.spec/`, except
            `init`, which creates it.
Guarantee - every mutation is atomic (temp file + replace) so a crash mid-write
            cannot leave the gate reading half a state file.
Maintain  - `approve` only ever stamps; it never advances `phase`. Approval and
            progression are separate acts, so an approval can never be inferred
            from progress or vice versa.
Assert    - hook mode never raises and never writes; on any error it prints
            nothing and exits 0.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spec_paths import (  # noqa: E402
    FIRST_ARTIFACT,
    PHASES,
    artifact_for,
    ears_violations,
    find_spec_root,
    is_bypassed,
    is_stub_artifact,
    list_specs,
    load_state,
    load_steering,
    missing_artifacts,
    next_phase,
    read_active,
    render_steering,
    resolve_active,
    specs_dir,
    state_path,
    steering_matches_path,
)

NAME_OK = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(message: str) -> int:
    sys.stderr.write(message.rstrip() + "\n")
    return 1


def write_json(path: str, data: dict) -> None:
    """Atomic write: a torn state.json would make the gate unpredictable."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def require_root() -> str | None:
    root = find_spec_root(os.getcwd())
    if not root:
        sys.stderr.write(
            "No .spec/ directory found above the working directory. "
            "Run /spec-init first to make this repo spec-driven.\n"
        )
    return root


def unchecked_tasks(root: str, feature: str) -> list[str]:
    """Unchecked markdown checkboxes in tasks.md, in file order."""
    path = os.path.join(specs_dir(root), feature, "tasks.md")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("- [ ]", "* [ ]", "+ [ ]")):
            out.append(stripped[5:].strip() or stripped)
    return out


def coverage(root: str, feature: str) -> list[dict] | None:
    """Per-requirement coverage read from spec.db.

    Returns None when there is no store to read (the store is opt-in, and a repo
    predating it must still get a status report), an empty list when the store
    exists but holds no requirements for this feature, otherwise one row per
    requirement in id order.

    Every failure path degrades to None rather than raising: `status` is a
    report, never a gate, and a status command that dies on a corrupt DB hides
    the rest of the state it was asked about.
    """
    try:
        import spec_store  # local: keeps status working if the store is absent
        conn = spec_store.connect(root)
    except Exception:
        return None
    if conn is None:
        return None
    try:
        reqs = conn.execute(
            "SELECT id, strength, pbt, pbt_reason FROM requirements WHERE feature = ? "
            "ORDER BY CAST(SUBSTR(id, 3) AS INTEGER)", (feature,)
        ).fetchall()
        props = conn.execute(
            "SELECT requirement_id, task_id, g1, g2, g3, g4 FROM properties "
            "WHERE feature = ?", (feature,)
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        conn.close()

    rows = []
    for rid, strength, pbt, pbt_reason in reqs:
        mine = [p for p in props if p[0] == rid]
        gates = [g for p in mine for g in p[2:6]]
        if not mine:
            # An `n/a` pbt with a stated reason is a recorded decision, not a
            # hole. Without the reason it is just an unproved requirement.
            verdict = "EXEMPT" if (pbt == "n/a" and pbt_reason) else "UNCOVERED"
        elif "fail" in gates:
            verdict = "FAIL"
        elif "unrun" in gates:
            verdict = "PARTIAL"
        else:
            verdict = "PASS"
        rows.append({
            "id": rid,
            "strength": strength or "?",
            "verdict": verdict,
            "props": len(mine),
            "tasks": len({p[1] for p in mine if p[1]}),
            "reason": pbt_reason or "",
        })
    return rows


def print_coverage(root: str, name: str, indent: str, full: bool) -> None:
    """Coverage block for one spec. Silent when the store is absent."""
    rows = coverage(root, name)
    if rows is None:
        return
    if not rows:
        print(f"{indent}coverage: spec.db has no requirements for this feature")
        return

    tally: dict[str, int] = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    summary = ", ".join(f"{v.lower()} {n}" for v, n in sorted(tally.items()))
    print(f"{indent}coverage: {len(rows)} requirements -- {summary}")

    # PASS rows are noise in the default view: the point of the report is what
    # still needs attention. `status --full` shows everything.
    shown = [r for r in rows if full or r["verdict"] != "PASS"]
    for r in shown:
        line = (f"{indent}  {r['id']:<6} {r['verdict']:<9} {r['strength']:<6} "
                f"props={r['props']} tasks={r['tasks']}")
        if r["verdict"] == "EXEMPT":
            line += f"  ({r['reason']})"
        print(line)


# --------------------------------------------------------------------------
# hook mode
# --------------------------------------------------------------------------

def hook_line(cwd: str) -> str | None:
    """One factual line about spec state, or None when there is nothing to say."""
    root = find_spec_root(cwd)
    if not root:
        return None

    if is_bypassed(root):
        return (
            "Spec state: this repo is spec-driven but the spec gate is currently "
            "BYPASSED (.spec/BYPASS exists or SPEC_GATE=off), so source edits are "
            "not being checked against a spec."
        )

    feature, error = resolve_active(root)
    if not feature:
        return (
            f"Spec state: this repo is spec-driven, but {error}. Source edits are "
            f"blocked until a spec reaches the implement phase."
        )

    state = load_state(root, feature) or {}
    phase = state.get("phase", "unknown")
    kind = state.get("kind", "feature")

    parts = [f"Spec state: active spec is '{feature}' ({kind}), phase '{phase}'"]

    if phase == "implement":
        pending = unchecked_tasks(root, feature)
        if pending:
            parts.append(f"{len(pending)} task(s) remain; next is: {pending[0]}")
        else:
            parts.append("all tasks in tasks.md are checked off")
        scope = state.get("scope")
        if scope:
            parts.append("edits are limited to " + ", ".join(scope))
    else:
        nxt = next_phase(phase)
        parts.append(
            f"source edits are blocked until phase '{nxt}' is reached and approved"
            if nxt else "the phase is unrecognized"
        )

    return ". ".join(parts) + "."


def steering_context(cwd: str, prompt: str) -> str | None:
    """Steering docs due for injection this turn.

    `always` docs go in unconditionally -- that is the contract, and it is what
    makes steering worth writing. `manual` docs go in only when the prompt names
    them as #<stem>, mirroring Kiro's reference syntax.

    Empty stubs are skipped: injecting "<!-- Fill this in -->" every turn would
    train the model to ignore the steering block entirely.
    """
    root = find_spec_root(cwd)
    if not root:
        return None

    docs = load_steering(root)
    if not docs:
        return None

    named = {m.lower() for m in re.findall(r"#([A-Za-z0-9._-]+)", prompt or "")}
    due = [
        d for d in docs
        if d["inclusion"] == "always"
        or (d["inclusion"] in ("manual", "auto") and d["stem"].lower() in named)
    ]
    body = render_steering(due)
    if not body:
        return None

    return ("Project steering (.spec/steering/, project-wide context every spec "
            "inherits):\n\n" + body)


def prompt_text(payload: dict) -> str:
    """The user's prompt, however this payload version happens to carry it."""
    for key in ("prompt", "user_prompt", "message"):
        v = payload.get(key)
        if isinstance(v, str):
            return v
    return ""


def emit(event: str, context: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": context,
        }
    }))


def run_hook() -> int:
    """Self-routing hook: behavior follows `hook_event_name` in the payload.

    One file serves both injection points so the phase model and the steering
    loader are stated once. Two hook scripts sharing this logic would drift, and
    a status line that disagrees with the gate is worse than none.

      UserPromptSubmit -> spec phase line + `always`/`#named` steering
      PostToolUse      -> `fileMatch` steering for the file just read

    fileMatch rides PostToolUse because that is the only point where the file
    actually being worked on is known. This mirrors how Claude Code's own
    path-scoped rules behave: they trigger on reading a matching file, not on
    every turn.
    """
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    event = payload.get("hook_event_name") or "UserPromptSubmit"
    cwd = payload.get("cwd") or os.getcwd()

    try:
        if event == "PostToolUse":
            path = (payload.get("tool_input") or {}).get("file_path") or ""
            root = find_spec_root(cwd) if path else None
            if not root:
                return 0
            due = [d for d in load_steering(root)
                   if steering_matches_path(d, path) and not d["empty"]]
            body = render_steering(due)
            if body:
                emit("PostToolUse",
                     f"Project steering matching {path}:\n\n{body}")
            return 0

        parts = []
        line = hook_line(cwd)
        if line:
            parts.append(line)
        steering = steering_context(cwd, prompt_text(payload))
        if steering:
            parts.append(steering)
        if parts:
            emit("UserPromptSubmit", "\n\n".join(parts))
    except Exception:
        return 0                          # never break a turn over context
    return 0


# --------------------------------------------------------------------------
# CLI mode
# --------------------------------------------------------------------------

def cmd_init() -> int:
    root = find_spec_root(os.getcwd())
    if root:
        print(f"Already spec-driven: {root}")
        return 0

    root = os.path.join(os.getcwd(), ".spec")
    os.makedirs(os.path.join(root, "steering"), exist_ok=True)
    os.makedirs(specs_dir(root), exist_ok=True)

    # The three foundation docs, matching Kiro. `inclusion: always` is the whole
    # point of steering -- these load into every turn once they have content.
    for name, heading, hint in (
        ("product.md", "Product", "Purpose, who uses it, key capabilities, what success means."),
        ("tech.md", "Tech", "Languages, frameworks, constraints, banned dependencies."),
        ("structure.md", "Structure", "Directory layout, naming, architectural decisions."),
    ):
        path = os.path.join(root, "steering", name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "---\ninclusion: always\n---\n\n"
                    f"# {heading}\n\n<!-- {hint} Empty stubs are NOT injected. -->\n"
                )

    gitignore = os.path.join(os.getcwd(), ".gitignore")
    try:
        existing = open(gitignore, encoding="utf-8").read() if os.path.exists(gitignore) else ""
        if ".spec/BYPASS" not in existing:
            with open(gitignore, "a", encoding="utf-8") as fh:
                fh.write("\n# spec gate escape hatch (local only)\n.spec/BYPASS\n")
    except OSError:
        pass                              # a missing gitignore is not fatal

    print(f"Initialized {root}")
    print("Steering docs are stubs at .spec/steering/ -- fill them in.")
    return 0


def cmd_new(args: list[str]) -> int:
    root = require_root()
    if not root:
        return 1
    if not args:
        return die("Usage: spec_state.py new <name> [--fix] [--scope GLOB ...]")

    name = args[0]
    if not NAME_OK.match(name):
        return die(f"Invalid spec name '{name}'. Use lowercase kebab-case, e.g. 'user-login'.")

    kind = "bugfix" if "--fix" in args else "feature"

    scope: list[str] = []
    if "--scope" in args:
        scope = [a for a in args[args.index("--scope") + 1:] if not a.startswith("--")]

    if load_state(root, name):
        return die(f"Spec '{name}' already exists. Use /spec-status to inspect it.")

    os.makedirs(os.path.join(specs_dir(root), name), exist_ok=True)
    write_json(state_path(root, name), {
        "feature": name,
        "kind": kind,
        "phase": "requirements",
        "approvals": {p: None for p in PHASES[:-1]},
        "scope": scope,
        "created": now(),
    })
    with open(os.path.join(root, "ACTIVE"), "w", encoding="utf-8") as fh:
        fh.write(name + "\n")

    artifact = FIRST_ARTIFACT[kind]
    print(f"Created spec '{name}' ({kind}), phase 'requirements'. ACTIVE set.")
    print(f"Next: draft .spec/specs/{name}/{artifact}, then the operator approves it.")
    return 0


def cmd_approve(args: list[str]) -> int:
    root = require_root()
    if not root:
        return 1

    feature, error = resolve_active(root)
    if not feature:
        return die(f"Cannot approve: {error}")

    state = load_state(root, feature)
    if state is None:
        return die(f"state.json for '{feature}' is missing or corrupt.")

    phase = args[0] if args and not args[0].startswith("--") else state.get("phase")
    if phase not in PHASES[:-1]:
        return die(f"'{phase}' is not an approvable phase. Choose one of: {', '.join(PHASES[:-1])}")

    if state.get("phase") != phase:
        return die(
            f"Spec '{feature}' is in phase '{state.get('phase')}', not '{phase}'. "
            f"Approve the current phase, or run advance first."
        )

    artifact = artifact_for(phase, state.get("kind", "feature")) or f"{phase}.md"
    artifact_path = os.path.join(specs_dir(root), feature, artifact)
    if not os.path.isfile(artifact_path):
        return die(
            f"Cannot approve '{phase}': .spec/specs/{feature}/{artifact} does not exist yet. "
            f"Draft it first."
        )

    # Existence is not content. An empty or still-boilerplate artifact approved
    # here would unlock the next phase on a promise nobody kept.
    try:
        with open(artifact_path, encoding="utf-8") as fh:
            body = fh.read()
    except OSError as exc:
        return die(f"Cannot approve '{phase}': {artifact} is unreadable ({exc}).")
    if is_stub_artifact(body):
        return die(
            f"Cannot approve '{phase}': .spec/specs/{feature}/{artifact} is empty or still "
            f"placeholder boilerplate. Draft it first."
        )

    # EARS is enforced only on the requirements lane, and only at approval --
    # drafting stays unimpeded, but an unfalsifiable requirement cannot be
    # signed off into a design.
    if phase == "requirements":
        bad = ears_violations(body)
        if bad:
            shown = "\n".join(f"    - {line}" for line in bad[:10])
            more = f"\n    ... and {len(bad) - 10} more" if len(bad) > 10 else ""
            return die(
                f"Cannot approve 'requirements': {len(bad)} requirement(s) are not valid EARS.\n"
                f"Use 'WHEN/IF/WHILE/WHERE <trigger>, THE <system> SHALL <response>' or the "
                f"ubiquitous 'THE <system> SHALL <response>'.\n"
                f"{shown}{more}"
            )

    state.setdefault("approvals", {})[phase] = now()
    write_json(state_path(root, feature), state)
    print(f"Approved '{phase}' for spec '{feature}'.")

    nxt = next_phase(phase)
    if nxt == "implement":
        print("All phases approved. Run advance to unlock source edits.")
    elif nxt:
        print(f"Next: run advance to move to '{nxt}', then draft {nxt}.md.")
    return 0


def cmd_advance() -> int:
    root = require_root()
    if not root:
        return 1

    feature, error = resolve_active(root)
    if not feature:
        return die(f"Cannot advance: {error}")

    state = load_state(root, feature)
    if state is None:
        return die(f"state.json for '{feature}' is missing or corrupt.")

    phase = state.get("phase")
    if phase == "implement":
        print(f"Spec '{feature}' is already in the implement phase.")
        return 0

    if not (state.get("approvals") or {}).get(phase):
        return die(
            f"Cannot advance: phase '{phase}' of spec '{feature}' is not approved. "
            f"The operator must run /spec-approve {phase} first. This is the gate."
        )

    # Check the whole prefix, not just the current phase. A spec advanced while
    # the gate was bypassed can otherwise sit at 'tasks' with no requirements.md
    # and nothing would ever notice.
    owed = missing_artifacts(root, feature, state)
    if owed:
        listed = ", ".join(owed)
        return die(
            f"Cannot advance: spec '{feature}' is missing or has empty artifact(s): {listed}. "
            f"Draft them under .spec/specs/{feature}/ first."
        )

    nxt = next_phase(phase)
    if not nxt:
        return die(f"Phase '{phase}' has no successor.")

    state["phase"] = nxt
    write_json(state_path(root, feature), state)
    print(f"Spec '{feature}' advanced to phase '{nxt}'.")
    if nxt == "implement":
        print("Source edits are now unlocked for this spec's scope.")
    else:
        print(f"Next: draft .spec/specs/{feature}/{nxt}.md, then the operator approves it.")
    return 0


def cmd_status(args: list[str]) -> int:
    full = "--full" in args
    for a in args:
        if a != "--full":
            return die(f"Unknown option '{a}' for status. Use: status [--full]")
    root = find_spec_root(os.getcwd())
    if not root:
        print("This repo is not spec-driven (no .spec/ directory). The gate is inactive here.")
        return 0

    print(f"Spec root : {root}")
    print(f"Bypassed  : {'YES -- the gate is disarmed' if is_bypassed(root) else 'no'}")
    print(f"ACTIVE    : {read_active(root) or '(unset)'}")

    # Steering is only useful if you can see what is actually reaching the model.
    docs = load_steering(root)
    if docs:
        print("\nSteering:")
        for d in docs:
            if d["empty"]:
                status = "EMPTY STUB -- not injected"
            elif d["inclusion"] == "always":
                status = f"injected every turn ({len(d['body'])} chars)"
            elif d["inclusion"] == "fileMatch":
                status = "on reading " + (", ".join(d["patterns"]) or "(no pattern set!)")
            elif d["inclusion"] == "auto":
                status = "auto is not implemented; behaves as manual (#" + d["stem"] + ")"
            else:
                status = f"manual only (reference as #{d['stem']})"
            mark = "" if d.get("declared") else "  <-- no frontmatter, defaulted"
            if d.get("unknown_mode"):
                mark = f"  <-- unknown mode {d['unknown_mode']!r}, defaulted"
            print(f"  {d['name']:<20} {d['inclusion']:<10} {status}{mark}")

        # The default is deliberate, not an accident, but a doc injected every
        # turn because nobody chose is still a doc nobody chose. Name the files
        # so the fix is a one-line edit rather than a hunt.
        undeclared = [d["name"] for d in docs
                      if not d.get("declared") or d.get("unknown_mode")]
        if undeclared:
            print(
                f"\n  WARNING: {len(undeclared)} steering doc(s) declare no usable "
                f"inclusion mode and default to 'always',\n"
                f"           so they are injected into every single turn: "
                f"{', '.join(undeclared)}.\n"
                f"           Add 'inclusion: always|fileMatch|manual' to the "
                f"frontmatter to choose deliberately."
            )
    else:
        print("\nSteering: none. .spec/steering/ is empty or missing.")

    names = list_specs(root)
    if not names:
        print("\nNo specs yet. Run /spec-new <name>.")
        return 0

    print("\nSpecs:")
    for name in names:
        state = load_state(root, name) or {}
        stamps = state.get("approvals") or {}
        marks = " ".join(f"{p}{'+' if stamps.get(p) else '-'}" for p in PHASES[:-1])
        print(f"  {name:<28} kind={state.get('kind','?'):<8} phase={state.get('phase','?'):<13} [{marks}]")
        if state.get("scope"):
            print(f"  {'':<28} scope={', '.join(state['scope'])}")
        if state.get("phase") == "implement":
            pending = unchecked_tasks(root, name)
            print(f"  {'':<28} tasks: {len(pending)} unchecked"
                  + (f"; next is {pending[0]}" if pending else ""))
        print_coverage(root, name, f"  {'':<28}", full)
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        return run_hook()

    command, args = argv[0], argv[1:]
    if command == "init":
        return cmd_init()
    if command == "new":
        return cmd_new(args)
    if command == "approve":
        return cmd_approve(args)
    if command == "advance":
        return cmd_advance()
    if command == "status":
        return cmd_status(args)
    return die(f"Unknown command '{command}'. Use: init | new | approve | advance | status")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
