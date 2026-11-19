"""Score the first taskq edit against evaluator-owned behavioral checks.

| Stage | Mechanism | Tag | Refs |
|---|---|---|---|
| INGEST | Resolve the immutable arm snapshot and verifier timeout | [mandatory] | P1, P2, P3 |
| CLEAN | Refuse missing or incomplete taskq snapshots as unscored | [mandatory] | P3 |
| SCORE | Execute three controlled retry scenarios in an isolated process | [mandatory] | P2, P3 |
| SERVE | Emit verdict, check digest, elapsed time, and check details as JSON | [mandatory] | P4, P5 |

EARS guards:
- R1: Both arms use the same three assertions and check digest.
- R2: A runnable snapshot that violates an assertion is fail.
- R3: Missing modules, import failures, and timeout are unscored.
- R4: The verifier never writes to the arm snapshot.

CLOSED:
- Process exit status does not establish acceptance; behavior is exercised
  independently in a child process with injected transient failures.

Preconditions: Snapshot contains importable `taskq` modules from the first edit.
Failure modes: Missing artifacts or verifier timeout return unscored; behavioral
exceptions or failed assertions return fail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

DRIVER = r"""
import json
import sys
from pathlib import Path

snapshot = Path.cwd()
sys.path.insert(0, str(snapshot))
try:
    from taskq.queue import TaskQueue
    from taskq.task import Task, TaskStatus
    from taskq.worker import Worker
except Exception as exc:
    print(json.dumps({"status": "unscored", "reason": f"taskq import failed: {type(exc).__name__}: {exc}"}))
    raise SystemExit(0)

def run_case(name, failures_before_success, expected_attempts, expected_status):
    class InjectedWorker(Worker):
        def __init__(self, queue):
            super().__init__(queue)
            self.attempts = 0

        def _execute(self, task):
            self.attempts += 1
            if self.attempts <= failures_before_success:
                raise RuntimeError("controlled transient failure")

    queue = TaskQueue()
    task = Task(name=f"pilot-{name}")
    queue.add(task)
    worker = InjectedWorker(queue)
    worker.run(poll_interval=0)
    actual_status = task.status.name
    if worker.attempts != expected_attempts or actual_status != expected_status:
        return {"name": name, "passed": False, "attempts": worker.attempts,
                "expected_attempts": expected_attempts, "status": actual_status,
                "expected_status": expected_status}
    return {"name": name, "passed": True, "attempts": worker.attempts,
            "status": actual_status}

try:
    checks = [
        run_case("first_attempt_success", 0, 1, "DONE"),
        run_case("transient_failure_recovery", 1, 2, "DONE"),
        run_case("retry_exhaustion", 100, 4, "DEAD"),
    ]
except Exception as exc:
    print(json.dumps({"status": "fail", "reason": f"behavior execution failed: {type(exc).__name__}: {exc}"}))
    raise SystemExit(0)

failed = [check for check in checks if not check["passed"]]
print(json.dumps({"status": "fail" if failed else "pass", "checks": checks,
                  "failed_checks": [check["name"] for check in failed]}))
"""


def verify_snapshot(snapshot: Path, timeout_seconds: int) -> dict[str, object]:
    """Return a bounded behavioral verdict for one immutable arm snapshot.

    Args:
        snapshot: Root containing the generated `taskq` package.
        timeout_seconds: Maximum child-process runtime.

    Returns:
        JSON-compatible status, evidence, duration, and verifier digest.

    Require: timeout_seconds is positive; snapshot is the frozen arm root.
    Guarantee: The verdict is pass, fail, or unscored and includes all checks
        completed before the result.
    Maintain: The verifier reads but never changes the snapshot.
    Assert: Timeout and import failures cannot be reported as pass.
    """
    started = time.monotonic()
    digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")
    if not snapshot.is_dir() or not (snapshot / "taskq").is_dir():
        return {"status": "unscored", "reason": "snapshot or taskq package is missing",
                "elapsed_seconds": round(time.monotonic() - started, 3), "check_digest": digest}
    required = [snapshot / "taskq" / name for name in ("__init__.py", "task.py", "queue.py", "worker.py")]
    if any(not path.is_file() for path in required):
        return {"status": "unscored", "reason": "required taskq module is missing",
                "elapsed_seconds": round(time.monotonic() - started, 3), "check_digest": digest}
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", DRIVER], cwd=snapshot,
            capture_output=True, text=True, timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"status": "unscored", "reason": "verifier timeout",
                "elapsed_seconds": round(time.monotonic() - started, 3), "check_digest": digest}
    elapsed = round(time.monotonic() - started, 3)
    if result.returncode != 0:
        return {"status": "unscored", "reason": f"verifier process exited {result.returncode}",
                "stderr": result.stderr[-1000:], "elapsed_seconds": elapsed, "check_digest": digest}
    try:
        evidence = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "unscored", "reason": "verifier produced no valid JSON verdict",
                "stdout": result.stdout[-1000:], "elapsed_seconds": elapsed, "check_digest": digest}
    return {**evidence, "elapsed_seconds": elapsed, "check_digest": digest}


def main(argv: list[str] | None = None) -> int:
    """Print one verifier receipt for an arm snapshot.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Zero when a verdict receipt is emitted; nonzero for invalid CLI input.

    Require: Caller supplies an arm snapshot and a positive timeout.
    Guarantee: One JSON receipt is written to stdout.
    Maintain: No files in the arm snapshot are written.
    Assert: Any timeout or evaluator failure is represented as unscored.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=55)
    args = parser.parse_args(argv)
    print(json.dumps(verify_snapshot(args.snapshot, args.timeout_seconds), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
