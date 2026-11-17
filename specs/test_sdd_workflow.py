"""Conformance tests for shared SDD artifact handoffs and resume behavior.

| Stage | Mechanism | Tag | Refs |
|---|---|---|---|
| FIXTURE | Build isolated spec and sw-design outputs with exact hashes | [mandatory] | REQ-85 |
| CHECK | Exercise schema, stage ordering, required kinds, content gates, and path safety | [mandatory] | REQ-85 |
| RESUME | Prove matching receipts are reused and stale outputs truncate downstream receipts | [mandatory] | REQ-86, REQ-87 |

EARS guards:
- R1: All fixture files live beneath pytest temporary workspaces.
- R2: Invalid handoffs do not modify the prior checkpoint.
- R3: Both profiles must accept their defined first-stage handoff and reject skips.

CLOSED:
- Live user workflow files are not fixtures; behavior is measured on generated varied artifacts.

Preconditions: pytest and pydantic v2 are installed.
Failure modes: Any contract regression fails this suite.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from specs.sdd_workflow import (
    ArtifactKind,
    ArtifactRef,
    ArtifactStatus,
    STAGE_CATALOG,
    StageReceipt,
    WorkflowError,
    WorkflowState,
    advance_workflow,
    expected_stage,
    main,
    resume_workflow,
)
from specs.policy_contracts import (
    LifecycleEvent,
    LifecycleEventType,
    PolicyPriority,
    PolicyRecord,
    VerdictStatus,
)
from specs.validators.sdd_workflow_validator import SddWorkflowValidator


def _state(tmp_path: Path, profile: str = "spec") -> WorkflowState:
    """Create a valid empty workflow checkpoint for a temporary workspace.

    Args:
        tmp_path: Pytest-owned workspace root.
        profile: Registered workflow profile.

    Returns:
        A valid, unadvanced workflow state.

    Require: Profile is in STAGE_CATALOG.
    Guarantee: State has no completed stages and a stable objective.
    Maintain: The fixture does not write outside tmp_path.
    Assert: The first stage is defined for the requested profile.
    """
    state = WorkflowState(schema_version=1, workflow_id=f"test-{profile}", profile=profile,
                          workspace=str(tmp_path), intent="Exercise the SDD handoff contract")
    assert expected_stage(state)[0] == STAGE_CATALOG[profile][0][0]
    return state


def _artifact(
    root: Path, stage: str, kind: ArtifactKind, content: bytes,
    role: str, status: ArtifactStatus = ArtifactStatus.draft,
    reviewer_id: str | None = None, review_decision: str | None = None,
) -> ArtifactRef:
    """Write one artifact and return a pointer carrying its exact hash.

    Args:
        root: Temporary workspace root.
        stage: Stage that owns this output.
        kind: Shared artifact type.
        content: Bytes to persist.
        role: Contract producer role.
        status: Artifact lifecycle status.
        reviewer_id: Human reviewer identity for approval fixtures.
        review_decision: Declared decision for approval fixtures.

    Returns:
        A typed pointer whose hash matches the written bytes.

    Require: The test provides a unique path per generated artifact.
    Guarantee: The returned file exists and carries an exact SHA-256 digest.
    Maintain: The fixture writes only beneath root.
    Assert: The content is persisted byte-for-byte.
    """
    relative = f"artifacts/{stage}-{kind.value}.dat"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return ArtifactRef(artifact_id=f"{stage}-{kind.value}", kind=kind, path=relative,
                       sha256=hashlib.sha256(content).hexdigest(), producer_stage=stage,
                       status=status, producer_role=role, reviewer_id=reviewer_id,
                       review_decision=review_decision)


def _advance_draft(state: WorkflowState, root: Path) -> WorkflowState:
    """Commit the first spec stage with a varied non-empty specification file.

    Args:
        state: Unadvanced spec state.
        root: Temporary workspace root.

    Returns:
        State with the draft stage receipt persisted in memory.

    Require: The profile's first stage is draft.
    Guarantee: Specification output is content- and hash-validated.
    Maintain: No unrelated state is changed.
    Assert: The resulting next stage is validate.
    """
    artifact = _artifact(root, "draft", ArtifactKind.specification,
                         b"# Spec\n\nA testable objective with a distinct case.\n", "spec")
    updated = advance_workflow(state, "draft", [artifact], root)
    assert expected_stage(updated)[0] == "validate"
    return updated


def test_missing_required_envelope_field_is_rejected() -> None:
    """Reject a workflow JSON object that omits its profile."""
    with pytest.raises(ValidationError, match="profile"):
        WorkflowState.model_validate({"schema_version": 1, "workflow_id": "x",
                                      "workspace": ".", "intent": "missing profile"})


@pytest.mark.parametrize("profile,first_stage,kind,role", [
    ("spec", "draft", ArtifactKind.specification, "spec"),
    ("sw-design", "decisions", ArtifactKind.decision_record, "sw-design"),
])
def test_both_profiles_accept_their_first_stage_and_reject_skips(
    tmp_path: Path, profile: str, first_stage: str, kind: ArtifactKind, role: str,
) -> None:
    """Prove the entry profiles share typed handoffs without sharing stage names."""
    state = _state(tmp_path, profile)
    with pytest.raises(WorkflowError, match="Invalid transition"):
        advance_workflow(state, "verify", [], tmp_path)
    wrong_kind = _artifact(tmp_path, first_stage, ArtifactKind.intent,
                           b"wrong kind for entry stage\n", role)
    with pytest.raises(WorkflowError, match="Missing required artifact kinds"):
        advance_workflow(state, first_stage, [wrong_kind], tmp_path)
    artifact = _artifact(tmp_path, first_stage, kind, f"{profile} artifact\n".encode(), role)
    updated = advance_workflow(state, first_stage, [artifact], tmp_path)
    assert updated.completed_stages[0].stage_id == first_stage
    assert expected_stage(updated)[0] == STAGE_CATALOG[profile][1][0]
    resumed, reusable = resume_workflow(updated, tmp_path)
    assert resumed == updated
    assert reusable == [artifact.artifact_id]


def test_missing_required_output_and_hash_mismatch_block(tmp_path: Path) -> None:
    """Block absent required kinds and a declared digest that differs from disk."""
    state = _state(tmp_path)
    wrong_kind = _artifact(tmp_path, "draft", ArtifactKind.intent, b"wrong output kind\n", "spec")
    with pytest.raises(WorkflowError, match="Missing required artifact kinds"):
        advance_workflow(state, "draft", [wrong_kind], tmp_path)
    artifact = _artifact(tmp_path, "draft", ArtifactKind.specification, b"draft body\n", "spec")
    artifact.sha256 = "0" * 64
    with pytest.raises(WorkflowError, match="hash mismatch"):
        advance_workflow(state, "draft", [artifact], tmp_path)


def test_approval_requires_matching_human_review_json(tmp_path: Path) -> None:
    """Refuse approval metadata that does not match the persisted review record."""
    state = _advance_draft(_state(tmp_path), tmp_path)
    report = _artifact(tmp_path, "validate", ArtifactKind.validation_report,
                       json.dumps({"passed": True, "checks": ["format"]}).encode(), "spec",
                       ArtifactStatus.validated)
    state = advance_workflow(state, "validate", [report], tmp_path)
    approval = _artifact(tmp_path, "review", ArtifactKind.approval,
                          b'{"decision":"rejected","reviewer_id":"reviewer-1"}', "human",
                          ArtifactStatus.approved, "reviewer-1", "approved")
    with pytest.raises(WorkflowError, match="does not match"):
        advance_workflow(state, "review", [approval], tmp_path)


def test_resume_reuses_matching_receipts_without_replaying_stage(tmp_path: Path) -> None:
    """Preserve a completed stage on resume and reject a duplicate stage advance."""
    state = _advance_draft(_state(tmp_path), tmp_path)
    resumed, reusable = resume_workflow(state, tmp_path)
    assert resumed == state
    assert reusable == ["draft-specification"]
    with pytest.raises(WorkflowError, match="expected stage validate"):
        advance_workflow(resumed, "draft", state.artifacts, tmp_path)


def test_resume_invalidates_earliest_changed_output_and_later_receipts(tmp_path: Path) -> None:
    """Drop a stale completed stage and every dependent receipt, keeping no false progress."""
    state = _advance_draft(_state(tmp_path), tmp_path)
    report = _artifact(tmp_path, "validate", ArtifactKind.validation_report,
                       json.dumps({"passed": True, "checks": ["shape"]}).encode(), "spec",
                       ArtifactStatus.validated)
    state = advance_workflow(state, "validate", [report], tmp_path)
    first_path = tmp_path / state.artifacts[0].path
    first_path.write_text("changed bytes\n", encoding="utf-8")

    resumed, reusable = resume_workflow(state, tmp_path)

    assert resumed.completed_stages == []
    assert resumed.artifacts == []
    assert reusable == []
    assert expected_stage(resumed)[0] == "draft"


def test_artifact_path_must_remain_inside_workspace(tmp_path: Path) -> None:
    """Reject a file reference that escapes its workflow workspace."""
    outside = tmp_path.parent / "outside-sdd-artifact.txt"
    outside.write_text("outside\n", encoding="utf-8")
    artifact = ArtifactRef(artifact_id="escape", kind=ArtifactKind.specification,
                           path="../outside-sdd-artifact.txt",
                           sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
                           producer_stage="draft", producer_role="spec")
    with pytest.raises(WorkflowError, match="escapes workspace"):
        advance_workflow(_state(tmp_path), "draft", [artifact], tmp_path)


@pytest.mark.parametrize("profile,stage", [("spec", "draft"), ("sw-design", "decisions")])
def test_gate_validator_blocks_bad_handoff_with_unmet_output(
    tmp_path: Path, profile: str, stage: str,
) -> None:
    """Expose a missing required output as a blocking gate verdict."""
    state = _state(tmp_path, profile)
    state_path = tmp_path / "workflow.json"
    state_path.write_text(state.model_dump_json(), encoding="utf-8")
    event = LifecycleEvent(
        event_id="event-1", event_type=LifecycleEventType.post_task_exec,
        harness_id="codex", project_slug="fixture", session_id="session-1",
        payload={"sdd_workflow_path": str(state_path), "sdd_stage": stage,
                 "sdd_workspace": str(tmp_path), "sdd_artifacts": []},
    )
    rule = PolicyRecord(rule_id="req:85", title="SDD handoff", criteria="validate",
                        priority=PolicyPriority.must, source_type="requirement", source_id=85)

    (verdict,) = SddWorkflowValidator().evaluate(event, [rule], "snapshot")

    assert verdict.status == VerdictStatus.block
    assert "no output artifacts" in verdict.message
    assert verdict.remediation_task_ref == "specs task #115"


def test_checkpoint_workspace_must_match_handoff_root(tmp_path: Path) -> None:
    """Prevent a caller from redirecting artifact checks to a different root."""
    state = _state(tmp_path)
    with pytest.raises(WorkflowError, match="does not match"):
        resume_workflow(state, tmp_path / "other")


def test_cli_checkpoint_resume_and_duplicate_advance_are_safe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Exercise the persisted workflow path, including idempotent resume and duplicate refusal."""
    state_path = tmp_path / ".sdd" / "workflow.json"
    assert main(["init", "--state", str(state_path), "--workspace", str(tmp_path),
                 "--profile", "spec", "--workflow-id", "cli-fixture", "--intent", "CLI check"]) == 0
    artifact = _artifact(tmp_path, "draft", ArtifactKind.specification,
                         b"# CLI spec\n", "spec")
    manifest = tmp_path / ".sdd" / "draft-artifacts.json"
    manifest.write_text(json.dumps([artifact.model_dump(mode="json")]), encoding="utf-8")
    args = ["advance", "--state", str(state_path), "--workspace", str(tmp_path),
            "--stage", "draft", "--artifacts", str(manifest)]
    assert main(args) == 0
    committed = state_path.read_bytes()
    assert main(["resume", "--state", str(state_path), "--workspace", str(tmp_path)]) == 0
    assert state_path.read_bytes() == committed
    capsys.readouterr()

    assert main(args) == 1
    assert state_path.read_bytes() == committed
    assert "expected stage validate" in capsys.readouterr().err


def test_stage_receipt_schema_requires_hashes_and_output_ids() -> None:
    """Reject incomplete stage receipts instead of accepting guessed completion."""
    with pytest.raises(ValidationError):
        StageReceipt.model_validate({"stage_id": "draft"})


def test_checkpoint_rejects_duplicate_artifact_ids_and_paths(tmp_path: Path) -> None:
    """Reject duplicate artifact keys before they can corrupt resume lookup."""
    state = _state(tmp_path)
    duplicate = ArtifactRef(artifact_id="same", kind=ArtifactKind.specification,
                            path="same.md", sha256="a" * 64, producer_stage="draft",
                            producer_role="spec")
    with pytest.raises(ValidationError, match="artifact_id values must be unique"):
        WorkflowState.model_validate({**state.model_dump(), "artifacts": [
            duplicate.model_dump(), duplicate.model_dump(),
        ]})
    with pytest.raises(ValidationError, match="artifact paths must be unique"):
        WorkflowState.model_validate({**state.model_dump(), "artifacts": [
            duplicate.model_dump(), {**duplicate.model_dump(), "artifact_id": "other"},
        ]})
