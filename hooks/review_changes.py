"""Stop hook: batched change review — shows this turn's diffs for approval.

Purpose: at task boundary, read the list of files written this turn,
produce a compact diff (changed lines only), and emit it as additionalContext
so the agent presents the batch to the user for review.

Optionally opens VS Code diff tabs if REVIEW_IN_VSCODE=1 is set.

Preconditions: registered on Stop event in settings.json.
Failure modes: any error -> exit 0 (fail-open, never block session end).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TURN_LOG = Path(".git/.turn_writes")


def get_turn_files() -> list[str]:
    """Read and dedupe the turn write log."""
    if not TURN_LOG.exists():
        return []
    try:
        lines = TURN_LOG.read_text(encoding="utf-8").strip().splitlines()
        # Dedupe preserving order
        seen = set()
        result = []
        for line in lines:
            if line and line not in seen:
                seen.add(line)
                result.append(line)
        return result
    except OSError:
        return []


def clear_turn_log():
    """Remove the turn log so next turn starts fresh."""
    try:
        TURN_LOG.unlink(missing_ok=True)
    except OSError:
        pass


def get_file_diff(file_path: str) -> str:
    """Get compact diff for a single file (changed lines + minimal context)."""
    try:
        # Try staged first, fall back to unstaged
        result = subprocess.run(
            ["git", "diff", "--unified=2", "--", file_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

        # Check if it's a new untracked file — show first 30 lines
        p = Path(file_path)
        if p.exists():
            # Check if tracked
            check = subprocess.run(
                ["git", "ls-files", file_path],
                capture_output=True, text=True, timeout=5,
            )
            if check.returncode == 0 and not check.stdout.strip():
                # Untracked new file — show preview
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                preview = lines[:30]
                header = f"+++ {file_path} (new file, {len(lines)} lines)"
                body = "\n".join(f"+{l}" for l in preview)
                if len(lines) > 30:
                    body += f"\n... ({len(lines) - 30} more lines)"
                return f"{header}\n{body}"
    except Exception:
        pass
    return ""


def open_vscode_diffs(files: list[str]):
    """Open changed files in VS Code diff view."""
    try:
        for f in files[:5]:  # Cap at 5 tabs to avoid flooding
            subprocess.Popen(
                ["code", "--diff", f, f],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def main():
    payload = {}
    if not sys.stdin.isatty():
        try:
            payload = json.load(sys.stdin)
        except Exception:
            pass

    # Guard: re-entrant Stop
    if payload.get("stop_hook_active"):
        return 0

    files = get_turn_files()
    if not files:
        return 0

    # Build compact diff output
    sections = []
    for f in files:
        diff = get_file_diff(f)
        if diff:
            sections.append(diff)

    if not sections:
        clear_turn_log()
        return 0

    # Optionally open VS Code
    if os.environ.get("REVIEW_IN_VSCODE", "").strip() == "1":
        open_vscode_diffs(files)

    # Build the review prompt
    file_list = ", ".join(Path(f).name for f in files)
    header = f"[change-review] {len(files)} file(s) modified this turn: {file_list}\n"
    header += "Review the changes below. Ask the user: proceed, revert, or adjust?\n"
    header += "=" * 60 + "\n"

    diff_output = header + "\n\n".join(sections)

    # Cap output to avoid overwhelming context (keep first 4000 chars)
    if len(diff_output) > 4000:
        diff_output = diff_output[:4000] + "\n\n... (truncated, run `git diff` for full output)"

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": diff_output
        }
    }))

    clear_turn_log()
    return 0


if __name__ == "__main__":
    sys.exit(main())
