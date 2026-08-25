"""Generic gate runner: evaluates registered validators against lifecycle events.

Purpose: one runner that accepts a lifecycle event and a policy snapshot, invokes
each registered validator, persists invocation/evidence/verdict records, and returns
an aggregate allow/block/warn/error without interpreting prose.

Preconditions: policy_contracts.py schemas available; SQLite for evidence ledger.
Failure modes: validator timeouts produce warn (fail-open) or block (fail-closed)
depending on the validator's registration. Runner itself never raises to the caller.

Contract:
    Require: a compiled PolicySnapshot and a LifecycleEvent.
    Guarantee: returns AggregateVerdict; all verdicts and evidence are persisted.
    Maintain: validators are read-only fact producers; runner never modifies source state.
    Assert: no verdict is returned without being persisted first.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Callable, Protocol

from .policy_contracts import (
    AggregateVerdict,
    EvidenceRef,
    LifecycleEvent,
    LifecycleEventType,
    PolicyRecord,
    PolicySnapshot,
    StructuredVerdict,
    ValidatorRegistration,
    VerdictStatus,
)


# --- Validator Protocol -----------------------------------------------------


class Validator(Protocol):
    """Interface that all validators must implement."""

    def evaluate(
        self,
        event: LifecycleEvent,
        rules: list[PolicyRecord],
        snapshot_hash: str,
    ) -> list[StructuredVerdict]:
        """Evaluate the event against the given rules. Return one verdict per rule evaluated."""
        ...


# --- Evidence Ledger (SQLite) -----------------------------------------------

LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS gate_invocations (
    invocation_id   TEXT PRIMARY KEY,
    event_id        TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    snapshot_hash   TEXT NOT NULL,
    overall_status  TEXT NOT NULL,
    harness_id      TEXT,
    project_slug    TEXT,
    timestamp       REAL NOT NULL,
    verdict_count   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_verdicts (
    verdict_id      TEXT PRIMARY KEY,
    invocation_id   TEXT NOT NULL,
    rule_id         TEXT NOT NULL,
    validator_id    TEXT NOT NULL,
    status          TEXT NOT NULL,
    message         TEXT,
    subject_ids     TEXT,
    evidence_json   TEXT,
    remediation_ref TEXT,
    timestamp       REAL NOT NULL,
    FOREIGN KEY (invocation_id) REFERENCES gate_invocations(invocation_id)
);

CREATE INDEX IF NOT EXISTS idx_verdicts_invocation ON gate_verdicts(invocation_id);
CREATE INDEX IF NOT EXISTS idx_verdicts_rule ON gate_verdicts(rule_id);
CREATE INDEX IF NOT EXISTS idx_invocations_event ON gate_invocations(event_id);
"""


