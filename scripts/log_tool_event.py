"""log_tool_event.py — PostToolUse hook that appends mechanical event records to JSONL.

Receives session context JSON on stdin from the Kiro hook system.
Appends one line per tool invocation to .harness/events/tool-events.jsonl.

Design principles (session-cartographer inspired):
  - Mechanical ground truth: logs what happened, not what the agent thinks happened
  - Provider-neutral: works across Kiro, Claude Code, Codex
  - No LLM calls, no network — pure local append
  - Failures are silent (exit 0) so a broken log never blocks the agent
  - Secrets filtered: strips env vars, auth headers, file contents over 200 chars

The JSONL file is the single source of truth. Everything else (search, analysis,
co-occurrence, failure detection) is a read-only consumer of this log.
"""
from __future__ import annotations

import json
import os
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

EVENTS_DIR = Path(
    os.environ.get("HARNESS_EVENTS_DIR")
    or Path(__file__).resolve().parent.parent / "events"
)
LOG_FILE = EVENTS_DIR / "tool-events.jsonl"

# Tools whose results are too noisy or contain secrets
SKIP_RESULT_TOOLS = frozenset({
    "read_file", "read_files", "read_code", "web_fetch",
    "remote_web_search", "get_process_output",
})

# Fields to never log from tool arguments
REDACT_FIELDS = frozenset({
    "env", "token", "password", "secret", "key", "authorization",
})

MAX_RESULT_LEN = 500
MAX_ARG_LEN = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _redact_args(args: dict) -> dict:
    """Shallow redaction of sensitive fields and long values."""
    cleaned = {}
    for k, v in args.items():
        if k.lower() in REDACT_FIELDS:
            cleaned[k] = "<redacted>"
        elif isinstance(v, str) and len(v) > MAX_ARG_LEN:
            cleaned[k] = v[:MAX_ARG_LEN] + f"...[{len(v)} chars]"
        else:
            cleaned[k] = v
    return cleaned


def _truncate_result(result: str, tool_name: str) -> str | None:
    """Truncate or skip result based on tool type."""
    if tool_name in SKIP_RESULT_TOOLS:
        return None  # don't log content of reads
    if not result:
        return None
    if len(result) > MAX_RESULT_LEN:
        return result[:MAX_RESULT_LEN] + f"...[{len(result)} chars]"
    return result


def _event_id(tool_name: str, timestamp: str, session_id: str) -> str:
    """Deterministic event ID for dedup."""
    raw = f"{tool_name}:{timestamp}:{session_id}"
    return "evt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def process_stdin():
    """Read hook context from stdin and append event."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        ctx = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return  # malformed input, silent exit

    # Extract fields from the hook context
    # Kiro PostToolUse sends: toolName, toolInput, toolOutput, sessionId, etc.
    tool_name = ctx.get("toolName") or ctx.get("tool_name") or "unknown"
    tool_input = ctx.get("toolInput") or ctx.get("tool_input") or {}
    tool_output = ctx.get("toolOutput") or ctx.get("tool_output") or ""
    session_id = ctx.get("sessionId") or ctx.get("session_id") or os.environ.get("KIRO_SESSION_ID", "unknown")
    
    # Build the event record
    timestamp = _now_iso()
    event = {
        "event_id": _event_id(tool_name, timestamp, session_id),
        "timestamp": timestamp,
        "type": "tool_use",
        "tool": tool_name,
        "session_id": session_id,
        "harness": "kiro",
        "project": os.environ.get("KIRO_WORKSPACE", Path.cwd().name),
    }

    # Add redacted args (skip for tools with huge inputs like fs_write)
    if isinstance(tool_input, dict):
        args = _redact_args(tool_input)
        # For file operations, keep the path but not the content
        if "path" in args:
            event["target_file"] = args["path"]
        if "command" in args:
            event["command"] = args["command"][:200] if isinstance(args["command"], str) else str(args["command"])[:200]
        # Store summary of what was done, not full args
        event["args_summary"] = {k: v for k, v in args.items()
                                  if k in ("path", "query", "command", "url", "oldStr", "name", "action")}

    # Truncated result (skip for read-heavy tools)
    result_summary = _truncate_result(
        tool_output if isinstance(tool_output, str) else json.dumps(tool_output)[:MAX_RESULT_LEN],
        tool_name
    )
    if result_summary:
        event["result_summary"] = result_summary

    # Write atomically
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        process_stdin()
    except Exception:
        # Never crash, never block the agent
        pass
    sys.exit(0)
