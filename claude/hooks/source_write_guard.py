"""source_write_guard.py -- Python source is written with Write/Edit, never through a shell, and must compile.

NO GOVERNING SPEC. Basis: operator 2026-09-26, RL_V2 session ("You keep making this mistake. You need to
create a hook and/or steering file under ~/.claude to avoid this repeated failure").

The failure it closes: Python source assembled inside a Bash heredoc or a `python -c` / `python -` string
had its "\\n" escapes turned into real newlines on the way to disk. src/reward.py gained an unterminated
f-string (SyntaxError at line 1501), then the first "fix" -- another shell-built string -- did the same.
Two layers of quoting (bash, then Python) is where escapes die; the Write/Edit tools have none.

Two modes, one file:
  PreToolUse  (Bash)             -- deny a command that writes a *.py file via heredoc, redirect, tee, or
                                    an inline python program that opens a .py for writing.
  PostToolUse (Write|Edit|MultiEdit) -- py_compile the touched *.py; block with the SyntaxError if it fails.
"""
import json
import py_compile
import re
import sys

PY_TARGET = r"""[^\s'"<>|;&]+\.py\b"""
SHELL_WRITES = [
    re.compile(r">>?\s*['\"]?" + PY_TARGET),                       # cat > x.py / echo ... >> x.py
    re.compile(r"\btee\s+(-a\s+)?['\"]?" + PY_TARGET),             # ... | tee x.py
    re.compile(r"\bsed\s+-i\b[^|;&]*" + PY_TARGET),                # sed -i on source (escape-mangling too)
]
INLINE_PY = re.compile(r"\bpython[0-9.]*(\.exe)?\s+(-c\b|-\s*<<)")
OPEN_PY_FOR_WRITE = re.compile(r"""(open\([^)]*\.py['"][^)]*['"][wa]|\.py['"]\s*,\s*['"][wa]|write_text\()""")

DENY = ("Python source must be written with the Write or Edit tool, not through the shell. "
        "Heredocs, redirects, tee, sed -i and inline `python -c`/`python -` programs add a second quoting "
        "layer that turns \\n escapes into real newlines (src/reward.py, 2026-09-26: unterminated f-string, "
        "twice). Use Write for a new file, Edit for a change. Scratch data files (.json/.txt/.log) are fine.")


def pre(tool_input: dict) -> None:
    cmd = tool_input.get("command", "") or ""
    hit = any(p.search(cmd) for p in SHELL_WRITES)
    if not hit and INLINE_PY.search(cmd) and OPEN_PY_FOR_WRITE.search(cmd) and re.search(PY_TARGET, cmd):
        hit = True
    if hit:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": DENY}}))


def post(tool_input: dict) -> None:
    path = tool_input.get("file_path", "") or ""
    if not path.endswith(".py"):
        return
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as exc:
        print(json.dumps({"decision": "block",
                          "reason": f"{path} does not compile after this edit -- fix it before anything else:\n{exc.msg}"}))


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return
    tool, tool_input = event.get("tool_name", ""), event.get("tool_input", {}) or {}
    if event.get("hook_event_name") == "PreToolUse" and tool == "Bash":
        pre(tool_input)
    elif event.get("hook_event_name") == "PostToolUse" and tool in {"Write", "Edit", "MultiEdit"}:
        post(tool_input)


if __name__ == "__main__":
    main()
