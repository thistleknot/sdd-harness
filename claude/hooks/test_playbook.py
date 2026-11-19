#!/usr/bin/env python3
"""Battery for `playbook.py`: the hook names party roles, never models; feature intake.

Spec: C:/Users/user/.claude/plans/make-harness-render-and-install-the-party.md, section 6
      (operator rule: never raise to Opus; model policy lives only in ~/.harness/tiers.toml).
      Feature intake: NO GOVERNING SPEC. Basis: leader instruction 2026-10-13.
Task: plan layer 4.

Run: python -m pytest test_playbook.py -q
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import playbook as pb  # noqa: E402

HOOK = os.path.join(HERE, "playbook.py")
MODEL_NAME = re.compile(r"\b(fable|opus|sonnet|haiku|gpt-\d|gemini|qwen)\b", re.I)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def emitted(capsys) -> str:
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def run_hook(payload: dict) -> str:
    """Run the hook as `--plan` with the payload on stdin; return additionalContext or ''."""
    p = subprocess.run([sys.executable, HOOK, "--plan"], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0
    if not p.stdout.strip():
        return ""
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(r)], check=True, capture_output=True)
    return r.resolve()


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


@pytest.mark.parametrize("prompt", ["feature: add dark mode", "/feature add export", "  FEATURE: x"])
def test_a_feature_prompt_injects_the_board_instruction(repo, prompt):
    text = run_hook({"prompt": prompt, "cwd": str(repo)})
    assert repo.as_posix().lower() in text.lower()
    assert "create_feature" in text and "STOP" in text
    assert len(text) < 2200
    assert not MODEL_NAME.search(text)


@pytest.mark.parametrize("prompt", [
    "how do I add a feature to this", "feature request: x", "please feature: x", "featured: x"])
def test_a_non_feature_prompt_emits_nothing(repo, prompt):
    assert run_hook({"prompt": prompt, "cwd": str(repo)}) == ""


def test_a_subagent_feature_prompt_emits_nothing(repo):
    assert run_hook({"prompt": "feature: x", "cwd": str(repo), "agent_id": "a1"}) == ""


def test_a_feature_prompt_inside_a_worktree_emits_nothing(repo):
    wt = repo / ".worktrees" / "story-x"
    wt.mkdir(parents=True)
    assert run_hook({"prompt": "feature: x", "cwd": str(wt)}) == ""


def test_a_feature_prompt_outside_a_git_repo_emits_nothing(tmp_path):
    outside = tmp_path / "plain"
    outside.mkdir()
    if pb._project_root(str(outside)) is not None:
        pytest.skip("tmp dir sits inside a git repo on this machine")
    assert run_hook({"prompt": "feature: x", "cwd": str(outside)}) == ""


def run_feature_flag(payload: dict) -> str:
    p = subprocess.run([sys.executable, HOOK, "--feature"], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0
    if not p.stdout.strip():
        return ""
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


def test_feature_flag_emits_neutral_board_instruction(repo):
    text = run_feature_flag({"prompt": "feature: add dark mode", "cwd": str(repo)})
    assert "create_feature" in text and "STOP" in text
    assert "mcp__" not in text and len(text) < 2200


def test_feature_flag_ignores_architect_prompt(repo):
    assert run_feature_flag({"prompt": "architect this", "cwd": str(repo)}) == ""


def test_an_architect_prompt_still_reaches_the_architect_request(tmp_path):
    text = run_hook({"prompt": "architect this", "cwd": str(tmp_path)})
    assert "ARCHITECT REQUEST DETECTED" in text
