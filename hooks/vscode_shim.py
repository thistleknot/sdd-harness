"""hooks/vscode_shim.py -- run the Claude Code hooks from VS Code Copilot.

Spec: no governing requirement. Basis: operator 2026-10-06 ("hooks and rules are
core to this whole harness"). Task: specs store #63. Promote to a REQ before
this is depended on.

VS Code Local hooks send a Claude-shaped envelope (session_id, cwd, tool_name,
tool_input, prompt, ...) but ignore matchers and name their tools differently
(replace_string_in_file, create_file, run_in_terminal). The harness hooks key on
Claude names and `file_path`, so VS Code is pointed at this shim, once per event:

    python vscode_shim.py <Event>      # payload on stdin

The shim maps the tool name and input to Claude's, re-applies the matcher from
~/.claude/settings.json, runs the matching commands with the translated payload,
and folds their verdicts back into VS Code's output contract
(PreToolUse: hookSpecificOutput.permissionDecision; other blocks: exit 2).

Require: ~/.claude/settings.json holds the hooks; payload JSON on stdin.
Guarantee: every raw payload is appended to .tmp/vscode-hook-audit.jsonl first,
           so the tool-name map can be checked against what VS Code really sends.
Maintain: fail open -- any shim error exits 0 rather than wedging the editor.
Not ported: transcript-dependent hooks (SKIP) and SessionEnd (no VS Code event).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import disabled  # noqa: E402

SETTINGS = Path.home() / ".claude" / "settings.json"
AUDIT = Path(__file__).resolve().parent.parent / ".tmp" / "vscode-hook-audit.jsonl"

# Read Claude's JSONL transcript, which VS Code does not write.
SKIP = ("verify_gate.py", "session_handoff.py")

# VS Code tool name -> Claude tool name. UNVERIFIED against a live session:
# the audit log is how this table gets corrected.
TOOL_MAP = {
    "replace_string_in_file": "Edit", "multi_replace_string_in_file": "Edit",
    "insert_edit_into_file": "Edit", "editFiles": "Edit", "apply_patch": "Edit",
    "create_file": "Write", "createFile": "Write",
    "edit_notebook_file": "NotebookEdit",
    "run_in_terminal": "Bash", "runInTerminal": "Bash", "run_command": "Bash",
    "read_file": "Read", "readFile": "Read",
}

PATH_KEYS = ("file_path", "filePath", "path", "uri")
PATCH_HEADER = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.MULTILINE)
RENAMES = {"content": "content", "oldString": "old_string", "newString": "new_string"}


def translate(payload: dict) -> dict:
    """Return a copy of the payload with Claude's tool name and input keys."""
    out = dict(payload)
    raw = payload.get("tool_name")
    if not raw:
        return out
    out["tool_name"] = TOOL_MAP.get(raw, raw)
    src = payload.get("tool_input")
    if not isinstance(src, dict):
        return out
    tool_input = dict(src)
    path = next((src[k] for k in PATH_KEYS if isinstance(src.get(k), str) and src[k]), "")
    if not path and isinstance(src.get("replacements"), list) and src["replacements"]:
        first = src["replacements"][0]
        path = next((first[k] for k in PATH_KEYS if isinstance(first, dict) and first.get(k)), "")
    if not path and isinstance(src.get("input"), str):
        found = PATCH_HEADER.search(src["input"])
        path = found.group(1).strip() if found else ""
    if path:
        tool_input["file_path"] = path
    for vs_key, claude_key in RENAMES.items():
        if vs_key in src:
            tool_input[claude_key] = src[vs_key]
    out["tool_input"] = tool_input
    return out


def audit(event: str, payload: dict, mapped: dict) -> None:
    """Append what VS Code actually sent; never raises."""
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        tool_input = payload.get("tool_input")
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event,
            "raw_tool": payload.get("tool_name"),
            "mapped_tool": mapped.get("tool_name"),
            "input_keys": sorted(tool_input) if isinstance(tool_input, dict) else None,
            "payload_keys": sorted(payload),
        }
        with AUDIT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def commands_for(event: str, raw_tool: str | None, claude_tool: str | None) -> list[dict]:
    """Hook entries for the event whose matcher accepts the tool, minus SKIP."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    found: list[dict] = []
    for group in settings.get("hooks", {}).get(event, []):
        matcher = group.get("matcher")
        if matcher and not any(t and re.search(matcher, t) for t in (claude_tool, raw_tool)):
            continue
        for hook in group.get("hooks", []):
            command = hook.get("command") or ""
            if command and not any(name in command for name in SKIP):
                found.append(hook)
    return found


def run_hook(hook: dict, payload: dict) -> tuple[int, str, str]:
    """Run one command with the translated payload on stdin."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=payload.get("cwd") or os.getcwd())
    try:
        done = subprocess.run(
            hook["command"], input=json.dumps(payload), shell=True, text=True,
            capture_output=True, timeout=hook.get("timeout") or 30,
            cwd=payload.get("cwd") or None, env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 0, "", f"vscode_shim: {hook['command'][:80]} skipped ({exc.__class__.__name__})"
    return done.returncode, done.stdout, done.stderr


def fold(event: str, results: list[tuple[int, str, str]]) -> tuple[dict, int, str]:
    """Merge hook results into (stdout JSON, exit code, stderr text)."""
    deny: list[str] = []
    block: list[str] = []
    context: list[str] = []
    messages: list[str] = []
    for code, stdout, stderr in results:
        if code == 2:
            block.append(stderr.strip() or "blocked by hook")
            continue
        text = stdout.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            context.append(text)            # plain stdout is context on session/prompt events
            continue
        if not isinstance(data, dict):
            continue
        spec = data.get("hookSpecificOutput") or {}
        if spec.get("permissionDecision") == "deny":
            deny.append(spec.get("permissionDecisionReason") or "denied by hook")
        if data.get("decision") == "block":
            (deny if event == "PreToolUse" else block).append(data.get("reason") or "blocked by hook")
        for extra in (spec.get("additionalContext"), data.get("additionalContext")):
            if extra:
                context.append(str(extra))
        if data.get("systemMessage"):
            messages.append(str(data["systemMessage"]))

    out: dict = {}
    spec_out: dict = {"hookEventName": event}
    if deny:
        spec_out.update(permissionDecision="deny", permissionDecisionReason="\n".join(deny))
    if context:
        spec_out["additionalContext"] = "\n\n".join(context)
    if len(spec_out) > 1:
        out["hookSpecificOutput"] = spec_out
    if messages:
        out["systemMessage"] = "\n".join(messages)
    if block:
        return out, 2, "\n".join(block)
    return out, 0, ""


def main() -> int:
    if disabled():
        return 0
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        event = event or payload.get("hook_event_name", "")
        mapped = translate(payload)
        audit(event, payload, mapped)
        hooks = commands_for(event, payload.get("tool_name"), mapped.get("tool_name"))
        results = [run_hook(h, mapped) for h in hooks]
        out, code, err = fold(event, results)
    except Exception as exc:  # fail open: never wedge the editor
        print(f"vscode_shim: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 0
    if out:
        print(json.dumps(out))
    if err:
        print(err, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
