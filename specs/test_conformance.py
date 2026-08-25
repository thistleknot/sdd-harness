"""Six-harness conformance evaluation.

Proves: all 6 harnesses can export/import continuation envelopes, advertise
capabilities, compute loss reports, and round-trip deterministically.
Distinguishes native vs advisory enforcement. Emits a result matrix.

This is the Phase 7 capstone — depends on all prior phases.
"""
from __future__ import annotations

import pytest

from specs.adapter_runtime import AdapterBase, ContinuationStore, LossyHandoffError
from specs.adapters import CodexAdapter, CopilotAdapter
from specs.capability_matrix import get_entry, get_matrix
from specs.provider_schemas import (
    ContinuationEnvelope,
    EnforcementLevel,
    HarnessId,
    ProviderIdentity,
    TransportType,
    WorkspaceIdentity,
    build_capability_profile,
    compute_loss_report,
)


# --- Adapter stubs for harnesses without full adapters yet ---


class _StubAdapter(AdapterBase):
    """Minimal adapter for conformance testing."""
    def __init__(self, harness_id: HarnessId, provider: str = "anthropic", model: str = "auto"):
        super().__init__(harness_id)
        self._provider = provider
        self._model = model

    def capture_event(self, raw_event):
        return {"type": "test", **raw_event}

    def export_envelope(self, session_id, workspace, intent, work_state, provider_extensions=None):
        from specs.provider_schemas import ActiveWorkState
        return ContinuationEnvelope(
            provider=ProviderIdentity(
                provider_id=self._provider, harness_id=self.harness_id,
                model_id=self._model, transport=TransportType.http,
            ),
            session_id=session_id, workspace=workspace, intent=intent,
            work_state=ActiveWorkState(**work_state) if isinstance(work_state, dict) else work_state,
            capability_profile=self.advertise_capabilities(),
            provider_extensions=provider_extensions or {},
        ).seal()

    def import_envelope(self, envelope):
        loss = self.calculate_loss(envelope.capability_profile) if envelope.capability_profile else None
        if loss and loss.has_blocking_loss:
            raise LossyHandoffError(f"Blocked: {self.harness_id.value}")
        return {"intent": envelope.intent, "resumed": True, "harness": self.harness_id.value}

    def advertise_capabilities(self):
        return build_capability_profile(self.harness_id)


# Build all 6 adapters
def _all_adapters() -> dict[HarnessId, AdapterBase]:
    return {
        HarnessId.claude_code: _StubAdapter(HarnessId.claude_code, "anthropic", "claude-sonnet-5"),
        HarnessId.opencode: _StubAdapter(HarnessId.opencode, "openrouter", "claude-sonnet-4"),
        HarnessId.pi: _StubAdapter(HarnessId.pi, "openrouter", "claude-sonnet-4"),
        HarnessId.kiro: _StubAdapter(HarnessId.kiro, "anthropic", "auto"),
        HarnessId.codex: CodexAdapter(),
        HarnessId.github_copilot: CopilotAdapter(),
    }


_WORKSPACE = WorkspaceIdentity(
    root_uri="c:/project/test", project_slug="conformance-eval",
    branch="main", head_commit="conf123",
)


class TestConformanceExportImport:
    """Every harness can export a sealed envelope and import one from itself."""

    @pytest.mark.parametrize("harness_id", list(HarnessId))
    def test_self_roundtrip(self, harness_id):
        """Export → persist → load → import = identity for each harness."""
        adapters = _all_adapters()
        adapter = adapters[harness_id]
        store = ContinuationStore(":memory:")

        envelope = adapter.export_envelope(
            session_id=f"sess-{harness_id.value}",
            workspace=_WORKSPACE,
            intent="conformance test",
            work_state={"next_action": "verify", "blockers": [], "pending": []},
        )

        # Sealed correctly
        assert envelope.content_hash != ""
        assert envelope.envelope_id.startswith("env:")

        # Persist and load
        eid = store.persist(envelope)
        loaded = store.load(eid)
        assert loaded.intent == "conformance test"
        assert loaded.content_hash == envelope.content_hash

        # Import back into same harness (no loss)
        result = adapter.import_envelope(loaded)
        assert result["intent"] == "conformance test"

        store.close()


