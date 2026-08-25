"""Phase 4 integration: capability matrix → adapter runtime → continuation store.

Proves: HarnessMatrixEntry feeds CapabilityProfile → ContinuationEnvelope sealed
→ ContinuationStore persists → load verifies hash → resume orchestrator checks
staleness/loss → child session lineage created.
"""
import pytest

from specs.adapter_runtime import (
    AdapterBase,
    ContinuationStore,
    LossyHandoffError,
    StaleCheckpointError,
    resume_from_checkpoint,
)
from specs.capability_matrix import get_entry, get_matrix
from specs.provider_schemas import (
    ContinuationEnvelope,
    HarnessId,
    ProviderIdentity,
    TransportType,
    WorkspaceIdentity,
    build_capability_profile,
    compute_loss_report,
)


class _TestAdapter(AdapterBase):
    """Minimal adapter for integration testing."""
    def capture_event(self, raw_event):
        return {"type": "test", **raw_event}

    def export_envelope(self, session_id, workspace, intent, work_state, provider_extensions=None):
        return ContinuationEnvelope(
            provider=ProviderIdentity(
                provider_id="test", harness_id=self.harness_id,
                model_id="test-model", transport=TransportType.http,
            ),
            session_id=session_id, workspace=workspace, intent=intent,
            capability_profile=self.advertise_capabilities(),
        ).seal()

    def import_envelope(self, envelope):
        return {"intent": envelope.intent, "resumed": True}

    def advertise_capabilities(self):
        return build_capability_profile(self.harness_id)


@pytest.fixture
def store():
    s = ContinuationStore(":memory:")
    yield s
    s.close()


class TestPhase4Integration:
    def test_matrix_to_profile_to_loss(self):
        """Capability matrix entries produce valid profiles that compute loss."""
        claude = get_entry(HarnessId.claude_code)
        opencode = get_entry(HarnessId.opencode)
        assert claude.enforcement.value == "native"
        assert opencode.enforcement.value == "advisory"

        loss = compute_loss_report(
            build_capability_profile(HarnessId.claude_code),
            build_capability_profile(HarnessId.opencode),
        )
        # Claude→OpenCode loses native capabilities
        assert loss.blocking is True
        assert any("native_gates" in e.source_field for e in loss.entries)

    def test_envelope_persist_load_roundtrip(self, store):
        """Sealed envelope persists and loads with hash integrity."""
        adapter = _TestAdapter(HarnessId.kiro)
        workspace = WorkspaceIdentity(
            root_uri="c:/project", project_slug="test",
            branch="main", head_commit="abc123",
        )
        envelope = adapter.export_envelope("sess-1", workspace, "test intent", {})
        eid = store.persist(envelope)

        loaded = store.load(eid)
        assert loaded.intent == "test intent"
        assert loaded.content_hash == envelope.content_hash

    def test_resume_creates_lineage(self, store):
        """Successful resume creates child-session lineage."""
        adapter = _TestAdapter(HarnessId.kiro)
        workspace = WorkspaceIdentity(
            root_uri="c:/project", project_slug="test",
            branch="main", head_commit="abc",
        )
        envelope = adapter.export_envelope("parent-sess", workspace, "continue", {})
        eid = store.persist(envelope)

        result = resume_from_checkpoint(
            store, eid, adapter, "child-sess",
            current_commit="abc", current_spec_hash="",
        )
        assert result["resumed"] is True

        lineage = store.get_lineage("child-sess")
        assert len(lineage) == 1
        assert lineage[0]["parent_session_id"] == "parent-sess"

    def test_stale_checkpoint_blocked(self, store):
        """Resume from stale checkpoint raises."""
        adapter = _TestAdapter(HarnessId.kiro)
        workspace = WorkspaceIdentity(
            root_uri="c:/project", project_slug="test",
            branch="main", head_commit="old-commit",
        )
        envelope = adapter.export_envelope("sess-1", workspace, "test", {})
        eid = store.persist(envelope)

        with pytest.raises(StaleCheckpointError):
            resume_from_checkpoint(
                store, eid, adapter, "child",
                current_commit="new-commit", current_spec_hash="",
            )

    def test_lossy_handoff_blocked(self, store):
        """Resume from native→advisory harness blocks on capability loss."""
        source_adapter = _TestAdapter(HarnessId.claude_code)
        target_adapter = _TestAdapter(HarnessId.opencode)
        workspace = WorkspaceIdentity(
            root_uri="c:/project", project_slug="test",
            branch="main", head_commit="abc",
        )
        envelope = source_adapter.export_envelope("sess-1", workspace, "test", {})
        eid = store.persist(envelope)

        with pytest.raises(LossyHandoffError):
            resume_from_checkpoint(
                store, eid, target_adapter, "child",
                current_commit="abc", current_spec_hash="",
            )
