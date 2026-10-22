"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| FIXTURE | Build temporary harness homes and representative MCP configs | [mandatory] | R1 |
| PROJECT | Invoke each harness adapter against its temporary destinations | [mandatory] | R1 |
| VERIFY | Check native formats, Hermes writer payload, retired-hook cleanup, and preserved files | [mandatory] | R2, R3, R5 |

R1: When a sync test runs, its fixtures MUST isolate writes from live config.
R2: When VS Code instructions are generated, they MUST contain the complete
canonical claude/AGENTS.md text (prompt-sync requirement R5).
R3: When VS Code sync repeats, its generated instructions MUST remain identical.
R4: When a local MCP is projected to OpenCode, the test MUST assert the configured
tool-fetch timeout covers the measured cold start.
R5: When a retired Graphify hook is removed, every unrelated hook and setting MUST survive.

CLOSED: Pinning the literal '# Operating Core' title was rejected because the
operator's updated canonical prompt uses '# Operating Contract'.

Preconditions: pytest and the adapter dependencies are installed.
Failure modes: malformed projection, omitted prompt text, overwritten unmanaged
files, or non-idempotent generation fail assertions.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from adapter import (
    HARNESS_AGENTS,
    ensure_global_hooks,
    load_harness,
    remove_retired_graphify_hooks,
    sync_claude_code,
    sync_codex,
    sync_codex_hooks,
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


def test_sync_opencode_uses_native_remote_and_local_schema(config, tmp_path):
    oc_dir = tmp_path / ".config" / "opencode"
    oc_dir.mkdir(parents=True)
    oc_json = oc_dir / "opencode.json"
    oc_json.write_text("{}", encoding="utf-8")
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_opencode(config)
    data = json.loads(oc_json.read_text())
    assert data["mcp"]["retrieve-skills"]["type"] == "remote"
    assert data["mcp"]["todo"]["type"] == "local"
    assert data["mcp"]["todo"]["command"] == ["python", "todo_mcp.py"]
    assert data["mcp"]["todo"]["timeout"] == 240000
    assert data["mcp"]["todo"]["environment"] == {"PYTHONUTF8": "1"}


def test_sync_opencode_reads_block_comments_trailing_commas_and_keeps_other_keys(config, tmp_path):
    """The shared JSONC parser handles what the old line-start regex could not (block comments, inline //)."""
    oc_dir = tmp_path / ".config" / "opencode"
    oc_dir.mkdir(parents=True)
    oc_json = oc_dir / "opencode.json"
    oc_json.write_text('{\n  /* block */ "model": "m", // inline\n  "url": "https://x.example/a//b",\n  "list": [1,],\n}\n',
                       encoding="utf-8")
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_opencode(config)
    data = json.loads(oc_json.read_text())
    assert (data["model"], data["url"], data["list"]) == ("m", "https://x.example/a//b", [1])
    assert "retrieve-skills" in data["mcp"]


def test_sync_opencode_skips_an_unparseable_config_without_touching_it(config, tmp_path, capsys):
    oc_dir = tmp_path / ".config" / "opencode"
    oc_dir.mkdir(parents=True)
    oc_json = oc_dir / "opencode.json"
    oc_json.write_bytes(b"{ not json")
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_opencode(config)
    assert oc_json.read_bytes() == b"{ not json" and "failed to parse config" in capsys.readouterr().out


REA_TABLE = (
    '[mcp_servers.rea]\n'
    'command = "npx"\n'
    'args = [ "-y", "rea-agents@4.0.1", "mcp" ]\n'
    'startup_timeout_sec = 30\n'
)


def _codex_sync(config, tmp_path, existing=None):
    cfg = tmp_path / ".codex" / "config.toml"
    if existing is not None:
        cfg.parent.mkdir(parents=True)
        cfg.write_bytes(existing.encode("utf-8"))
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_codex(config)
    return cfg


def _toml_loads(text):
    try:
        import tomllib as parser  # TOML parser used: tomllib (3.11+) else tomli
    except ImportError:
        import tomli as parser
    return parser.loads(text)


def test_sync_codex_adds_block_and_keeps_rea_bytes(config, tmp_path):
    cfg = _codex_sync(config, tmp_path, existing=REA_TABLE)
    text = cfg.read_bytes().decode("utf-8")
    begin = text.index("# >>> harness mcp servers")
    assert text[:begin].rstrip("\n") + "\n" == REA_TABLE
    assert "[mcp_servers.retrieve-skills]" in text and "[mcp_servers.todo]" in text
    assert not (tmp_path / ".codex" / "mcp.json").exists()


def test_sync_codex_second_run_is_noop(config, tmp_path, capsys):
    cfg = _codex_sync(config, tmp_path, existing=REA_TABLE)
    first = cfg.read_bytes()
    capsys.readouterr()
    _codex_sync(config, tmp_path)
    assert cfg.read_bytes() == first
    assert "unchanged" in capsys.readouterr().out


def test_sync_codex_renders_stdio_and_http(config, tmp_path):
    text = _codex_sync(config, tmp_path).read_text(encoding="utf-8")
    assert '[mcp_servers.retrieve-skills]\nurl = "http://127.0.0.1:8765/mcp"' in text
    assert '[mcp_servers.todo]\ncommand = "python"\nargs = ["todo_mcp.py"]' in text
    assert '[mcp_servers.todo.env]\n"PYTHONUTF8" = "1"' in text


def test_sync_codex_refuses_duplicate_table(config, tmp_path):
    existing = REA_TABLE + '\n[mcp_servers.retrieve-skills]\nurl = "http://x"\n'
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(existing.encode("utf-8"))
    with patch("adapter.Path.home", return_value=tmp_path):
        with pytest.raises(RuntimeError, match=r"\[mcp_servers\.retrieve-skills\]"):
            sync_codex(config)
    assert cfg.read_bytes() == existing.encode("utf-8")


def test_sync_codex_result_parses_as_toml(config, tmp_path):
    cfg = _codex_sync(config, tmp_path, existing=REA_TABLE)
    data = _toml_loads(cfg.read_text(encoding="utf-8"))
    assert data["mcp_servers"]["rea"]["startup_timeout_sec"] == 30
    assert data["mcp_servers"]["retrieve-skills"]["url"] == "http://127.0.0.1:8765/mcp"
    assert data["mcp_servers"]["todo"]["env"] == {"PYTHONUTF8": "1"}


def _hooks_sync(config, tmp_path, existing=None):
    f = tmp_path / ".codex" / "hooks.json"
    if existing is not None:
        f.parent.mkdir(parents=True)
        f.write_text(existing, encoding="utf-8")
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_codex_hooks(config)
    return f


def test_sync_codex_hooks_new_file_has_entry_and_second_run_unchanged(config, tmp_path, capsys):
    f = _hooks_sync(config, tmp_path)
    cmd = json.loads(f.read_text())["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert cmd["type"] == "command" and cmd["timeout"] == 30
    assert cmd["command"].endswith("playbook.py --feature")
    assert "updated" in capsys.readouterr().out
    before = f.read_bytes()
    _hooks_sync(config, tmp_path)
    assert f.read_bytes() == before
    assert "unchanged" in capsys.readouterr().out


def test_sync_codex_hooks_keeps_unrelated_hooks(config, tmp_path):
    other = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "echo hi", "timeout": 5}]}]}}
    f = _hooks_sync(config, tmp_path, json.dumps(other))
    data = json.loads(f.read_text())
    assert data["hooks"]["PreToolUse"] == other["hooks"]["PreToolUse"]
    assert "UserPromptSubmit" in data["hooks"]


