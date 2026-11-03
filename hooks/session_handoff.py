"""| Stage | Mechanism | Contract |
| INTEGRATE | Append project-tagged archives without overwriting authored prompts | [mandatory] R1,R2,R9 |

Spec: docs/playbooks/memory-and-harness-integration.md R1,R2,R9.
CLOSED: parallel registries or writers for the same feature.
Preconditions and failure modes: see the governing spec and incumbent contract below.

Session Handoff: package context into prompt.md for cross-session continuity.

Purpose: when context is getting heavy or a logical breakpoint is reached,
generate a prompt.md that captures the current state so the next session
(or a fresh continuation) can resume without loss.

Three disposition modes:
  migrate  — write prompt.md, signal agent to re-read it as seed context
  close    — task complete, archive final state, no continuation expected
  handoff  — write prompt.md + conversation.log ref, signal "next session picks up"

Usage:
  # As a hook (Stop trigger):
  Receives JSON on stdin with session context.

  # As standalone (agent-invoked):
  python session_handoff.py --mode handoff --workspace <path> --objective "..." --state "..."

  # Agent can also pipe structured JSON:
  echo '{"mode":"handoff","objective":"...","state":{...}}' | python session_handoff.py

Preconditions: workspace or project path resolvable.
Failure modes: any error → exit 0 (fail-open, never block session end).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import sys as _ks
_ks.path.insert(0, str(Path(__file__).parent))
from _common import disabled

sys.path.insert(0, str(Path.home() / '.skills' / 'memory-index'))
from conversation_store import project_identity

MEMORY_DIR = Path(os.path.expanduser("~/memory-bank"))
HANDOFF_DIR = MEMORY_DIR / "handoffs"


def derive_objective(transcript_path: str | None) -> str:
    """Recover the operator's stated objective from the session transcript.

    NO GOVERNING SPEC. Basis: operator instruction 2026-09-12 — "when you do the
    obvious hook I want you to also carry forward the identified users objective
    intent", after a handoff emitted `## Objective\n[not specified]`. Root cause:
    the Stop payload Claude Code sends carries no `objective` key, so the merge at
    `objective = args.objective or payload.get("objective", "")` was always empty
    in hook mode. It does carry `transcript_path`, which nothing read.

    Returns the first substantive operator turn (the stated objective) and, when the
    latest turn has moved on, that too — so a resumed session sees both what the work
    was for and where it had got to. Empty string if nothing usable.
    """
    if not transcript_path:
        return ""
    try:
        p = Path(transcript_path)
        if not p.is_file():
            return ""
        turns: list[str] = []
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") != "user" or rec.get("isMeta"):
                    continue
                content = (rec.get("message") or {}).get("content")
                if isinstance(content, list):
                    # A list payload carrying tool_result blocks is the harness
                    # replying to itself, not the operator speaking.
                    if any(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content
                    ):
                        continue
                    content = " ".join(
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                if not isinstance(content, str):
                    continue
                text = _strip_injected(content).strip()
                # Slash-command envelopes and bare hook echoes are not intent.
                if not text or text.startswith("<command-") or len(text) < 12:
                    continue
                turns.append(" ".join(text.split()))
        if not turns:
            return ""
        first = turns[0][:400]
        if len(turns) > 1 and turns[-1][:400] != first:
            return f"{first}\n\nLatest focus: {turns[-1][:400]}"
        return first
    except Exception:
        return ""


# Envelopes that arrive on a "user" record but are the harness talking to itself:
# hook injections, slash-command echoes and stdout, and background-task notifications.
# Verified against real transcripts 2026-09-12 — without these, a handoff objective
# reads "<local-command-stdout>Goal set: ..." or a raw <task-notification> block.
_ENVELOPE_TAGS = (
    "system-reminder",
    "local-command-stdout",
    "local-command-caveat",
    "command-name",
    "command-message",
    "command-args",
    "task-notification",
)
_ENVELOPE_RE = re.compile(
    r"<(" + "|".join(_ENVELOPE_TAGS) + r")\b[^>]*>.*?</\1\s*>|<(?:" + "|".join(_ENVELOPE_TAGS) + r")\b[^>]*>.*",
    re.DOTALL | re.IGNORECASE,
)


def _strip_injected(text: str) -> str:
    """Drop harness-injected blocks so only the operator's own words remain."""
    return _ENVELOPE_RE.sub(" ", text)


