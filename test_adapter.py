"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| FIXTURE | Build temporary harness homes and representative MCP configs | [mandatory] | R1 |
| PROJECT | Invoke each harness adapter against its temporary destinations | [mandatory] | R1 |
| ROUTE | Check Codex proxy projection preserves provider roles, protocol, and auth mode | [mandatory] | R7, R10 |
| PLUGIN | Check OpenCode projects and registers its canonical SDD plugin and direct Oracle handoff | [mandatory] | R11-R13 |
| FILTER | Check per-agent tool patterns, MCP permissions, and role settings survive OpenCode projection | [mandatory] | R8, R14 |
| VERIFY | Check native formats, registry-backed prompt text, Hermes writer payload, and preserved files | [mandatory] | R2, R3, R5, R6 |

R1: When a sync test runs, its fixtures MUST isolate writes from live config.
R2: When VS Code instructions are generated, they MUST contain the complete
canonical claude/AGENTS.md text (prompt-sync requirement R5).
R3: When VS Code sync repeats, its generated instructions MUST remain identical.
R4: When a local MCP is projected to OpenCode, the test MUST assert the configured
tool-fetch timeout covers the measured cold start.
R5: When a retired Graphify hook is removed, every unrelated hook and setting MUST survive.
R6: When the instruction registry exists, VS Code prompt content MUST equal its rendered shared document.
R7: When Codex Headroom routing is enabled, tests MUST verify the selected provider URL changes while model IDs, credentials, wire_api, and unmanaged settings survive.
R8: When OpenCode agent tool patterns are projected, tests MUST verify only the selected agent changes and the write is repeatable.
R9: When Codex routing sees an empty ignored api_key, tests MUST confirm its removal; nonempty unsupported credentials MUST refuse writes.
R10: When Codex's custom provider has no supported credential, the system shall project `requires_openai_auth = false`. If it has a supported credential, then the system shall preserve its authentication setting.
R11: When OpenCode sync applies, the system shall project the canonical SDD plugin and its helper files.
R12: When an Oracle task is prepared, the generated plugin shall preserve the original task and evidence without a pre-dispatch model request.
R13: When OpenCode sync applies, the system shall register the projected SDD plugin once and preserve unrelated registered plugins.
R14: When OpenCode sync applies, the Oracle role shall receive only the configured skill-retrieval MCP permissions, with other role permissions unchanged and repeat sync idempotent.

CLOSED: Pinning the literal '# Operating Core' title was rejected because the
operator's updated canonical prompt uses '# Operating Contract'.

Preconditions: pytest and the adapter dependencies are installed.
Failure modes: malformed projection, omitted prompt text, overwritten unmanaged
files, or non-idempotent generation fail assertions.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import ast
from pathlib import Path
from unittest.mock import patch

import pytest
import harness_write

from adapter import (
    HARNESS_AGENTS,
    HARNESS_RULES_DB,
    _harness_agents_text,
    _project_opencode_agent_tools,
    ensure_global_hooks,
    load_harness,
    remove_retired_graphify_hooks,
    sync_claude_code,
    sync_codex,
    sync_codex_hooks,
    _project_codex_provider_route,
    tomllib,
    sync_github_copilot,
    sync_kiro,
    sync_opencode,
    sync_vscode,
    sync_instruction_plugins,
    _render_opencode_rule_plugin,
    _render_claude_rule_plugin,
)
from instructions.rules import RuleStore


@pytest.fixture(autouse=True)
def isolate_user_home(tmp_path, monkeypatch):
    """Keep adapter tests and backup writes inside pytest-owned storage.

    Require: pytest supplies a temporary directory before each test.
    Guarantee: Path.home resolves to that isolated home for every adapter operation.
    Maintain: Canonical source paths captured at import time are unchanged.
    Assert: Tests cannot populate the operator's live backup directory.
    """
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))


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
    config["opencode_plugins"] = ["@tarquinen/opencode-dcp@latest"]
    with patch("adapter.Path.home", return_value=tmp_path):
        sync_opencode(config)
    data = json.loads(oc_json.read_text())
    assert data["mcp"]["retrieve-skills"]["type"] == "remote"
    assert data["mcp"]["todo"]["type"] == "local"
    assert data["mcp"]["todo"]["command"] == ["python", "todo_mcp.py"]
    assert data["mcp"]["todo"]["timeout"] == 240000
    assert data["mcp"]["todo"]["environment"] == {"PYTHONUTF8": "1"}
    assert data["plugin"] == [
        str(oc_dir / "plugins" / "sdd-harness.js"),
        "@tarquinen/opencode-dcp@latest",
    ]


