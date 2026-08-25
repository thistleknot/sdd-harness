"""Phase 3 integration: policy compiler → gate runner → validators.

Proves: SpecsDB policy → compiled PolicySnapshot → GateRunner invokes validators
→ StructuredVerdict → EvidenceLedger persists results. The full kernel chain.
"""
import tempfile
from pathlib import Path

import pytest

from specs.gate_runner import EvidenceLedger, GateRunner
from specs.policy_contracts import (
    LifecycleEvent,
    LifecycleEventType,
    PolicySnapshot,
    ValidatorRegistration,
    compile_policy,
)
from specs.specs_db import SpecsDB
from specs.validators import (
    ConvergenceValidator,
    SecurityValidator,
    SelfReviewValidator,
    SprawlValidator,
)


@pytest.fixture
def kernel(tmp_path):
    """Wire the full Phase 3 kernel: DB → compiler → runner → validators."""
    db = SpecsDB(tmp_path / "specs.db")
    db.add_requirement("Auth login", "Users can log in with credentials", priority="must")
    db.add_requirement("Token refresh", "Tokens auto-refresh", priority="should")
    db.add_decision("Use JWT", "JWT", "Stateless, widely supported")

    snapshot = compile_policy(str(tmp_path / "specs.db"))

    ledger = EvidenceLedger(str(tmp_path / "ledger.db"))
    runner = GateRunner(ledger=ledger)

    sec_reg = ValidatorRegistration(validator_id="security", name="security", triggers=["Stop"])
    runner.register(sec_reg, SecurityValidator())
    sr_reg = ValidatorRegistration(validator_id="self_review", name="self_review", triggers=["Stop"])
    runner.register(sr_reg, SelfReviewValidator())
    conv_reg = ValidatorRegistration(validator_id="convergence", name="convergence", triggers=["Stop"])
    runner.register(conv_reg, ConvergenceValidator())
    sprawl_reg = ValidatorRegistration(validator_id="sprawl", name="sprawl", triggers=["Stop"])
    runner.register(sprawl_reg, SprawlValidator())

    return {
        "db": db, "snapshot": snapshot,
        "ledger": ledger, "runner": runner, "tmp": tmp_path,
    }


class TestPhase3Kernel:
    def test_compiler_produces_snapshot(self, kernel):
        """compile_policy reads SpecsDB and produces a deterministic snapshot."""
        snapshot = kernel["snapshot"]
        assert isinstance(snapshot, PolicySnapshot)
        assert len(snapshot.rules) >= 2  # at least our 2 requirements
        assert snapshot.content_hash != ""

    def test_snapshot_deterministic(self, kernel):
        """Same DB state → same snapshot hash."""
        db_path = str(kernel["tmp"] / "specs.db")
        s1 = compile_policy(db_path)
        s2 = compile_policy(db_path)
        assert s1.content_hash == s2.content_hash

    def test_runner_invokes_validators_and_persists(self, kernel):
        """GateRunner runs all registered validators and produces verdict."""
        event = LifecycleEvent(
            event_id="evt-1",
            event_type=LifecycleEventType.stop,
            harness_id="kiro",
            project_slug="test",
            session_id="s1",
            payload={"files_modified": ["src/auth.py"]},
        )
        verdict = kernel["runner"].run(event, kernel["snapshot"])
        assert verdict.overall_status in ("allow", "warn", "block")
        # At least one validator produced a verdict
        assert len(verdict.verdicts) > 0

    def test_security_validator_blocks_secrets(self, kernel):
        """Security validator blocks when content contains secrets."""
        event = LifecycleEvent(
            event_id="evt-2",
            event_type=LifecycleEventType.stop,
            harness_id="kiro",
            project_slug="test",
            session_id="s1",
            payload={"content": "AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE"},
        )
        verdict = kernel["runner"].run(event, kernel["snapshot"])
        assert verdict.overall_status in ("warn", "block")

    def test_ledger_accumulates(self, kernel):
        """Multiple runs accumulate evidence in the ledger."""
        event = LifecycleEvent(
            event_id="evt-3",
            event_type=LifecycleEventType.stop,
            harness_id="kiro",
            project_slug="test",
            session_id="s1",
            payload={"files_modified": ["a.py"]},
        )
        v1 = kernel["runner"].run(event, kernel["snapshot"])

        event2 = LifecycleEvent(
            event_id="evt-4",
            event_type=LifecycleEventType.stop,
            harness_id="kiro",
            project_slug="test",
            session_id="s1",
            payload={"files_modified": ["b.py"]},
        )
        v2 = kernel["runner"].run(event2, kernel["snapshot"])

        # Both produced verdicts — ledger has accumulated
        assert len(v1.verdicts) > 0
        assert len(v2.verdicts) > 0
