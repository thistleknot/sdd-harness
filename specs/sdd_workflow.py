"""Versioned SDD handoffs and resume-safe stage gating.

| Stage | Mechanism | Tag | Refs |
|---|---|---|---|
| PARSE | Load a strict versioned workflow and typed artifact references | [mandatory] | REQ-85 |
| VALIDATE | Check profile order, artifact ownership, workspace paths, hashes, and kind-specific content | [mandatory] | REQ-85 |
| COMMIT | Atomically persist a stage receipt after its required outputs pass | [mandatory] | REQ-85, REQ-86, REQ-87 |
| RESUME | Reuse matching completed receipts and invalidate the earliest stale stage plus dependents | [mandatory] | REQ-86, REQ-87 |

EARS guards:
- R1: A stage can complete only after its required output kinds exist and validate.
- R2: A stage receipt records its input and output hashes; completed matching stages are never executed again by this module.
- R3: A changed or missing output invalidates that stage and every later receipt.
- R4: The `spec` and `sw-design` profiles use distinct, ordered stage catalogs.

CLOSED:
- LangGraph is deferred: the existing gate kernel and atomic JSON checkpoint provide the required order and resume behavior; reconsider only if a concrete routing or durable checkpoint need exceeds this contract.
- A report's `passed` field is a declared result, not proof of semantic correctness; the harness independently checks its structure, source hashes, required outputs, approval shape, and stage order.

Preconditions: The workspace is a directory; handoff paths are relative to it; SHA-256 values identify the exact file bytes.
Failure modes: Invalid schema, unknown stage, skipped stage, missing required kind, path escape, changed hash, malformed approval, or failed verification blocks the handoff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ArtifactKind(str, Enum):
    """Artifact types shared by the spec and sw-design workflows."""

    intent = "intent"
    decision_record = "decision_record"
    specification = "specification"
    requirements = "requirements"
    design = "design"
    use_cases = "use_cases"
    entity_model = "entity_model"
    approval = "approval"
    ecore = "ecore"
    generated_classes = "generated_classes"
    implementation = "implementation"
    tests = "tests"
    validation_report = "validation_report"
    verification_report = "verification_report"


class ArtifactStatus(str, Enum):
    """Lifecycle status carried by a typed artifact reference."""

    draft = "draft"
    validated = "validated"
    approved = "approved"


class ArtifactRef(BaseModel):
    """Typed pointer to a persisted artifact produced by one workflow stage."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    kind: ArtifactKind
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    producer_stage: str = Field(min_length=1)
    status: ArtifactStatus = ArtifactStatus.draft
    producer_role: str = Field(min_length=1)
    reviewer_id: str | None = None
    review_decision: str | None = None


class StageReceipt(BaseModel):
    """Persisted proof that one stage completed for exact input and output bytes."""

    model_config = ConfigDict(extra="forbid")

    stage_id: str
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_ids: list[str] = Field(min_length=1)
    completed_at: str