def test_sync_opencode_projects_the_canonical_sdd_plugin_and_helper(config, tmp_path):
    oc_dir = tmp_path / ".config" / "opencode"
    oc_dir.mkdir(parents=True)
    oc_json = oc_dir / "opencode.json"
    oc_json.write_text(json.dumps({"plugin": ["operator-plugin"]}), encoding="utf-8")
    backup_root = tmp_path / "backups"
    with patch("adapter.Path.home", return_value=tmp_path), patch("adapter.BACKUP_RUN", backup_root):
        sync_opencode(config)
        plugin_path = oc_dir / "plugins" / "sdd-harness.js"
        helper_path = oc_dir / "plugins" / "oracle-context.py"
        plugin_text = plugin_path.read_text(encoding="utf-8")
        assert plugin_text == (Path(__file__).parent / "plugin" / ".opencode" / "plugins" / "sdd-harness.js").read_text(encoding="utf-8")
        assert helper_path.read_bytes() == (Path(__file__).parent / "plugin" / ".opencode" / "plugins" / "oracle-context.py").read_bytes()
        assert "Original Leader task" in plugin_text
        assert "Recent Leader evidence" in plugin_text
        assert "summarizeForOracle" not in plugin_text
        assert "oracleSummaryEndpoint" not in plugin_text
        assert "44017" not in plugin_text
        projected = json.loads(oc_json.read_text(encoding="utf-8"))
        assert projected["plugin"] == ["operator-plugin", str(plugin_path)]
        first_hashes = (plugin_path.read_bytes(), helper_path.read_bytes(), oc_json.read_bytes())
        sync_opencode(config)
        assert (plugin_path.read_bytes(), helper_path.read_bytes(), oc_json.read_bytes()) == first_hashes


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


@pytest.mark.parametrize(
    ("agent_name", "model", "pattern"),
    [
        ("orchestrator", "litellm/party-leader", "rea*"),
        ("reader", "litellm/party-scout", "graphify*"),
        ("oracle", "litellm/party-oracle", "data-science-skills*"),
    ],
)
def test_opencode_agent_tool_projection_preserves_role_and_unmanaged_config(
    agent_name, model, pattern, tmp_path
):
    oc_json = tmp_path / "opencode.json"
    oc_json.write_text(
        json.dumps({
            "agent": {
                agent_name: {"model": model, "prompt": "Keep this prompt", "tools": {"read": True}},
                "unselected": {"model": "litellm/party-fighter", "tools": {"edit": True}},
            },
            "provider": {"litellm": {"baseURL": "http://127.0.0.1:8789/v1"}},
        }),
        encoding="utf-8",
    )
    rules = {agent_name: {pattern: False}}

    assert _project_opencode_agent_tools(oc_json, rules)
    before = oc_json.read_bytes()
    data = json.loads(before)
    assert data["agent"][agent_name]["model"] == model
    assert data["agent"][agent_name]["prompt"] == "Keep this prompt"
    assert data["agent"][agent_name]["tools"] == {"read": True, pattern: False}
    assert data["agent"]["unselected"] == {"model": "litellm/party-fighter", "tools": {"edit": True}}
    assert data["provider"]["litellm"]["baseURL"] == "http://127.0.0.1:8789/v1"
    assert not _project_opencode_agent_tools(oc_json, rules)
    assert oc_json.read_bytes() == before


