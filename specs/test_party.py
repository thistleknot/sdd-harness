"""Tests for party.py: dial resolution, window clamping and the squash rule.

Spec: C:/Users/user/.claude/plans/make-harness-render-and-install-the-party.md, section 2.
Run from ~/.harness: python -m pytest specs/test_party.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

import party

try:
    import tomllib
except ModuleNotFoundError:  # py310 pin
    import tomli as tomllib

TIERS = Path(__file__).resolve().parent.parent / "tiers.toml"

ROLES = {
    "leader": {"tier": "L1", "reasoning": "medium", "kind": "session", "tools": [], "name": "leader"},
    "reader": {"tier": "L0", "reasoning": "low", "tools": ["Read", "Grep"], "name": "reader"},
    "doer": {"tier": "L1", "reasoning": "low", "tools": ["Read", "Edit", "Bash"], "name": "doer"},
    "oracle": {"tier": "L3", "reasoning": "high", "tools": ["Read", "Bash", "Write"], "name": "oracle"},
}
EFFORTS = {"low": "l", "medium": "m", "high": "h"}


def schema() -> dict:
    return {
        "escalation": {"leader_attempts": 2},
        "harness": {
            "h": {"providers": ["three", "two"], "effort_key": "eff"},
            "docs": {"providers": []},
        },
        "binding": {
            "three": {"L0": "mini", "L1": "mid", "L2": "mid", "L3": "big", "effort_key": "e",
                      "effort_map": dict(EFFORTS),
                      "dial": [["L0", "low"], ["L1", "low"], ["L1", "medium"], ["L1", "high"],
                               ["L3", "medium"], ["L3", "high"]]},
            "two": {"L0": "mini", "L1": "mid", "L2": "mid", "L3": "mid", "effort_key": "e",
                    "effort_map": dict(EFFORTS),
                    "dial": [["L0", "low"], ["L1", "low"], ["L1", "medium"], ["L3", "high"]]},
        },
        "role": ROLES,
    }


def by_role(p: party.Party) -> dict:
    return {r.role: r for r in p.roles}


def test_three_model_dial_gives_each_role_its_own_step():
    p = party.resolve_party(schema(), "h", "three")
    r = by_role(p)
    assert [(r[k].model, r[k].effort, r[k].step) for k in ("reader", "doer", "leader", "oracle")] == [
        ("mini", "low", 0), ("mid", "low", 1), ("mid", "medium", 2), ("big", "high", 5)]
    assert p.warnings == [] and p.groups == [["leader"], ["reader"], ["doer"], ["oracle"]]
    assert [x.name for x in p.agent_roles()] == ["reader", "doer", "oracle"]
    assert p.leader_attempts == 2


def test_two_model_dial_puts_the_oracle_on_the_leaders_model_at_high_effort():
    p = party.resolve_party(schema(), "h", "two")
    r = by_role(p)
    assert (r["oracle"].model, r["oracle"].effort, r["oracle"].step) == ("mid", "high", 3)
    assert (r["leader"].model, r["leader"].effort) == ("mid", "medium")
    assert p.warnings == []                               # medium vs high: not the same context


def test_window_that_lowers_the_ceiling_squashes_the_oracle_into_the_leader():
    p = party.resolve_party(schema(), "h", "two", window=(0, 2))
    r = by_role(p)
    assert (r["oracle"].step, r["oracle"].target) == (2, 3)
    assert r["oracle"].squashed_into == "leader"
    assert [x.name for x in p.agent_roles()] == ["reader", "doer"]      # no agent file for the oracle
    assert any("oracle squashed into leader" in w for w in p.warnings)
    assert any("nobody above him to escalate to" in w for w in p.warnings)
    assert any("clamped from step 3 to 2" in w for w in p.warnings)


def test_window_that_raises_the_floor_makes_reader_and_doer_share_a_context_but_keep_their_tools():
    p = party.resolve_party(schema(), "h", "two", window=(1, 3))
    r = by_role(p)
    assert (r["reader"].model, r["reader"].effort) == (r["doer"].model, r["doer"].effort) == ("mid", "low")
    assert r["reader"].squashed_into is None and r["doer"].squashed_into is None
    assert r["reader"].tools == ("Read", "Grep") and "Edit" in r["doer"].tools
    assert any("reader + doer share one context" in w for w in p.warnings)
    assert any("mix read-only and write roles" in w for w in p.warnings)
    assert [x.name for x in p.agent_roles()] == ["reader", "doer", "oracle"]


def test_single_step_window_squashes_every_agent_into_the_leader():
    p = party.resolve_party(schema(), "h", "two", window=(2, 2))
    assert p.agent_roles() == []
    assert {r.squashed_into for r in p.roles if r.kind == "agent"} == {"leader"}
    assert p.groups == [["leader", "reader", "doer", "oracle"]]


@pytest.mark.parametrize("window", [(-1, 2), (0, 4), (3, 2)])
def test_window_outside_the_dial_raises(window):
    with pytest.raises(party.PartyError, match="outside the 4-step dial"):
        party.resolve_party(schema(), "h", "two", window=window)


def test_provider_must_be_one_the_harness_speaks_and_doc_only_harnesses_have_none():
    s = schema()
    s["binding"]["other"] = s["binding"]["two"]
    with pytest.raises(party.PartyError, match="cannot speak provider 'other'"):
        party.resolve_party(s, "h", "other")
    with pytest.raises(party.PartyError, match="instruction document only"):
        party.resolve_party(s, "docs")


def test_default_provider_is_the_first_one_the_harness_speaks_and_legacy_names_still_work():
    s = schema()
    assert party.resolve_party(s, "h").provider == "three"
    s["binding"]["legacy"] = s["binding"]["two"]
    assert party.resolve_party(s, "legacy").provider == "legacy"


def test_an_unbound_tier_is_an_error_not_a_blank_model():
    s = schema()
    s["binding"]["three"]["L3"] = ""
    with pytest.raises(party.PartyError, match="no model bound to L3"):
        party.resolve_party(s, "h", "three")


def test_effort_key_comes_from_the_harness_and_value_from_the_provider_map():
    s = schema()
    s["binding"]["three"]["effort_map"] = {"low": "1", "medium": "2", "high": "3"}
    r = by_role(party.resolve_party(s, "h", "three"))
    assert (r["oracle"].effort_key, r["oracle"].effort_value) == ("eff", "3")
    del s["harness"]["h"]["effort_key"]
    assert by_role(party.resolve_party(s, "h", "three"))["oracle"].effort_key == "e"


def test_a_missing_dial_or_effort_entry_is_reported():
    s = schema()
    del s["binding"]["two"]["dial"]
    with pytest.raises(party.PartyError, match="declares no dial"):
        party.resolve_party(s, "h", "two")
    s = schema()
    del s["binding"]["three"]["effort_map"]["medium"]
    with pytest.raises(party.PartyError, match="effort_map has no entry for 'medium'"):
        party.resolve_party(s, "h", "three")


def test_a_role_whose_tier_has_no_exact_step_takes_the_nearest_effort_on_its_model():
    s = schema()
    s["role"]["doer"] = {"tier": "L1", "reasoning": "high", "tools": ["Edit"], "name": "doer"}
    s["binding"]["two"]["dial"] = [["L0", "low"], ["L1", "low"], ["L1", "medium"]]
    assert by_role(party.resolve_party(s, "h", "two"))["doer"].step == 2     # no L1/high step: medium is nearest


@pytest.mark.parametrize("text,expected", [(None, (0, 3)), ("", (0, 3)), ("1:2", (1, 2)), (":2", (0, 2)), ("1:", (1, 3))])
def test_parse_window(text, expected):
    assert party.parse_window(text, 4) == expected


def test_report_lists_steps_roles_squashes_and_notes():
    text = party.report(party.resolve_party(schema(), "h", "two", window=(0, 2)))
    assert "h / two  window 0:2  (4 steps)" in text
    assert "step 3: mid / high  [L3]" in text
    assert "oracle   mid / medium  (step 2)  -> squashed into leader" in text
    assert "note: oracle: clamped from step 3 to 2 by window 0:2" in text


# ---- the real tiers.toml ----------------------------------------------------------------

@pytest.fixture(scope="module")
def real() -> dict:
    with TIERS.open("rb") as fh:
        return tomllib.load(fh)


PROVIDERS = ["anthropic", "openai", "openrouter", "ollama"]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_every_bound_provider_resolves_the_whole_party(real, provider):
    harness = next(h for h, v in real["harness"].items() if provider in v.get("providers", []))
    p = party.resolve_party(real, harness, provider)
    r = by_role(p)
    assert (r["leader"].effort, r["leader"].kind) == ("medium", "session")
    assert (r["reader"].effort, r["doer"].effort, r["oracle"].effort) == ("low", "low", "high")
    assert p.warnings == [] and p.leader_attempts == 1


def test_never_opus_by_construction(real):
    for name in ("anthropic", "openrouter"):
        b = real["binding"][name]
        ids = [b[t] for t in ("L0", "L1", "L2", "L3")]
        assert not any("opus" in i.lower() for i in ids), (name, ids)


def test_anthropic_oracle_is_the_leaders_model_at_high_effort(real):
    r = by_role(party.resolve_party(real, "claude"))
    assert r["oracle"].model == r["leader"].model == "claude-sonnet-5-5"
    assert (r["leader"].effort, r["oracle"].effort) == ("medium", "high")
    assert r["reader"].model == "claude-haiku-5-5"


def test_openrouter_and_ollama_candidates_start_with_the_bound_model(real):
    for name in ("openrouter", "ollama"):
        b = real["binding"][name]
        assert (b["candidates"]["light"][0], b["candidates"]["mid"][0], b["candidates"]["heavy"][0]) == \
               (b["L0"], b["L1"], b["L3"]), name


def test_every_harness_provider_has_a_binding_and_google_is_unbound(real):
    for h, v in real["harness"].items():
        for prov in v.get("providers", []):
            assert prov in real["binding"], (h, prov)
    with pytest.raises(party.PartyError, match="no model bound"):
        party.resolve_party(real, "claude", "anthropic", window=None) and party.resolve_party(
            {**real, "harness": {"g": {"providers": ["google"]}}}, "g", "google")


def test_a_harness_can_render_every_provider_template_it_speaks(real):
    assert real["harness"]["opencode"]["providers"] == ["openrouter", "ollama"]
    assert real["harness"]["pi"]["providers"] == ["ollama", "openrouter"]
    for prov in real["harness"]["opencode"]["providers"]:
        assert party.resolve_party(real, "opencode", prov).provider == prov