class WorkflowState(BaseModel):
    """Versioned workflow checkpoint shared across SDD entry points."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1, le=1)
    workflow_id: str = Field(min_length=1)
    profile: Literal["spec", "sw-design"]
    workspace: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    completed_stages: list[StageReceipt] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_artifacts_and_stage_order(self) -> "WorkflowState":
        """Reject duplicate artifact identities and non-sequential receipts.

        Require: The profile is known before stage ordering is checked.
        Guarantee: Every persisted artifact id/path and completed stage id is unique.
        Maintain: Receipts remain an ordered prefix of their workflow profile.
        Assert: A malformed checkpoint cannot silently advance or resume.
        """
        artifact_ids = [item.artifact_id for item in self.artifacts]
        artifact_paths = [item.path for item in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("Workflow artifact_id values must be unique")
        if len(artifact_paths) != len(set(artifact_paths)):
            raise ValueError("Workflow artifact paths must be unique")
        stage_ids = [item.stage_id for item in self.completed_stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("Completed stage receipts must be unique")
        profile_stages = STAGE_CATALOG.get(self.profile)
        if profile_stages is not None and stage_ids != [row[0] for row in profile_stages[:len(stage_ids)]]:
            raise ValueError("Completed stage receipts must form an ordered profile prefix")
        return self


class WorkflowError(ValueError):
    """Raised when a stage handoff violates its workflow contract."""


STAGE_CATALOG: dict[str, list[tuple[str, tuple[ArtifactKind, ...], str, bool]]] = {
    "spec": [
        ("draft", (ArtifactKind.specification,), "spec", False),
        ("validate", (ArtifactKind.validation_report,), "spec", False),
        ("review", (ArtifactKind.approval,), "human", True),
        ("implement", (ArtifactKind.implementation, ArtifactKind.tests), "implementer", False),
        ("verify", (ArtifactKind.verification_report,), "verifier", False),
    ],
    "sw-design": [
        ("decisions", (ArtifactKind.decision_record,), "sw-design", False),
        ("specification", (ArtifactKind.specification,), "spec", False),
        ("requirements", (ArtifactKind.requirements,), "sw-design", False),
        ("design", (ArtifactKind.design,), "sw-design", False),
        ("use-cases", (ArtifactKind.use_cases, ArtifactKind.entity_model), "sw-design", False),
        ("review", (ArtifactKind.approval,), "human", True),
        ("ecore", (ArtifactKind.ecore,), "sw-design", False),
        ("generate", (ArtifactKind.generated_classes,), "pyecoregen", False),
        ("verify", (ArtifactKind.verification_report,), "verifier", False),
    ],
}


def _digest(data: bytes) -> str:
    """Return a SHA-256 digest for exact persisted bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical_digest(value: Any) -> str:
    """Hash deterministic JSON for workflow inputs or outputs."""
    return _digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _workspace_path(root: Path, relative_path: str) -> Path:
    """Resolve a workspace-relative artifact path without allowing escape."""
    workspace = root.resolve()
    target = (workspace / relative_path).resolve()
    if target != workspace and workspace not in target.parents:
        raise WorkflowError(f"Artifact path escapes workspace: {relative_path}")
    if not target.is_file():
        raise WorkflowError(f"Artifact is missing: {relative_path}")
    return target


def _check_artifact(artifact: ArtifactRef, stage_id: str, root: Path) -> None:
    """Validate bytes, ownership, and special approval/report contracts."""
    if artifact.producer_stage != stage_id:
        raise WorkflowError(f"{artifact.artifact_id}: producer_stage must be {stage_id}")
    path = _workspace_path(root, artifact.path)
    content = path.read_bytes()
    if not content.strip():
        raise WorkflowError(f"Artifact is empty: {artifact.path}")
    actual_hash = _digest(content)
    if actual_hash != artifact.sha256:
        raise WorkflowError(f"Artifact hash mismatch: {artifact.path}")
    if artifact.kind == ArtifactKind.approval:
        if artifact.status != ArtifactStatus.approved or not artifact.reviewer_id:
            raise WorkflowError("Approval artifact requires approved status and reviewer_id")
        if artifact.review_decision != "approved":
            raise WorkflowError("Approval artifact review_decision must be approved")
        try:
            payload = json.loads(content)
        except (ValueError, UnicodeDecodeError) as exc:
            raise WorkflowError("Approval artifact must contain JSON") from exc
        if payload.get("decision") != "approved" or payload.get("reviewer_id") != artifact.reviewer_id:
            raise WorkflowError("Approval JSON does not match its typed reviewer and decision")
    if artifact.kind in (ArtifactKind.validation_report, ArtifactKind.verification_report):
        try:
            payload = json.loads(content)
        except (ValueError, UnicodeDecodeError) as exc:
            raise WorkflowError(f"{artifact.kind.value} must contain JSON") from exc
        if payload.get("passed") is not True or not payload.get("checks"):
            raise WorkflowError(f"{artifact.kind.value} requires passed=true and non-empty checks")
        if artifact.status != ArtifactStatus.validated:
            raise WorkflowError(f"{artifact.kind.value} must have validated status")


def expected_stage(state: WorkflowState) -> tuple[str, tuple[ArtifactKind, ...], str, bool] | None:
    """Return the next stage contract, or None when the profile is complete."""
    if state.profile not in STAGE_CATALOG:
        raise WorkflowError(f"Unknown workflow profile: {state.profile}")
    stages = STAGE_CATALOG[state.profile]
    if len(state.completed_stages) > len(stages):
        raise WorkflowError("Checkpoint contains more completed stages than its profile")
    for index, receipt in enumerate(state.completed_stages):
        if receipt.stage_id != stages[index][0]:
            raise WorkflowError(f"Invalid completed-stage order at {receipt.stage_id}")
    return stages[len(state.completed_stages)] if len(state.completed_stages) < len(stages) else None


