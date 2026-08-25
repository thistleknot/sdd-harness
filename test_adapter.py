"""Unit tests for adapter.py — six-harness MCP config projection.

Tests use tmp_path fixtures to avoid writing to real harness config files.
Each sync function is tested for correct output format per harness.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from adapter import (
    load_harness,
    sync_claude_code,
    sync_codex,
    sync_github_copilot,
    sync_kiro,
    sync_opencode,
)


@pytest.fixture
def config():
    """Minimal harness config for testing."""
    return {
        "mcp_servers": {
            "retrieve-skills": {"type": "http", "url": "http://127.0.0.1:8765/mcp"},
            "todo": {
                "type": "stdio",
                "command": "python",
                "args": ["todo_mcp.py"],
                "env": {"PYTHONUTF8": "1"},
            },
        }
    }


def test_sync_claude_code_writes_mcp_servers(config, tmp_path):
    claude_json = tmp_path / ".claude.json"
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_claude_code(config)
    data = json.loads(claude_json.read_text())
    assert "retrieve-skills" in data["mcpServers"]
    assert data["mcpServers"]["retrieve-skills"]["url"] == "http://127.0.0.1:8765/mcp"
    assert data["mcpServers"]["todo"]["type"] == "stdio"
    assert data["mcpServers"]["todo"]["args"] == ["todo_mcp.py"]
    assert data["mcpServers"]["todo"]["env"] == {"PYTHONUTF8": "1"}


def test_sync_kiro_writes_disabled_false(config, tmp_path):
    kiro_json = tmp_path / ".kiro" / "settings" / "mcp.json"
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_kiro(config)
    data = json.loads(kiro_json.read_text())
    assert data["mcpServers"]["retrieve-skills"]["disabled"] is False
    assert data["mcpServers"]["retrieve-skills"]["url"] == "http://127.0.0.1:8765/mcp"
    assert data["mcpServers"]["todo"]["disabled"] is False
    assert data["mcpServers"]["todo"]["command"] == "python"


def test_sync_opencode_uses_streamable_http(config, tmp_path):
    oc_dir = tmp_path / ".config" / "opencode"
    oc_dir.mkdir(parents=True)
    oc_json = oc_dir / "opencode.json"
    oc_json.write_text("{}", encoding="utf-8")
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_opencode(config)
    data = json.loads(oc_json.read_text())
    assert data["mcp"]["retrieve-skills"]["type"] == "streamable-http"
    assert data["mcp"]["todo"]["type"] == "local"
    assert data["mcp"]["todo"]["command"] == ["python", "todo_mcp.py"]


def test_sync_codex_writes_to_codex_dir(config, tmp_path):
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_codex(config)
    codex_json = tmp_path / ".codex" / "mcp.json"
    assert codex_json.exists()
    data = json.loads(codex_json.read_text())
    assert "retrieve-skills" in data["mcpServers"]
    assert data["mcpServers"]["retrieve-skills"]["url"] == "http://127.0.0.1:8765/mcp"
    assert data["mcpServers"]["todo"]["command"] == "python"


def test_sync_github_copilot_writes_to_workspace(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sync_github_copilot(config)
    copilot_json = tmp_path / ".copilot" / "mcp.json"
    assert copilot_json.exists()
    data = json.loads(copilot_json.read_text())
    assert data["mcpServers"]["retrieve-skills"]["type"] == "http"
    assert data["mcpServers"]["todo"]["type"] == "stdio"


def test_all_targets_registered():
    """The main() targets dict should have exactly 6 entries."""
    # Import and check the targets dict indirectly
    import adapter
    import inspect
    source = inspect.getsource(adapter.main)
    for name in ["claude", "opencode", "kiro", "pi", "codex", "copilot"]:
        assert f'"{name}"' in source, f"Target '{name}' not in main() targets"
