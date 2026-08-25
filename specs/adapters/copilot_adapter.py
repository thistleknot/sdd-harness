"""GitHub Copilot adapter.

Purpose: implement the AdapterBase interface for GitHub Copilot.
Handles steering (.github/copilot-instructions.md), MCP registration
(.copilot/mcp.json), event capture (limited — VS Code chat context),
envelope export/import, and LossReport generation.

All Copilot-specific logic lives here — the canonical kernel has no Copilot branches.

Preconditions: adapter_runtime.py, provider_schemas.py available.
Failure modes: LossyHandoffError on blocking capability gaps.
"""
from __future__ import annotations

import time
from typing import Any

from ..adapter_runtime import AdapterBase, LossyHandoffError
from ..provider_schemas import (
    ActiveWorkState,
    CapabilityProfile,
    ContinuationEnvelope,
    HarnessId,
    LossReport,
    ProviderIdentity,
    TransportType,
    WorkspaceIdentity,
    build_capability_profile,
    compute_loss_report,
)


class CopilotAdapter(AdapterBase):
    """Adapter for GitHub Copilot (VS Code extension).

    Contract:
        Require: valid session context.
        Guarantee: deterministic envelope export; no Copilot-specific logic leaks to kernel.
        Maintain: .github/copilot-instructions.md as primary steering;
                  .copilot/mcp.json for MCP server registration.

    Limitations:
        - No lifecycle hooks (advisory enforcement only)
        - No transcript persistence (ephemeral chat context)
        - Event capture limited to what VS Code extension exposes
    """

    def __init__(self):
        super().__init__(HarnessId.github_copilot)

    def capture_event(self, raw_event: dict) -> dict:
        """Normalize a Copilot event to canonical schema.

        Copilot events are limited — mostly chat messages and file edits.
        """
        return {
            "type": raw_event.get("type", "message"),
            "timestamp": raw_event.get("timestamp", time.time()),
            "session_id": raw_event.get("conversation_id", ""),
            "content": raw_event.get("content", raw_event.get("text", "")),
            "tool_name": raw_event.get("participant", ""),
            "provider_meta": {
                "model": raw_event.get("model", "gpt-4o"),
                "participant": raw_event.get("participant", "@workspace"),
                "source": "vscode-copilot",
            },
        }

    def export_envelope(
        self,
        session_id: str,
        workspace: WorkspaceIdentity,
        intent: str,
        work_state: dict,
        provider_extensions: dict | None = None,
    ) -> ContinuationEnvelope:
        """Build a sealed ContinuationEnvelope from Copilot session state."""
        active_work = ActiveWorkState(
            current_disposition=work_state.get("disposition", ""),
            next_action=work_state.get("next_action", ""),
            blockers=work_state.get("blockers", []),
            pending_work=work_state.get("pending", []),
        )

        envelope = ContinuationEnvelope(
            provider=ProviderIdentity(
                provider_id="openai",
                harness_id=HarnessId.github_copilot,
                model_id=work_state.get("model", "gpt-4o"),
                transport=TransportType.http,
            ),
            session_id=session_id,
            workspace=workspace,
            intent=intent,
            work_state=active_work,
            capability_profile=self.advertise_capabilities(),
            provider_extensions=provider_extensions or {
                "copilot": {
                    "editor": "vscode",
                    "participants": ["@workspace", "@terminal"],
                }
            },
        )
        return envelope.seal()

    def import_envelope(self, envelope: ContinuationEnvelope) -> dict:
        """Import an envelope and produce a Copilot-native resume packet.

        Returns a dict suitable for populating copilot-instructions.md context.
        Copilot has no native resume mechanism — this produces a context summary.
        """
        loss = self.calculate_loss(envelope.capability_profile) if envelope.capability_profile else None
        if loss and loss.has_blocking_loss:
            raise LossyHandoffError(
                f"Cannot resume in Copilot: {len([e for e in loss.entries if e.severity == 'block'])} "
                f"blocking capabilities missing"
            )

        return {
            "intent": envelope.intent,
            "workspace_root": envelope.workspace.root_uri,
            "branch": envelope.workspace.branch,
            "commit": envelope.workspace.head_commit,
            "next_action": envelope.work_state.next_action,
            "blockers": envelope.work_state.blockers,
            "pending": envelope.work_state.pending_work,
            "context_injection": self._build_context_injection(envelope),
            "steering_file": ".github/copilot-instructions.md",
            "mcp_config": ".copilot/mcp.json",
        }

    def advertise_capabilities(self) -> CapabilityProfile:
        """Return Copilot's capability profile."""
        return build_capability_profile(HarnessId.github_copilot)

    def emit_steering(self, policy_rules: list[dict]) -> str:
        """Generate copilot-instructions.md content from policy rules."""
        lines = [
            "# Copilot Instructions (generated)\n",
            "Follow these project conventions:\n",
        ]
        for rule in policy_rules:
            priority = rule.get("priority", "normal")
            marker = "MUST" if priority == "must" else "SHOULD" if priority == "should" else "MAY"
            lines.append(f"- {marker}: {rule.get('title', '')} — {rule.get('criteria', '')}")
        return "\n".join(lines)

    def _build_context_injection(self, envelope: ContinuationEnvelope) -> str:
        """Build a context string for Copilot chat to resume work."""
        parts = [
            f"Resuming from session {envelope.session_id}.",
            f"Intent: {envelope.intent}",
        ]
        if envelope.work_state.next_action:
            parts.append(f"Next action: {envelope.work_state.next_action}")
        if envelope.work_state.blockers:
            parts.append(f"Blockers: {', '.join(envelope.work_state.blockers)}")
        return " ".join(parts)
