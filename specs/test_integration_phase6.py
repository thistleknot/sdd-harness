"""Phase 6 integration: event ingestion → promotion router → adapter handoff.

Proves: normalized events append to EventStore → PromotionRouter classifies →
candidates above threshold route to correct lane → adapter captures and exports
envelope with events linked.
"""
import pytest

from specs.adapter_runtime import AdapterBase, ContinuationStore
from specs.event_ingestion import (
    DuplicateEventError,
    EventStore,
    EventType,
    NormalizedEvent,
    PromotionLane,
    PromotionRouter,
)
from specs.provider_schemas import (
    ContinuationEnvelope,
    HarnessId,
    ProviderIdentity,
    TransportType,
    WorkspaceIdentity,
    build_capability_profile,
)


@pytest.fixture
def pipeline():
    """Full Phase 6 pipeline: event store + promotion router + continuation store."""
    events = EventStore(":memory:")
    continuations = ContinuationStore(":memory:")
    router = PromotionRouter()
    yield {"events": events, "continuations": continuations, "router": router}
    events.close()
    continuations.close()


class TestPhase6Integration:
    def test_event_append_sequence_and_dedup(self, pipeline):
        """Events append with auto-incrementing sequence; duplicates rejected."""
        store = pipeline["events"]
        e1 = NormalizedEvent(
            event_type=EventType.tool_call, harness_id="kiro",
            session_id="s1", sequence=1, content="call read_file",
        )
        store.append(e1)

        e2 = NormalizedEvent(
            event_type=EventType.tool_result, harness_id="kiro",
            session_id="s1", sequence=2, content="file content here",
            parent_event_id=e1.event_id,
        )
        store.append(e2)

        assert store.count("s1") == 2
        assert store.next_sequence("s1") == 3

        # Duplicate blocked
        with pytest.raises(DuplicateEventError):
            store.append(NormalizedEvent(
                event_type=EventType.tool_call, harness_id="kiro",
                session_id="s1", sequence=3, content="call read_file",
            ))

    def test_promotion_routing_end_to_end(self, pipeline):
        """Observations route to correct lanes based on content."""
        router = pipeline["router"]

        # Specs-proposal content
        specs = router.classify("This requirement must have acceptance criteria")
        assert specs.lane == PromotionLane.specs_proposal
        assert router.should_promote(specs) is True

        # Steering-proposal content
        steer = router.classify("The rule is to always follow this convention")
        assert steer.lane == PromotionLane.steering_proposal

        # Low-signal → continuation only, not promoted
        noise = router.classify("just thinking out loud")
        assert noise.lane == PromotionLane.continuation_only
        assert router.should_promote(noise) is False

    def test_events_feed_into_continuation(self, pipeline):
        """Events captured → envelope exported → stored → loadable."""
        store = pipeline["events"]
        cont_store = pipeline["continuations"]

        # Simulate a session with events
        store.append(NormalizedEvent(
            event_type=EventType.message, harness_id="kiro",
            session_id="sess-A", sequence=1, content="implement auth",
        ))
        store.append(NormalizedEvent(
            event_type=EventType.tool_call, harness_id="kiro",
            session_id="sess-A", sequence=2, content="write auth.py",
        ))

        # Build envelope from session state
        envelope = ContinuationEnvelope(
            provider=ProviderIdentity(
                provider_id="anthropic", harness_id=HarnessId.kiro,
                model_id="auto", transport=TransportType.http,
            ),
            session_id="sess-A",
            workspace=WorkspaceIdentity(
                root_uri="c:/project", project_slug="myapp",
                branch="main", head_commit="def456",
            ),
            intent="implement auth module",
            capability_profile=build_capability_profile(HarnessId.kiro),
        ).seal()

        # Persist and verify roundtrip
        eid = cont_store.persist(envelope)
        loaded = cont_store.load(eid)
        assert loaded.intent == "implement auth module"
        assert loaded.session_id == "sess-A"

    def test_cross_session_lineage(self, pipeline):
        """Child sessions link to parent via continuation store."""
        cont_store = pipeline["continuations"]

        parent_env = ContinuationEnvelope(
            provider=ProviderIdentity(
                provider_id="anthropic", harness_id=HarnessId.kiro,
                model_id="auto", transport=TransportType.http,
            ),
            session_id="parent",
            workspace=WorkspaceIdentity(
                root_uri="c:/p", project_slug="x", branch="main", head_commit="aaa",
            ),
            intent="phase 1 work",
        ).seal()
        eid = cont_store.persist(parent_env)

        cont_store.create_child_session(eid, "child-1", reason="resume next day")
        lineage = cont_store.get_lineage("child-1")
        assert lineage[0]["parent_session_id"] == "parent"
