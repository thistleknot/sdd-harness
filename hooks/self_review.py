"""Stop hook: self-review guard — catches incomplete implementations.

Purpose: before declaring a task done, scan recent file changes for signs
of incomplete work: TODO comments, placeholder text, mock implementations,
commented-out code blocks, or empty function bodies. If found, emit a
warning as additionalContext so the agent addresses them before finishing.

Preconditions: hook registered on Stop event in settings.json.
Failure modes: any error → exit 0 (fail-open, never block completion).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# Patterns that indicate incomplete work
INCOMPLETE_PATTERNS = [
    "TODO",
    "FIXME",
    "HACK",
    "XXX",
    "placeholder",
    "not implemented",
    "mock implementation",
    "pass  # ",
    "raise NotImplementedError",
    "...",  # ellipsis as placeholder body
]


def get_recently_modified_files(minutes: int = 15) -> list[str]:
    """Find files modified in the last N minutes via git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"--diff-filter=ACMR", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()
    except Exception:
        pass
    return []


def scan_file(path: str) -> list[str]:
    """Scan a file for incomplete patterns. Returns list of findings."""
    findings = []
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(content.splitlines(), 1):
            for pattern in INCOMPLETE_PATTERNS:
                if pattern in line and not line.strip().startswith("#!"):
                    # Skip if it's in a test file checking for these patterns
                    if "test_" in path or "_test." in path:
                        continue
                    findings.append(f"  {path}:{i} → {line.strip()[:80]}")
                    break
    except OSError:
        pass
    return findings


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    files = get_recently_modified_files()
    if not files:
        return 0

    all_findings = []
    for f in files:
        if Path(f).suffix in (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"):
            all_findings.extend(scan_file(f))

    if all_findings:
        warning = (
            "[self-review] Incomplete work detected in recently modified files:\n"
            + "\n".join(all_findings[:10])
        )
        if len(all_findings) > 10:
            warning += f"\n  ... and {len(all_findings) - 10} more"
        warning += "\n\nAddress these before declaring done."

        print(json.dumps({
            "hookSpecificOutput": {
                "additionalContext": warning
            }
        }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