def validate_handoff(
    state: WorkflowState, stage_id: str, artifacts: list[ArtifactRef], root: Path,
) -> tuple[str, str]:
    """Validate a proposed stage transition and compute its receipt hashes."""
    if root.resolve() != Path(state.workspace).resolve():
        raise WorkflowError("Handoff workspace does not match the checkpoint workspace")
    stage = expected_stage(state)
    if stage is None:
        raise WorkflowError("Workflow is already complete")
    expected_id, required_kinds, producer_role, needs_approval = stage
    if stage_id != expected_id:
        raise WorkflowError(f"Invalid transition: expected stage {expected_id}, received {stage_id}")
    if not artifacts:
        raise WorkflowError(f"Stage {stage_id} has no output artifacts")
    present_kinds = {artifact.kind for artifact in artifacts}
    missing = set(required_kinds) - present_kinds
    if missing:
        raise WorkflowError("Missing required artifact kinds: " + ", ".join(sorted(item.value for item in missing)))
    known_ids = {artifact.artifact_id for artifact in state.artifacts}
    candidate_ids = [artifact.artifact_id for artifact in artifacts]
    if len(candidate_ids) != len(set(candidate_ids)) or known_ids.intersection(candidate_ids):
        raise WorkflowError("Artifact IDs must be unique across the workflow")
    for artifact in artifacts:
        if artifact.producer_role != producer_role:
            raise WorkflowError(f"{artifact.artifact_id}: stage {stage_id} requires producer_role {producer_role}")
        _check_artifact(artifact, stage_id, root)
    if needs_approval and not any(item.kind == ArtifactKind.approval for item in artifacts):
        raise WorkflowError("Review stage requires an approval artifact")
    previous_hash = state.completed_stages[-1].output_sha256 if state.completed_stages else _canonical_digest(state.intent)
    input_hash = _canonical_digest({"previous": previous_hash, "stage": stage_id})
    output_hash = _canonical_digest(sorted((item.artifact_id, item.sha256) for item in artifacts))
    return input_hash, output_hash


def advance_workflow(
    state: WorkflowState, stage_id: str, artifacts: list[ArtifactRef], root: Path,
) -> WorkflowState:
    """Return a checkpoint with the next verified stage committed."""
    input_hash, output_hash = validate_handoff(state, stage_id, artifacts, root)
    updated = state.model_copy(deep=True)
    updated.artifacts.extend(artifacts)
    updated.completed_stages.append(StageReceipt(
        stage_id=stage_id,
        input_sha256=input_hash,
        output_sha256=output_hash,
        artifact_ids=[item.artifact_id for item in artifacts],
        completed_at=datetime.now(timezone.utc).isoformat(),
    ))
    return updated


def resume_workflow(state: WorkflowState, root: Path) -> tuple[WorkflowState, list[str]]:
    """Retain valid receipts and discard the earliest stale stage and dependents."""
    if root.resolve() != Path(state.workspace).resolve():
        raise WorkflowError("Resume workspace does not match the checkpoint workspace")
    stage_catalog = STAGE_CATALOG.get(state.profile)
    if stage_catalog is None:
        raise WorkflowError(f"Unknown workflow profile: {state.profile}")
    artifact_by_id = {item.artifact_id: item for item in state.artifacts}
    retained: list[StageReceipt] = []
    reusable: list[str] = []
    previous_hash = _canonical_digest(state.intent)
    for index, receipt in enumerate(state.completed_stages):
        expected = stage_catalog[index] if index < len(stage_catalog) else None
        if expected is None or receipt.stage_id != expected[0]:
            break
        artifacts = [artifact_by_id.get(item_id) for item_id in receipt.artifact_ids]
        if any(item is None for item in artifacts):
            break
        try:
            for artifact in artifacts:
                _check_artifact(artifact, receipt.stage_id, root)
        except (WorkflowError, OSError):
            break
        output_hash = _canonical_digest(sorted((item.artifact_id, item.sha256) for item in artifacts))
        input_hash = _canonical_digest({"previous": previous_hash, "stage": receipt.stage_id})
        if output_hash != receipt.output_sha256 or input_hash != receipt.input_sha256:
            break
        retained.append(receipt)
        reusable.extend(item.artifact_id for item in artifacts)
        previous_hash = output_hash
    updated = state.model_copy(deep=True)
    updated.completed_stages = retained
    live_ids = {item_id for receipt in retained for item_id in receipt.artifact_ids}
    updated.artifacts = [item for item in state.artifacts if item.artifact_id in live_ids]
    return updated, reusable


