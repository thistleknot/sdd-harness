"""Tests for source_write_guard.py -- each case is a real command shape from the 2026-09-26 failure."""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(__file__), "source_write_guard.py")


def run(event):
    out = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, timeout=30)
    return json.loads(out.stdout) if out.stdout.strip() else None


def bash(cmd):
    return run({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}})


def denied(res):
    return bool(res) and res["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_heredoc_into_py_is_denied():
    assert denied(bash("cat > .tmp/jev_parity.py <<'EOF'\nprint('a\\nb')\nEOF"))


def test_inline_python_writing_py_is_denied():
    cmd = "python - <<'PYEOF'\ns=open('src/reward.py').read()\nopen('src/reward.py','w').write(s)\nPYEOF"
    assert denied(bash(cmd))


def test_sed_in_place_on_py_is_denied():
    assert denied(bash("sed -i 's#a#b#' .tmp/jev_parity.py"))


def test_running_python_and_non_py_writes_pass():
    assert bash("PYTHONIOENCODING=utf-8 python .tmp/jev_parity.py 2>&1 | tail -3") is None
    assert bash("python -c \"import json;print(json.load(open('m.json')))\"") is None
    assert bash("cat >> dispositions.md <<'EOF'\ntext\nEOF") is None
    assert bash("printf 'row\\n' >> .tmp/processes.md") is None


def test_post_edit_blocks_uncompilable_py():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write('x = (f"Context:\n{1}")\n')  # the exact defect: a real newline inside an f-string
    res = run({"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": f.name}})
    os.unlink(f.name)
    assert res and res["decision"] == "block"


def test_post_edit_passes_good_py():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write('x = f"Context:\\n{1}"\n')
    res = run({"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": f.name}})
    os.unlink(f.name)
    assert res is None
