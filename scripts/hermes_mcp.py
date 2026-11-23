"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| BOOTSTRAP | Add the Hermes checkout root from the active virtualenv so native top-level packages resolve | [mandatory] | R1 |
| LOAD | Read configuration through Hermes in its native environment | [mandatory] | R1 |
| MERGE | Overlay registry-owned transport fields and retain user controls | [mandatory] | R2 |
| VALIDATE | Validate the complete proposed batch before mutation | [mandatory] | R3 |
| SNAPSHOT | Verify Hermes' native snapshot contains preceding config bytes | [mandatory] | R4 |
| SAVE | Use Hermes' MCP writer only for changed entries | [mandatory] | R5 |
| VERIFY | Read back managed entries and preserved settings | [contract] | R6 |
| PROBE | Initialize native transports, list tools, and execute retrieval canaries with --verify | [opt] | R7 |
| PARTY | Resolve canonical role aliases and project Hermes model defaults through its native config API | [opt] | R8-R11 |

R1: When configuration is accessed, the system shall use Hermes' installed configuration APIs.
R2: When entries are merged, the system shall preserve root settings, unmanaged servers, user tool/auth controls, and unowned environment keys.
R3: If any proposed entry is invalid, then the system shall reject the batch before snapshot or save.
R4: When existing configuration would change, the system shall verify a native configuration snapshot before saving.
R5: When projection is semantically unchanged, the system shall perform no snapshot or save.
R6: If backup, save, or readback fails, then the system shall report failure without emitting configuration values.
R7: Where --verify is requested, the system shall prove connected catalogs and three named retrieval lookups within a 270-second deadline and report server-name-only progress on stderr.
R8: When a party projection is requested, the system shall preserve unowned provider, model, delegation, credential, and MCP fields.
R9: When a party projection changes configuration, the system shall verify a native snapshot before calling Hermes' native save API and verify model fields after readback.
R10: When a party projection is unchanged, the system shall perform no snapshot or save.
R11: If role aliases, endpoint data, snapshot, save, or readback is invalid, then the system shall report failure without emitting configuration values.

CLOSED: Generic harness_write access to Hermes config is denied; full-home backup and an independent YAML writer are unnecessary because native snapshots and Hermes' native configuration save API exist.
Preconditions: execute with the installed Hermes Python; input contains only projected registry entries.
Failure modes: invalid config, incomplete snapshot, native rejection, or readback mismatch raises; a completed snapshot remains available after a partial native-write failure.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

# Hermes' bundled venv can locate the editable `hermes_cli` package without adding its
# checkout root, while sibling top-level packages (for example `persistence`) need it.
HERMES_SOURCE = next((parent for parent in Path(sys.executable).parents
                      if (parent / "hermes_cli").is_dir() and (parent / "persistence").is_dir()), None)
if HERMES_SOURCE is not None:
    sys.path.insert(0, str(HERMES_SOURCE))

from hermes_cli.backup import create_quick_snapshot
from hermes_cli.config import get_config_path, load_config, save_config
from hermes_cli.mcp_config import _resolve_mcp_server_config, _save_mcp_server
from hermes_cli.mcp_security import validate_mcp_server_entry
from tools.mcp_tool import MCPServerTask
from tools.mcp_tool_loop import _ensure_mcp_loop, _run_on_mcp_loop, _stop_mcp_loop


def _verified_snapshot(label: str) -> str | None:
    """Capture and verify Hermes' native snapshot before a config mutation.

    Args:
        label: Non-secret artifact label identifying the projection type.

    Returns:
        Snapshot identifier, or None when Hermes has no config file to capture.

    Require: Hermes has resolved its active config path.
    Guarantee: A returned snapshot contains the exact preceding config bytes.
    Maintain: The helper never reads or emits configuration values beyond the snapshot boundary.
    Assert: Native snapshot metadata points to a readable byte-identical config copy.
    """
    config_path = get_config_path()
    if not config_path.exists():
        return None
    before = config_path.read_bytes()
    snapshot = create_quick_snapshot(
        label=f"harness-{label}-{uuid4().hex[:8]}", hermes_home=config_path.parent)
    if not snapshot:
        raise RuntimeError("Hermes configuration snapshot was not created")
    captured = config_path.parent / "state-snapshots" / snapshot / "config.yaml"
    if not captured.is_file() or captured.read_bytes() != before:
        raise RuntimeError("Hermes configuration snapshot did not capture preceding bytes")
    return snapshot


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

    snapshot = _verified_snapshot("mcp")
    for name in changed:
        if not _save_mcp_server(name, proposed[name]):
            raise RuntimeError(f"Hermes did not save MCP entry {name!r}")

    observed = load_config()
    if observed.get("mcp_servers", {}) != proposed:
        raise RuntimeError("Hermes MCP projection readback differs from the proposed batch")
    if any(observed.get(key) != value for key, value in current.items() if key != "mcp_servers"):
        raise RuntimeError("Hermes changed unrelated configuration during projection")
    return {"configured": list(servers), "changed": changed, "snapshot": snapshot}


