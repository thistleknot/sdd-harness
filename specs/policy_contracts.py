"""Policy compiler and validator contracts for the SDD gate kernel.

Purpose: define the schemas that all validators, the gate runner, and the policy
compiler use to communicate. These are the stable interfaces that #26 (gate runner)
and #27 (migrate controls) depend on.

Preconditions: pydantic v2 installed (already in py310 env).
Failure modes: schema validation raises ValidationError; compiler raises PolicyCompileError.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# --- Enums ------------------------------------------------------------------


class VerdictStatus(str, Enum):
    allow = "allow"
    block = "block"
    warn = "warn"
    error = "error"


class LifecycleEventType(str, Enum):
    session_start = "SessionStart"
    user_prompt_submit = "UserPromptSubmit"
    pre_tool_use = "PreToolUse"
    post_tool_use = "PostToolUse"
    pre_task_exec = "PreTaskExec"
    post_task_exec = "PostTaskExec"
    post_file_save = "PostFileSave"
    post_file_create = "PostFileCreate"
    post_file_delete = "PostFileDelete"
    stop = "Stop"


class PolicyPriority(str, Enum):
    must = "must"
    should = "should"
    could = "could"


# --- Core Schemas -----------------------------------------------------------


class EvidenceRef(BaseModel):
    """Pointer to a piece of evidence supporting a verdict."""
    ref_type: str = Field(description="Type: 'file', 'tool_output', 'db_row', 'url', 'volley_id'")
    ref_id: str = Field(description="Stable identifier for the evidence")
    description: str = Field(default="", description="One-line summary of what this evidences")
    timestamp: float = Field(default_factory=time.time)


class StructuredVerdict(BaseModel):
    """One validator's verdict on one lifecycle event against one policy rule.

    Every validator MUST return exactly this schema. The gate runner
    aggregates these into an AggregateVerdict.
    """
    rule_id: str = Field(description="Policy rule identifier (requirement ID or decision ID)")
    validator_id: str = Field(description="Which validator produced this")
    status: VerdictStatus
    subject_ids: list[str] = Field(default_factory=list, description="IDs of artifacts/symbols/files evaluated")
    evidence: list[EvidenceRef] = Field(default_factory=list)
    message: str = Field(default="", description="Human-readable explanation")
    remediation_task_ref: Optional[str] = Field(default=None, description="SpecsDB task ID if remediation is needed")
    timestamp: float = Field(default_factory=time.time)


class AggregateVerdict(BaseModel):
    """Gate runner's combined result from all validators for one lifecycle event."""
    event_id: str
    event_type: LifecycleEventType
    overall_status: VerdictStatus = Field(description="Worst status across all verdicts")
    verdicts: list[StructuredVerdict] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)

    @property
    def blocking(self) -> list[StructuredVerdict]:
        return [v for v in self.verdicts if v.status == VerdictStatus.block]

    @property
    def warnings(self) -> list[StructuredVerdict]:
        return [v for v in self.verdicts if v.status == VerdictStatus.warn]


class LifecycleEvent(BaseModel):
    """A lifecycle event that triggers the gate runner."""
    event_id: str = Field(description="Unique event identifier")
    event_type: LifecycleEventType
    harness_id: str
    project_slug: str
    session_id: str
    timestamp: float = Field(default_factory=time.time)
    payload: dict[str, Any] = Field(default_factory=dict, description="Event-specific data: tool_name, file_path, etc.")


class PolicyRecord(BaseModel):
    """One compiled policy rule derived from a requirement or decision.

    The policy compiler produces a list of these from SpecsDB.
    Validators evaluate lifecycle events against these.
    """
    rule_id: str = Field(description="Stable ID: 'req:<id>' or 'dec:<id>'")
    title: str
    criteria: str = Field(description="The testable acceptance criteria or chosen approach")
    priority: PolicyPriority
    source_type: str = Field(description="'requirement' or 'decision'")
    source_id: int
    triggers: list[LifecycleEventType] = Field(
        default_factory=list,
        description="Which lifecycle events this rule should be evaluated on; empty = all"
    )
    content_hash: str = Field(default="", description="SHA-256 of criteria text for change detection")


class ValidatorRegistration(BaseModel):
    """Registration entry for a validator in the gate runner registry."""
    validator_id: str = Field(description="Unique identifier for this validator")
    name: str = Field(description="Human-readable name")
    description: str = Field(default="")
    triggers: list[LifecycleEventType] = Field(
        default_factory=list,
        description="Which events this validator handles; empty = all"
    )
    rule_ids: list[str] = Field(
        default_factory=list,
        description="Which policy rules this validator evaluates; empty = all"
    )
    fail_open: bool = Field(default=True, description="If True, validator errors produce 'warn' not 'block'")
    timeout_seconds: float = Field(default=30.0)