def test_opencode_agent_permission_projection_adds_only_named_mcp_access(tmp_path):
    oc_json = tmp_path / "opencode.json"
    oc_json.write_text(
        json.dumps({
            "agent": {
                "oracle": {
                    "model": "litellm/party-oracle",
                    "permission": {"*": "deny", "read": "allow", "task": "deny"},
                    "tools": {"read": True},
                },
                "orchestrator": {
                    "model": "litellm/party-leader",
                    "permission": {"task": {"*": "deny", "oracle": "allow"}},
                },
            },
        }),
        encoding="utf-8",
    )
    permissions = {
        "oracle": {
            "retrieve-skills_retrieve_skills": "allow",
            "retrieve-skills_read_skill": "allow",
        },
    }

    assert _project_opencode_agent_tools(oc_json, {}, permissions)
    before = oc_json.read_bytes()
    data = json.loads(before)
    assert data["agent"]["oracle"]["permission"] == {
        "*": "deny",
        "read": "allow",
        "task": "deny",
        "retrieve-skills_retrieve_skills": "allow",
        "retrieve-skills_read_skill": "allow",
    }
    assert data["agent"]["oracle"]["tools"] == {"read": True}
    assert data["agent"]["oracle"]["model"] == "litellm/party-oracle"
    assert data["agent"]["orchestrator"]["permission"] == {
        "task": {"*": "deny", "oracle": "allow"},
    }
    assert not _project_opencode_agent_tools(oc_json, {}, permissions)
    assert oc_json.read_bytes() == before


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


@pytest.mark.parametrize(
    ("model_id", "configured_url"),
    [
        ("gpt-5.4", "http://127.0.0.1:4000/v1"),
        ("gpt-5.4-mini", "http://localhost:4000/v1"),
        ("qwopus-coding-thinking-256k:9b", "http://127.0.0.1:4000/v1"),
    ],
)
def test_codex_context_route_preserves_role_and_provider_settings(model_id, configured_url, tmp_path):
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        f'model = "{model_id}"\nmodel_provider = "copilot-proxy"\n\n'
        '[model_providers.copilot-proxy]\n'
        'name = "copilot-proxy"\n'
        f'base_url = "{configured_url}" # shared local gateway\n'
        'wire_api = "responses"\n'
        'env_key = "CODEX_GATEWAY_API_KEY"\n'
        '\n[profiles.party_oracle_openai]\n'
        'model = "gpt-6.2-sol"\nmodel_provider = "copilot-proxy"\n',
        encoding="utf-8",
    )
    proxy = {
        "provider": "copilot-proxy",
        "upstream_url": "http://127.0.0.1:4000/v1",
        "proxy_url": "http://127.0.0.1:8789/v1",
    }

    assert _project_codex_provider_route(cfg, proxy)
    text = cfg.read_text(encoding="utf-8")
    projected = tomllib.loads(text)
    assert projected["model"] == model_id
    assert projected["model_provider"] == "copilot-proxy"
    assert projected["model_providers"]["copilot-proxy"]["base_url"] == proxy["proxy_url"]
    assert projected["model_providers"]["copilot-proxy"]["wire_api"] == "responses"
    assert projected["model_providers"]["copilot-proxy"]["env_key"] == "CODEX_GATEWAY_API_KEY"
    assert projected["profiles"]["party_oracle_openai"]["model"] == "gpt-6.2-sol"
    assert "# shared local gateway" in text
    assert not _project_codex_provider_route(cfg, proxy)


def test_codex_route_removes_empty_ignored_api_key_and_keeps_comment(tmp_path):
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '[model_providers.copilot-proxy]\n'
        'base_url = "http://127.0.0.1:4000/v1"\n'
        'wire_api = "responses"\n'
        'api_key = "" # no credential configured\n',
        encoding="utf-8",
    )
    proxy = {
        "provider": "copilot-proxy",
        "upstream_url": "http://127.0.0.1:4000/v1",
        "proxy_url": "http://127.0.0.1:8789/v1",
    }

    assert _project_codex_provider_route(cfg, proxy)
    text = cfg.read_text(encoding="utf-8")
    provider = tomllib.loads(text)["model_providers"]["copilot-proxy"]
    assert provider == {
        "base_url": proxy["proxy_url"],
        "wire_api": "responses",
        "requires_openai_auth": False,
    }
    assert "# no credential configured" in text
    assert not _project_codex_provider_route(cfg, proxy)