def get_git_root(cwd: str | None = None) -> str | None:
    """Get the git repo name from CWD."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
            cwd=cwd,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except Exception:
        pass
    return None


def get_git_diff_summary(cwd: str | None = None) -> str:
    """Get a short summary of uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=cwd,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def get_recent_commits(cwd: str | None = None, n: int = 5) -> str:
    """Get last N commit onelines for context."""
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=10,
            cwd=cwd,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def build_prompt_md(
    mode: str,
    objective: str,
    state: dict,
    decisions: list[str],
    files_touched: list[str],
    next_steps: list[str],
    blockers: list[str] | None = None,
    conversation_log: str | None = None,
    git_context: dict | None = None,
) -> str:
    """Build the prompt.md content."""
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    lines = []

    # Header with disposition
    lines.append(f"# Session Handoff — {mode.upper()}")
    lines.append(f"Generated: {timestamp}")
    lines.append(f"Mode: {mode}")
    if conversation_log:
        lines.append(f"Conversation log: {conversation_log}")
    lines.append("")

    # Objective
    lines.append("## Objective")
    lines.append(objective or "[not specified]")
    lines.append("")

    # Current state
    lines.append("## State")
    done = state.get("done", [])
    in_progress = state.get("in_progress", [])
    pending = state.get("pending", [])
    blocked = state.get("blocked", [])

    if done:
        lines.append("### Done")
        for item in done:
            lines.append(f"- [x] {item}")
        lines.append("")
    if in_progress:
        lines.append("### In Progress")
        for item in in_progress:
            lines.append(f"- [~] {item}")
        lines.append("")
    if pending:
        lines.append("### Pending")
        for item in pending:
            lines.append(f"- [ ] {item}")
        lines.append("")
    if blocked:
        lines.append("### Blocked")
        for item in blocked:
            lines.append(f"- [!] {item}")
        lines.append("")

    # Key decisions (don't re-litigate)
    if decisions:
        lines.append("## Key Decisions (settled)")
        for d in decisions:
            lines.append(f"- {d}")
        lines.append("")

    # Files touched
    if files_touched:
        lines.append("## Files Touched")
        for f in files_touched:
            lines.append(f"- `{f}`")
        lines.append("")

    # Git context
    if git_context:
        if git_context.get("diff_summary"):
            lines.append("## Uncommitted Changes")
            lines.append("```")
            lines.append(git_context["diff_summary"])
            lines.append("```")
            lines.append("")
        if git_context.get("recent_commits"):
            lines.append("## Recent Commits")
            lines.append("```")
            lines.append(git_context["recent_commits"])
            lines.append("```")
            lines.append("")

    # Blockers
    if blockers:
        lines.append("## Blockers")
        for b in blockers:
            lines.append(f"- {b}")
        lines.append("")

    # Next steps (the resume point)
    lines.append("## Next Steps")
    if next_steps:
        for i, step in enumerate(next_steps, 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("[no explicit next steps — review state above]")
    lines.append("")

    # Instructions for the receiving session
    if mode == "handoff":
        lines.append("---")
        lines.append("## Resumption Instructions")
        lines.append("This is a handoff from a prior session. The context above is your starting state.")
        lines.append("Do NOT re-derive decisions marked as settled. Resume from Next Steps.")
        lines.append("If blockers are listed, address those first.")
        lines.append("")
    elif mode == "migrate":
        lines.append("---")
        lines.append("## Migration Note")
        lines.append("Context was migrated mid-session to avoid rot. Continue working from Next Steps.")
        lines.append("")
    elif mode == "close":
        lines.append("---")
        lines.append("## Closure")
        lines.append("Task is complete. This file serves as archival reference only.")
        lines.append("")

    return "\n".join(lines)


def resolve_output_path(workspace: str | None, mode: str) -> Path:
    """Choose a canonical-project archive without overwriting human prompt.md.

    Require: explicit existing workspace; mode has been validated by the caller.
    Guarantee: projects with equal basenames use different archives.
    Maintain: common Git worktrees share project continuity.
    Assert: closed archives cannot become automatic resume candidates.
    """
    identity = project_identity(workspace or '')
    key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    directory = HANDOFF_DIR / 'projects' / key
    directory.mkdir(parents=True, exist_ok=True)
    prefix = 'closed' if mode == 'close' else 'prompt'
    return directory / f'{prefix}-{time.time_ns()}.md'


def main():
    if disabled() or os.environ.get('RSI_EVALUATION'):
        return 0
    # Try to read from stdin first (hook mode)
    payload = {}
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            payload = json.loads(raw) if raw.strip() else {}
        except Exception:
            pass

    # Guard: if Stop hook is re-firing (blocking loop), exit silently.
    # Claude Code sets stop_hook_active=true on re-entrant Stop invocations.
    if payload.get("stop_hook_active"):
        return 0

    # CLI args override payload
    parser = argparse.ArgumentParser(description="Session handoff: generate prompt.md")
    parser.add_argument("--mode", choices=["migrate", "close", "handoff"], default=None)
    parser.add_argument("--workspace", type=str, default=None)
    parser.add_argument("--objective", type=str, default=None)
    parser.add_argument("--state", type=str, default=None, help="JSON string of state dict")
    parser.add_argument("--decisions", type=str, default=None, help="JSON list of decisions")
    parser.add_argument("--files", type=str, default=None, help="JSON list of files touched")
    parser.add_argument("--next-steps", type=str, default=None, help="JSON list of next steps")
    parser.add_argument("--blockers", type=str, default=None, help="JSON list of blockers")
    parser.add_argument("--conversation-log", type=str, default=None)

    args, _ = parser.parse_known_args()

    # Merge: CLI > payload
    mode = args.mode or payload.get("mode", "handoff")
    workspace = args.workspace or payload.get("workspace") or payload.get("cwd")
    if not workspace:
        return 0
    objective = args.objective or payload.get("objective", "")
    if not objective:
        # Hook mode: the Stop payload never carries `objective`, so derive it from
        # the transcript rather than emitting "[not specified]" (CLAUDE.md, "every
        # handoff carries the objective intent").
        objective = derive_objective(payload.get("transcript_path"))
    conversation_log = args.conversation_log or payload.get("conversation_log")

    # Parse structured fields
    def parse_json_field(cli_val, payload_key, default):
        if cli_val:
            try:
                return json.loads(cli_val)
            except Exception:
                return default
        return payload.get(payload_key, default)

    state = parse_json_field(args.state, "state", {})
    decisions = parse_json_field(args.decisions, "decisions", [])
    files_touched = parse_json_field(args.files, "files_touched", [])
    next_steps = parse_json_field(args.next_steps, "next_steps", [])
    blockers = parse_json_field(args.blockers, "blockers", [])

    # Gather git context if workspace available
    git_context = None
    if workspace and mode != "close":
        diff_summary = get_git_diff_summary(workspace)
        recent_commits = get_recent_commits(workspace)
        if diff_summary or recent_commits:
            git_context = {
                "diff_summary": diff_summary,
                "recent_commits": recent_commits,
            }

    # Build the prompt.md
    content = build_prompt_md(
        mode=mode,
        objective=objective,
        state=state,
        decisions=decisions,
        files_touched=files_touched,
        next_steps=next_steps,
        blockers=blockers,
        conversation_log=conversation_log,
        git_context=git_context,
    )

    # Write it
    try:
        output_path = resolve_output_path(workspace, mode)
        identity = project_identity(workspace)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0  # Hook failure is noncritical; never choose an unrelated global workspace.
    content = f'Project-URI: {identity}\nSession-ID: {payload.get("session_id", "")}\n\n' + content
    output_path.write_text(content, encoding="utf-8")

    # Output for hook consumers
    result = {
        "mode": mode,
        "path": str(output_path),
        "message": f"Session {mode} written to {output_path.name}",
    }

    # For migrate mode, emit hook output so agent re-reads
    if mode == "migrate":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": (
                    f"[session-handoff] Context migrated to {output_path}. "
                    f"Re-read this file as your new seed context. "
                    f"Prior conversational context may be stale."
                )
            }
        }))
    else:
        print(json.dumps(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
