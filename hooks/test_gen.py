"""PostToolUse hook: prompt unit test generation after code writes.

Purpose: after Edit/Write/MultiEdit on a source file, emit additionalContext
instructing the agent to generate or update unit tests for that file.

Adapted from dotnet/skills code-testing-generator (Direct strategy).

Gate logic:
- SKIP test files, config files, hooks/scripts/infra glue
- PROCEED only for source files containing testable logic

Preconditions: registered on PostToolUse with matcher ^(Edit|Write|MultiEdit)$
Failure modes: any error -> exit 0, empty stdout (fail-open, no context injected).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Extensions that are never testable
CONFIG_EXTS = {
    ".json", ".toml", ".yaml", ".yml", ".md", ".txt", ".env",
    ".gitignore", ".dockerignore", ".lock", ".ini", ".cfg",
    ".csv", ".svg", ".png", ".jpg", ".ico",
}

# Path fragments that indicate test files (skip to avoid recursion)
TEST_INDICATORS = {"test", "spec", "tests", "__tests__", "_test", ".test.", ".spec."}

# Path fragments that indicate infra/hook/script (not business logic)
INFRA_INDICATORS = {"hooks/", "hooks\\", ".kiro/", ".claude/", "node_modules/"}


def should_skip(file_path: str) -> bool:
    """Return True if this file should NOT trigger test generation."""
    p = Path(file_path)

    # Config/non-code
    if p.suffix.lower() in CONFIG_EXTS:
        return True

    # Test file (avoid infinite loop)
    lower_path = file_path.lower().replace("\\", "/")
    for indicator in TEST_INDICATORS:
        if indicator in lower_path:
            return True

    # Infrastructure/hook files
    for indicator in INFRA_INDICATORS:
        if indicator in lower_path:
            return True

    return False


def main():
    # Read hook payload from stdin
    payload = {}
    if not sys.stdin.isatty():
        try:
            payload = json.load(sys.stdin)
        except Exception:
            pass

    # Extract the file path from the tool input
    # Claude Code PostToolUse payload: {tool_name, tool_input: {file_path|path|...}, output}
    tool_input = payload.get("tool_input", {})
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("filePath")
        or ""
    )

    if not file_path:
        return 0  # No file context, skip silently

    if should_skip(file_path):
        return 0  # Not a testable file

    # Emit instruction as additionalContext
    instruction = f"""You just wrote/edited `{file_path}`. Generate or update unit tests for it:

1. **Discover conventions** — find existing test files, match the framework and naming pattern.
2. **Identify targets** — public functions/methods, edge cases from conditionals, error paths, boundary conditions.
3. **Write tests** — append to existing test file or create one. Assert concrete values (not just type/null checks). Each test must fail if the function body is emptied.
4. **Run tests** — execute the project's test runner. If failures: read production code, fix assertions, re-run. Never skip/ignore.
5. **Report** — one line: N tests added/updated, file, pass/fail.

Constraints: don't test trivial getters/setters, don't modify the source file, don't create test infra unless none exists, preserve existing tests."""

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": instruction,
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