def test_codex_route_refuses_nonempty_unsupported_api_key_without_writing(tmp_path):
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    original = (
        '[model_providers.copilot-proxy]\n'
        'base_url = "http://127.0.0.1:4000/v1"\n'
        'wire_api = "responses"\n'
        'api_key = "secret"\n'
    )
    cfg.write_text(original, encoding="utf-8")
    proxy = {
        "provider": "copilot-proxy",
        "upstream_url": "http://127.0.0.1:4000/v1",
        "proxy_url": "http://127.0.0.1:8789/v1",
    }

    with pytest.raises(harness_write.WriteError, match="nonempty unsupported api_key"):
        _project_codex_provider_route(cfg, proxy)
    assert cfg.read_text(encoding="utf-8") == original


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


def test_harness_instruction_text_uses_registry_when_available(tmp_path, monkeypatch):
    """Make the SQLite render the VS Code prompt source after registry setup.

    Require: the registry has a shared document that differs from the Markdown export.
    Guarantee: adapter returns rendered registry bytes, not the export file contents.
    Assert: exact UTF-8 text survives the adapter source boundary.
    """
    source = tmp_path / "source.md"
    source.write_bytes(b"# Registry authority\n")
    store = RuleStore(tmp_path / "rules.sqlite")
    store.import_markdown("shared", source)
    monkeypatch.setattr("adapter.HARNESS_RULES_DB", store.path)
    monkeypatch.setattr("adapter.HARNESS_AGENTS", tmp_path / "stale.md")
    (tmp_path / "stale.md").write_text("# stale export\n", encoding="utf-8")
    assert _harness_agents_text().encode("utf-8") == store.render("shared")


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


def _plugin_rule_source(root: Path, audience: str = "opencode") -> Path:
    """Create one explicitly scoped canonical rule fixture."""
    source = root / "rules"
    source.mkdir()
    (source / "100-rule.md").write_text(
        f"---\nharnesses: [{audience}]\norder: 100\n---\n# Marker\nplugin-rule-marker\n",
        encoding="utf-8",
    )
    return source


def test_instruction_plugin_preview_is_read_only(tmp_path, capsys):
    source = _plugin_rule_source(tmp_path)
    database = tmp_path / "rules.sqlite"
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    assert sync_instruction_plugins(clients=["opencode"], source_dir=source, database=database) == 0

    after = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before
    assert not database.exists()
    assert "would_write" in capsys.readouterr().out


def test_instruction_plugin_without_client_previews_every_verified_route(tmp_path, capsys):
    source = _plugin_rule_source(tmp_path, "claude, opencode")
    database = tmp_path / "rules.sqlite"

    assert sync_instruction_plugins(source_dir=source, database=database) == 0

    output = capsys.readouterr().out
    assert "claude: would_write" in output
    assert "opencode: would_write" in output
    assert not database.exists()
    assert not list(tmp_path.rglob("*.js"))
    assert not list(tmp_path.rglob("rules.py"))


def test_instruction_plugin_unsupported_target_has_no_fallback(tmp_path, capsys):
    source = _plugin_rule_source(tmp_path, "copilot")
    database = tmp_path / "rules.sqlite"

    assert sync_instruction_plugins(clients=["copilot"], apply=True, source_dir=source, database=database) == 1

    assert not database.exists()
    assert not (tmp_path / ".copilot" / "instructions" / "harness-rules.instructions.md").exists()
    assert "no base export attempted" in capsys.readouterr().out


def test_instruction_plugin_cli_routes_apply_to_plugin_export(monkeypatch):
    import adapter

    seen = []
    monkeypatch.setattr(adapter, "sync_instruction_plugins", lambda **kwargs: seen.append(kwargs) or 0)
    monkeypatch.setattr("sys.argv", ["adapter.py", "--target", "instructions", "--client", "opencode", "--plugin", "--apply"])

    with pytest.raises(SystemExit) as exit_status:
        adapter.main()

    assert exit_status.value.code == 0
    assert seen == [{"clients": ["opencode"], "apply": True}]


