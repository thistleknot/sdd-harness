"""Tests for start_router_cpu.py — retrieve-skills server discovery.

The script is a top-level entrypoint: at import time it chdir()s into the
server directory and exec()s server.py. It therefore cannot be imported for
unit testing without launching a real server, so these run it as a subprocess
with a redirected USERPROFILE and a stub server.py that reports its cwd.

The ordering assertions matter: two divergent retrieve-skills installs exist
(~/.claude/skills/retrieve-skills and ~/.skills/retrieve-skills) with separate
index.db files. This entrypoint must load the .claude copy.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "start_router_cpu.py"

# Stub stands in for the real server; it reports which directory got loaded.
STUB = 'import os\nprint("CWD:" + os.getcwd())\n'


def _install_stub(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "server.py").write_text(STUB, encoding="utf-8")
    return root


def _run(home: Path, **overrides) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["USERPROFILE"] = str(home)
    env["HOME"] = str(home)
    env.pop("RETRIEVE_SKILLS_SRC", None)
    env.pop("SKILL_STORE", None)
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = str(v)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=60, env=env,
    )


def _loaded_dir(proc: subprocess.CompletedProcess) -> str:
    for line in proc.stdout.splitlines():
        if line.startswith("CWD:"):
            return os.path.normcase(line[4:].strip())
    raise AssertionError(f"stub never ran.\nstdout={proc.stdout}\nstderr={proc.stderr}")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def test_claude_copy_wins_over_skills_store(home):
    """Regression: both installs exist, .claude must be chosen."""
    claude = _install_stub(home / ".claude" / "skills" / "retrieve-skills")
    _install_stub(home / ".skills" / "retrieve-skills")

    proc = _run(home)

    assert proc.returncode == 0, proc.stderr
    assert _loaded_dir(proc) == os.path.normcase(str(claude))


def test_falls_back_to_skills_store_when_claude_copy_absent(home):
    store = _install_stub(home / ".skills" / "retrieve-skills")

    proc = _run(home)

    assert proc.returncode == 0, proc.stderr
    assert _loaded_dir(proc) == os.path.normcase(str(store))


def test_explicit_src_env_overrides_both_installs(home, tmp_path):
    _install_stub(home / ".claude" / "skills" / "retrieve-skills")
    _install_stub(home / ".skills" / "retrieve-skills")
    explicit = _install_stub(tmp_path / "explicit")

    proc = _run(home, RETRIEVE_SKILLS_SRC=explicit)

    assert proc.returncode == 0, proc.stderr
    assert _loaded_dir(proc) == os.path.normcase(str(explicit))


def test_skill_store_env_relocates_the_store_candidate(home, tmp_path):
    # SKILL_STORE/retrieve-skills is the probed path.
    store = _install_stub(tmp_path / "store" / "retrieve-skills")

    proc = _run(home, SKILL_STORE=tmp_path / "store")

    assert proc.returncode == 0, proc.stderr
    assert _loaded_dir(proc) == os.path.normcase(str(store))


def test_exits_nonzero_when_no_install_is_found(home):
    proc = _run(home)

    assert proc.returncode != 0
    assert "not found" in proc.stderr.lower()


def test_failure_message_lists_the_paths_searched(home):
    proc = _run(home)

    assert ".claude" in proc.stderr
    assert ".skills" in proc.stderr
    assert "RETRIEVE_SKILLS_SRC" in proc.stderr


def test_directory_without_server_py_is_not_selected(home):
    # .claude dir exists but is empty -> must skip to the store copy.
    (home / ".claude" / "skills" / "retrieve-skills").mkdir(parents=True)
    store = _install_stub(home / ".skills" / "retrieve-skills")

    proc = _run(home)

    assert proc.returncode == 0, proc.stderr
    assert _loaded_dir(proc) == os.path.normcase(str(store))
