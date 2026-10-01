"""UserPromptSubmit hook: inject invisible codebase map on first prompt.

Purpose: give the agent an automatic understanding of project structure
without the user needing to explain it. Fires once per session (caches
a session marker to avoid re-injecting on every prompt).

Preconditions: registered on UserPromptSubmit in settings.json.
Failure modes: any error → exit 0 (fail-open, no injection).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import sys as _ks
_ks.path.insert(0, str(Path(__file__).parent))
from _common import disabled

# Cache: don't re-inject after first prompt in a session
SESSION_MARKER = Path(os.environ.get("TEMP", "/tmp")) / ".harness_map_injected"
MAP_TTL = 300  # regenerate map if older than 5 minutes
COUNT_CAP = 1000  # stop counting a dir here; an uncapped walk of 80k files blew the 5s hook timeout


def count_files(top: Path, skip: set[str]) -> int:
    """Count files under top, pruning skip dirs, stopping at COUNT_CAP."""
    count = 0
    for _, dirnames, filenames in os.walk(top):
        dirnames[:] = [d for d in dirnames if d not in skip]
        count += len(filenames)
        if count >= COUNT_CAP:
            return COUNT_CAP
    return count


def get_git_root() -> Path | None:
    """Get git root of CWD."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return None


def generate_map(root: Path) -> str:
    """Generate a compact project structure summary."""
    lines = [f"Project: {root.name}"]

    # Detect tech stack from key files
    indicators = {
        "package.json": "Node.js",
        "pyproject.toml": "Python",
        "Cargo.toml": "Rust",
        "go.mod": "Go",
        "pom.xml": "Java/Maven",
        "build.gradle": "Java/Gradle",
        "Makefile": "Make",
        "CMakeLists.txt": "C/C++",
        "next.config.ts": "Next.js",
        "next.config.js": "Next.js",
        "vite.config.ts": "Vite",
    }
    stack = []
    for fname, tech in indicators.items():
        if (root / fname).exists():
            stack.append(tech)
    if stack:
        lines.append(f"Stack: {', '.join(stack)}")

    # Top-level directory listing (skip hidden, node_modules, etc.)
    skip = {".git", "node_modules", "__pycache__", ".next", "venv", ".venv", "dist", "build", ".cache"}
    dirs = []
    files = []
    for item in sorted(root.iterdir()):
        if item.name.startswith(".") and item.name not in (".github", ".claude"):
            continue
        if item.name in skip:
            continue
        if item.is_dir():
            count = count_files(item, skip)
            label = f"{COUNT_CAP}+" if count >= COUNT_CAP else str(count)
            dirs.append(f"  {item.name}/ ({label} files)")
        else:
            files.append(f"  {item.name}")

    if dirs:
        lines.append("Directories:")
        lines.extend(dirs[:20])
        if len(dirs) > 20:
            lines.append(f"  ... +{len(dirs) - 20} more")

    if files:
        lines.append("Root files:")
        lines.extend(files[:15])

    return "\n".join(lines)


def main():
    if disabled():
        return 0
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    # Check if already injected this session
    session_id = payload.get("session_id", "")
    marker = SESSION_MARKER.with_suffix(f".{session_id[:8]}")

    if marker.exists():
        age = time.time() - marker.stat().st_mtime
        if age < MAP_TTL:
            return 0  # already injected, skip

    # Generate map
    root = get_git_root() or Path.cwd()
    try:
        project_map = generate_map(root)
    except Exception:
        return 0

    if not project_map:
        return 0

    # Mark as injected
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(time.time()))
    except Exception:
        pass

    # Inject as additionalContext
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"[codebase-map] {project_map}"
        }
    }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
