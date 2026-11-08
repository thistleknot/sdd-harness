"""adapter.ensure_global_hooks — append-only merge of global hooks into a Claude hooks file.

Spec: none found. Basis: operator bug report 2026-11-07 (adapter.py --target claude crashed
with AttributeError: 'str' object has no attribute 'get' on the vault settings file, whose
events are single group objects rather than lists).

Preconditions: pytest is installed; tmp_path is writable.
Failure modes: a dict-valued event is iterated by key (crash); a rerun appends duplicates.
"""
from __future__ import annotations

import json
from pathlib import Path

import adapter

HOOK_A = {"event": "Stop", "command": "python a.py", "timeout": 5}
HOOK_B = {"event": "PreToolUse", "matcher": "Bash", "command": "python b.py"}


def _run(monkeypatch, tmp_path, path: Path, hooks: list[dict]) -> bool:
    """Call ensure_global_hooks with backups redirected into tmp_path.

    Require: path is inside tmp_path.
    Guarantee: only `path` and tmp_path backups are written.
    Maintain: BACKUP_RUN is restored by monkeypatch after the test.
    Assert: none.
    """
    monkeypatch.setattr(adapter, "BACKUP_RUN", tmp_path / "backups")
    return adapter.ensure_global_hooks(path, hooks)


def test_single_group_dict_event_is_normalized_and_hook_appended(monkeypatch, tmp_path):
    """A single-object event (the vault shape that crashed) becomes a list with the new group appended.

    Require: settings file has Stop as a bare group dict.
    Guarantee: Stop ends as [original_group, new_group]; the original group is kept verbatim.
    Maintain: other events are untouched.
    Assert: exact list length and commands.
    """
    path = tmp_path / "settings.json"
    original = {"hooks": [{"type": "command", "command": "python keep.py"}]}
    path.write_text(json.dumps({"hooks": {"Stop": {"hooks": original["hooks"]}, "Other": []}}), encoding="utf-8")

    assert _run(monkeypatch, tmp_path, path, [HOOK_A]) is True

    data = json.loads(path.read_text(encoding="utf-8"))
    stop = data["hooks"]["Stop"]
    assert isinstance(stop, list) and len(stop) == 2
    assert stop[0] == {"hooks": original["hooks"]}
    assert stop[1] == {"hooks": [{"type": "command", "command": "python a.py", "timeout": 5}]}
    assert data["hooks"]["Other"] == []


def test_rerun_is_a_noop_for_an_already_present_hook(monkeypatch, tmp_path):
    """A second run with the same hook adds no group.

    Require: the hook was installed by a first run.
    Guarantee: the group count for the event stays at 1 and the file is rewritten with the same content.
    Maintain: identity of (event, matcher, command) is the dedupe key.
    Assert: exact group count after two runs.
    """
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")

    _run(monkeypatch, tmp_path, path, [HOOK_A, HOOK_B])
    _run(monkeypatch, tmp_path, path, [HOOK_A, HOOK_B])

    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["hooks"]["Stop"]) == 1
    assert len(data["hooks"]["PreToolUse"]) == 1
    assert data["hooks"]["PreToolUse"][0] == {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "python b.py"}],
    }


def test_matcher_difference_adds_a_new_group(monkeypatch, tmp_path):
    """Same command under a different matcher is a distinct hook and gets its own group.

    Require: an existing PreToolUse group with matcher Bash and command python b.py.
    Guarantee: adding the same command with matcher Grep appends a second group.
    Maintain: the Bash group is untouched.
    Assert: two groups with distinct matchers.
    """
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    _run(monkeypatch, tmp_path, path, [HOOK_B])

    grep_variant = {"event": "PreToolUse", "matcher": "Grep", "command": "python b.py"}
    _run(monkeypatch, tmp_path, path, [grep_variant])

    groups = json.loads(path.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert [g["matcher"] for g in groups] == ["Bash", "Grep"]
