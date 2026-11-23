"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| FIXTURE | Supply isolated native-API doubles and dummy configuration | [mandatory] | R1 |
| PROJECT | Exercise MCP and party merges, preflight, snapshot, native saves, and readback | [mandatory] | R2, R4 |
| ASSERT | Verify preservation, rejection, and unchanged-byte behavior | [contract] | R3 |

R1: When tests execute, the system shall avoid live Hermes configuration and installed providers.
R2: When a native API rejects or loses data, the system shall expose projection failure.
R3: When projection repeats, the system shall preserve bytes and backup count.
CLOSED: Payload-only subprocess mocks do not establish preservation or snapshot behavior.
R4: When party models are projected, the system shall preserve provider credentials, unrelated aliases, MCP registrations, and non-owned model/delegation settings.
Preconditions: pytest is installed. Failure modes: any incorrect stage transition fails assertions.
"""
from __future__ import annotations

import copy
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pytest


@pytest.fixture
def native_bridge(tmp_path, monkeypatch):
    """Load the optional Hermes bridge against isolated native API doubles.

    Returns:
        Bridge module, dummy configuration path, and call counters.

    Require: pytest supplies isolated storage and restores module patches.
    Guarantee: Imports cannot load installed Hermes or read operator data.
    Maintain: The backend stores only synthetic JSON fixture values.
    Assert: Native API calls are counted independently from projection assertions.
    """
    path = tmp_path / "config.yaml"
    initial = {"model": {"provider": "fixture"}, "sentinel": [1, 2], "mcp_servers": {
        "unmanaged": {"url": "http://localhost:9998/mcp"},
        "managed": {"command": "old.exe", "args": [], "env": {"KEEP": "yes", "OWNED": "old"},
                    "headers": {"X-Fixture": "preserve"}, "tools": {"exclude": ["unsafe"]}},
    }}
    path.write_text(json.dumps(initial), encoding="utf-8")
    calls = {"snapshot": 0, "save": 0, "config_save": 0}

    def load():
        """Read synthetic state; require fixture path, guarantee an independent mapping."""
        return json.loads(path.read_text(encoding="utf-8"))

    def save(name, entry):
        """Persist one dummy native entry; maintain all other fixture fields."""
        calls["save"] += 1
        data = load()
        data["mcp_servers"][name] = copy.deepcopy(entry)
        path.write_text(json.dumps(data), encoding="utf-8")
        return True

    def snapshot(label, hermes_home):
        """Capture dummy bytes before native saves and return the native identifier."""
        calls["snapshot"] += 1
        destination = hermes_home / "state-snapshots" / label / "config.yaml"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(path.read_bytes())
        return label

    def save_config(config, *, merge_existing=False):
        """Persist the proposed full configuration through a native API double."""
        assert merge_existing is True
        calls["config_save"] += 1
        path.write_text(json.dumps(config), encoding="utf-8")

    modules = {
        "hermes_cli.backup": {"create_quick_snapshot": snapshot},
        "hermes_cli.config": {"get_config_path": lambda: path, "load_config": load, "save_config": save_config},
        "hermes_cli.mcp_config": {"_save_mcp_server": save, "_resolve_mcp_server_config": lambda entry: entry},
        "hermes_cli.mcp_security": {"validate_mcp_server_entry": lambda name, entry: []},
        "tools.mcp_tool": {"MCPServerTask": None},
        "tools.mcp_tool_loop": {"_ensure_mcp_loop": None, "_run_on_mcp_loop": None, "_stop_mcp_loop": None},
    }
    monkeypatch.setitem(sys.modules, "hermes_cli", ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "tools", ModuleType("tools"))
    for name, attributes in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    source = Path(__file__).resolve().parents[1] / "scripts" / "hermes_mcp.py"
    spec = importlib.util.spec_from_file_location("hermes_bridge_fixture", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path, calls


@pytest.mark.parametrize("incoming", [
    {"command": "current.exe", "args": ["serve"], "env": {"OWNED": "current"}, "enabled": True, "connect_timeout": 240},
    {"url": "http://localhost:9999/mcp", "enabled": True},
    {"command": "current.exe", "args": [], "enabled": True},
])
def test_preserves_controls_and_root_values_and_skips_repeat_writes(native_bridge, incoming):
    """Require varied transports; guarantee preserved controls and no second mutation."""
    bridge, path, calls = native_bridge
    before = json.loads(path.read_text())
    result = bridge.project({"managed": incoming})
    after = json.loads(path.read_text())
    assert result["changed"] == ["managed"] and result["snapshot"]
    assert after["model"] == before["model"] and after["sentinel"] == before["sentinel"]
    assert after["mcp_servers"]["unmanaged"] == before["mcp_servers"]["unmanaged"]
    managed = after["mcp_servers"]["managed"]
    assert managed["tools"] == {"exclude": ["unsafe"]} and managed["headers"] == {"X-Fixture": "preserve"}
    if "command" in incoming:
        assert managed["env"]["KEEP"] == "yes"
    unchanged = path.read_bytes()
    assert bridge.project({"managed": incoming})["changed"] == []
    assert path.read_bytes() == unchanged and calls == {"snapshot": 1, "save": 1, "config_save": 0}


def test_invalid_final_entry_prevents_every_write(native_bridge, monkeypatch):
    """Require an invalid later entry; guarantee full-batch rejection before backup."""
    bridge, path, calls = native_bridge
    before = path.read_bytes()
    monkeypatch.setattr(bridge, "validate_mcp_server_entry", lambda name, entry: ["invalid"] if name == "bad" else [])
    with pytest.raises(ValueError, match="bad"):
        bridge.project({"managed": {"url": "http://localhost/mcp"}, "bad": {"url": "invalid"}})
    assert path.read_bytes() == before and calls == {"snapshot": 0, "save": 0, "config_save": 0}


@pytest.mark.parametrize("snapshot_result", [None, "missing-capture"])
def test_snapshot_failure_prevents_saves(native_bridge, monkeypatch, snapshot_result):
    """Require a failed or incomplete native snapshot; guarantee unchanged config."""
    bridge, path, calls = native_bridge
    before = path.read_bytes()
    monkeypatch.setattr(bridge, "create_quick_snapshot", lambda **kwargs: snapshot_result)
    with pytest.raises(RuntimeError, match="snapshot"):
        bridge.project({"managed": {"url": "http://localhost/mcp"}})
    assert path.read_bytes() == before and calls["save"] == 0


def test_false_native_save_is_not_reported_as_success(native_bridge, monkeypatch):
    """Require native rejection after backup; guarantee visible failure and recovery copy."""
    bridge, path, calls = native_bridge
    before = path.read_bytes()
    monkeypatch.setattr(bridge, "_save_mcp_server", lambda name, entry: False)
    with pytest.raises(RuntimeError, match="did not save"):
        bridge.project({"managed": {"url": "http://localhost/mcp"}})
    assert path.read_bytes() == before and calls["snapshot"] == 1


@pytest.mark.parametrize("unowned", [
    {"providers": {"litellm": {"key_env": "FIXTURE_LITELLM_KEY"}}},
    {"model": {"provider": "fixture", "max_tokens": 4096},
     "model_aliases": {"personal": {"model": "fixture-model", "provider": "fixture"}}},
    {"delegation": {"max_iterations": 17}, "sentinel": {"retain": True}},
])
def test_party_projection_sets_four_roles_and_preserves_unowned_config(native_bridge, unowned):
    """Require varied native state; guarantee role defaults and user-owned data survive."""
    bridge, path, calls = native_bridge
    before = json.loads(path.read_text(encoding="utf-8"))
    before.update(copy.deepcopy(unowned))
    path.write_text(json.dumps(before), encoding="utf-8")
    roles = {"leader": "party-leader", "fighter": "party-fighter",
             "scout": "party-scout", "oracle": "party-oracle"}
    payload = {"provider": "litellm", "base_url": "http://127.0.0.1:4000/v1", "models": roles}

    result = bridge.project_party(payload)
    after = json.loads(path.read_text(encoding="utf-8"))
    assert result == {"default_model": "party-leader", "delegation_model": "party-fighter",
                      "aliases": ["fighter", "leader", "oracle", "scout"],
                      "changed": True, "snapshot": result["snapshot"]}
    assert result["snapshot"]
    assert after["providers"]["litellm"]["api"] == payload["base_url"]
    assert after["model"] | {} == {**before.get("model", {}), "provider": "custom:litellm", "default": "party-leader"}
    assert {key: after["model_aliases"][key]["model"] for key in roles} == roles
    assert after["delegation"]["model"] == "party-fighter"
    assert after["mcp_servers"] == before["mcp_servers"] and after["sentinel"] == before["sentinel"]
    for section, values in unowned.items():
        if section == "providers":
            for provider_name, provider_values in values.items():
                assert all(after[section][provider_name][key] == value
                           for key, value in provider_values.items())
        else:
            assert all(after[section][key] == value
                       for key, value in values.items()
                       if key not in {"provider", "default"} or section != "model")
    unchanged = path.read_bytes()
    repeated = bridge.project_party(payload)
    assert repeated["changed"] is False and repeated["snapshot"] is None
    assert path.read_bytes() == unchanged and calls["config_save"] == 1 and calls["snapshot"] == 1


def test_party_projection_rejects_invalid_roles_before_snapshot(native_bridge):
    """Require a missing alias; guarantee no Hermes config mutation starts."""
    bridge, path, calls = native_bridge
    before = path.read_bytes()
    with pytest.raises(ValueError, match="four non-empty role model IDs"):
        bridge.project_party({"provider": "litellm", "base_url": "http://localhost/v1",
                              "models": {"leader": "party-leader"}})
    assert path.read_bytes() == before and calls["snapshot"] == calls["config_save"] == 0


def test_party_snapshot_failure_prevents_native_save(native_bridge, monkeypatch):
    """Require an invalid snapshot; guarantee Hermes' native writer is not called."""
    bridge, path, calls = native_bridge
    before = path.read_bytes()
    monkeypatch.setattr(bridge, "create_quick_snapshot", lambda **kwargs: None)
    with pytest.raises(RuntimeError, match="snapshot"):
        bridge.project_party({"provider": "litellm", "base_url": "http://localhost/v1",
                              "models": {"leader": "L", "fighter": "F", "scout": "S", "oracle": "O"}})
    assert path.read_bytes() == before and calls["config_save"] == 0


