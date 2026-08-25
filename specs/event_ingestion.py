"""Provider-event ingestion and gated memory promotion.

Purpose: extend provider event capture to all adapters with append-only
sequence/parent/tool-call linkage. Feed normalized observations into
memory-index for identity resolution, deduplication, contradiction checks,
epistemic classification, and candidate retrieval. Implement explicit
promotion routers.

Preconditions: adapter_runtime.py, provider_schemas.py available.
Failure modes: DuplicateEventError on replay; PromotionRejection on invalid lane.

Usage:
    from specs.event_ingestion import EventStore, PromotionRouter
    store = EventStore(":memory:")
    store.append(event)
    router = PromotionRouter()
    lane = router.classify(observation)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .provider_schemas import HarnessId


# --- Enums -------------------------------------------------------------------


class EventType(str, Enum):
    tool_call = "tool_call"
    tool_result = "tool_result"
    message = "message"
    decision = "decision"
    observation = "observation"
    error = "error"


class PromotionLane(str, Enum):
    continuation_only = "continuation-only"  # stays in conversation store
    repo_memory = "repo-memory"             # local project memory
    global_memory = "global-memory"          # cross-project pattern
    specs_proposal = "specs-proposal"        # propose to SpecsDB
    steering_proposal = "steering-proposal"  # propose steering rule
    skill_candidate = "skill-candidate"      # candidate for skill store
    reject = "reject"                        # noise, discard


class EpistemicClass(str, Enum):
    observed = "observed"       # direct tool output, file content
    inferred = "inferred"      # derived from observations
    proposed = "proposed"      # suggested but unconfirmed
    contradicted = "contradicted"  # falsified by evidence


# --- Data Models -------------------------------------------------------------


@dataclass
class NormalizedEvent:
    """A provider-neutral event in the ingestion pipeline."""
    event_id: str = ""
    event_type: EventType = EventType.observation
    harness_id: str = ""
    session_id: str = ""
    sequence: int = 0
    parent_event_id: str = ""
    tool_name: str = ""
    content: str = ""
    content_hash: str = ""
    timestamp: float = 0
    epistemic_class: EpistemicClass = EpistemicClass.observed
    metadata: dict = field(default_factory=dict)

    def compute_hash(self) -> str:
        payload = f"{self.harness_id}:{self.session_id}:{self.content}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class PromotionCandidate:
    """An observation ready for promotion routing."""
    content: str
    source_event_id: str
    lane: PromotionLane = PromotionLane.continuation_only
    confidence: float = 0.5
    reason: str = ""


# --- Exceptions --------------------------------------------------------------


class DuplicateEventError(Exception):
    pass


class PromotionRejection(Exception):
    pass


# --- Event Store (SQLite) ----------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EventStore:
    """Append-only event store with sequence/parent linkage.

    Contract:
        Require: writable DB path or :memory:.
        Guarantee: append-only; no updates or deletes.
        Maintain: event_id uniqueness; sequence ordering per session.
        Assert: content_hash deduplication prevents replay.
    """

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, isolation_level="DEFERRED")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                harness_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                parent_event_id TEXT DEFAULT '',
                tool_name TEXT DEFAULT '',
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                timestamp REAL NOT NULL,
                epistemic_class TEXT DEFAULT 'observed',
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_session
                ON events(session_id, sequence);
            CREATE INDEX IF NOT EXISTS idx_events_hash
                ON events(content_hash);
            CREATE INDEX IF NOT EXISTS idx_events_type
                ON events(event_type);
        """)
        self.conn.commit()

    def append(self, event: NormalizedEvent) -> str:
        """Append an event. Deduplicates by content_hash."""
        if not event.content_hash:
            event.content_hash = event.compute_hash()
        if not event.event_id:
            event.event_id = f"evt:{event.content_hash}:{event.sequence}"

        # Check for duplicate
        existing = self.conn.execute(
            "SELECT event_id FROM events WHERE content_hash=? AND session_id=?",
            (event.content_hash, event.session_id),
        ).fetchone()
        if existing:
            raise DuplicateEventError(
                f"Event with hash {event.content_hash} already exists in session {event.session_id}"
            )

        now = _now()
        self.conn.execute(
            """INSERT INTO events
               (event_id, event_type, harness_id, session_id, sequence,
                parent_event_id, tool_name, content, content_hash,
                timestamp, epistemic_class, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id, event.event_type.value, event.harness_id,
                event.session_id, event.sequence, event.parent_event_id,
                event.tool_name, event.content, event.content_hash,
                event.timestamp or time.time(), event.epistemic_class.value,
                json.dumps(event.metadata), now,
            ),
        )
        self.conn.commit()
        return event.event_id

    def get_session_events(
        self, session_id: str, event_type: str | None = None
    ) -> list[NormalizedEvent]:
        """Get all events for a session in sequence order."""
        query = "SELECT * FROM events WHERE session_id=?"
        params: list = [session_id]
        if event_type:
            query += " AND event_type=?"
            params.append(event_type)
        query += " ORDER BY sequence"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_event(self, event_id: str) -> Optional[NormalizedEvent]:
        """Get a single event by ID."""
        row = self.conn.execute(
            "SELECT * FROM events WHERE event_id=?", (event_id,)
        ).fetchone()
        return self._row_to_event(row) if row else None

    def next_sequence(self, session_id: str) -> int:
        """Get the next sequence number for a session."""
        row = self.conn.execute(
            "SELECT MAX(sequence) as m FROM events WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return (row["m"] or 0) + 1

    def count(self, session_id: str | None = None) -> int:
        """Count events, optionally filtered by session."""
        if session_id:
            row = self.conn.execute(
                "SELECT COUNT(*) as c FROM events WHERE session_id=?", (session_id,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) as c FROM events").fetchone()
        return row["c"]

    def _row_to_event(self, row) -> NormalizedEvent:
        return NormalizedEvent(
            event_id=row["event_id"],
            event_type=EventType(row["event_type"]),
            harness_id=row["harness_id"],
            session_id=row["session_id"],
            sequence=row["sequence"],
            parent_event_id=row["parent_event_id"],
            tool_name=row["tool_name"],
            content=row["content"],
            content_hash=row["content_hash"],
            timestamp=row["timestamp"],
            epistemic_class=EpistemicClass(row["epistemic_class"]),
            metadata=json.loads(row["metadata"]),
        )

    def close(self):
        self.conn.close()


# --- Promotion Router --------------------------------------------------------


# Keyword sets for lane classification
_SPECS_KEYWORDS = {"requirement", "decision", "task", "acceptance", "criteria", "should", "must"}
_STEERING_KEYWORDS = {"rule", "always", "never", "convention", "standard", "pattern"}
_SKILL_KEYWORDS = {"technique", "algorithm", "method", "approach", "recipe", "workflow"}


class PromotionRouter:
    """Route observations to the correct promotion lane.

    Contract:
        Require: non-empty content string.
        Guarantee: exactly one lane per observation.
        Maintain: no direct durable writes from raw responses.
    """

    def classify(self, content: str, metadata: dict | None = None) -> PromotionCandidate:
        """Classify content into a promotion lane."""
        meta = metadata or {}
        content_lower = content.lower()

        # Check for explicit lane hints in metadata
        if meta.get("lane"):
            try:
                lane = PromotionLane(meta["lane"])
                return PromotionCandidate(
                    content=content, source_event_id=meta.get("event_id", ""),
                    lane=lane, confidence=0.9, reason="explicit metadata hint",
                )
            except ValueError:
                pass

        # Keyword-based classification
        specs_score = sum(1 for kw in _SPECS_KEYWORDS if kw in content_lower)
        steering_score = sum(1 for kw in _STEERING_KEYWORDS if kw in content_lower)
        skill_score = sum(1 for kw in _SKILL_KEYWORDS if kw in content_lower)

        # Threshold: need at least 2 keyword hits for non-default lanes
        if specs_score >= 2 and specs_score > steering_score:
            return PromotionCandidate(
                content=content, source_event_id=meta.get("event_id", ""),
                lane=PromotionLane.specs_proposal, confidence=min(specs_score / 5, 0.9),
                reason=f"specs keywords ({specs_score} hits)",
            )
        elif steering_score >= 2 and steering_score > specs_score:
            return PromotionCandidate(
                content=content, source_event_id=meta.get("event_id", ""),
                lane=PromotionLane.steering_proposal, confidence=min(steering_score / 5, 0.9),
                reason=f"steering keywords ({steering_score} hits)",
            )
        elif skill_score >= 2:
            return PromotionCandidate(
                content=content, source_event_id=meta.get("event_id", ""),
                lane=PromotionLane.skill_candidate, confidence=min(skill_score / 5, 0.9),
                reason=f"skill keywords ({skill_score} hits)",
            )

        # Default: repo memory if project-specific, otherwise continuation-only
        if meta.get("project_slug"):
            return PromotionCandidate(
                content=content, source_event_id=meta.get("event_id", ""),
                lane=PromotionLane.repo_memory, confidence=0.4,
                reason="project-scoped observation",
            )

        return PromotionCandidate(
            content=content, source_event_id=meta.get("event_id", ""),
            lane=PromotionLane.continuation_only, confidence=0.3,
            reason="default — no strong signal",
        )

    def should_promote(self, candidate: PromotionCandidate, threshold: float = 0.5) -> bool:
        """Check if a candidate meets promotion threshold."""
        if candidate.lane == PromotionLane.reject:
            return False
        if candidate.lane == PromotionLane.continuation_only:
            return False
        return candidate.confidence >= threshold
