"""Stop hook: self-review guard — catches incomplete implementations.

Purpose: before declaring a task done, scan recent file changes for signs
of incomplete work: TODO comments, placeholder text, mock implementations,
commented-out code blocks, or empty function bodies. If found, emit a
warning as additionalContext so the agent addresses them before finishing.

Preconditions: hook registered on Stop event in settings.json.
Failure modes: any error -> exit 0 (fail-open, never block completion).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Patterns that indicate incomplete work — anchored regexes, not bare substrings.
# Each is compiled with IGNORECASE off unless noted.
INCOMPLETE_PATTERNS = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bHACK\b"),
    re.compile(r"\bXXX\b"),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),  # word-boundary, not substring
    re.compile(r"\bnot implemented\b", re.IGNORECASE),
    re.compile(r"\bmock implementation\b", re.IGNORECASE),
    re.compile(r"^\s*pass\s+#"),          # pass with inline comment = stub body
    re.compile(r"\braise NotImplementedError\b"),
    re.compile(r"^\s*\.\.\.\s*$"),        # ellipsis as entire statement, not in strings
]

# State file for dedup across firings
SEEN_HASH_FILE = Path(".git/.self_review_seen")


def get_recently_modified_files(minutes: int = 15) -> list[str]:
    """Find files modified in the last N minutes.

    Uses git diff --name-only HEAD for tracked changes, plus
    git ls-files --others for untracked. Filters by mtime to
    honour the recency claim.
    """
    files: list[str] = []
    try:
        # Tracked modifications
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            files.extend(result.stdout.strip().splitlines())

        # Untracked files (new code the detector was missing)
        result2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=10,
        )
        if result2.returncode == 0 and result2.stdout.strip():
            files.extend(result2.stdout.strip().splitlines())
    except Exception:
        pass

    # Filter by actual mtime — honour the recency parameter
    cutoff = time.time() - minutes * 60
    recent = []
    for f in files:
        p = Path(f)
        try:
            if p.exists() and p.stat().st_mtime > cutoff:
                recent.append(f)
        except OSError:
            pass

    return recent


def is_code_line(line: str) -> bool:
    """Heuristic: skip lines that are inside strings or comments.

    Returns False for:
    - Lines that are pure comments (# ...)
    - Lines that look like docstrings (triple-quote lines)
    - Lines inside f-strings or log messages (contains quotes + the match)
    """
    stripped = line.strip()

    # Pure comment
    if stripped.startswith("#"):
        return False

    # Docstring boundaries
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return False
    if stripped.startswith('r"') or stripped.startswith("r'"):
        return False

    # Line is entirely a string literal (common for log messages)
    if (stripped.startswith('"') and stripped.endswith('"')) or \
       (stripped.startswith("'") and stripped.endswith("'")):
        return False
    if (stripped.startswith('f"') and stripped.endswith('"')) or \
       (stripped.startswith("f'") and stripped.endswith("'")):
        return False

    return True


def is_test_file(path: str) -> bool:
    """Check once per file, not per line."""
    lower = path.lower().replace("\\", "/")
    return any(ind in lower for ind in ("test_", "_test.", ".test.", ".spec.", "/tests/", "/__tests__/"))


def scan_file(path: str) -> list[str]:
    """Scan a file for incomplete patterns. Returns list of findings."""
    if is_test_file(path):
        return []

    findings = []
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        in_docstring = False

        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()

            # Track docstring state (triple-quote toggle)
            if '"""' in stripped or "'''" in stripped:
                count = stripped.count('"""') + stripped.count("'''")
                if count % 2 == 1:
                    in_docstring = not in_docstring
                continue
            if in_docstring:
                continue

            # Skip non-code lines
            if not is_code_line(line):
                continue

            for pattern in INCOMPLETE_PATTERNS:
                if pattern.search(line):
                    findings.append(f"  {path}:{i} -> {stripped[:80]}")
                    break
    except OSError:
        pass
    return findings


def compute_findings_hash(findings: list[str]) -> str:
    """Hash the findings list for dedup."""
    return hashlib.md5("\n".join(sorted(findings)).encode()).hexdigest()


def already_reported(findings_hash: str) -> bool:
    """Check if these exact findings were already reported this session."""
    try:
        if SEEN_HASH_FILE.exists():
            stored = SEEN_HASH_FILE.read_text(encoding="utf-8").strip()
            return stored == findings_hash
    except OSError:
        pass
    return False


def mark_reported(findings_hash: str) -> None:
    """Record that these findings have been reported."""
    try:
        SEEN_HASH_FILE.write_text(findings_hash, encoding="utf-8")
    except OSError:
        pass


def main():
    payload = {}
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        pass

    # Guard: if Stop hook is re-firing (blocking loop), exit silently.
    if payload.get("stop_hook_active"):
        return 0

    files = get_recently_modified_files(minutes=15)
    if not files:
        return 0

    all_findings = []
    for f in files:
        if Path(f).suffix in (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".cs"):
            all_findings.extend(scan_file(f))

    if not all_findings:
        return 0

    # Dedup: if identical findings already reported, don't nag again
    fhash = compute_findings_hash(all_findings)
    if already_reported(fhash):
        return 0

    mark_reported(fhash)

    warning = (
        "[self-review] Incomplete work detected in recently modified files:\n"
        + "\n".join(all_findings[:10])
    )
    if len(all_findings) > 10:
        warning += f"\n  ... and {len(all_findings) - 10} more"
    warning += "\n\nAddress these before declaring done."

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": warning
        }
    }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
