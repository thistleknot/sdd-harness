"""Canonical six-harness capability matrix.

Purpose: single source of truth for provider, transport, model routing,
enforcement level, steering format, and session mechanism per harness.
Reconciles OpenRouter vs Ollama, stale paths, and downstream adapter diffs.

Preconditions: provider_schemas.py in same package.
Failure modes: ValueError on unknown harness_id.

Usage:
    from capability_matrix import get_matrix, get_entry, render_matrix_table
    matrix = get_matrix()
    entry = get_entry(HarnessId.kiro)
"""
from __future__ import annotations

from pathlib import Path

from .provider_schemas import (
    EnforcementLevel,
    HarnessId,
    HarnessMatrixEntry,
    TransportType,
)


def _build_matrix() -> dict[HarnessId, HarnessMatrixEntry]:
    """Build the canonical matrix from known harness configurations."""
    return {
        HarnessId.claude_code: HarnessMatrixEntry(
            harness_id=HarnessId.claude_code,
            provider_id="anthropic",
            transport=TransportType.http,
            model_per_role={
                "orchestrator": "claude-sonnet-5",
                "planner": "claude-opus-5",
                "critic": "claude-sonnet-5",
                "fixer": "claude-opus-4-8",
                "architect": "claude-fable-5",
                "worker": "claude-haiku-4.5",
            },
            enforcement=EnforcementLevel.native,
            steering_format="CLAUDE.md + AGENTS.md",
            steering_path="~/.harness/claude/CLAUDE.md",
            mcp_config_format="claude.json",
            mcp_config_path="~/.claude.json",
            session_mechanism="transcript JSONL",
            hook_format="hooks/*.py (pre/post subcommand)",
            hook_path="~/.harness/claude/hooks/",
            notes="Full native enforcement: hooks gate writes, pre-commit, verify",
        ),
        HarnessId.opencode: HarnessMatrixEntry(
            harness_id=HarnessId.opencode,
            provider_id="openrouter",
            transport=TransportType.streamable_http,
            model_per_role={
                "orchestrator": "anthropic/claude-sonnet-4",
                "planner": "anthropic/claude-sonnet-4",
                "critic": "anthropic/claude-sonnet-4",
                "fixer": "anthropic/claude-sonnet-4",
                "architect": "anthropic/claude-sonnet-4",
                "worker": "anthropic/claude-sonnet-4",
            },
            enforcement=EnforcementLevel.advisory,
            steering_format="AGENTS.md + opencode.json",
            steering_path="~/.config/opencode/AGENTS.md",
            mcp_config_format="opencode.json (mcp block)",
            mcp_config_path="~/.config/opencode/opencode.json",
            session_mechanism="opencode run -c/-s",
            hook_format="none",
            hook_path="",
            notes="Advisory only — no lifecycle hooks, no native gates. OpenRouter provider.",
        ),
        HarnessId.pi: HarnessMatrixEntry(
            harness_id=HarnessId.pi,
            provider_id="openrouter (via litellm)",
            transport=TransportType.http,
            model_per_role={
                "orchestrator": "anthropic/claude-sonnet-4",
                "planner": "anthropic/claude-sonnet-4",
                "critic": "anthropic/claude-sonnet-4",
                "fixer": "anthropic/claude-sonnet-4",
                "architect": "anthropic/claude-sonnet-4",
                "worker": "anthropic/claude-sonnet-4",
            },
            enforcement=EnforcementLevel.native,
            steering_format="inherits CLAUDE.md + litellm_config.yaml",
            steering_path="~/.harness/claude/CLAUDE.md",
            mcp_config_format="inherits claude.json",
            mcp_config_path="~/.claude.json",
            session_mechanism="pi -p (persistent session)",
            hook_format="inherits Claude hooks",
            hook_path="~/.harness/claude/hooks/",
            notes="Shares Claude MCP config. Routes via litellm to OpenRouter. Native hooks inherited.",
        ),
        HarnessId.kiro: HarnessMatrixEntry(
            harness_id=HarnessId.kiro,
            provider_id="anthropic (server-side)",
            transport=TransportType.http,
            model_per_role={
                "orchestrator": "auto (server-selected)",
                "planner": "auto (server-selected)",
                "critic": "auto (server-selected)",
                "fixer": "auto (server-selected)",
                "architect": "auto (server-selected)",
                "worker": "auto (server-selected)",
            },
            enforcement=EnforcementLevel.native,
            steering_format=".kiro/steering/*.md",
            steering_path=".kiro/steering/",
            mcp_config_format="mcp.json (mcpServers block)",
            mcp_config_path="~/.kiro/settings/mcp.json",
            session_mechanism="context window (no transcript export)",
            hook_format=".kiro/hooks/*.json (v1 schema)",
            hook_path=".kiro/hooks/",
            notes="Native hooks (PreToolUse, PostFileSave, etc). Server-side model selection.",
        ),
        HarnessId.codex: HarnessMatrixEntry(
            harness_id=HarnessId.codex,
            provider_id="openai",
            transport=TransportType.http,
            model_per_role={
                "orchestrator": "codex-1 (o4-mini-based)",
                "planner": "codex-1",
                "critic": "codex-1",
                "fixer": "codex-1",
                "architect": "codex-1",
                "worker": "codex-1",
            },
            enforcement=EnforcementLevel.advisory,
            steering_format="AGENTS.md",
            steering_path="AGENTS.md (repo root)",
            mcp_config_format="codex mcp.json (TBD)",
            mcp_config_path="~/.codex/mcp.json",
            session_mechanism="codex --resume (sandboxed)",
            hook_format="none",
            hook_path="",
            notes="Advisory only. Sandboxed execution. MCP support via config. No hooks.",
        ),
        HarnessId.github_copilot: HarnessMatrixEntry(
            harness_id=HarnessId.github_copilot,
            provider_id="openai (GitHub)",
            transport=TransportType.http,
            model_per_role={
                "orchestrator": "gpt-4o / claude-sonnet-4 (user choice)",
                "planner": "gpt-4o",
                "critic": "gpt-4o",
                "fixer": "gpt-4o",
                "architect": "gpt-4o",
                "worker": "gpt-4o",
            },
            enforcement=EnforcementLevel.advisory,
            steering_format=".github/copilot-instructions.md + .copilot/",
            steering_path=".github/copilot-instructions.md",
            mcp_config_format="copilot mcp.json",
            mcp_config_path=".copilot/mcp.json",
            session_mechanism="VS Code chat context (ephemeral)",
            hook_format="none",
            hook_path="",
            notes="Advisory only. No lifecycle hooks. MCP via VS Code extension settings.",
        ),
    }


