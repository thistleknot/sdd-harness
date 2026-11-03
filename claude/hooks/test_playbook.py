#!/usr/bin/env python3
"""Battery for `playbook.py`: the hook names party roles, never models.

Spec: C:/Users/user/.claude/plans/make-harness-render-and-install-the-party.md, section 6
      (operator rule: never raise to Opus; model policy lives only in ~/.harness/tiers.toml).
Task: plan layer 4.

Run from ~/.harness/claude/hooks: python -m pytest test_playbook.py -q
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import playbook as pb  # noqa: E402

MODEL_NAME = re.compile(r"\b(fable|opus|sonnet|haiku|gpt-\d|gemini|qwen)\b", re.I)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def emitted(capsys) -> str:
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def test_the_hook_source_and_the_rules_file_never_name_a_model():
    for path in (os.path.join(HERE, "playbook.py"), os.path.join(HERE, "..", "rules", "playbook.md")):
        found = MODEL_NAME.findall(read(path))
        assert not found, f"{os.path.basename(path)} names models {sorted(set(found))}; roles only"


def test_an_architect_request_tells_the_session_to_dispatch_the_oracle_and_run_the_party(tmp_path, capsys):
    assert pb._architect_request({"prompt": "architect the migration", "cwd": str(tmp_path)}) == 0
    text = emitted(capsys)
    assert "Dispatch ONE subagent of type `oracle`" in text
    assert "a `doer` agent implements it" in text and "the Leader (this session) writes the subplan" in text
    assert "doer ->" in text and "the Leader (one clarification)" in text
    assert "max 4" in text and "tiers.toml" in text
    assert not MODEL_NAME.search(text)


def test_an_unrelated_prompt_emits_nothing(tmp_path, capsys):
    assert pb._architect_request({"prompt": "what time is it", "cwd": str(tmp_path)}) == 0
    assert capsys.readouterr().out == ""


def test_a_blocked_task_escalates_doer_then_leader_then_oracle(tmp_path, capsys):
    ledger = tmp_path / "playbook.md"
    ledger.write_text("# Playbook: x\n\n## Layer 1 - parallel\n- [BLOCKED] T1 first\n  _Files:_ a.py\n"
                      "- [OPEN] T2 second\n  _Files:_ b.py\n", encoding="utf-8")
    assert pb._status({"cwd": str(tmp_path), "hook_event_name": "UserPromptSubmit"}) == 0
    text = emitted(capsys)
    assert "BLOCKED -- it holds the barrier; escalate one step (doer -> Leader -> oracle)" in text
    assert not MODEL_NAME.search(text)
