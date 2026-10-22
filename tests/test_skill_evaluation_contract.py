"""Test deterministic contract helpers in the retrieve-skills canary suite.

| Stage | Mechanism | Contract | Req |
|---|---|---|---|
| LOAD | Import canary helpers without starting the router | [mandatory] | R64, R65 |
| CHECK | Exercise minimum case counts and selected-skill usability | [mandatory] | R64, R65 |

EARS guards:
- R1: Cases are synthetic and do not invoke embeddings, rerankers, or network services.
- R2: A selected skill passes only when its path names a readable non-empty SKILL.md.

CLOSED:
- Model-judged behavioral scoring is excluded; the behavioral check validates that a selected
  instruction can actually be handed to the caller.

Preconditions: The separate ~/.skills retrieve-skills test file is present.
Failure modes: Contract drift or unreadable selected skill fixtures fail the tests.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


CANARY_FILE = Path.home() / ".skills" / "retrieve-skills" / "test_retrieval.py"
SPEC = importlib.util.spec_from_file_location("retrieve_skill_canaries", CANARY_FILE)
assert SPEC and SPEC.loader
CANARIES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANARIES)


def test_canary_suite_keeps_minimum_positive_and_negative_case_counts():
    """Prevent silent reduction below the adopted trigger-evaluation floor.

    Require: The canonical canary module is importable.
    Guarantee: At least three positive and two negative cases are required.
    Maintain: This test does not run retrieval models.
    Assert: The current case inventory satisfies its own coverage guard.
    """
    assert len(CANARIES.CANARY_TESTS) >= 3
    assert len(CANARIES.NEGATIVE_TESTS) >= 2
    assert CANARIES.validate_case_coverage() == []


def test_canary_coverage_guard_fails_when_either_case_family_shrinks(monkeypatch):
    """Prove that coverage enforcement rejects a reduced positive/negative battery.

    Args:
        monkeypatch: Pytest fixture that restores the canonical case lists.

    Require: The imported canary module exposes its two case collections.
    Guarantee: Undersized collections yield separate findings.
    Maintain: Original cases are restored after the test.
    Assert: Both minimum thresholds are actively enforced.
    """
    monkeypatch.setattr(CANARIES, "CANARY_TESTS", CANARIES.CANARY_TESTS[:2])
    monkeypatch.setattr(CANARIES, "NEGATIVE_TESTS", CANARIES.NEGATIVE_TESTS[:1])

    findings = CANARIES.validate_case_coverage()

    assert len(findings) == 2
    assert any("at least 3 positive" in finding for finding in findings)
    assert any("at least 2 negative" in finding for finding in findings)


def test_selected_skill_behavior_requires_readable_nonempty_skill_markdown(tmp_path: Path):
    """Check the deterministic behavioral handoff for a selected skill.

    Args:
        tmp_path: Pytest-owned fixture directory.

    Require: The behavior helper accepts a result record with a path.
    Guarantee: Readable non-empty SKILL.md passes; empty, absent, or wrong targets fail.
    Maintain: Only fixture files are written.
    Assert: The check is content-independent apart from non-emptiness.
    """
    skill_file = tmp_path / "sample" / "SKILL.md"
    skill_file.parent.mkdir()
    skill_file.write_text("---\nname: sample\ndescription: Sample skill.\n---\nDo the task.\n", encoding="utf-8")

    assert CANARIES.validate_selected_skill_behavior({"name": "sample", "path": str(skill_file)}) is None
    skill_file.write_text("", encoding="utf-8")
    assert "is empty" in CANARIES.validate_selected_skill_behavior({"name": "sample", "path": str(skill_file)})
    assert "not a SKILL.md" in CANARIES.validate_selected_skill_behavior({"name": "sample", "path": str(tmp_path)})