def test_sync_codex_hooks_refuses_foreign_user_prompt_submit(config, tmp_path):
    foreign = json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [
        {"type": "command", "command": "mine.exe"}]}]}})
    with pytest.raises(RuntimeError, match="mine.exe"):
        _hooks_sync(config, tmp_path, foreign)
    assert (tmp_path / ".codex" / "hooks.json").read_text() == foreign


def test_sync_github_copilot_writes_user_config_and_preserves_workspace_independent_entries(config, tmp_path):
    path = tmp_path / ".copilot" / "mcp-config.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"unmanaged": {"command": "keep"}}}), encoding="utf-8")
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_github_copilot(config)
    copilot_json = path
    assert copilot_json.exists()
    data = json.loads(copilot_json.read_text())
    assert data["mcpServers"]["retrieve-skills"]["type"] == "http"
    assert data["mcpServers"]["todo"]["type"] == "stdio"
    assert data["mcpServers"]["unmanaged"] == {"command": "keep"}


def test_pi_sync_does_not_write_claude_mcp_config(config, tmp_path, capsys):
    from adapter import sync_pi

    with patch("adapter.Path.home", return_value=tmp_path):
        sync_pi(config)
    assert not (tmp_path / ".claude.json").exists()
    assert "retrieve-skills extension" in capsys.readouterr().out


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
    """Guarantee: generated instructions embed the canonical prompt verbatim."""
    monkeypatch.setattr("adapter.vscode_user_dir", lambda: tmp_path)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    mine = prompts / "coding.instructions.md"
    mine.write_bytes(b"---\napplyTo: '**'\n---\nhand written\n")
    before = mine.read_bytes()
    sync_vscode(config)
    first = (prompts / "harness-core.instructions.md").read_text(encoding="utf-8")
    assert first.startswith("---\napplyTo: '**'\n---")
    assert HARNESS_AGENTS.read_text(encoding="utf-8") in first
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
    assert set(adapter.TARGETS) == {"claude", "opencode", "kiro", "pi", "hermes", "codex", "copilot", "vscode"}


