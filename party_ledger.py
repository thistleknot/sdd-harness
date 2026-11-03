"""party_ledger.py -- the measurement ledger behind tiers.toml [escalation] leader_attempts.

Spec: C:/Users/user/.claude/plans/make-harness-render-and-install-the-party.md (verification:
      "log attempts, outcome, tokens, cost and seconds ... first data toward the cap") and
      tiers.toml [escalation]: keep trying while P(next attempt resolves) > cost(Leader attempt) /
      cost(Oracle call).
Task: plan layer 5, end-to-end party run. CONTRACT written by the Leader; bodies by a Fighter.

One JSON object per line, appended to a ledger file (default ~/.harness/ledger/party-runs.jsonl).
A "Leader attempt" is the Leader's own try at a Fighter-reported bug; the Oracle call that follows
a failed one is recorded with resolver="oracle".
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Attempt:
    """One attempt at a Fighter-reported bug.

    Attributes:
        bug: Free-text identifier of the bug; attempts at the same bug share it.
        attempt: 1-based attempt number at this bug (the Leader's first try is 1).
        resolver: Who made the attempt: "leader" or "oracle".
        resolved: True if this attempt cleared the bug.
        tokens: Total tokens the attempt used.
        cost_usd: Dollar cost of the attempt.
        seconds: Wall-clock seconds the attempt took.
    """

    bug: str
    attempt: int
    resolver: str
    resolved: bool
    tokens: int
    cost_usd: float
    seconds: float


def record(path: Path, attempt: Attempt) -> None:
    """Append one attempt to the ledger as a single JSON line.

    Creates the file and any missing parent directories. Existing lines are never rewritten.

    Args:
        path: The ledger file.
        attempt: The attempt to record.

    Raises:
        ValueError: If attempt.attempt is less than 1, or attempt.resolver is not "leader" or
            "oracle". Nothing is written in that case.
    """
    if attempt.attempt < 1:
        raise ValueError(f"attempt number must be >= 1, got {attempt.attempt}")
    if attempt.resolver not in ("leader", "oracle"):
        raise ValueError(f"resolver must be 'leader' or 'oracle', got {attempt.resolver!r}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(attempt)) + "\n")


def load(path: Path) -> list[Attempt]:
    """Read every attempt from the ledger, in file order.

    Args:
        path: The ledger file.

    Returns:
        The attempts, oldest first. A missing file gives an empty list. Blank lines are skipped.

    Raises:
        ValueError: If a line is not valid JSON for an Attempt. The message names the 1-based
            line number of the first bad line.
    """
    path = Path(path)
    if not path.exists():
        return []
    names = [f.name for f in fields(Attempt)]
    out: list[Attempt] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                out.append(Attempt(**{n: obj[n] for n in names}))
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"bad ledger entry at line {lineno}: {exc}") from exc
    return out


def resolution_rates(attempts: list[Attempt]) -> dict[int, tuple[int, int]]:
    """Count, per attempt number, how many Leader attempts resolved their bug.

    Only attempts with resolver == "leader" count.

    Args:
        attempts: Attempts from the ledger.

    Returns:
        A dict mapping attempt number k to (resolved_count, tried_count). Only attempt numbers
        that occur appear as keys.
    """
    rates: dict[int, tuple[int, int]] = {}
    for a in attempts:
        if a.resolver != "leader":
            continue
        done, tried = rates.get(a.attempt, (0, 0))
        rates[a.attempt] = (done + (1 if a.resolved else 0), tried + 1)
    return rates


def cost_ratio(attempts: list[Attempt]) -> float | None:
    """The cost of a Leader attempt relative to an Oracle call.

    Args:
        attempts: Attempts from the ledger.

    Returns:
        mean(cost_usd of resolver == "leader") divided by mean(cost_usd of resolver == "oracle").
        None if either group is empty or the Oracle mean is 0.
    """
    lead = [a.cost_usd for a in attempts if a.resolver == "leader"]
    orac = [a.cost_usd for a in attempts if a.resolver == "oracle"]
    if not lead or not orac:
        return None
    orac_mean = sum(orac) / len(orac)
    if orac_mean == 0:
        return None
    return (sum(lead) / len(lead)) / orac_mean


def break_even_cap(attempts: list[Attempt], min_samples: int = 5, default: int = 1) -> int:
    """How many Leader attempts at a bug are worth making before calling the Oracle.

    Keep trying while P(attempt k resolves) = resolved(k) / tried(k) exceeds cost_ratio. The cap is
    the largest k such that EVERY attempt number j from 1 to k has tried(j) >= min_samples and
    P(j) > cost_ratio, counting consecutively from 1. This is a stopping rule: it assumes P(k) is
    non-increasing in k, and it can only ever return a number the ledger already has data for, so
    it cannot learn past its own cap. Use exploration_depth to decide how deep the Leader may go.

    Args:
        attempts: Attempts from the ledger.
        min_samples: Minimum Leader attempts needed at an attempt number before its rate is trusted.
        default: Returned when there is not enough data to decide: cost_ratio is None, or
            attempt number 1 has fewer than min_samples tries.

    Returns:
        The cap, 0 or more. 0 means attempt 1 has enough data and is not worth making
        (P(1) <= cost_ratio), so go straight to the Oracle.
    """
    ratio = cost_ratio(attempts)
    rates = resolution_rates(attempts)
    if ratio is None or rates.get(1, (0, 0))[1] < min_samples:
        return default
    cap = 0
    k = 1
    while k in rates:
        done, tried = rates[k]
        if tried < min_samples or done / tried <= ratio:
            break
        cap = k
        k += 1
    return cap


def exploration_depth(attempts: list[Attempt], min_samples: int = 5, default: int = 1,
                      explore_every: int = 10) -> int:
    """How many Leader attempts the Leader may make at the next bug, so the ledger keeps learning.

    break_even_cap alone is absorbing: at cap 1 no attempt number 2 is ever logged, so the cap can
    never rise; at cap 0 no Leader attempt is ever logged, so it can never recover. This function
    adds bounded exploration (a demote, never a freeze).

    Args:
        attempts: Attempts from the ledger, oldest first.
        min_samples: Passed to break_even_cap; also the number of tries an attempt number needs
            before its rate is trusted.
        default: Returned when there is not enough data to decide, exactly as in break_even_cap
            (cost_ratio is None, or attempt number 1 has fewer than min_samples Leader tries).
        explore_every: When the cap is 0, how many bugs handled by the Oracle alone (an Oracle
            attempt on a bug that has no Leader attempt anywhere in the ledger), counted after the
            last Leader attempt in file order, must pass before attempt 1 is tried again.

    Returns:
        The attempt depth allowed at the next bug. Let cap = break_even_cap(...). When there is not
        enough data, default. When cap >= 1: cap + 1 if attempt number cap + 1 has fewer than
        min_samples Leader tries (one exploratory attempt past the cap), else cap. When cap == 0:
        1 if at least explore_every Oracle-only bugs have been handled since the last Leader
        attempt, else 0.
    """
    rates = resolution_rates(attempts)
    if cost_ratio(attempts) is None or rates.get(1, (0, 0))[1] < min_samples:
        return default
    cap = break_even_cap(attempts, min_samples, default)
    if cap >= 1:
        return cap + 1 if rates.get(cap + 1, (0, 0))[1] < min_samples else cap
    leader_bugs = {a.bug for a in attempts if a.resolver == "leader"}
    last = max((i for i, a in enumerate(attempts) if a.resolver == "leader"), default=-1)
    oracle_only = {a.bug for a in attempts[last + 1:]
                   if a.resolver == "oracle" and a.bug not in leader_bugs}
    return 1 if len(oracle_only) >= explore_every else 0