def test_instruction_cli_without_plugin_keeps_base_export_default(monkeypatch):
    import adapter

    seen = []
    monkeypatch.setattr(adapter, "sync_instructions", lambda **kwargs: seen.append(kwargs) or 0)
    monkeypatch.setattr(adapter, "sync_instruction_plugins", lambda **kwargs: pytest.fail("plugin route selected"))
    monkeypatch.setattr("sys.argv", ["adapter.py", "--target", "instructions", "--client", "claude"])

    with pytest.raises(SystemExit) as exit_status:
        adapter.main()

    assert exit_status.value.code == 0
    assert seen == [{"clients": ["claude"], "apply": False, "map_baseline": False}]


def test_opencode_instruction_plugin_runtime_hook_preserves_system_prompt(tmp_path):
    source = _plugin_rule_source(tmp_path)
    fragments, _ = __import__("adapter")._instruction_fragments(source)
    plugin = tmp_path / "harness-rules.js"
    plugin.write_bytes(_render_opencode_rule_plugin(fragments))
    probe = (
        f"const p=require({json.dumps(str(plugin))});"
        "(async()=>{const h=await p.server({});const o={system:['base-system']};"
        "await h['experimental.chat.system.transform']({},o);console.log(JSON.stringify(o.system));})();"
    )
    result = subprocess.run(["node", "-e", probe], capture_output=True, text=True, check=True)
    injected = json.loads(result.stdout)
    assert injected[0] == "base-system"
    assert "plugin-rule-marker" in injected[1]


def test_claude_instruction_plugin_preview_is_read_only_and_package_valid(tmp_path, capsys):
    source = _plugin_rule_source(tmp_path, "claude")
    database = tmp_path / "rules.sqlite"
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    assert sync_instruction_plugins(clients=["claude"], source_dir=source, database=database) == 0

    after = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before and not database.exists()
    rendered = _render_claude_rule_plugin(__import__("adapter")._instruction_fragments(source)[0])
    package = tmp_path / "package"
    for relative, content in rendered.items():
        if str(relative).startswith("../../"):
            continue
        destination = package / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    validation = subprocess.run(["claude", "plugin", "validate", str(package), "--json"],
                                capture_output=True, text=True, check=False)
    assert validation.returncode == 0, validation.stderr
    assert "would run plugin install --scope user" in capsys.readouterr().out


def test_claude_instruction_plugin_chunks_selected_rules_in_hook_order():
    fragments = [
        {"body": "a" * 7999 + "\n"},
        {"body": "b" * 7999 + "\n"},
        {"body": "c" * 41},
    ]
    expected = "\n".join(item["body"].rstrip("\r\n") for item in fragments).rstrip() + "\n"
    rendered = _render_claude_rule_plugin(fragments)
    hooks = json.loads(rendered[Path("hooks/hooks.json")])
    commands = hooks["hooks"]["UserPromptSubmit"]
    chunks = []
    for entry in commands:
        command = entry["hooks"][0]["command"]
        relative = Path(command.rsplit("/hooks/", 1)[1].rstrip('"'))
        script = rendered[Path("hooks") / relative].decode("utf-8")
        assignment = ast.parse(script).body[2]
        assert isinstance(assignment, ast.Assign)
        chunk = ast.literal_eval(assignment.value)
        assert len(chunk) <= 8000
        chunks.append(chunk)
    assert "".join(chunks) == expected


