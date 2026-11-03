"""Acceptance tests for party_ledger.py (the contract's behaviour, written before the bodies).

Spec: party_ledger.py docstrings. Run from ~/.harness: python -m pytest specs/test_party_ledger.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from party_ledger import Attempt, break_even_cap, cost_ratio, exploration_depth, load, record, resolution_rates


def att(bug="b", n=1, who="leader", ok=False, cost=1.0, tokens=100, secs=10.0) -> Attempt:
    return Attempt(bug, n, who, ok, tokens, cost, secs)


def test_record_appends_one_json_line_per_attempt_and_creates_parents(tmp_path):
    path = tmp_path / "deep" / "dir" / "ledger.jsonl"
    record(path, att(bug="x", ok=True, cost=0.5))
    record(path, att(bug="y", n=2, who="oracle", tokens=7, secs=1.5))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["bug"] == "x" and first["resolved"] is True and first["cost_usd"] == 0.5
    assert json.loads(lines[1])["resolver"] == "oracle" and json.loads(lines[1])["tokens"] == 7


@pytest.mark.parametrize("bad", [att(n=0), att(n=-3), att(who="fighter"), att(who="")])
def test_record_rejects_bad_attempts_and_writes_nothing(tmp_path, bad):
    path = tmp_path / "l.jsonl"
    with pytest.raises(ValueError):
        record(path, bad)
    assert not path.exists()


def test_load_round_trips_in_file_order_and_a_missing_file_is_empty(tmp_path):
    path = tmp_path / "l.jsonl"
    assert load(path) == []
    items = [att(bug="a", n=1), att(bug="a", n=2, who="oracle", ok=True, cost=2.25, tokens=9, secs=0.5)]
    for a in items:
        record(path, a)
    assert load(path) == items


def test_load_skips_blank_lines_and_names_the_first_bad_line(tmp_path):
    path = tmp_path / "l.jsonl"
    record(path, att())
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n   \n")
        fh.write("{not json}\n")
        fh.write('{"bug": "late"}\n')
    with pytest.raises(ValueError, match="line 4"):
        load(path)


def test_resolution_rates_counts_only_leader_attempts_per_attempt_number():
    attempts = [att(n=1, ok=True), att(n=1, ok=False), att(n=1, ok=False), att(n=2, ok=True), att(n=2, ok=False),
                att(n=1, who="oracle", ok=True), att(n=3, who="oracle", ok=True)]
    assert resolution_rates(attempts) == {1: (1, 3), 2: (1, 2)}
    assert resolution_rates([]) == {}


def test_cost_ratio_is_mean_leader_cost_over_mean_oracle_cost():
    attempts = [att(cost=1.0), att(cost=3.0), att(who="oracle", cost=8.0)]
    assert cost_ratio(attempts) == pytest.approx(2.0 / 8.0)


@pytest.mark.parametrize("attempts", [[], [att()], [att(who="oracle")], [att(), att(who="oracle", cost=0.0)]])
def test_cost_ratio_is_none_when_a_side_is_missing_or_the_oracle_is_free(attempts):
    assert cost_ratio(attempts) is None


def leaders(k, tried, resolved, cost=1.0):
    return [att(bug=f"k{k}-{i}", n=k, ok=i < resolved, cost=cost) for i in range(tried)]


def test_break_even_cap_counts_consecutive_attempts_that_beat_the_ratio():
    oracle = [att(who="oracle", cost=5.0)]                        # ratio = 1.0 / 5.0 = 0.2
    data = leaders(1, 10, 6) + leaders(2, 10, 3) + leaders(3, 10, 1) + oracle      # P = .6, .3, .1
    assert break_even_cap(data, min_samples=5) == 2


def test_break_even_cap_stops_at_the_first_attempt_number_that_fails_even_if_a_later_one_passes():
    oracle = [att(who="oracle", cost=5.0)]
    data = leaders(1, 10, 6) + leaders(2, 10, 1) + leaders(3, 10, 9) + oracle      # P(2)=.1 < .2 < P(3)=.9
    assert break_even_cap(data, min_samples=5) == 1


def test_break_even_cap_is_zero_when_the_first_attempt_is_not_worth_making():
    oracle = [att(who="oracle", cost=1.0)]                        # ratio 1.0; P(1) = 0.4 <= 1.0
    assert break_even_cap(leaders(1, 10, 4) + oracle, min_samples=5) == 0


def test_break_even_cap_needs_min_samples_and_returns_the_default_without_data():
    oracle = [att(who="oracle", cost=5.0)]
    assert break_even_cap([], default=1) == 1
    assert break_even_cap(leaders(1, 10, 9), default=2) == 2                                  # no oracle cost: ratio None
    assert break_even_cap(leaders(1, 3, 3) + oracle, min_samples=5, default=2) == 2           # too few first attempts
    assert break_even_cap(leaders(1, 10, 9) + leaders(2, 4, 4) + oracle, min_samples=5) == 1  # attempt 2 untrusted


# ---- exploration: the Oracle's finding that the cap alone can never learn past itself --------
# (2026-10-08, live Oracle verdict NO: at cap 1 no attempt-2 row is ever logged, and cap 0 is
#  absorbing too; exploration_depth is the corrected spec's bounded way out.)

ORACLE = [att(bug="k1-0", n=2, who="oracle", cost=5.0)]     # ratio = 1.0 / 5.0 = 0.2; k1-0 is a bug the Leader tried (leaders())


def oracle_only(count, start=0):
    return [att(bug=f"oracle-only-{start + i}", n=1, who="oracle", ok=True, cost=5.0) for i in range(count)]


def test_the_absorbing_state_is_real_the_cap_never_rises_from_attempt_one_data_alone():
    data = leaders(1, 20, 10) + ORACLE                                           # P(1) = 0.5 > 0.2, no attempt-2 rows
    assert break_even_cap(data, min_samples=5) == 1 and break_even_cap(data * 5, min_samples=5) == 1


def test_exploration_allows_one_attempt_past_the_cap_until_that_number_has_enough_data():
    data = leaders(1, 20, 10) + ORACLE
    assert exploration_depth(data, min_samples=5) == 2                           # the test that catches the flaw
    assert exploration_depth(data + leaders(2, 3, 0), min_samples=5) == 2        # 3 of 5 tries: keep exploring
    assert exploration_depth(data + leaders(2, 5, 1), min_samples=5) == 1        # P(2)=0.2 is not > 0.2: stop at the cap


def test_exploration_follows_the_cap_up_when_the_new_depth_pays():
    data = leaders(1, 20, 10) + leaders(2, 5, 4) + ORACLE                        # P(2)=0.8 > 0.2, so the cap is 2
    assert break_even_cap(data, min_samples=5) == 2
    assert exploration_depth(data, min_samples=5) == 3                           # and attempt 3 is now unexplored


def test_exploration_returns_the_default_until_there_is_enough_data_to_decide():
    assert exploration_depth([], default=1) == 1
    assert exploration_depth(leaders(1, 10, 9), default=2) == 2                  # no oracle cost, so no ratio
    assert exploration_depth(leaders(1, 3, 3) + ORACLE, min_samples=5, default=2) == 2
    assert exploration_depth([], default=0) == 0                                 # the default is returned verbatim


def test_cap_zero_reopens_attempt_one_after_explore_every_oracle_only_bugs():
    bad = leaders(1, 10, 1) + ORACLE                                             # P(1)=0.1 < 0.2: cap 0
    assert break_even_cap(bad, min_samples=5) == 0
    assert exploration_depth(bad + oracle_only(9), min_samples=5, explore_every=10) == 0
    assert exploration_depth(bad + oracle_only(10), min_samples=5, explore_every=10) == 1
    assert exploration_depth(bad + oracle_only(25), min_samples=5, explore_every=10) == 1


def test_the_oracle_only_count_restarts_after_each_leader_attempt():
    bad = leaders(1, 10, 1) + ORACLE
    reopened = bad + oracle_only(10) + [att(bug="probe", n=1, ok=False)]         # the Leader tried again; one more miss
    assert exploration_depth(reopened, min_samples=5, explore_every=10) == 0     # the count starts over from zero
    assert exploration_depth(reopened + oracle_only(10, start=100), min_samples=5, explore_every=10) == 1


def test_oracle_rows_for_a_bug_the_leader_also_tried_are_not_oracle_only():
    bad = leaders(1, 10, 1) + ORACLE
    mixed = bad + [att(bug="k1-0", n=2, who="oracle", ok=True, cost=5.0)] * 12   # bug 'k1-0' HAS a Leader attempt above
    assert exploration_depth(mixed, min_samples=5, explore_every=10) == 0
