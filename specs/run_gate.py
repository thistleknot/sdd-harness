"""Run the SDD gate kernel: compile policy, invoke validators, persist evidence.

This is the single integration script that wires policy_contracts, gate_runner,
and all validators together. It is both a CLI tool and an importable module.

Usage:
    python run_gate.py --event PostFileSave --harness kiro --project harness
    python run_gate.py --event Stop --harness kiro --project harness --scan-dir .

Phases within this script (must not exceed 4):
    1. Compile policy snapshot from specs.db
    2. Construct lifecycle event from args/payload
    3. Register applicable validators and run the gate
    4. Report results and exit with appropriate code

Exit codes:
    0 = all allow (or only warns)
    1 = at least one block verdict
    2 = gate runner error
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure specs/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from .gate_runner import EvidenceLedger, GateRunner
from .policy_contracts import (
    LifecycleEvent,
    LifecycleEventType,
    PolicySnapshot,
    ValidatorRegistration,
    VerdictStatus,
    compile_policy,
    PolicyCompileError,
)
from .validators import (
    ConvergenceValidator,
    SecurityValidator,
    SelfReviewValidator,
    SprawlValidator,
)


# --- Defaults ---------------------------------------------------------------

DEFAULT_DB = Path(__file__).parent / "specs.db"
DEFAULT_LEDGER = Path(__file__).parent / "gate_ledger.db"
DEFAULT_SCAN_DIR = Path(__file__).parent


# --- Validator Registry -----------------------------------------------------

def build_registry() -> list[tuple[ValidatorRegistration, object]]:
    """Return the full validator registry with trigger bindings."""
    return [
        (
            ValidatorRegistration(
                validator_id="security-scan",
                name="Security Scan",
                triggers=[LifecycleEventType.pre_tool_use],
                fail_open=False,
                timeout_seconds=10,
            ),
            SecurityValidator(),
        ),
        (
            ValidatorRegistration(
                validator_id="self-review",
                name="Self Review",
                triggers=[LifecycleEventType.stop],
                fail_open=True,
                timeout_seconds=15,
            ),
            SelfReviewValidator(),
        ),
        (
            ValidatorRegistration(
                validator_id="convergence",
                name="Convergence Check",
                triggers=[LifecycleEventType.stop, LifecycleEventType.post_task_exec],
                fail_open=True,
                timeout_seconds=30,
            ),
            ConvergenceValidator(),
        ),
        (
            ValidatorRegistration(
                validator_id="sprawl-census",
                name="Sprawl Census",
                triggers=[
                    LifecycleEventType.post_file_save,
                    LifecycleEventType.post_file_create,
                    LifecycleEventType.stop,
                ],
                fail_open=True,
                timeout_seconds=30,
            ),
            SprawlValidator(),
        ),
    ]


# --- Main -------------------------------------------------------------------

def run_gate(
    event_type: str,
    harness_id: str = "kiro",
    project_slug: str = "harness",
    session_id: str = "cli",
    payload: dict | None = None,
    db_path: Path = DEFAULT_DB,
    ledger_path: Path = DEFAULT_LEDGER,
) -> dict:
    """Run the gate kernel and return the aggregate result as a dict.

    Returns: {overall_status, blocking_count, warn_count, total_verdicts, invocation_id}
    """
    # Phase 1: Compile policy
    try:
        snapshot = compile_policy(db_path)
    except PolicyCompileError as e:
        return {"error": f"Policy compile failed: {e.issues}", "overall_status": "error"}

    # Phase 2: Construct event
    try:
        evt_type = LifecycleEventType(event_type)
    except ValueError:
        return {"error": f"Unknown event type: {event_type}", "overall_status": "error"}

    event = LifecycleEvent(
        event_id=f"gate-{int(time.time())}",
        event_type=evt_type,
        harness_id=harness_id,
        project_slug=project_slug,
        session_id=session_id,
        payload=payload or {},
    )

    # Phase 3: Register validators and run
    ledger = EvidenceLedger(ledger_path)
    runner = GateRunner(ledger, max_workers=4)

    for reg, validator in build_registry():
        runner.register(reg, validator)

    aggregate = runner.run(event, snapshot)
    ledger.close()

    # Phase 4: Report
    return {
        "overall_status": aggregate.overall_status.value,
        "blocking_count": len(aggregate.blocking),
        "warn_count": len(aggregate.warnings),
        "total_verdicts": len(aggregate.verdicts),
        "event_type": event_type,
        "snapshot_hash": snapshot.content_hash,
    }


def main():
    parser = argparse.ArgumentParser(description="Run the SDD gate kernel")
    parser.add_argument("--event", required=True, help="Lifecycle event type (e.g. Stop, PostFileSave)")
    parser.add_argument("--harness", default="kiro", help="Harness ID")
    parser.add_argument("--project", default="harness", help="Project slug")
    parser.add_argument("--session", default="cli", help="Session ID")
    parser.add_argument("--scan-dir", default=None, help="Directory to scan for sprawl")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to specs.db")
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER), help="Path to evidence ledger")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    payload = {}
    if args.scan_dir:
        payload["scan_dir"] = args.scan_dir
    payload["specs_db_path"] = args.db
    payload["specs_dir"] = str(Path(args.db).parent)

    result = run_gate(
        event_type=args.event,
        harness_id=args.harness,
        project_slug=args.project,
        session_id=args.session,
        payload=payload,
        db_path=Path(args.db),
        ledger_path=Path(args.ledger),
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = result.get("overall_status", "error")
        print(f"Gate: {status.upper()}")
        if result.get("blocking_count"):
            print(f"  Blocking: {result['blocking_count']}")
        if result.get("warn_count"):
            print(f"  Warnings: {result['warn_count']}")
        if result.get("error"):
            print(f"  Error: {result['error']}")
        print(f"  Verdicts: {result.get('total_verdicts', 0)}")

    # Exit code: 0=allow/warn, 1=block, 2=error
    if result.get("overall_status") == "block":
        sys.exit(1)
    elif result.get("overall_status") == "error":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
