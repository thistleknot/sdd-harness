#!/usr/bin/env python3
"""UserPromptSubmit router: send every plan request through the plan-do skill.

Thesis
------
A plan written straight into a chat is a localized plan with no critique behind it.
This hook makes the plan-do skill the entry point for any plan request, so the three
tracking artifacts exist before a localized plan is applied: `plan.md` (objective,
dependency order, acceptance, approach), `critique.md` (dated evidence receipts) and
`critique-todo.md` (OPEN -> DOING -> DONE burndown). Routing is advisory context,
not a write gate.

Spec: ~/.skills/plan-do/SKILL.md (the workflow this routes to).
Task: none. Operator request 2026-11-06: route to "the plan-todo skill" whenever a
downstream harness plans. No skill named plan-todo exists in the skill roots; plan-do
owns exactly the three artifacts requested, so it is the target.

Require   - stdin is the UserPromptSubmit JSON payload (prompt, cwd); absent or malformed
            input is a no-op.
Guarantee - when the prompt is a plan request, stdout carries one hookSpecificOutput
            JSON object naming the skill, its path, and which of the three artifacts
            exist under <root>/.tmp/. Otherwise stdout is empty.
Maintain  - read-only: this hook never creates, edits or deletes a file.
Assert    - exit code 0 always.

Failure modes
-------------
- HARNESS_HOOKS_ENABLED=0 -> silent no-op (shared kill switch in _common.disabled).
- Subagent payloads (agent_id / agent_type set) -> no-op: a dispatched worker was
  already briefed by the Leader and must not re-route itself.
- No git root -> the payload cwd is the root.
- Prompts that say "architect" are NOT matched: that keyword belongs to
  ~/.claude/hooks/playbook.py, which writes playbook.md, a different artifact.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import disabled

SKILL_PATH = Path.home() / ".skills" / "plan-do" / "SKILL.md"
ARTIFACTS = ("plan.md", "critique.md", "critique-todo.md")

# Narrow on purpose: a bare "plan" appears in ordinary prose ("the plan is fine")
# and every false positive injects a paragraph of context. Each alternative needs
# an explicit request verb or a plan-as-action phrase.
PLAN_REQUEST_RE = re.compile(
    r"^\s*/plan\b"
    r"|\b(?:make|write|draft|create|build|give me|come up with|propose|lay out|sketch"
    r"|sequence|outline)\s+(?:me\s+)?(?:a|an|the|some)?\s*(?:implementation\s+|detailed\s+)?plan\b"
    r"|\bplan (?:this|it|out|for how|the)\b"
    r"|\b(?:let.s|please|can you|could you|go)\s+plan\b"
    r"|\bplan mode\b",
    re.IGNORECASE,
)


def _root(cwd: str) -> str:
    """Resolve the project root: the git toplevel when inside a repo, else cwd.

    Require: cwd is a directory path string.
    Guarantee: returns an absolute path; falls back to cwd on any git failure.
    """
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.abspath(cwd)


def _artifact_state(tmp: Path) -> str:
    """Name which plan-do artifacts already exist in the scratch folder.

    Require: tmp is the <root>/.tmp directory (may be absent).
    Guarantee: returns one line naming present and missing artifacts; read-only.
    """
    present = [a for a in ARTIFACTS if (tmp / a).is_file()]
    missing = [a for a in ARTIFACTS if a not in present]
    if not missing:
        return "All three plan-do artifacts exist: %s." % ", ".join(ARTIFACTS)
    return ("Present: %s. Missing: %s. Create the missing ones before the localized plan."
            % (", ".join(present) or "none", ", ".join(missing)))


def main() -> int:
    """Read the prompt payload from stdin and emit routing context on a match.

    Guarantee: exit 0; stdout is one JSON object on a match, empty otherwise.
    """
    if disabled():
        return 0
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if payload.get("agent_id") or payload.get("agent_type"):
        return 0
    prompt = payload.get("prompt") or ""
    if not PLAN_REQUEST_RE.search(prompt):
        return 0

    tmp = Path(_root(payload.get("cwd") or os.getcwd())) / ".tmp"
    text = (
        "PLAN REQUEST DETECTED. Route through the plan-do skill before writing any "
        "localized plan.\n"
        "  1. Read %s and follow it.\n"
        "  2. Keep the three artifacts in %s: plan.md (objective, dependency order, "
        "acceptance, chosen approach), critique.md (dated evidence receipts), "
        "critique-todo.md (OPEN -> DOING -> DONE items).\n"
        "  3. Do not apply a localized plan until all three exist and plan.md states "
        "the approach.\n"
        "  %s"
        % (SKILL_PATH, tmp, _artifact_state(tmp))
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": text,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
