"""Codex CLI adapter.

Purpose: implement the AdapterBase interface for OpenAI Codex CLI.
Handles steering emission (AGENTS.md), MCP registration, event capture,
envelope export/import, and LossReport generation.

All Codex-specific logic lives here — the canonical kernel has no Codex branches.

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


class CodexAdapter(AdapterBase):
    """Adapter for OpenAI Codex CLI.

    Contract:
        Require: valid session context.
        Guarantee: deterministic envelope export; no Codex-specific logic leaks to kernel.
        Maintain: AGENTS.md as steering format; sandboxed execution model.
    """

    def __init__(self):
        super().__init__(HarnessId.codex)

    def capture_event(self, raw_event: dict) -> dict:
        """Normalize a Codex CLI event to canonical schema.

        Codex events come from sandbox execution logs.
        """
        return {
            "type": raw_event.get("type", "observation"),
            "timestamp": raw_event.get("timestamp", time.time()),
            "session_id": raw_event.get("session_id", ""),
            "content": raw_event.get("output", raw_event.get("content", "")),
            "tool_name": raw_event.get("tool", ""),
            "provider_meta": {
                "sandbox_id": raw_event.get("sandbox_id", ""),
                "exit_code": raw_event.get("exit_code"),
                "model": raw_event.get("model", "codex-1"),
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
        """Build a sealed ContinuationEnvelope from Codex session state."""
        active_work = ActiveWorkState(
            current_disposition=work_state.get("disposition", ""),
            next_action=work_state.get("next_action", ""),
            blockers=work_state.get("blockers", []),
            pending_work=work_state.get("pending", []),
        )

        envelope = ContinuationEnvelope(
            provider=ProviderIdentity(
                provider_id="openai",
                harness_id=HarnessId.codex,
                model_id="codex-1",
                transport=TransportType.http,
            ),
            session_id=session_id,
            workspace=workspace,
            intent=intent,
            work_state=active_work,
            capability_profile=self.advertise_capabilities(),
            provider_extensions=provider_extensions or {
                "codex": {
                    "sandbox_mode": "sandbox",
                    "approval_mode": "auto-edit",
                }
            },
        )
        return envelope.seal()

    def import_envelope(self, envelope: ContinuationEnvelope) -> dict:
        """Import an envelope and produce a Codex-native resume packet.

        Returns a dict suitable for `codex --resume` initialization.
        """
        loss = self.calculate_loss(envelope.capability_profile) if envelope.capability_profile else None
        if loss and loss.has_blocking_loss:
            raise LossyHandoffError(
                f"Cannot resume in Codex: {len([e for e in loss.entries if e.severity == 'block'])} "
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
            "provider_extensions": envelope.provider_extensions,
            "steering": "AGENTS.md",
            "model": "codex-1",
        }

    def advertise_capabilities(self) -> CapabilityProfile:
        """Return Codex's capability profile."""
        return build_capability_profile(HarnessId.codex)

    def emit_steering(self, policy_rules: list[dict]) -> str:
        """Generate AGENTS.md content from policy rules for Codex."""
        lines = ["# AGENTS.md (generated for Codex CLI)\n"]
        for rule in policy_rules:
            priority = rule.get("priority", "normal").upper()
            lines.append(f"- [{priority}] {rule.get('title', '')}: {rule.get('criteria', '')}")
        return "\n".join(lines)
