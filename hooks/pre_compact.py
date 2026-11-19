"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| READ | Read hook payload and transcript source when present | [mandatory] | R1 |
| BACKUP | Persist original payload in compaction-backups | [mandatory] | R1 |
| INDEX | Store bounded transcript chunks as session-scoped memory-index records | [opt] | R2-R4 |
| EMIT | Tell the host which local backup was written | [contract] | R1 |

R1: WHEN PreCompact runs, the hook shall persist its payload and never block compaction.
R2: WHEN transcript_path, cwd and session_id are available, the hook shall index source chunks under the canonical workspace and session.
R3: IF indexing fails, THEN payload backup still succeeds and the hook exits successfully.
R4: WHEN a transcript exceeds the memory-index record limit, the hook shall split it into ordered chunks without dropping lines.
CLOSED: A second transcript database is rejected because memory-index already provides raw evidence, scope authorization and search/open.
Preconditions: hook is registered for PreCompact; optional memory-index source is installed at ~/.mcp/memory-index.
Failure modes: payload or filesystem errors retain fail-open behavior; indexing errors do not block compaction.
"""
import json
import os
import sys
import time
from pathlib import Path

import sys as _ks
_ks.path.insert(0, str(Path(__file__).parent))
from _common import disabled

BACKUP_DIR = Path(os.path.expanduser("~/memory-bank/compaction-backups"))
MEMORY_INDEX = Path.home() / ".mcp" / "memory-index"
MEMORY_DB = Path.home() / "memory-bank" / "conversations.sqlite3"
MAX_RECORD_CHARS = 60000


def index_transcript(payload: dict) -> int:
    """Persist transcript chunks as scoped, searchable source records.

    Require: payload has transcript_path, cwd and session_id; memory-index source exists.
    Guarantee: each chunk has a session-scoped record linked to immutable raw evidence.
    Maintain: chunk order and all transcript lines are preserved.
    Assert: no record exceeds the memory-index 65,536-character bound.

    Returns:
        Number of indexed chunks, or zero when required context is absent.
    """
    transcript_path = Path(str(payload.get("transcript_path") or ""))
    workspace = str(payload.get("cwd") or "")
    session_id = str(payload.get("session_id") or "")
    if not transcript_path.is_file() or not workspace or not session_id or not MEMORY_INDEX.is_dir():
        return 0

    sys.path.insert(0, str(MEMORY_INDEX))
    import conversation_store as convstore

    conn = convstore.connect(MEMORY_DB)
    count = 0
    current = ""
    try:
        with transcript_path.open("r", encoding="utf-8") as source:
            for line in source:
                remaining = line
                while remaining:
                    room = MAX_RECORD_CHARS - len(current)
                    current += remaining[:room]
                    remaining = remaining[room:]
                    if len(current) == MAX_RECORD_CHARS:
                        count += 1
                        body = current
                        convstore.write_record(
                            conn,
                            f"PreCompact transcript {session_id[:12]} part {count}",
                            body,
                            mtype="reference",
                            description="Raw transcript chunk captured before compaction.",
                            workspace_root=workspace,
                            scope="session",
                            session_id=session_id,
                            harness_id="claude",
                            source_ref=f"{transcript_path}#part={count}",
                            origin="document",
                            epistemic="observed",
                            memory_function="experiential",
                        )
                        current = ""
        if current:
            count += 1
            convstore.write_record(
                conn,
                f"PreCompact transcript {session_id[:12]} part {count}",
                current,
                mtype="reference",
                description="Raw transcript chunk captured before compaction.",
                workspace_root=workspace,
                scope="session",
                session_id=session_id,
                harness_id="claude",
                source_ref=f"{transcript_path}#part={count}",
                origin="document",
                epistemic="observed",
                memory_function="experiential",
            )
    finally:
        conn.close()
    return count


def main():
    """Back up the PreCompact payload and index transcript evidence when available.

    Require: hook payload is JSON on stdin; optional indexing needs transcript, workspace and session.
    Guarantee: payload backup remains the primary fail-open action.
    Maintain: indexing errors never block host compaction.
    Assert: optional records are written through memory-index scope validation.
    """
    if disabled():
        return 0
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

    try:
        indexed = index_transcript(payload)
    except Exception:
        indexed = 0

    # Emit context so the agent knows the backup happened
    print(
        json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": f"[pre-compact] Transcript backed up to {backup_path.name}; indexed {indexed} source chunk(s)"
            }
        })
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