def test_party_readback_failure_is_not_reported_as_success(native_bridge, monkeypatch):
    """Require a native save that drops the proposal; guarantee readback refuses success."""
    bridge, path, calls = native_bridge
    monkeypatch.setattr(bridge, "save_config", lambda config, **kwargs: None)
    with pytest.raises(RuntimeError, match="readback"):
        bridge.project_party({"provider": "litellm", "base_url": "http://localhost/v1",
                              "models": {"leader": "L", "fighter": "F", "scout": "S", "oracle": "O"}})
    assert calls["snapshot"] == 1 and path.is_file()


def test_silent_native_noop_fails_readback(native_bridge, monkeypatch):
    """Require a falsely successful writer; guarantee readback catches missing changes."""
    bridge, _, _ = native_bridge
    monkeypatch.setattr(bridge, "_save_mcp_server", lambda name, entry: True)
    with pytest.raises(RuntimeError, match="readback"):
        bridge.project({"managed": {"url": "http://localhost/mcp"}})


@pytest.mark.parametrize("failure", [None, "empty", "timeout", "canary"])
def test_native_probe_separates_connection_and_usability_and_always_closes(native_bridge, monkeypatch, failure):
    """Require varied native outcomes; guarantee bounded failure and sibling teardown.

    Require: The transport double exposes the native task/session contract.
    Guarantee: Empty catalogs, startup failure, and incorrect canaries reject success.
    Maintain: Every created server task is shut down without model or network calls.
    Assert: Successful evidence contains both catalog counts and executed canaries.
    """
    bridge, _, _ = native_bridge
    closed = []
    configured = {"managed": {"command": "fixture.exe"}, "retrieve-skills": {"url": "http://localhost/mcp"}}

    class Server:
        """Supply a deterministic native-task boundary for lifecycle verification."""

        def __init__(self, name):
            """Require a registered name; maintain independent tool-call counters."""
            self.name = name
            self._tools = [] if failure == "empty" and name == "managed" else [SimpleNamespace(name="fixture_tool")]
            self.session = self
            self.called = 0

        async def start(self, config):
            """Guarantee either native readiness or a simulated startup deadline."""
            if failure == "timeout" and self.name == "managed":
                raise asyncio.TimeoutError()

        async def call_tool(self, name, arguments):
            """Return varied deterministic retrieval evidence without network access."""
            expected = ["graphify", "speckit", "retrieve-skills"][self.called]
            assert name == "retrieve_skills" and arguments == {"query": expected, "k": 3}
            self.called += 1
            text = "PASS unrelated " if failure == "canary" else f"PASS {expected} "
            return SimpleNamespace(isError=False, content=[SimpleNamespace(text=text)])

        async def shutdown(self):
            """Record teardown so failed initialization cannot orphan a child task."""
            closed.append(self.name)

    monkeypatch.setattr(bridge, "load_config", lambda: {"mcp_servers": configured})
    monkeypatch.setattr(bridge, "MCPServerTask", Server)
    monkeypatch.setattr(bridge, "_ensure_mcp_loop", lambda: None)
    monkeypatch.setattr(bridge, "_run_on_mcp_loop", lambda coroutine, timeout: asyncio.run(coroutine))
    monkeypatch.setattr(bridge, "_stop_mcp_loop", lambda **kwargs: True)
    if failure:
        with pytest.raises((RuntimeError, asyncio.TimeoutError)):
            bridge.verify(configured)
    else:
        result = bridge.verify(configured)
        assert result["connected"] == {"managed": 1, "retrieve-skills": 1}
        assert result["usable"] == ["graphify", "speckit", "retrieve-skills"]
    assert set(closed) == set(configured)