class EvidenceLedger:
    """Append-only evidence ledger for gate invocations and verdicts.

    Require: db_path parent directory exists.
    Guarantee: all writes are transactional; a partial invocation is never visible.
    Maintain: the ledger is append-only; no updates or deletes.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(LEDGER_SCHEMA)

    def persist(self, event: LifecycleEvent, aggregate: AggregateVerdict) -> str:
        """Persist one gate invocation and all its verdicts atomically.

        Returns the invocation_id.
        """
        invocation_id = _make_id(event.event_id, aggregate.timestamp)

        with self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO gate_invocations
                   (invocation_id, event_id, event_type, snapshot_hash, overall_status,
                    harness_id, project_slug, timestamp, verdict_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    invocation_id,
                    event.event_id,
                    event.event_type.value,
                    aggregate.event_id,  # carries snapshot_hash via the runner
                    aggregate.overall_status.value,
                    event.harness_id,
                    event.project_slug,
                    aggregate.timestamp,
                    len(aggregate.verdicts),
                ),
            )
            for i, v in enumerate(aggregate.verdicts):
                verdict_id = f"{invocation_id}:{i}"
                self._conn.execute(
                    """INSERT OR IGNORE INTO gate_verdicts
                       (verdict_id, invocation_id, rule_id, validator_id, status,
                        message, subject_ids, evidence_json, remediation_ref, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        verdict_id,
                        invocation_id,
                        v.rule_id,
                        v.validator_id,
                        v.status.value,
                        v.message,
                        json.dumps(v.subject_ids),
                        json.dumps([e.model_dump() for e in v.evidence]),
                        v.remediation_task_ref,
                        v.timestamp,
                    ),
                )
        return invocation_id

    def query_invocations(
        self, event_id: str | None = None, limit: int = 20
    ) -> list[dict]:
        """Query recent invocations, optionally filtered by event_id."""
        if event_id:
            rows = self._conn.execute(
                "SELECT * FROM gate_invocations WHERE event_id=? ORDER BY timestamp DESC LIMIT ?",
                (event_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM gate_invocations ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def query_verdicts(self, invocation_id: str) -> list[dict]:
        """Return all verdicts for a given invocation."""
        rows = self._conn.execute(
            "SELECT * FROM gate_verdicts WHERE invocation_id=? ORDER BY timestamp",
            (invocation_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()


# --- Gate Runner ------------------------------------------------------------


class GateRunner:
    """Evaluates all registered validators against a lifecycle event.

    Require: at least one validator registered; a compiled PolicySnapshot provided.
    Guarantee: returns AggregateVerdict with all verdicts persisted before return.
    Maintain: validators are invoked read-only; runner does not modify policy or source.
    """

    def __init__(self, ledger: EvidenceLedger, max_workers: int = 4):
        self._ledger = ledger
        self._validators: dict[str, tuple[ValidatorRegistration, Validator]] = {}
        self._max_workers = max_workers

    def register(self, registration: ValidatorRegistration, validator: Validator) -> None:
        """Register a validator. Duplicate IDs overwrite."""
        self._validators[registration.validator_id] = (registration, validator)

    def unregister(self, validator_id: str) -> None:
        """Remove a validator by ID."""
        self._validators.pop(validator_id, None)

    @property
    def registered_count(self) -> int:
        return len(self._validators)

    def run(self, event: LifecycleEvent, snapshot: PolicySnapshot) -> AggregateVerdict:
        """Evaluate all applicable validators, persist results, return aggregate.

        Ordering: validators are invoked in registration order.
        Timeout: per-validator, controlled by ValidatorRegistration.timeout_seconds.
        Deduplication: same event_id re-evaluated produces a new invocation (append-only ledger).
        Concurrency: validators run in a thread pool for bounded parallelism.
        """
        applicable = self._applicable_validators(event)
        verdicts: list[StructuredVerdict] = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for reg, validator in applicable:
                rules = self._rules_for_validator(reg, snapshot)
                if not rules:
                    continue

                future = executor.submit(
                    self._invoke_validator, validator, event, rules, snapshot.content_hash
                )
                try:
                    result = future.result(timeout=reg.timeout_seconds)
                    verdicts.extend(result)
                except FuturesTimeout:
                    verdicts.append(self._timeout_verdict(reg, event, reg.timeout_seconds))
                except Exception as exc:
                    verdicts.append(self._error_verdict(reg, event, exc))

        # Compute overall status: worst across all verdicts
        overall = self._worst_status(verdicts)

        aggregate = AggregateVerdict(
            event_id=snapshot.content_hash,
            event_type=event.event_type,
            overall_status=overall,
            verdicts=verdicts,
            timestamp=time.time(),
        )

        # Persist before returning — the assert in the contract
        self._ledger.persist(event, aggregate)

        return aggregate

    def _applicable_validators(
        self, event: LifecycleEvent
    ) -> list[tuple[ValidatorRegistration, Validator]]:
        """Filter validators by trigger match."""
        result = []
        for reg, validator in self._validators.values():
            if not reg.triggers or event.event_type in reg.triggers:
                result.append((reg, validator))
        return result

    def _rules_for_validator(
        self, reg: ValidatorRegistration, snapshot: PolicySnapshot
    ) -> list[PolicyRecord]:
        """Filter policy rules to those this validator covers."""
        if not reg.rule_ids:
            return snapshot.rules  # validator covers all rules
        return [r for r in snapshot.rules if r.rule_id in reg.rule_ids]

    def _invoke_validator(
        self,
        validator: Validator,
        event: LifecycleEvent,
        rules: list[PolicyRecord],
        snapshot_hash: str,
    ) -> list[StructuredVerdict]:
        """Call the validator's evaluate method."""
        return validator.evaluate(event, rules, snapshot_hash)

    def _timeout_verdict(
        self, reg: ValidatorRegistration, event: LifecycleEvent, timeout: float
    ) -> StructuredVerdict:
        """Produce a verdict when a validator times out."""
        status = VerdictStatus.warn if reg.fail_open else VerdictStatus.block
        return StructuredVerdict(
            rule_id="*",
            validator_id=reg.validator_id,
            status=status,
            message=f"Validator '{reg.name}' timed out after {timeout}s",
        )

    def _error_verdict(
        self, reg: ValidatorRegistration, event: LifecycleEvent, exc: Exception
    ) -> StructuredVerdict:
        """Produce a verdict when a validator raises an exception."""
        status = VerdictStatus.warn if reg.fail_open else VerdictStatus.block
        return StructuredVerdict(
            rule_id="*",
            validator_id=reg.validator_id,
            status=status,
            message=f"Validator '{reg.name}' error: {type(exc).__name__}: {str(exc)[:200]}",
        )

    @staticmethod
    def _worst_status(verdicts: list[StructuredVerdict]) -> VerdictStatus:
        """Return the most severe status across all verdicts."""
        if not verdicts:
            return VerdictStatus.allow
        severity = {
            VerdictStatus.allow: 0,
            VerdictStatus.warn: 1,
            VerdictStatus.error: 2,
            VerdictStatus.block: 3,
        }
        worst = max(verdicts, key=lambda v: severity.get(v.status, 0))
        return worst.status


# --- Helpers ----------------------------------------------------------------


def _make_id(event_id: str, timestamp: float) -> str:
    sig = hashlib.sha256(f"{event_id}:{timestamp}".encode()).hexdigest()[:12]
    return f"inv:{sig}"
