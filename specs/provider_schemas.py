"""Cross-provider metadata and continuation schemas.

Purpose: define the canonical envelope that all harnesses export/import for
cross-harness resumability, plus adapter contracts for schema translation.

These models are the interoperability boundary (Decision #8). Provider-specific
quirks live in namespaced extensions; the canonical core is harness-neutral.

Preconditions: pydantic v2.
Failure modes: ValidationError on malformed envelopes; LossReport on lossy transforms.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Enums ------------------------------------------------------------------


class HarnessId(str, Enum):
    claude_code = "claude-code"
    opencode = "opencode"
    pi = "pi"
    kiro = "kiro"
    codex = "codex"
    github_copilot = "github-copilot"


class TransportType(str, Enum):
    http = "http"
    stdio = "stdio"
    streamable_http = "streamable-http"


class EnforcementLevel(str, Enum):
    native = "native"       # harness enforces mechanically
    advisory = "advisory"   # harness receives guidance only, cannot block


class TaskStatus(str, Enum):
    planned = "planned"
    doing = "doing"
    done = "done"
    blocked = "blocked"
    deprecated = "deprecated"


class LossType(str, Enum):
    missing_field = "missing_field"
    unsupported_capability = "unsupported_capability"
    lossy_transform = "lossy_transform"
    semantic_mismatch = "semantic_mismatch"
    stale_reference = "stale_reference"


# --- Capability Profile -----------------------------------------------------


class CapabilityEntry(BaseModel):
    """One capability a harness supports or doesn't."""
    name: str = Field(description="e.g. 'lifecycle_hooks', 'mcp_http', 'native_gates'")
    supported: bool
    enforcement: EnforcementLevel = EnforcementLevel.advisory
    notes: str = ""


class CapabilityProfile(BaseModel):
    """What a harness can actually do — advertised at handoff time."""
    harness_id: HarnessId
    harness_version: str = ""
    capabilities: list[CapabilityEntry] = Field(default_factory=list)
    steering_format: str = Field(description="e.g. 'CLAUDE.md', '.kiro/steering/*.md'")
    mcp_config_path: str = Field(description="e.g. '.kiro/settings/mcp.json'")
    session_mechanism: str = Field(description="e.g. 'transcript JSONL', 'context window'")


# --- Provider Identity ------------------------------------------------------


class ProviderIdentity(BaseModel):
    """Separate provider, harness, model, and transport — never conflate."""
    provider_id: str = Field(description="e.g. 'anthropic', 'openai', 'openrouter', 'ollama'")
    harness_id: HarnessId
    model_id: str = Field(description="e.g. 'claude-sonnet-5', 'gpt-4o', 'deepseek-v4-flash'")
    transport: TransportType = TransportType.http


# --- Workspace Identity -----------------------------------------------------


class WorkspaceIdentity(BaseModel):
    """Normalized workspace/repo state at envelope creation time."""
    root_uri: str = Field(description="Normalized absolute path or URI")
    project_slug: str
    branch: str = ""
    base_commit: str = ""
    head_commit: str = ""
    dirty_state_hash: str = Field(default="", description="Hash of uncommitted changes")


# --- Artifact Reference -----------------------------------------------------


class ArtifactRef(BaseModel):
    """Reference to a produced artifact with integrity hash."""
    artifact_type: str = Field(description="e.g. 'file', 'db_row', 'test_result', 'service'")
    path: str
    content_hash: str = ""
    producer: str = Field(default="", description="Which task/validator/phase produced this")


# --- Loss Report ------------------------------------------------------------


class LossEntry(BaseModel):
    """One piece of information that was lost or degraded in translation."""
    loss_type: LossType
    source_field: str
    target_field: str = ""
    description: str
    reversible: bool = False
    severity: str = Field(default="info", description="'info', 'warn', 'block'")


class LossReport(BaseModel):
    """Accumulated translation losses from adapter import/export."""
    source_harness: HarnessId
    target_harness: HarnessId
    entries: list[LossEntry] = Field(default_factory=list)
    blocking: bool = Field(default=False, description="True if any entry is severity=block")
    timestamp: float = Field(default_factory=time.time)

    @property
    def has_blocking_loss(self) -> bool:
        return any(e.severity == "block" for e in self.entries)


# --- Transform Record -------------------------------------------------------


class TransformRecord(BaseModel):
    """One field-level transformation applied by an adapter."""
    transform_id: str = ""
    source_field: str
    target_field: str
    transform_version: str = "1.0"
    before_hash: str = ""
    after_hash: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reversible: bool = True


