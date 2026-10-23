"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| LOAD | Read configuration through Hermes in its native environment | [mandatory] | R1 |
| MERGE | Overlay registry-owned transport fields and retain user controls | [mandatory] | R2 |
| VALIDATE | Validate the complete proposed batch before mutation | [mandatory] | R3 |
| SNAPSHOT | Verify Hermes' native snapshot contains preceding config bytes | [mandatory] | R4 |
| SAVE | Use Hermes' MCP writer only for changed entries | [mandatory] | R5 |
| VERIFY | Read back managed entries and preserved settings | [contract] | R6 |
| PROBE | Initialize native transports, list tools, and execute retrieval canaries with --verify | [opt] | R7 |

R1: When configuration is accessed, the system shall use Hermes' installed configuration APIs.
R2: When entries are merged, the system shall preserve root settings, unmanaged servers, user tool/auth controls, and unowned environment keys.
R3: If any proposed entry is invalid, then the system shall reject the batch before snapshot or save.
R4: When existing configuration would change, the system shall verify a native configuration snapshot before saving.
R5: When projection is semantically unchanged, the system shall perform no snapshot or save.
R6: If backup, save, or readback fails, then the system shall report failure without emitting configuration values.
R7: Where --verify is requested, the system shall prove connected catalogs and three named retrieval lookups within a 270-second deadline and report server-name-only progress on stderr.

CLOSED: Generic harness_write access to Hermes config is denied; full-home backup and an independent YAML writer are unnecessary because native snapshots and the native MCP writer exist.
Preconditions: execute with the installed Hermes Python; input contains only projected registry entries.
Failure modes: invalid config, incomplete snapshot, native rejection, or readback mismatch raises; a completed snapshot remains available after a partial native-write failure.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from uuid import uuid4

from hermes_cli.backup import create_quick_snapshot
from hermes_cli.config import get_config_path, load_config
from hermes_cli.mcp_config import _resolve_mcp_server_config, _save_mcp_server
from hermes_cli.mcp_security import validate_mcp_server_entry
from tools.mcp_tool import MCPServerTask, _ensure_mcp_loop, _run_on_mcp_loop, _stop_mcp_loop_if_idle


def project(servers: dict) -> dict:
    """Merge, snapshot, save, and verify a registry projection inside Hermes.

    Args:
        servers: Native Hermes MCP entries with registry-owned connection fields.

    Returns:
        Server names, changed names, and a native snapshot identifier; no config values.

    Require: Native Hermes configuration APIs are available and servers is a mapping.
    Guarantee: All proposals pass native validation before writes; backups precede changes.
    Maintain: Unowned settings survive; unchanged calls leave config bytes untouched.
    Assert: Readback matches both proposed entries and the preceding unowned config.
    """
    current = load_config()
    existing = current.get("mcp_servers", {})
    if not isinstance(existing, dict):
        raise ValueError("Hermes mcp_servers must be a mapping")
    proposed = copy.deepcopy(existing)
    changed = []
    for name, incoming in servers.items():
        entry = copy.deepcopy(existing.get(name, {}))
        if not isinstance(entry, dict):
            raise ValueError(f"Hermes MCP entry {name!r} must be a mapping")
        if "url" in incoming:
            for key in ("command", "args", "env"):
                entry.pop(key, None)
        else:
            entry.pop("url", None)
        if "env" in incoming:
            entry["env"] = {**entry.get("env", {}), **incoming["env"]}
        entry.update({key: value for key, value in incoming.items() if key != "env"})
        issues = validate_mcp_server_entry(name, entry)
        if issues:
            raise ValueError(f"Hermes rejected MCP entry {name!r} ({len(issues)} validation issues)")
        proposed[name] = entry
        if entry != existing.get(name):
            changed.append(name)
    if not changed:
        return {"configured": list(servers), "changed": [], "snapshot": None}

    config_path = get_config_path()
    snapshot = None
    if config_path.exists():
        before = config_path.read_bytes()
        snapshot = create_quick_snapshot(label=f"harness-mcp-{uuid4().hex[:8]}", hermes_home=config_path.parent)
        if not snapshot:
            raise RuntimeError("Hermes configuration snapshot was not created")
        captured = config_path.parent / "state-snapshots" / snapshot / "config.yaml"
        if not captured.is_file() or captured.read_bytes() != before:
            raise RuntimeError("Hermes configuration snapshot did not capture preceding bytes")
    for name in changed:
        if not _save_mcp_server(name, proposed[name]):
            raise RuntimeError(f"Hermes did not save MCP entry {name!r}")

    observed = load_config()
    if observed.get("mcp_servers", {}) != proposed:
        raise RuntimeError("Hermes MCP projection readback differs from the proposed batch")
    if any(observed.get(key) != value for key, value in current.items() if key != "mcp_servers"):
        raise RuntimeError("Hermes changed unrelated configuration during projection")
    return {"configured": list(servers), "changed": changed, "snapshot": snapshot}


