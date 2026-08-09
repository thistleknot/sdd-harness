"""PostToolUse hook: log files written this turn for batched review.

Purpose: records each file path written by Edit/Write/MultiEdit into
.git/.turn_writes so the Stop-hook reviewer can diff only this turn's changes.

Preconditions: registered on PostToolUse with matcher ^(Edit|Write|MultiEdit)$
Failure modes: any error -> exit 0 (fail-open, never block writes).
"""
import json
import sys
from pathlib import Path

import sys as _ks
_ks.path.insert(0, str(Path(__file__).parent))
from _common import disabled

TURN_LOG = Path(".git/.turn_writes")


def main():
    if disabled():
        return 0
    payload = {}
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            payload = json.loads(raw) if raw.strip() else {}
        except Exception:
            pass

    # Extract file path from tool input
    tool_input = payload.get("tool_input", {})
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("filePath")
        or ""
    )

    if not file_path:
        return 0

    # Append to turn log (one path per line, deduped on read)
    try:
        TURN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with TURN_LOG.open("a", encoding="utf-8") as f:
            f.write(file_path + "\n")
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