def load_state(path: Path) -> WorkflowState:
    """Load a workflow checkpoint and validate its complete JSON schema."""
    try:
        return WorkflowState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise WorkflowError(f"Cannot load workflow state {path}: {exc}") from exc


def save_state(path: Path, state: WorkflowState) -> None:
    """Atomically save a validated JSON checkpoint in its destination directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(state.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main(argv: list[str] | None = None) -> int:
    """Validate and persist workflow handoffs from a small CLI.

    Args:
        argv: Optional command arguments.

    Returns:
        Zero when the requested operation passes; one when it blocks.

    Require: The state file and artifact manifest use the versioned schemas.
    Guarantee: `advance` writes a receipt only after every declared output passes.
    Maintain: A matching completed stage is never advanced a second time.
    Assert: A failed validation leaves the previous checkpoint bytes untouched.
    """
    parser = argparse.ArgumentParser(description="Validate and resume shared SDD workflows")
    subparsers = parser.add_subparsers(dest="command", required=True)
    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--state", required=True, type=Path)
    resume_parser.add_argument("--workspace", required=True, type=Path)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--state", required=True, type=Path)
    init_parser.add_argument("--workspace", required=True, type=Path)
    init_parser.add_argument("--profile", required=True, choices=sorted(STAGE_CATALOG))
    init_parser.add_argument("--workflow-id", required=True)
    init_parser.add_argument("--intent", required=True)
    subparsers.add_parser("schema")
    advance_parser = subparsers.add_parser("advance")
    advance_parser.add_argument("--state", required=True, type=Path)
    advance_parser.add_argument("--workspace", required=True, type=Path)
    advance_parser.add_argument("--stage", required=True)
    advance_parser.add_argument("--artifacts", required=True, type=Path, help="JSON array of typed artifact references")
    args = parser.parse_args(argv)
    try:
        if args.command == "schema":
            print(json.dumps({"workflow": WorkflowState.model_json_schema(),
                              "artifact": ArtifactRef.model_json_schema(),
                              "stage_profiles": {key: [row[0] for row in value]
                                                 for key, value in STAGE_CATALOG.items()}}, indent=2))
            return 0
        if args.command == "init":
            if args.state.exists():
                raise WorkflowError(f"Workflow checkpoint already exists: {args.state}")
            args.workspace.mkdir(parents=True, exist_ok=True)
            initial = WorkflowState(schema_version=1, workflow_id=args.workflow_id,
                                    profile=args.profile, workspace=str(args.workspace.resolve()),
                                    intent=args.intent)
            save_state(args.state, initial)
            print(json.dumps({"workflow_id": initial.workflow_id,
                              "profile": initial.profile,
                              "next_stage": expected_stage(initial)[0]}))
            return 0
        state = load_state(args.state)
        resumed, reusable = resume_workflow(state, args.workspace)
        if args.command == "resume":
            if len(resumed.completed_stages) != len(state.completed_stages):
                save_state(args.state, resumed)
            stage = expected_stage(resumed)
            print(json.dumps({"profile": resumed.profile, "reusable_artifacts": reusable,
                              "next_stage": stage[0] if stage else None,
                              "invalidated_receipts": len(state.completed_stages) - len(resumed.completed_stages)}))
            return 0
        if resumed.model_dump(mode="json") != state.model_dump(mode="json"):
            raise WorkflowError("Checkpoint contains stale artifacts; run resume and regenerate from the earliest invalidated stage")
        artifact_data = json.loads(args.artifacts.read_text(encoding="utf-8"))
        if not isinstance(artifact_data, list):
            raise WorkflowError("Artifact manifest must be a JSON array")
        artifacts = [ArtifactRef.model_validate(item) for item in artifact_data]
        updated = advance_workflow(state, args.stage, artifacts, args.workspace)
        save_state(args.state, updated)
        print(json.dumps({"completed_stage": args.stage, "next_stage": (expected_stage(updated) or (None,))[0],
                          "artifact_ids": [item.artifact_id for item in artifacts]}))
        return 0
    except (WorkflowError, OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"blocked": True, "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