def test_agents_target_is_opt_in_so_target_all_never_edits_agent_settings():
    import adapter
    assert adapter.OPT_IN_TARGETS == ("agents",) and "agents" not in adapter.TARGETS


def test_sync_agents_plans_by_default_and_applies_only_when_asked(monkeypatch):
    import adapter
    import render_agents
    seen = []
    monkeypatch.setattr(render_agents, "main", lambda argv: seen.append(argv) or 0)
    adapter.sync_agents({})
    adapter.sync_agents({}, apply=True)
    assert seen == [["--harness", "all", "--plan"], ["--harness", "all", "--apply"]]


GRAPH_HOOKS = [
    {"event": "PreToolUse", "matcher": "Bash|Grep", "command": "g hook-guard search", "timeout": 10},
    {"event": "PreToolUse", "matcher": "Read|Glob", "command": "g hook-guard read", "timeout": 10},
]


def test_ensure_global_hooks_appends_beside_existing_and_is_idempotent(tmp_path):
    path = tmp_path / "settings.json"
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}
    path.write_text(json.dumps({"model": "x", "hooks": {"PreToolUse": [other]}}), encoding="utf-8")

    assert ensure_global_hooks(path, GRAPH_HOOKS) is True
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = data["hooks"]["PreToolUse"]
    assert groups[0] == other
    assert [g["matcher"] for g in groups] == ["Bash", "Bash|Grep", "Read|Glob"]
    assert groups[1]["hooks"] == [{"type": "command", "command": "g hook-guard search", "timeout": 10}]
    assert data["model"] == "x"

    assert ensure_global_hooks(path, GRAPH_HOOKS) is False
    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_ensure_global_hooks_creates_absent_file_and_omits_empty_matcher(tmp_path):
    path = tmp_path / "hooks.json"
    ensure_global_hooks(path, [{"event": "Stop", "command": "c"}])
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "c"}]}]}}


def test_remove_retired_graphify_hooks_keeps_unrelated_entries(tmp_path):
    path = tmp_path / "settings.json"
    other = {"type": "command", "command": "python keep.py"}
    retired = {"type": "command", "command": "C:/Users/user/.local/bin/graphify.EXE hook-guard search"}
    current = {"type": "command", "command": "F:/Python/uv-tools/bin/graphify.EXE hook-guard read"}
    path.write_text(json.dumps({"model": "keep", "hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [other, retired, current]},
        {"matcher": "Read", "hooks": [
            {"type": "command", "command": "C:/Users/user/.local/bin/graphify.EXE hook-guard read"}]},
        {"matcher": "Empty", "hooks": []},
    ], "Stop": {"hooks": [other, {"type": "command",
                                    "command": "C:/Users/user/.local/bin/graphify.EXE hook-check"}]}}}),
        encoding="utf-8")

    assert remove_retired_graphify_hooks(path) is True
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = data["hooks"]["PreToolUse"]
    assert data["model"] == "keep"
    assert groups[0]["hooks"] == [other, current]
    assert groups[1] == {"matcher": "Empty", "hooks": []}
    assert data["hooks"]["Stop"] == {"hooks": [other]}
    assert all("C:/Users/user/.local/bin/graphify.EXE" not in hook["command"]
               for group in groups for hook in group["hooks"])
    assert remove_retired_graphify_hooks(path) is False


def test_sync_hermes_uses_native_writer_for_registry_entries(config, tmp_path, monkeypatch, capsys):
    import subprocess
    import adapter

    hermes = tmp_path / "venv" / "Scripts" / "hermes.exe"
    hermes.parent.mkdir(parents=True)
    python = hermes.with_name("python.exe")
    python.touch()
    monkeypatch.setattr(adapter.shutil, "which", lambda name: str(hermes))
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, '{"saved": ["retrieve-skills", "todo"]}', "")

    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    adapter.sync_hermes(config)

    args, kwargs = calls[0]
    assert args[:2] == [str(python), "-c"]
    assert json.loads(kwargs["input"]) == {
        "retrieve-skills": {"enabled": True, "url": "http://127.0.0.1:8765/mcp"},
        "todo": {"enabled": True, "command": "python", "args": ["todo_mcp.py"],
                 "env": {"PYTHONUTF8": "1"}},
    }
    assert kwargs["check"] is True and kwargs["capture_output"] is True
    assert "projected 2 servers" in capsys.readouterr().out
