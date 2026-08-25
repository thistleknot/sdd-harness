"""Universal adapter runtime and continuation store.

Purpose: implement the provider adapter interface — capture, normalize,
export/import envelopes, persist checkpoints, manage session lineage,
and block stale or lossy handoffs.

Preconditions: provider_schemas.py in same package. sqlite3 available.
Failure modes: StaleCheckpointError on outdated resume; LossyHandoffError on blocking loss.

Usage:
    from adapter_runtime import ContinuationStore, AdapterBase
    store = ContinuationStore("continuations.db")
    store.persist(envelope)
    restored = store.load(envelope_id)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .provider_schemas import (
    ContinuationEnvelope,
    CapabilityProfile,
    DefinitionLock,
    HarnessId,
    LossReport,
    ProviderIdentity,
    WorkspaceIdentity,
    compute_loss_report,
)


# --- Exceptions --------------------------------------------------------------


class StaleCheckpointError(Exception):
    """Raised when resuming from a checkpoint that doesn't match current state."""
    pass


class LossyHandoffError(Exception):
    """Raised when a handoff would lose blocking information."""
    pass


class LineageError(Exception):
    """Raised when session lineage is broken or invalid."""
    pass


# --- Continuation Store (SQLite) ---------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ContinuationStore:
    """SQLite-backed persistence for continuation envelopes.

    Contract:
        Require: writable db_path.
        Guarantee: append-only checkpoints; child-session lineage on resume.
        Maintain: envelope_id uniqueness; content_hash integrity.
        Assert: load returns sealed envelope matching stored hash.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), isolation_level="DEFERRED")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                envelope_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                parent_session_id TEXT,
                harness_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                spec_snapshot_hash TEXT DEFAULT '',
                head_commit TEXT DEFAULT '',
                intent TEXT DEFAULT '',
                envelope_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lineage (
                child_session_id TEXT PRIMARY KEY,
                parent_session_id TEXT NOT NULL,
                parent_envelope_id TEXT NOT NULL,
                resumed_at TEXT NOT NULL,
                resume_reason TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_checkpoints_session
                ON checkpoints(session_id);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_harness
                ON checkpoints(harness_id);
            CREATE INDEX IF NOT EXISTS idx_lineage_parent
                ON lineage(parent_session_id);
        """)
        self.conn.commit()

    def persist(self, envelope: ContinuationEnvelope) -> str:
        """Persist a sealed envelope. Returns envelope_id."""
        if not envelope.content_hash:
            envelope.seal()

        now = _now()
        self.conn.execute(
            """INSERT OR REPLACE INTO checkpoints
               (envelope_id, session_id, parent_session_id, harness_id,
                content_hash, spec_snapshot_hash, head_commit, intent,
                envelope_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                envelope.envelope_id,
                envelope.session_id,
                envelope.parent_session_id or "",
                envelope.provider.harness_id.value,
                envelope.content_hash,
                envelope.spec_snapshot_hash,
                envelope.workspace.head_commit,
                envelope.intent,
                envelope.model_dump_json(),
                now,
            ),
        )
        self.conn.commit()
        return envelope.envelope_id

    def load(self, envelope_id: str) -> Optional[ContinuationEnvelope]:
        """Load an envelope by ID. Returns None if not found."""
        row = self.conn.execute(
            "SELECT envelope_json, content_hash FROM checkpoints WHERE envelope_id=?",
            (envelope_id,),
        ).fetchone()
        if not row:
            return None

        envelope = ContinuationEnvelope.model_validate_json(row["envelope_json"])
        # Verify integrity
        if envelope.compute_hash() != row["content_hash"]:
            raise StaleCheckpointError(
                f"Content hash mismatch for {envelope_id}: "
                f"stored={row['content_hash']}, computed={envelope.compute_hash()}"
            )
        return envelope

    def load_latest(self, session_id: str) -> Optional[ContinuationEnvelope]:
        """Load the most recent checkpoint for a session."""
        row = self.conn.execute(
            "SELECT envelope_json FROM checkpoints WHERE session_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return ContinuationEnvelope.model_validate_json(row["envelope_json"])

    def list_checkpoints(
        self, harness_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        """List checkpoint summaries."""
        query = "SELECT envelope_id, session_id, harness_id, intent, created_at FROM checkpoints"
        params: list = []
        if harness_id:
            query += " WHERE harness_id=?"
            params.append(harness_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def create_child_session(
        self,
        parent_envelope_id: str,
        child_session_id: str,
        reason: str = "",
    ) -> None:
        """Record a child-session lineage entry for resume tracking."""
        parent = self.load(parent_envelope_id)
        if not parent:
            raise LineageError(f"Parent envelope not found: {parent_envelope_id}")

        now = _now()
        self.conn.execute(
            """INSERT OR REPLACE INTO lineage
               (child_session_id, parent_session_id, parent_envelope_id, resumed_at, resume_reason)
               VALUES (?, ?, ?, ?, ?)""",
            (child_session_id, parent.session_id, parent_envelope_id, now, reason),
        )
        self.conn.commit()

    def get_lineage(self, session_id: str) -> list[dict]:
        """Get full lineage chain for a session (ancestors first)."""
        chain: list[dict] = []
        current = session_id

        # Walk up the lineage
        for _ in range(100):  # safety bound
            row = self.conn.execute(
                "SELECT * FROM lineage WHERE child_session_id=?", (current,)
            ).fetchone()
            if not row:
                break
            chain.insert(0, dict(row))
            current = row["parent_session_id"]

        return chain

    def is_stale(
        self, envelope_id: str, current_commit: str, current_spec_hash: str
    ) -> bool:
        """Check if a checkpoint is stale relative to current state."""
        row = self.conn.execute(
            "SELECT head_commit, spec_snapshot_hash FROM checkpoints WHERE envelope_id=?",
            (envelope_id,),
        ).fetchone()
        if not row:
            return True
        # Stale if commit moved OR spec changed
        if current_commit and row["head_commit"] and row["head_commit"] != current_commit:
            return True
        if current_spec_hash and row["spec_snapshot_hash"] and row["spec_snapshot_hash"] != current_spec_hash:
            return True
        return False

    def close(self):
        self.conn.close()


# --- Adapter Interface (ABC) -------------------------------------------------


class AdapterBase(ABC):
    """Abstract base for all provider adapters.

    Each harness implements this interface to participate in cross-harness
    continuation. Adapters are pure at the boundary: they transform events
    and envelopes but don't own persistence (ContinuationStore does).

    Contract:
        Require: valid harness_id and capability_profile.
        Guarantee: deterministic round-trip (export then import = identity).
        Maintain: no provider-specific logic leaks into kernel.
    """

    def __init__(self, harness_id: HarnessId):
        self.harness_id = harness_id

    @abstractmethod
    def capture_event(self, raw_event: dict) -> dict:
        """Capture a native event and normalize to canonical schema.

        Args:
            raw_event: Provider-specific event payload.
        Returns:
            Normalized event dict with at minimum:
            {type, timestamp, session_id, content, provider_meta}.
        """
        ...

    @abstractmethod
    def export_envelope(
        self,
        session_id: str,
        workspace: WorkspaceIdentity,
        intent: str,
        work_state: dict,
        provider_extensions: dict | None = None,
    ) -> ContinuationEnvelope:
        """Build and seal a ContinuationEnvelope for export.

        The envelope captures everything needed to resume in another harness.
        """
        ...

    @abstractmethod
    def import_envelope(self, envelope: ContinuationEnvelope) -> dict:
        """Import an envelope and produce a native resume packet.

        Returns a dict in the format the harness expects for session init.
        Raises LossyHandoffError if blocking capabilities are missing.
        """
        ...

    @abstractmethod
    def advertise_capabilities(self) -> CapabilityProfile:
        """Return the capability profile for this harness."""
        ...

    def calculate_loss(self, source_profile: CapabilityProfile) -> LossReport:
        """Calculate information loss importing from source to this harness."""
        return compute_loss_report(source_profile, self.advertise_capabilities())

    def verify_definition_lock(
        self, envelope: ContinuationEnvelope, lock: DefinitionLock
    ) -> bool:
        """Verify the target's repeat-back matches our envelope.

        Returns True if the lock is acceptable (target understood correctly).
        """
        if lock.envelope_id != envelope.envelope_id:
            return False
        # Check loss report doesn't have blocking entries
        if lock.loss_report and lock.loss_report.has_blocking_loss:
            return False
        return lock.accepted


# --- Resume Orchestrator -----------------------------------------------------


def resume_from_checkpoint(
    store: ContinuationStore,
    envelope_id: str,
    target_adapter: AdapterBase,
    child_session_id: str,
    current_commit: str = "",
    current_spec_hash: str = "",
) -> dict:
    """Orchestrate a cross-harness resume from a stored checkpoint.

    1. Load the envelope from store.
    2. Check staleness — block if stale.
    3. Calculate loss — block if blocking loss.
    4. Create child session lineage.
    5. Import into target adapter and return native resume packet.

    Returns:
        Native resume packet dict for the target harness.

    Raises:
        StaleCheckpointError: if checkpoint doesn't match current state.
        LossyHandoffError: if handoff would lose blocking information.
        LineageError: if envelope not found.
    """
    # 1. Load
    envelope = store.load(envelope_id)
    if not envelope:
        raise LineageError(f"Envelope not found: {envelope_id}")

    # 2. Staleness check
    if store.is_stale(envelope_id, current_commit, current_spec_hash):
        raise StaleCheckpointError(
            f"Checkpoint {envelope_id} is stale. "
            f"Current commit: {current_commit}, spec_hash: {current_spec_hash}"
        )

    # 3. Loss check
    if envelope.capability_profile:
        loss = target_adapter.calculate_loss(envelope.capability_profile)
        if loss.has_blocking_loss:
            blocking_entries = [e for e in loss.entries if e.severity == "block"]
            raise LossyHandoffError(
                f"Handoff blocked: {len(blocking_entries)} capabilities would be lost. "
                f"First: {blocking_entries[0].description if blocking_entries else 'unknown'}"
            )

    # 4. Lineage
    store.create_child_session(envelope_id, child_session_id, reason="cross-harness resume")

    # 5. Import
    return target_adapter.import_envelope(envelope)
