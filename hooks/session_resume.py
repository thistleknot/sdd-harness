"""SessionStart hook: inject existing prompt.md as seed context.

Purpose: on session start, check for a handoff prompt.md from a prior session
and output its content so it gets injected as seed context.

Lookup order:
  1. ~/memory-bank/projects/<repo>/prompt.md (project-specific)
  2. ~/memory-bank/handoffs/prompt-*.md (latest global fallback)

If found, prints content to stdout (exit 0 → forwarded as context).
If not found, prints nothing (exit 0 → no-op).

Preconditions: hook registered on SessionStart.
Failure modes: any error → exit 0 (fail-open).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import sys as _ks
_ks.path.insert(0, str(Path(__file__).parent))
from _common import disabled

MEMORY_DIR = Path(os.path.expanduser("~/memory-bank"))


def get_git_root() -> str | None:
    """Get the git repo name from CWD."""
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


def find_prompt_md() -> Path | None:
    """Find the most relevant prompt.md for the current context."""
    # 1. Project root (CWD or git root) — the canonical location
    cwd_prompt = Path.cwd() / "prompt.md"
    if cwd_prompt.exists():
        return cwd_prompt

    repo = get_git_root()
    if repo:
        # Try git root directly
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                root_prompt = Path(result.stdout.strip()) / "prompt.md"
                if root_prompt.exists():
                    return root_prompt
        except Exception:
            pass

    # 2. Legacy location (memory-bank) — for backward compat
    if repo:
        project_prompt = MEMORY_DIR / "projects" / repo / "prompt.md"
        if project_prompt.exists():
            return project_prompt

    # 3. Global fallback — latest handoff prompt
    handoffs_dir = MEMORY_DIR / "handoffs"
    if handoffs_dir.exists():
        candidates = sorted(
            handoffs_dir.glob("prompt-*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]

    return None


def main():
    if disabled():
        return 0
    try:
        # Consume stdin if provided (hook payload), but we don't need it
        if not sys.stdin.isatty():
            try:
                sys.stdin.read()  # consume but discard
            except Exception:
                pass

        prompt_path = find_prompt_md()
        if prompt_path:
            content = prompt_path.read_text(encoding="utf-8")
            # Emit as context injection
            print(content)
    except Exception:
        pass  # fail-open

    return 0


if __name__ == "__main__":
    sys.exit(main())
