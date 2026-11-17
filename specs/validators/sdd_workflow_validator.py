"""Gate-runner adapter for typed SDD workflow handoffs.

| Stage | Mechanism | Tag | Refs |
|---|---|---|---|
| READ | Ignore unrelated lifecycle events or load the declared checkpoint | [mandatory] | REQ-85 |
| CHECK | Validate stage order and all typed output artifact bytes | [mandatory] | REQ-85 |
| REPORT | Return a structured block or allow verdict to the shared kernel | [mandatory] | REQ-85 |

EARS guards:
- R1: Missing workflow fields are a no-op; a declared handoff never fails open.
- R2: The validator reads files and state only; `sdd_workflow.py` owns checkpoint writes.

CLOSED:
- Stage policy is not embedded here; `STAGE_CATALOG` is the single stage source.

Preconditions: A declared workflow event supplies checkpoint, stage, artifact manifest, and workspace paths.
Failure modes: Invalid state, artifact schema, path, hash, order, or content produces a blocking verdict.
"""
from __future__ import annotations

from pathlib import Path

from ..policy_contracts import (
    EvidenceRef,
    LifecycleEvent,
    PolicyRecord,
    StructuredVerdict,
    VerdictStatus,
)
from ..sdd_workflow import ArtifactRef, WorkflowError, load_state, validate_handoff


class SddWorkflowValidator:
    """Validate an explicit SDD stage payload in the shared gate runner."""

    VALIDATOR_ID = "sdd-deliverables"

    def evaluate(
        self, event: LifecycleEvent, rules: list[PolicyRecord], snapshot_hash: str,
    ) -> list[StructuredVerdict]:
        """Check a handoff payload and return one structured verdict per active rule.

        Require: The payload is either unrelated or contains `sdd_workflow_path`,
            `sdd_stage`, and a JSON list in `sdd_artifacts`.
        Guarantee: A malformed declared handoff blocks every rule passed to this validator.
        Maintain: Validation is read-only and delegates artifact checks to the workflow contract.
        Assert: Every declared output path and hash matches the workspace bytes.
        """
        payload = event.payload
        if not payload.get("sdd_workflow_path"):
            return [StructuredVerdict(
                rule_id=rule.rule_id,
                validator_id=self.VALIDATOR_ID,
                status=VerdictStatus.allow,
                message="No SDD workflow handoff declared",
            ) for rule in rules]
        try:
            state_path = Path(payload["sdd_workflow_path"])
            state = load_state(state_path)
            artifact_values = payload.get("sdd_artifacts")
            if not isinstance(artifact_values, list):
                raise WorkflowError("sdd_artifacts must be a JSON array")
            artifacts = [ArtifactRef.model_validate(item) for item in artifact_values]
            workspace = Path(payload.get("sdd_workspace") or state.workspace)
            input_hash, output_hash = validate_handoff(
                state, str(payload.get("sdd_stage") or ""), artifacts, workspace,
            )
            message = f"Stage {payload['sdd_stage']} outputs validated"
            status = VerdictStatus.allow
            evidence = [EvidenceRef(
                ref_type="workflow", ref_id=str(state_path),
                description=f"input {input_hash}; output {output_hash}",
            )]
        except (WorkflowError, OSError, ValueError, TypeError, KeyError) as exc:
            message = f"SDD handoff blocked: {exc}"
            status = VerdictStatus.block
            evidence = []
        return [StructuredVerdict(
            rule_id=rule.rule_id,
            validator_id=self.VALIDATOR_ID,
            status=status,
            subject_ids=[str(payload.get("sdd_stage", ""))],
            evidence=evidence,
            message=message,
            remediation_task_ref="specs task #115" if status == VerdictStatus.block else None,
        ) for rule in rules]
