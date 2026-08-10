#!/usr/bin/env python3
"""Lifecycle hook: append every session event to the capture store.

Thesis
------
This is deliberately the thinnest possible hook. All schema and policy live in
`memory-index/events_store.py` so there is exactly one owner; this file resolves
that module, hands it stdin, and exits 0 no matter what happens.

Why Python and not PowerShell
-----------------------------
Same constraint `membank.py` documents: Claude Code runs hook command strings
through a POSIX-ish shell here, which strips Windows backslashes from the path,
and `pwsh` resolves to an unreliable WindowsApps stub. Invoke as:
`python C:/Users/user/.claude/hooks/log_event.py` (forward slashes).

Contract
--------
Require   - nothing. Absent store, absent module, malformed payload are all
            valid states.
Guarantee - exit code 0, always. Stdout stays EMPTY: this hook runs on
            PreToolUse/PostToolUse, where stdout is fed back to the model, and a
            capture hook has nothing to say to the model.
Maintain  - no session is ever blocked, slowed past one local SQLite write, or
            shown an error from the memory layer.
Assert    - failures are reported on stderr only, once, without a traceback.

Failure modes
-------------
- `events_store` unimportable (skills repo moved) -> silent exit 0. The path is
  resolved at call time rather than pinned in settings.json so a moved repo
  degrades to no-capture instead of an error on every event.
- DB locked or read-only -> `log_event` returns False, nothing printed.
- Running inside the dream pass's own `claude -p` -> no-op by design.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

STORE_DIR = Path.home() / "Documents" / "dev" / "skills" / "memory-index"


def main() -> int:
    if str(STORE_DIR) not in sys.path:
        sys.path.insert(0, str(STORE_DIR))
    try:
        import events_store
    except Exception:
        return 0

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if not isinstance(data, dict):
        return 0

    events_store.log_event(data)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a capture hook must never break a session
        print(f"[log_event] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(0)