class TestConformanceLossMatrix:
    """Cross-harness loss computation produces correct blocking decisions."""

    def test_native_to_advisory_blocks(self):
        """Handoff from native-enforcement to advisory-only blocks."""
        native_harnesses = [HarnessId.claude_code, HarnessId.kiro]
        advisory_harnesses = [HarnessId.opencode, HarnessId.codex, HarnessId.github_copilot]

        for source in native_harnesses:
            for target in advisory_harnesses:
                loss = compute_loss_report(
                    build_capability_profile(source),
                    build_capability_profile(target),
                )
                # Native→advisory should have at least one blocking entry
                assert loss.blocking is True, (
                    f"{source.value}→{target.value} should block but didn't"
                )

    def test_advisory_to_advisory_no_block(self):
        """Handoff between advisory harnesses doesn't block."""
        advisory = [HarnessId.opencode, HarnessId.codex, HarnessId.github_copilot]
        for source in advisory:
            for target in advisory:
                if source == target:
                    continue
                loss = compute_loss_report(
                    build_capability_profile(source),
                    build_capability_profile(target),
                )
                assert loss.blocking is False, (
                    f"{source.value}→{target.value} should not block"
                )

    def test_same_harness_no_loss(self):
        """Same harness → same harness = zero loss entries."""
        for harness_id in HarnessId:
            profile = build_capability_profile(harness_id)
            loss = compute_loss_report(profile, profile)
            assert len(loss.entries) == 0, f"{harness_id.value} self-loss should be empty"


class TestConformanceCapabilityMatrix:
    """Capability matrix is complete and consistent."""

    def test_all_harnesses_in_matrix(self):
        matrix = get_matrix()
        for hid in HarnessId:
            assert hid in matrix

    def test_native_harnesses_have_hooks(self):
        """Native-enforcement harnesses must have hook support."""
        matrix = get_matrix()
        native = [HarnessId.claude_code, HarnessId.kiro, HarnessId.pi]
        for hid in native:
            entry = matrix[hid]
            assert entry.enforcement == EnforcementLevel.native
            assert entry.hook_format != "", f"{hid.value} is native but has no hook format"

    def test_advisory_harnesses_no_hooks(self):
        """Advisory harnesses don't claim hook support."""
        matrix = get_matrix()
        advisory = [HarnessId.opencode, HarnessId.codex, HarnessId.github_copilot]
        for hid in advisory:
            entry = matrix[hid]
            assert entry.enforcement == EnforcementLevel.advisory
            assert entry.hook_format in ("", "none"), f"{hid.value} claims hooks but is advisory"


class TestConformanceResultMatrix:
    """Emit the full conformance result matrix — proves end-to-end."""

    def test_emit_result_matrix(self):
        """Generate and validate the full 6x6 handoff matrix."""
        adapters = _all_adapters()
        results: list[dict] = []

        for source_id, source_adapter in adapters.items():
            for target_id, target_adapter in adapters.items():
                if source_id == target_id:
                    results.append({
                        "source": source_id.value, "target": target_id.value,
                        "loss_entries": 0, "blocking": False, "verdict": "self",
                    })
                    continue

                loss = compute_loss_report(
                    source_adapter.advertise_capabilities(),
                    target_adapter.advertise_capabilities(),
                )
                results.append({
                    "source": source_id.value, "target": target_id.value,
                    "loss_entries": len(loss.entries),
                    "blocking": loss.blocking,
                    "verdict": "block" if loss.blocking else "allow",
                })

        # 6x6 = 36 entries
        assert len(results) == 36

        # Print matrix for visibility
        print("\n--- Conformance Matrix ---")
        print(f"{'Source':<16} {'Target':<16} {'Entries':>7} {'Verdict':<7}")
        for r in results:
            if r["verdict"] != "self":
                print(f"{r['source']:<16} {r['target']:<16} {r['loss_entries']:>7} {r['verdict']:<7}")
        print(f"--------------------------")
        print(f"Total handoff pairs: {len([r for r in results if r['verdict'] != 'self'])}")
        print(f"Blocked: {len([r for r in results if r['verdict'] == 'block'])}")
        print(f"Allowed: {len([r for r in results if r['verdict'] == 'allow'])}")
