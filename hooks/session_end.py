"""SessionEnd hook: auto-update last_session.md with session summary.

Purpose: capture what was worked on before the session closes, so the next
session can resume context without manual effort. Appends a timestamped
entry to ~/memory-bank/projects/<repo>/last_session.md (or global if no repo).

Preconditions: hook registered on Stop event in settings.json.
Failure modes: any error → exit 0 (fail-open).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MEMORY_DIR = Path(os.path.expanduser("~/memory-bank"))
MAX_LINES = 50


def get_git_root():
    """Get the git root of CWD, or None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except Exception:
        pass
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    repo = get_git_root()
    if repo:
        target = MEMORY_DIR / "projects" / repo / "last_session.md"
    else:
        target = MEMORY_DIR / "last_session.md"

    target.parent.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%d %H:%M")
    session_id = payload.get("session_id", "unknown")[:12]

    # Build a minimal entry from what we know
    entry = f"\n### {timestamp} (session {session_id})\n"
    entry += "- Session ended (auto-logged by session_end hook)\n"

    # Append to file, cap at MAX_LINES
    if target.exists():
        lines = target.read_text(encoding="utf-8").splitlines()
    else:
        lines = ["# Last Session"]

    lines.extend(entry.splitlines())

    # Keep only the last MAX_LINES
    if len(lines) > MAX_LINES:
        lines = lines[:1] + lines[-(MAX_LINES - 1):]

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
