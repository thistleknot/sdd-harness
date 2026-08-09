"""PreCompact hook: backup transcript/context before compaction.

Purpose: preserve the full conversation state before Claude Code compacts
context, so continuity survives context window resets. Writes a timestamped
backup to ~/memory-bank/compaction-backups/.

Preconditions: hook registered on PreCompact event in settings.json.
Failure modes: any error → exit 0 (fail-open, never block compaction).
"""
import json
import os
import sys
import time
from pathlib import Path

BACKUP_DIR = Path(os.path.expanduser("~/memory-bank/compaction-backups"))


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    session_id = payload.get("session_id", "unknown")[:12]

    backup_path = BACKUP_DIR / f"pre-compact-{timestamp}-{session_id}.json"
    backup_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )

    # Emit context so the agent knows the backup happened
    print(
        json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": f"[pre-compact] Transcript backed up to {backup_path.name}"
            }
        })
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