# Module-level singleton
_MATRIX: dict[HarnessId, HarnessMatrixEntry] | None = None


def get_matrix() -> dict[HarnessId, HarnessMatrixEntry]:
    """Return the full canonical matrix (cached)."""
    global _MATRIX
    if _MATRIX is None:
        _MATRIX = _build_matrix()
    return _MATRIX


def get_entry(harness_id: HarnessId) -> HarnessMatrixEntry:
    """Get single harness entry. Raises ValueError if unknown."""
    matrix = get_matrix()
    if harness_id not in matrix:
        raise ValueError(f"Unknown harness: {harness_id}")
    return matrix[harness_id]


def reconcile_harness_json(harness_json_path: str | Path) -> list[str]:
    """Compare the matrix against harness.json and report discrepancies.

    Returns a list of human-readable discrepancy strings.
    Empty list = fully reconciled.
    """
    import json

    path = Path(harness_json_path)
    if not path.exists():
        return [f"harness.json not found at {path}"]

    config = json.loads(path.read_text(encoding="utf-8"))
    matrix = get_matrix()
    issues: list[str] = []

    # Check model routing against matrix
    model_routing = config.get("model_routing", {})

    # Claude Code uses the "claude-code" key in model_routing
    claude_routing = model_routing.get("claude-code", {})
    claude_entry = matrix[HarnessId.claude_code]
    for role, model in claude_entry.model_per_role.items():
        cfg_model = claude_routing.get(role, "")
        if cfg_model and cfg_model != model:
            issues.append(
                f"claude-code.{role}: matrix={model}, harness.json={cfg_model}"
            )

    # Check MCP servers exist
    mcp_servers = config.get("mcp_servers", {})
    expected_servers = {"retrieve-skills", "memory-index", "todo", "specs", "data-science-skills"}
    missing = expected_servers - set(mcp_servers.keys())
    if missing:
        issues.append(f"Missing MCP servers in harness.json: {missing}")

    # Check transport types match
    for name, srv in mcp_servers.items():
        if srv.get("type") == "http" and not srv.get("url", "").startswith("http"):
            issues.append(f"MCP server '{name}': type=http but url missing/invalid")

    # Check for stale paths
    for name, srv in mcp_servers.items():
        if srv.get("type") == "stdio":
            cmd = srv.get("command", "")
            args = srv.get("args", [])
            for arg in args:
                p = Path(arg)
                if p.suffix == ".py" and not p.exists():
                    issues.append(f"MCP server '{name}': stale path {arg}")

    return issues


def render_matrix_table() -> str:
    """Render the matrix as a markdown table."""
    matrix = get_matrix()
    lines = [
        "| Harness | Provider | Transport | Enforcement | Steering | MCP Config | Hooks |",
        "|---------|----------|-----------|-------------|----------|------------|-------|",
    ]
    for entry in matrix.values():
        lines.append(
            f"| {entry.harness_id.value} "
            f"| {entry.provider_id} "
            f"| {entry.transport.value} "
            f"| {entry.enforcement.value} "
            f"| {entry.steering_format} "
            f"| {entry.mcp_config_path} "
            f"| {entry.hook_format or 'none'} |"
        )
    return "\n".join(lines)


def render_model_routing_table() -> str:
    """Render model-per-role as a markdown table."""
    matrix = get_matrix()
    roles = ["orchestrator", "planner", "critic", "fixer", "architect", "worker"]
    header = "| Harness | " + " | ".join(roles) + " |"
    sep = "|---------|" + "|".join(["--------"] * len(roles)) + "|"
    lines = [header, sep]
    for entry in matrix.values():
        cells = [entry.model_per_role.get(r, "-") for r in roles]
        lines.append(f"| {entry.harness_id.value} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