# --- Active Work State ------------------------------------------------------


class ActiveTaskRef(BaseModel):
    """Reference to an active spec task at envelope time."""
    task_id: int
    title: str
    status: TaskStatus
    parent_id: Optional[int] = None


class ActiveWorkState(BaseModel):
    """Current execution state: what's done, in progress, blocked."""
    active_requirement_ids: list[str] = Field(default_factory=list)
    active_decision_ids: list[str] = Field(default_factory=list)
    active_tasks: list[ActiveTaskRef] = Field(default_factory=list)
    current_disposition: str = ""
    next_action: str = ""
    blockers: list[str] = Field(default_factory=list)
    unresolved_decisions: list[str] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    pending_work: list[str] = Field(default_factory=list)


# --- Continuation Envelope --------------------------------------------------


class ContinuationEnvelope(BaseModel):
    """The canonical provider-neutral continuation state.

    Every harness MUST be able to export and import this schema.
    Required missing fields block resume; optional missing carry missing_reason.

    Contract:
        Require: all required fields populated; content_hash matches payload.
        Guarantee: deterministic serialization; JSON-schema validatable.
        Maintain: provider_extensions preserved without interpretation.
    """
    # --- Envelope metadata ---
    schema_version: str = Field(default="1.0")
    envelope_id: str = Field(default="", description="Content-addressed ID")
    created_at: float = Field(default_factory=time.time)

    # --- Identity (never conflated) ---
    provider: ProviderIdentity
    session_id: str
    parent_session_id: Optional[str] = None

    # --- Workspace ---
    workspace: WorkspaceIdentity

    # --- Spec state ---
    spec_snapshot_hash: str = Field(default="", description="Hash of PolicySnapshot at capture")
    intent: str = Field(default="", description="Current objective/intent")

    # --- Active work ---
    work_state: ActiveWorkState = Field(default_factory=ActiveWorkState)

    # --- Artifacts ---
    artifacts: list[ArtifactRef] = Field(default_factory=list)

    # --- Capability ---
    capability_profile: Optional[CapabilityProfile] = None

    # --- Provider extensions (namespaced, preserved without interpretation) ---
    provider_extensions: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw provider-specific payload preserved by reference",
    )
    provider_payload_hash: str = Field(default="", description="Hash of raw provider data")

    # --- Redaction ---
    redacted_fields: list[str] = Field(default_factory=list)

    # --- Content addressing ---
    content_hash: str = Field(default="")

    def compute_hash(self) -> str:
        """Deterministic content hash from canonical fields (excludes derived fields)."""
        payload = self.model_dump(exclude={"content_hash", "created_at", "envelope_id"})
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    def seal(self) -> "ContinuationEnvelope":
        """Compute and set the content hash. Returns self for chaining."""
        self.content_hash = self.compute_hash()
        self.envelope_id = f"env:{self.content_hash}"
        return self


# --- Definition Lock (for resume handshake) ---------------------------------


class DefinitionLock(BaseModel):
    """The repeat-back contract a target harness emits before resuming.

    The source compares this against the envelope to confirm alignment.
    """
    envelope_id: str
    restated_intent: str
    restated_constraints: list[str] = Field(default_factory=list)
    restated_blockers: list[str] = Field(default_factory=list)
    restated_next_action: str = ""
    restated_done_conditions: list[str] = Field(default_factory=list)
    capability_gaps: list[str] = Field(
        default_factory=list,
        description="Capabilities the source has that the target lacks",
    )
    loss_report: Optional[LossReport] = None
    accepted: bool = Field(default=False, description="True if target can proceed")


# --- Harness Matrix Entry ---------------------------------------------------


class HarnessMatrixEntry(BaseModel):
    """One row in the six-harness capability matrix."""
    harness_id: HarnessId
    provider_id: str
    transport: TransportType
    model_per_role: dict[str, str] = Field(default_factory=dict)
    enforcement: EnforcementLevel
    steering_format: str
    steering_path: str
    mcp_config_format: str
    mcp_config_path: str
    session_mechanism: str
    hook_format: str = ""
    hook_path: str = ""
    notes: str = ""


# --- Factory helpers --------------------------------------------------------