def test_claude_instruction_plugin_apply_uses_native_user_activation_without_base_mutation(tmp_path, monkeypatch):
    source = _plugin_rule_source(tmp_path, "claude")
    database = tmp_path / "rules.sqlite"
    RuleStore(database)
    base = tmp_path / ".claude" / "AGENTS.md"
    base.parent.mkdir(parents=True)
    base.write_bytes(b"base-rule-bytes")
    calls = []
    installed = False

    def fake_cli(args):
        nonlocal installed
        calls.append(args)
        if args == ["list", "--json"]:
            if not installed:
                return subprocess.CompletedProcess(args, 0, "[]", "")
            manifest = json.loads((tmp_path / ".harness" / "plugin-export" / "claude" / "plugins" / "harness-rules" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
            return subprocess.CompletedProcess(args, 0, json.dumps([{
                "id": "harness-rules@harness-rules-local", "version": manifest["version"],
                "scope": "user", "enabled": True,
            }]), "")
        if args[0] == "install":
            installed = True
        return subprocess.CompletedProcess(args, 0, "{}", "")

    monkeypatch.setattr("adapter._run_claude_plugin", fake_cli)
    assert sync_instruction_plugins(clients=["claude"], apply=True, source_dir=source, database=database) == 0
    root = tmp_path / ".harness" / "plugin-export" / "claude" / "plugins" / "harness-rules"
    hook = root / "hooks" / "rules.py"
    assert b"plugin-rule-marker" in hook.read_bytes()
    assert (root / ".claude-plugin" / "plugin.json").is_file()
    assert (root.parent.parent / ".claude-plugin" / "marketplace.json").is_file()
    assert base.read_bytes() == b"base-rule-bytes"
    assert ["validate", str(root)] in calls
    assert any(call[:2] == ["install", "harness-rules"] and "--scope" in call and "user" in call for call in calls)
    assert ["list", "--json"] in calls


def test_instruction_plugin_apply_preserves_base_settings_and_is_idempotent(tmp_path):
    source = _plugin_rule_source(tmp_path)
    database = tmp_path / "rules.sqlite"
    RuleStore(database)
    base = tmp_path / ".config" / "opencode" / "harness-registry-shared.md"
    base.parent.mkdir(parents=True)
    base.write_bytes(b"base-rule-bytes")
    config = base.parent / "opencode.json"
    config.write_text(json.dumps({"model": "keep", "plugin": ["existing-plugin"], "mcp": {"keep": {}}}), encoding="utf-8")

    assert sync_instruction_plugins(clients=["opencode"], apply=True, source_dir=source, database=database) == 0
    plugin_path = base.parent / "plugins" / "harness-rules.js"
    first_plugin = plugin_path.read_bytes()
    first_config = json.loads(config.read_text(encoding="utf-8"))
    assert b"plugin-rule-marker" in first_plugin
    assert base.read_bytes() == b"base-rule-bytes"
    assert first_config["model"] == "keep" and first_config["mcp"] == {"keep": {}}
    assert first_config["plugin"][0] == "existing-plugin"
    assert first_config["plugin"].count(str(plugin_path)) == 1

    assert sync_instruction_plugins(clients=["opencode"], apply=True, source_dir=source, database=database) == 0
    assert plugin_path.read_bytes() == first_plugin
    assert json.loads(config.read_text(encoding="utf-8")) == first_config
    with sqlite3.connect(database) as db:
        docs = {row[0] for row in db.execute("SELECT document_id FROM documents")}
    assert "export-opencode-plugin" in docs


def test_claude_instruction_plugin_updates_version_and_reenables_disabled_install(tmp_path, monkeypatch):
    source = _plugin_rule_source(tmp_path, "claude")
    database = tmp_path / "rules.sqlite"
    RuleStore(database)
    calls = []
    version = "0.1.0"
    enabled = False

    def fake_cli(args):
        nonlocal version, enabled
        calls.append(args)
        if args == ["list", "--json"]:
            return subprocess.CompletedProcess(args, 0, json.dumps([{
                "id": "harness-rules@harness-rules-local", "version": version,
                "scope": "user", "enabled": enabled,
            }]), "")
        if args[:1] == ["update"]:
            manifest = json.loads((tmp_path / ".harness" / "plugin-export" / "claude" / "plugins" / "harness-rules" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
            version = manifest["version"]
        if args[:1] == ["enable"]:
            enabled = True
        return subprocess.CompletedProcess(args, 0, "{}", "")

    monkeypatch.setattr("adapter._run_claude_plugin", fake_cli)
    assert sync_instruction_plugins(clients=["claude"], apply=True, source_dir=source, database=database) == 0
    assert ["marketplace", "update", "harness-rules-local"] in calls
    assert any(call[:2] == ["update", "harness-rules@harness-rules-local"] for call in calls)
    assert any(call[:2] == ["enable", "harness-rules@harness-rules-local"] for call in calls)
    assert enabled is True


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
        if args[-1] == "--party":
            return subprocess.CompletedProcess(args, 0,
                '{"default_model": "party-leader", "delegation_model": "party-fighter", '
                '"aliases": ["leader", "fighter", "scout", "oracle"], '
                '"changed": true, "snapshot": "fixture-party"}', "")
        return subprocess.CompletedProcess(args, 0,
            '{"configured": ["retrieve-skills", "todo"], "changed": ["todo"], "snapshot": "fixture"}', "")

    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    adapter.sync_hermes(config)

    args, kwargs = calls[0]
    assert args == [str(python), str(adapter.HERMES_BRIDGE)]
    assert json.loads(kwargs["input"]) == {
        "retrieve-skills": {"enabled": True, "url": "http://127.0.0.1:8765/mcp"},
        "todo": {"enabled": True, "command": "python", "args": ["todo_mcp.py"], "connect_timeout": 240,
                 "env": {"PYTHONUTF8": "1"}},
    }
    assert kwargs["check"] is True and kwargs["capture_output"] is True
    assert kwargs["timeout"] == 300
    party_args, party_kwargs = calls[1]
    assert party_args == [str(python), str(adapter.HERMES_BRIDGE), "--party"]
    assert json.loads(party_kwargs["input"]) == {
        "provider": "litellm",
        "base_url": "http://127.0.0.1:4000/v1",
        "models": {"leader": "party-leader", "fighter": "party-fighter",
                   "scout": "party-scout", "oracle": "party-oracle"},
    }
    output = capsys.readouterr().out
    assert "configured 2 servers; changed 1; snapshot verified" in output
    assert "default=party-leader; delegated=party-fighter; aliases=4; changed=True; snapshot verified" in output


def test_hermes_command_resolves_windows_source_virtualenv(tmp_path, monkeypatch):
    """Require Hermes' bundled executable layout; guarantee its native Python is selected."""
    import adapter

    home = tmp_path / "hermes-home"
    executable = home / "bin" / "hermes.exe"
    interpreter = home / "hermes-agent" / "venv" / "Scripts" / "python.exe"
    executable.parent.mkdir(parents=True)
    interpreter.parent.mkdir(parents=True)
    executable.touch()
    interpreter.touch()
    monkeypatch.setattr(adapter.shutil, "which", lambda name: str(executable))
    monkeypatch.setenv("HERMES_HOME", str(home))

    assert adapter.hermes_command() == [str(interpreter), str(adapter.HERMES_BRIDGE)]


def test_canonical_registry_sync_cannot_reinstall_retired_graphify_hooks(tmp_path):
    """Exercise published registry values rather than a hand-built hook fixture.

    Require: The canonical registry contains the intended runtime paths.
    Guarantee: Both native hook projections contain only current Graphify commands.
    Maintain: All writes use the test's isolated home.
    Assert: Every canonical local interpreter is on F: and no retired hook returns.
    """
    import adapter

    config = load_harness()
    for server in config["mcp_servers"].values():
        if server["type"] == "stdio":
            assert server["command"].lower().startswith("f:/")
    for target in ("claude", "codex"):
        adapter.sync_global_hooks(config, target)
    for path in [tmp_path / ".claude" / "settings.json", tmp_path / ".codex" / "hooks.json"]:
        content = path.read_text(encoding="utf-8")
        assert "F:/Python/uv-tools/bin/graphify.EXE" in content
        assert not any(command in content for command in adapter.RETIRED_GRAPHIFY_HOOK_COMMANDS)


@pytest.mark.parametrize("name,key", [("claude", "mcpServers"), ("codex", "mcp_servers"),
                                      ("vscode", "servers"), ("opencode", "mcp")])
def test_native_projection_metadata_has_the_actual_server_key(name, key):
    """Keep destination metadata usable across different native schemas.

    Require: name identifies an existing native target.
    Guarantee: Metadata exposes its native mapping key and user config path.
    Maintain: No live configuration is read or written.
    Assert: The reported disposition is GENERATE with the expected key.
    """
    import adapter

    contract = adapter.mcp_projection_contract(name)
    assert contract["strategy"] == "GENERATE" and contract["key"] == key
    assert Path(contract["target"]).is_absolute()