def project_party(party: dict) -> dict:
    """Apply the canonical role models through Hermes' native config API.

    Args:
        party: Provider name, OpenAI-compatible endpoint, and four resolved role model IDs.

    Returns:
        Configured default/delegation model names, aliases, changed state, and snapshot ID.

    Require: Role models are resolved from the canonical party binding before this call.
    Guarantee: Leader becomes the main default, Fighter the default child route, and all roles are selectable.
    Maintain: Existing credentials and every unowned Hermes setting survive; repeat calls are byte-stable.
    Assert: Hermes' native save API accepts the full proposal and readback matches its owned fields.
    Failure modes: Invalid inputs, snapshots, native saves, or readback raise without returning success.
    """
    expected_roles = {"leader", "fighter", "scout", "oracle"}
    provider = party.get("provider")
    base_url = party.get("base_url")
    models = party.get("models")
    parsed = urlsplit(base_url if isinstance(base_url, str) else "")
    if (not isinstance(provider, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", provider)
            or parsed.scheme not in {"http", "https"} or not parsed.netloc
            or not isinstance(models, dict) or set(models) != expected_roles
            or any(not isinstance(model, str) or not model.strip() for model in models.values())):
        raise ValueError("Hermes party projection requires a provider, HTTP endpoint, and four non-empty role model IDs")

    current = load_config()
    proposed = copy.deepcopy(current)
    providers = proposed.setdefault("providers", {})
    model = proposed.setdefault("model", {})
    aliases = proposed.setdefault("model_aliases", {})
    delegation = proposed.setdefault("delegation", {})
    if not all(isinstance(section, dict) for section in (providers, model, aliases, delegation)):
        raise ValueError("Hermes providers, model, model_aliases, and delegation settings must be mappings")
    provider_config = providers.setdefault(provider, {})
    if not isinstance(provider_config, dict):
        raise ValueError(f"Hermes provider {provider!r} must be a mapping")

    custom_provider = f"custom:{provider}"
    provider_config.update({"api": base_url, "transport": "chat_completions"})
    model.update({"provider": custom_provider, "default": models["leader"]})
    for role in sorted(expected_roles):
        aliases[role] = {"model": models[role], "provider": custom_provider}
    delegation.update({"provider": custom_provider, "model": models["fighter"],
                       "base_url": base_url, "api_mode": "chat_completions"})

    if proposed == current:
        return {"default_model": models["leader"], "delegation_model": models["fighter"],
                "aliases": sorted(expected_roles), "changed": False, "snapshot": None}

    snapshot = _verified_snapshot("party")
    save_config(proposed, merge_existing=True)
    observed = load_config()
    if (observed.get("providers", {}).get(provider) != provider_config
            or observed.get("model", {}).get("provider") != custom_provider
            or observed.get("model", {}).get("default") != models["leader"]
            or any(observed.get("model_aliases", {}).get(role) != aliases[role] for role in expected_roles)
            or any(observed.get("delegation", {}).get(key) != delegation[key]
                   for key in ("provider", "model", "base_url", "api_mode"))):
        raise RuntimeError("Hermes party projection readback differs from the proposed defaults")
    managed = {"providers", "model", "model_aliases", "delegation"}
    if any(observed.get(key) != value for key, value in current.items() if key not in managed):
        raise RuntimeError("Hermes changed unrelated configuration during party projection")
    current_providers = current.get("providers", {})
    observed_providers = observed.get("providers", {})
    if any(observed_providers.get(name) != value for name, value in current_providers.items() if name != provider):
        raise RuntimeError("Hermes changed an unrelated provider during party projection")
    owned_provider_keys = {"api", "transport"}
    if any(provider_config.get(key) != value for key, value in current_providers.get(provider, {}).items()
           if key not in owned_provider_keys):
        raise RuntimeError("Hermes changed provider credentials or unowned provider settings")
    for section, owned in (("model", {"provider", "default"}),
                           ("model_aliases", expected_roles),
                           ("delegation", {"provider", "model", "base_url", "api_mode"})):
        before_section = current.get(section, {})
        after_section = observed.get(section, {})
        if any(after_section.get(key) != value for key, value in before_section.items() if key not in owned):
            raise RuntimeError(f"Hermes changed unowned {section} settings during party projection")
    return {"default_model": models["leader"], "delegation_model": models["fighter"],
            "aliases": sorted(expected_roles), "changed": True, "snapshot": snapshot}


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
        _stop_mcp_loop(only_if_idle=True)
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
    mode.add_argument("--party", action="store_true")
    args = parser.parse_args()
    if args.config_path:
        result = {"path": str(get_config_path())}
    elif args.party:
        result = project_party(json.load(sys.stdin))
    else:
        servers = json.load(sys.stdin)
        result = verify(servers) if args.verify else project(servers)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
