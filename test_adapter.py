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
    sync_vscode,
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


@pytest.fixture
def vscode_home(tmp_path, monkeypatch):
    """Keep sync_vscode off the real ~/.copilot and ~/.claude."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("adapter.Path.home", lambda: home)
    return home


def test_sync_vscode_writes_hooks_config_pointing_at_shim(config, tmp_path, monkeypatch, vscode_home):
    monkeypatch.setattr("adapter.vscode_user_dir", lambda: tmp_path / "Code" / "User")
    sync_vscode(config)
    data = json.loads((vscode_home / ".copilot" / "hooks" / "harness.json").read_text())
    assert set(data["hooks"]) == {"SessionStart", "UserPromptSubmit", "PreToolUse",
                                  "PostToolUse", "PreCompact", "Stop"}
    pre = data["hooks"]["PreToolUse"][0]
    assert pre["type"] == "command"
    assert "vscode_shim.py" in pre["command"] and pre["command"].endswith(" PreToolUse")
    assert "matcher" not in pre


def test_sync_vscode_uses_servers_key_and_preserves_existing(config, tmp_path, monkeypatch, vscode_home):
    monkeypatch.setattr("adapter.vscode_user_dir", lambda: tmp_path)
    existing = {
        "servers": {"memory": {"type": "stdio", "command": "npx"}},
        "inputs": [{"id": "k"}],
    }
    (tmp_path / "mcp.json").write_text(json.dumps(existing), encoding="utf-8")
    sync_vscode(config)
    data = json.loads((tmp_path / "mcp.json").read_text())
    assert "mcpServers" not in data
    assert data["servers"]["retrieve-skills"] == {"type": "http", "url": "http://127.0.0.1:8765/mcp"}
    assert data["servers"]["todo"]["type"] == "stdio"
    assert data["servers"]["todo"]["env"] == {"PYTHONUTF8": "1"}
    assert data["servers"]["memory"] == {"type": "stdio", "command": "npx"}
    assert data["inputs"] == [{"id": "k"}]


def test_sync_vscode_creates_file_when_absent(config, tmp_path, monkeypatch, vscode_home):
    monkeypatch.setattr("adapter.vscode_user_dir", lambda: tmp_path / "Code" / "User")
    sync_vscode(config)
    data = json.loads((tmp_path / "Code" / "User" / "mcp.json").read_text())
    assert set(data["servers"]) == {"retrieve-skills", "todo"}


def test_sync_vscode_writes_core_instructions_and_spares_others(config, tmp_path, monkeypatch, vscode_home):
    monkeypatch.setattr("adapter.vscode_user_dir", lambda: tmp_path)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    mine = prompts / "coding.instructions.md"
    mine.write_bytes(b"---\napplyTo: '**'\n---\nhand written\n")
    before = mine.read_bytes()
    sync_vscode(config)
    first = (prompts / "harness-core.instructions.md").read_text(encoding="utf-8")
    assert first.startswith("---\napplyTo: '**'\n---")
    assert "# Operating Core" in first
    assert "Generated by" in first
    assert "## Where the rest lives" in first
    assert str(Path.home() / ".harness" / "constitution.md") in first
    assert str(Path.home() / ".skills" / "GLOSSARY.md") in first
    assert mine.read_bytes() == before
    sync_vscode(config)
    assert (prompts / "harness-core.instructions.md").read_text(encoding="utf-8") == first


def test_all_targets_registered():
    """TARGETS holds every harness and --target can select each one."""
    import adapter
    assert set(adapter.TARGETS) == {"claude", "opencode", "kiro", "pi", "codex", "copilot", "vscode"}
