"""Battery for hooks/vscode_shim.py -- tool-name translation, matcher re-application,
verdict folding, and an end-to-end run through a real subprocess.

Spec: no governing requirement. Task: specs store #63.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "hooks"))
import vscode_shim as shim  # noqa: E402

SHIM = Path(__file__).parent / "hooks" / "vscode_shim.py"


def test_translate_replace_string_maps_to_edit_with_file_path():
    out = shim.translate({
        "tool_name": "replace_string_in_file",
        "tool_input": {"filePath": "C:/r/a.py", "oldString": "x", "newString": "y"},
    })
    assert out["tool_name"] == "Edit"
    assert out["tool_input"]["file_path"] == "C:/r/a.py"
    assert out["tool_input"]["old_string"] == "x"
    assert out["tool_input"]["new_string"] == "y"


def test_translate_apply_patch_takes_path_from_patch_header():
    patch = "*** Begin Patch\n*** Update File: src/net.py\n@@\n-a\n+b\n*** End Patch"
    out = shim.translate({"tool_name": "apply_patch", "tool_input": {"input": patch}})
    assert out["tool_name"] == "Edit"
    assert out["tool_input"]["file_path"] == "src/net.py"


def test_translate_terminal_is_bash_and_unknown_tool_passes_through():
    term = shim.translate({"tool_name": "run_in_terminal", "tool_input": {"command": "ls"}})
    assert term["tool_name"] == "Bash"
    assert term["tool_input"]["command"] == "ls"
    other = shim.translate({"tool_name": "semantic_search", "tool_input": {"query": "q"}})
    assert other["tool_name"] == "semantic_search"
    assert "file_path" not in other["tool_input"]


def test_translate_multi_replace_uses_first_replacement_path():
    out = shim.translate({
        "tool_name": "multi_replace_string_in_file",
        "tool_input": {"replacements": [{"filePath": "a.py"}, {"filePath": "b.py"}]},
    })
    assert out["tool_input"]["file_path"] == "a.py"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hooks": {"PreToolUse": [
        {"hooks": [{"command": "python log.py"}]},
        {"matcher": "^(Edit|Write)$", "hooks": [{"command": "python gate.py"}]},
        {"matcher": "^Bash$", "hooks": [{"command": "python shell_guard.py"}]},
    ], "Stop": [
        {"hooks": [{"command": "python verify_gate.py"}, {"command": "python audit.py"}]},
    ]}}), encoding="utf-8")
    monkeypatch.setattr(shim, "SETTINGS", path)
    return path


def test_commands_for_reapplies_matcher_vscode_ignores(settings):
    edit = [h["command"] for h in shim.commands_for("PreToolUse", "replace_string_in_file", "Edit")]
    assert edit == ["python log.py", "python gate.py"]
    bash = [h["command"] for h in shim.commands_for("PreToolUse", "run_in_terminal", "Bash")]
    assert bash == ["python log.py", "python shell_guard.py"]
    read = [h["command"] for h in shim.commands_for("PreToolUse", "read_file", "Read")]
    assert read == ["python log.py"]


def test_commands_for_drops_transcript_dependent_hooks(settings):
    stop = [h["command"] for h in shim.commands_for("Stop", None, None)]
    assert stop == ["python audit.py"]


def test_fold_deny_becomes_permission_decision():
    deny = json.dumps({"hookSpecificOutput": {"permissionDecision": "deny",
                                              "permissionDecisionReason": "SPEC GATE: no"}})
    out, code, err = shim.fold("PreToolUse", [(0, "", ""), (0, deny, "")])
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "SPEC GATE" in out["hookSpecificOutput"]["permissionDecisionReason"]
    assert code == 0 and err == ""


def test_fold_exit_two_blocks_and_legacy_stop_block_exits_two():
    _, code, err = shim.fold("Stop", [(2, "", "unclaimed files")])
    assert code == 2 and "unclaimed files" in err
    legacy = json.dumps({"decision": "block", "reason": "no verdict"})
    _, code, err = shim.fold("Stop", [(0, legacy, "")])
    assert code == 2 and "no verdict" in err


def test_fold_plain_stdout_becomes_additional_context():
    out, code, _ = shim.fold("UserPromptSubmit", [(0, "memory: recalled thing", "")])
    assert out["hookSpecificOutput"]["additionalContext"] == "memory: recalled thing"
    assert code == 0


def _run_shim(tmp_path, event, payload):
    """Run the shim as VS Code would, with HOME pointed at a tmp settings tree."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    gate = tmp_path / "gate.py"
    gate.write_text(
        "import json,sys\n"
        "p=json.load(sys.stdin)\n"
        "if p['tool_name']=='Edit' and p['tool_input'].get('file_path','').endswith('.py'):\n"
        "    print(json.dumps({'hookSpecificOutput':{'permissionDecision':'deny',"
        "'permissionDecisionReason':'gate saw '+p['tool_input']['file_path']}}))\n",
        encoding="utf-8",
    )
    (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "^(Edit|Write)$", "hooks": [{"command": f'"{sys.executable}" "{gate}"'}]},
    ]}}), encoding="utf-8")
    env = {"USERPROFILE": str(home), "HOME": str(home), "SYSTEMROOT": "C:/Windows", "PATH": ""}
    return subprocess.run([sys.executable, str(SHIM), event], input=json.dumps(payload),
                          text=True, capture_output=True, env=env, cwd=tmp_path)


def test_end_to_end_denies_vscode_edit_of_python_file(tmp_path):
    done = _run_shim(tmp_path, "PreToolUse", {
        "tool_name": "replace_string_in_file", "cwd": str(tmp_path),
        "tool_input": {"filePath": "C:/r/mod.py", "oldString": "a", "newString": "b"}})
    out = json.loads(done.stdout)
    assert done.returncode == 0
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "gate saw C:/r/mod.py" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_end_to_end_allows_non_matching_tool_and_non_python_edit(tmp_path):
    read = _run_shim(tmp_path, "PreToolUse", {
        "tool_name": "read_file", "cwd": str(tmp_path), "tool_input": {"filePath": "C:/r/mod.py"}})
    assert read.returncode == 0 and read.stdout.strip() == ""
    note = _run_shim(tmp_path, "PreToolUse", {
        "tool_name": "create_file", "cwd": str(tmp_path),
        "tool_input": {"filePath": "C:/r/notes.md", "content": "x"}})
    assert note.returncode == 0 and note.stdout.strip() == ""


def test_audit_row_records_raw_and_mapped_tool(tmp_path, monkeypatch):
    log = tmp_path / "audit.jsonl"
    monkeypatch.setattr(shim, "AUDIT", log)
    payload = {"tool_name": "create_file", "tool_input": {"filePath": "a.md"}, "cwd": "x"}
    shim.audit("PreToolUse", payload, shim.translate(payload))
    row = json.loads(log.read_text().splitlines()[0])
    assert row["raw_tool"] == "create_file" and row["mapped_tool"] == "Write"
    assert row["input_keys"] == ["filePath"]