def verify(servers: dict) -> dict:
    """Check registered entries through Hermes' native transport and session implementation.

    Args:
        servers: Canonical server mapping; only its names select probe targets.

    Returns:
        Configured names, connected tool counts, and successful retrieval canaries.

    Require: Native services are already supervised; stdin names identify their registrations.
    Guarantee: Each selected server initializes and lists at least one tool; retrieval canaries execute.
    Maintain: Temporary stdio children are shut down and no configuration is written.
    Assert: Connection/tool failures or missing expected skills propagate before any success summary.
    """
    configured = load_config().get("mcp_servers", {})
    if set(servers) - set(configured):
        raise ValueError("Hermes configuration is missing canonical MCP registrations")
    connected = {}
    usable = []

    async def probe(name: str) -> None:
        """Require one native registration; guarantee teardown after catalog and canary calls."""
        config = _resolve_mcp_server_config(configured[name])
        server = MCPServerTask(name)
        print(f"Connecting {name}", file=sys.stderr, flush=True)
        try:
            await asyncio.wait_for(server.start(config), timeout=config.get("connect_timeout", 60))
            tools = [tool.name for tool in server._tools]
            if not tools:
                raise RuntimeError(f"Hermes discovered an empty MCP catalog for {name!r}")
            connected[name] = len(tools)
            print(f"Connected {name}: {len(tools)} tools", file=sys.stderr, flush=True)
            if name == "retrieve-skills":
                canaries = [
                    ("graphify", "graphify"),
                    ("speckit", "speckit"),
                    ("retrieve-skills", "retrieve-skills"),
                ]
                for query, expected in canaries:
                    response = await asyncio.wait_for(server.session.call_tool(
                        "retrieve_skills", arguments={"query": query, "k": 3}), timeout=30)
                    text = "\n".join(getattr(block, "text", "") for block in response.content)
                    if response.isError or f"PASS {expected} " not in text:
                        raise RuntimeError(f"Hermes retrieval canary did not return {expected!r}")
                    usable.append(expected)
                    print(f"Usable retrieval lookup: {expected}", file=sys.stderr, flush=True)
        finally:
            await asyncio.wait_for(server.shutdown(), timeout=10)

    async def probe_all() -> None:
        """Require bounded native probes; guarantee all siblings finish teardown after a failure."""
        outcomes = await asyncio.gather(*(probe(name) for name in servers), return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome

    _ensure_mcp_loop()
    try:
        _run_on_mcp_loop(probe_all(), timeout=270)
    finally:
        _stop_mcp_loop_if_idle()
    return {"configured": list(servers), "connected": connected, "usable": usable}


def main() -> None:
    """Expose native destination metadata or execute a JSON-stdin projection.

    Require: The caller uses Hermes' interpreter and captures output privately.
    Guarantee: Stdout contains only path metadata or a value-free projection summary.
    Maintain: Destination inspection does not run load_config or project.
    Assert: Write failures propagate as nonzero process status.
    """
    parser = argparse.ArgumentParser(description="Hermes-native harness MCP projection")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--config-path", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.config_path:
        result = {"path": str(get_config_path())}
    else:
        servers = json.load(sys.stdin)
        result = verify(servers) if args.verify else project(servers)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
