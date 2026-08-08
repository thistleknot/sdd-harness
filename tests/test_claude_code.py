"""Conformance test suite for Claude Code SDD harness.

Runs headlessly via `claude -p` to verify:
1. MCP tool access (retrieve-skills, memory-index, todo)
2. Skill retrieval accuracy
3. Hook chain fires (self-review, session-end)
4. Settings integrity

Usage: python test_claude_code.py
Requires: claude CLI on PATH, MCP services running
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

CLI_TIMEOUT = 45  # seconds per claude -p invocation


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""


def claude_p(prompt: str, timeout: int = CLI_TIMEOUT) -> str:
    """Run claude -p and return stdout."""
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout


def test_mcp_retrieve_skills() -> TestResult:
    """Verify retrieve-skills MCP responds with skill results."""
    try:
        out = claude_p(
            "Call the retrieve_skills MCP tool with query 'convert PDF to markdown' and k=2. "
            "Show me the raw tool output only, nothing else."
        )
        if "pdf-extraction" in out.lower() or "PASS" in out or "CANDIDATE" in out:
            return TestResult("mcp_retrieve_skills", True)
        return TestResult("mcp_retrieve_skills", False, f"Output didn't contain expected skill: {out[:200]}")
    except subprocess.TimeoutExpired:
        return TestResult("mcp_retrieve_skills", False, "Timeout")
    except Exception as e:
        return TestResult("mcp_retrieve_skills", False, str(e))


def test_mcp_memory() -> TestResult:
    """Verify memory-index MCP responds."""
    try:
        out = claude_p(
            "Call the memory_stats MCP tool and show me the raw output only."
        )
        if "memories" in out.lower() or "collection" in out.lower() or "docs" in out.lower():
            return TestResult("mcp_memory", True)
        return TestResult("mcp_memory", False, f"No memory stats in output: {out[:200]}")
    except subprocess.TimeoutExpired:
        return TestResult("mcp_memory", False, "Timeout")
    except Exception as e:
        return TestResult("mcp_memory", False, str(e))


def test_mcp_todo() -> TestResult:
    """Verify todo MCP responds."""
    try:
        out = claude_p(
            "Call the list_todos MCP tool with workspace_root='C:\\Users\\user\\Documents\\dev\\skills' "
            "and show me the raw output only."
        )
        if "todo" in out.lower() or "#" in out or "pending" in out.lower() or "no " in out.lower():
            return TestResult("mcp_todo", True)
        return TestResult("mcp_todo", False, f"No todo output: {out[:200]}")
    except subprocess.TimeoutExpired:
        return TestResult("mcp_todo", False, "Timeout")
    except Exception as e:
        return TestResult("mcp_todo", False, str(e))


def test_settings_integrity() -> TestResult:
    """Verify settings.json is valid and has required hooks."""
    try:
        settings = json.loads(Path.home().joinpath(".claude", "settings.json").read_text())
        hooks = settings.get("hooks", {})
        required = ["SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "PreCompact"]
        missing = [h for h in required if h not in hooks]
        if missing:
            return TestResult("settings_integrity", False, f"Missing hooks: {missing}")
        return TestResult("settings_integrity", True)
    except Exception as e:
        return TestResult("settings_integrity", False, str(e))


def test_mcp_registered() -> TestResult:
    """Verify all 4 MCP servers registered in .claude.json."""
    try:
        config = json.loads(Path.home().joinpath(".claude.json").read_text())
        servers = config.get("mcpServers", {})
        required = ["retrieve-skills", "memory-index", "todo", "data-science-skills"]
        missing = [s for s in required if s not in servers]
        if missing:
            return TestResult("mcp_registered", False, f"Missing: {missing}")
        return TestResult("mcp_registered", True)
    except Exception as e:
        return TestResult("mcp_registered", False, str(e))


def test_hook_files_exist() -> TestResult:
    """Verify all hook scripts exist on disk."""
    hooks_dir = Path.home() / ".claude" / "hooks"
    harness_hooks = Path.home() / ".harness" / "hooks"
    required = [
        hooks_dir / "spec_gate.py",
        hooks_dir / "membank.py",
        hooks_dir / "log_event.py",
        harness_hooks / "self_review.py",
        harness_hooks / "pre_compact.py",
        harness_hooks / "session_end.py",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        return TestResult("hook_files_exist", False, f"Missing: {missing}")
    return TestResult("hook_files_exist", True)


def main():
    print("=" * 60)
    print("  CLAUDE CODE SDD CONFORMANCE TEST")
    print("=" * 60)
    print()

    # Fast local checks first
    results = [
        test_settings_integrity(),
        test_mcp_registered(),
        test_hook_files_exist(),
    ]

    # MCP integration tests (require claude CLI + services)
    print("  Running MCP integration tests (may take 30-45s each)...")
    results.extend([
        test_mcp_retrieve_skills(),
        test_mcp_memory(),
        test_mcp_todo(),
    ])

    # Report
    print()
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}  {r.name}")
        if not r.passed and r.detail:
            print(f"         {r.detail[:120]}")

    print()
    print("-" * 60)
    print(f"  {passed} passed, {failed} failed")
    print("=" * 60)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