def build_capability_profile(harness_id: HarnessId) -> CapabilityProfile:
    """Build a default capability profile for a known harness."""
    profiles = {
        HarnessId.claude_code: CapabilityProfile(
            harness_id=HarnessId.claude_code,
            capabilities=[
                CapabilityEntry(name="lifecycle_hooks", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="mcp_http", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="mcp_stdio", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="native_gates", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="subagents", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="transcript_persistence", supported=True, enforcement=EnforcementLevel.native),
            ],
            steering_format="CLAUDE.md + AGENTS.md",
            mcp_config_path=".claude.json",
            session_mechanism="transcript JSONL",
        ),
        HarnessId.kiro: CapabilityProfile(
            harness_id=HarnessId.kiro,
            capabilities=[
                CapabilityEntry(name="lifecycle_hooks", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="mcp_http", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="mcp_stdio", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="native_gates", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="subagents", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="transcript_persistence", supported=False, enforcement=EnforcementLevel.advisory),
            ],
            steering_format=".kiro/steering/*.md",
            mcp_config_path=".kiro/settings/mcp.json",
            session_mechanism="context window",
        ),
        HarnessId.opencode: CapabilityProfile(
            harness_id=HarnessId.opencode,
            capabilities=[
                CapabilityEntry(name="lifecycle_hooks", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="mcp_http", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="mcp_stdio", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="native_gates", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="subagents", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="transcript_persistence", supported=False, enforcement=EnforcementLevel.advisory),
            ],
            steering_format="AGENTS.md + opencode.json",
            mcp_config_path="opencode.json",
            session_mechanism="opencode run -c/-s",
        ),
        HarnessId.pi: CapabilityProfile(
            harness_id=HarnessId.pi,
            capabilities=[
                CapabilityEntry(name="lifecycle_hooks", supported=True, enforcement=EnforcementLevel.native, notes="inherits Claude"),
                CapabilityEntry(name="mcp_http", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="mcp_stdio", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="native_gates", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="subagents", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="transcript_persistence", supported=True, enforcement=EnforcementLevel.native),
            ],
            steering_format="inherits Claude + litellm_config.yaml",
            mcp_config_path="inherits Claude user scope",
            session_mechanism="pi -p",
        ),
        HarnessId.codex: CapabilityProfile(
            harness_id=HarnessId.codex,
            capabilities=[
                CapabilityEntry(name="lifecycle_hooks", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="mcp_http", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="mcp_stdio", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="native_gates", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="subagents", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="transcript_persistence", supported=False, enforcement=EnforcementLevel.advisory),
            ],
            steering_format="AGENTS.md",
            mcp_config_path="codex MCP config (TBD)",
            session_mechanism="codex --resume (TBD)",
        ),
        HarnessId.github_copilot: CapabilityProfile(
            harness_id=HarnessId.github_copilot,
            capabilities=[
                CapabilityEntry(name="lifecycle_hooks", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="mcp_http", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="mcp_stdio", supported=True, enforcement=EnforcementLevel.native),
                CapabilityEntry(name="native_gates", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="subagents", supported=False, enforcement=EnforcementLevel.advisory),
                CapabilityEntry(name="transcript_persistence", supported=False, enforcement=EnforcementLevel.advisory),
            ],
            steering_format=".github/copilot-instructions.md + .copilot/",
            mcp_config_path=".copilot/mcp.json",
            session_mechanism="VS Code chat context",
        ),
    }
    return profiles.get(harness_id, profiles[HarnessId.opencode])


def compute_loss_report(
    source: CapabilityProfile, target: CapabilityProfile
) -> LossReport:
    """Compare two capability profiles and produce a LossReport.

    Identifies capabilities the source has that the target lacks.
    """
    entries: list[LossEntry] = []
    source_caps = {c.name: c for c in source.capabilities}
    target_caps = {c.name: c for c in target.capabilities}

    for name, src_cap in source_caps.items():
        tgt_cap = target_caps.get(name)
        if src_cap.supported and (tgt_cap is None or not tgt_cap.supported):
            severity = "block" if src_cap.enforcement == EnforcementLevel.native else "warn"
            entries.append(LossEntry(
                loss_type=LossType.unsupported_capability,
                source_field=f"capability:{name}",
                target_field="",
                description=f"Source has '{name}' (native); target does not support it",
                severity=severity,
            ))
        elif src_cap.supported and tgt_cap and tgt_cap.supported:
            if src_cap.enforcement == EnforcementLevel.native and tgt_cap.enforcement == EnforcementLevel.advisory:
                entries.append(LossEntry(
                    loss_type=LossType.lossy_transform,
                    source_field=f"capability:{name}",
                    target_field=f"capability:{name}",
                    description=f"'{name}' downgraded from native to advisory enforcement",
                    severity="warn",
                ))

    return LossReport(
        source_harness=source.harness_id,
        target_harness=target.harness_id,
        entries=entries,
        blocking=any(e.severity == "block" for e in entries),
    )