class ProjectionSpec(BaseModel):
    """Declares a downstream projection to be generated from the policy snapshot."""
    projection_id: str
    name: str
    target_harness: Optional[str] = Field(default=None, description="None = all harnesses")
    target_path: str = Field(description="Relative path where the projection is written")
    source_type: str = Field(description="'steering', 'mcp_config', 'hook_config', 'uml', 'report'")
    content_hash: str = Field(default="", description="Hash of last rendered content for staleness detection")


# --- Policy Snapshot --------------------------------------------------------


class PolicySnapshot(BaseModel):
    """Complete compiled policy state at a point in time.

    Deterministic: same DB state → same snapshot (sorted, hashed).
    """
    compiled_at: float = Field(default_factory=time.time)
    content_hash: str = Field(default="", description="Hash of the full snapshot for change detection")
    rules: list[PolicyRecord] = Field(default_factory=list)
    validators: list[ValidatorRegistration] = Field(default_factory=list)
    projections: list[ProjectionSpec] = Field(default_factory=list)

    def compute_hash(self) -> str:
        """Deterministic content hash from sorted rules."""
        payload = json.dumps(
            [r.model_dump() for r in sorted(self.rules, key=lambda r: r.rule_id)],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


# --- Policy Compile Errors --------------------------------------------------


class PolicyCompileError(Exception):
    """Raised when the policy cannot be compiled from SpecsDB."""
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__(f"Policy compilation failed: {len(issues)} issue(s)")


# --- Policy Compiler --------------------------------------------------------

_CLARIFICATION_RE = re.compile(r"\[NEEDS\s+CLARIFICATION[:\s]", re.IGNORECASE)


def compile_policy(db_path: str | Path) -> PolicySnapshot:
    """Compile active requirements and decisions from SpecsDB into a PolicySnapshot.

    Require: db_path points to a valid specs.db with current schema.
    Guarantee: returns a deterministic snapshot or raises PolicyCompileError.
    Maintain: tasks are never compiled as policy; only requirements and decisions.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    issues: list[str] = []
    rules: list[PolicyRecord] = []
    seen_rule_ids: set[str] = set()

    # --- Compile requirements ---
    rows = conn.execute(
        "SELECT * FROM requirements WHERE status IN ('active', 'met') ORDER BY id"
    ).fetchall()
    for r in rows:
        rule_id = f"req:{r['id']}"

        # Check for duplicate rule keys
        if rule_id in seen_rule_ids:
            issues.append(f"Duplicate rule_id: {rule_id}")
            continue
        seen_rule_ids.add(rule_id)

        criteria = r["criteria"] or ""

        # Reject unresolved clarification markers
        if _CLARIFICATION_RE.search(criteria):
            issues.append(f"{rule_id} ({r['title']}): contains unresolved [NEEDS CLARIFICATION]")
            continue

        content_hash = hashlib.sha256(criteria.encode()).hexdigest()[:16]
        rules.append(PolicyRecord(
            rule_id=rule_id,
            title=r["title"],
            criteria=criteria,
            priority=PolicyPriority(r["priority"]) if r["priority"] in ("must", "should", "could") else PolicyPriority.must,
            source_type="requirement",
            source_id=r["id"],
            content_hash=content_hash,
        ))

    # --- Compile decisions ---
    rows = conn.execute("SELECT * FROM decisions ORDER BY id").fetchall()
    for r in rows:
        rule_id = f"dec:{r['id']}"
        if rule_id in seen_rule_ids:
            issues.append(f"Duplicate rule_id: {rule_id}")
            continue
        seen_rule_ids.add(rule_id)

        chosen = r["chosen"] or ""
        if _CLARIFICATION_RE.search(chosen):
            issues.append(f"{rule_id} ({r['title']}): contains unresolved [NEEDS CLARIFICATION]")
            continue

        content_hash = hashlib.sha256(chosen.encode()).hexdigest()[:16]
        rules.append(PolicyRecord(
            rule_id=rule_id,
            title=r["title"],
            criteria=chosen,
            priority=PolicyPriority.must,  # decisions are binding
            source_type="decision",
            source_id=r["id"],
            content_hash=content_hash,
        ))

    conn.close()

    # --- Validate: no tasks leaked as policy ---
    # (Tasks table is never read by this compiler — structural guarantee)

    if issues:
        raise PolicyCompileError(issues)

    snapshot = PolicySnapshot(rules=rules, compiled_at=time.time())
    snapshot.content_hash = snapshot.compute_hash()
    return snapshot


def compile_policy_json(db_path: str | Path) -> str:
    """Compile and return as deterministic JSON string."""
    snapshot = compile_policy(db_path)
    return snapshot.model_dump_json(indent=2)
