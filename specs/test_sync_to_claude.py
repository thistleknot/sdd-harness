"""Tests for sync-to-claude.ps1.

The script exposes -HarnessRoot / -ClaudeRoot, so tests point it at a sandbox
tree and invoke it directly -- no source rewriting required.

Layout the script expects:
    <HarnessRoot>/claude/...   vault
    <ClaudeRoot>/...           live tree
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "sync-to-claude.ps1"

pytestmark = pytest.mark.skipif(
    shutil.which("powershell") is None and shutil.which("pwsh") is None,
    reason="PowerShell not available",
)


def _shell() -> str:
    return shutil.which("pwsh") or shutil.which("powershell")


def run_sync(tmp_path: Path, *args: str):
    return subprocess.run(
        [
            _shell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-HarnessRoot", str(tmp_path / "harness"),
            "-ClaudeRoot", str(tmp_path / "live"),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )


def write(path: Path, text: str, *, age: float = 0.0) -> Path:
    """Write text; optionally backdate mtime by `age` seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if age:
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def tree(tmp_path: Path):
    """Vault + live tree: one changed file, one identical, one vault-only, one live-only."""
    vault = tmp_path / "harness" / "claude"
    live = tmp_path / "live"

    # live is backdated so this fixture models an ordinary push. Left current, it
    # would be newer *and* smaller than the vault copy -- the reduction signature
    # -- and the guard would (correctly) hold it back.
    write(vault / "CLAUDE.md", "VAULT VERSION\n")
    write(live / "CLAUDE.md", "LIVE VERSION\n", age=86400)

    write(vault / "SOUL.md", "IDENTICAL\n")
    write(live / "SOUL.md", "IDENTICAL\n")

    write(vault / "agents" / "planner.md", "new agent\n")

    write(vault / "settings.json", '{"from":"vault"}\n')
    write(live / "settings.json", '{"from":"live","merged":true}\n')

    write(live / "agents" / "handwritten.md", "do not delete me\n")
    return tmp_path


# --- default is safe ---------------------------------------------------------

def test_no_flags_defaults_to_dry_run(tree):
    live = tree / "live"
    r = run_sync(tree)

    assert r.returncode == 0, r.stderr
    assert live.joinpath("CLAUDE.md").read_text(encoding="utf-8") == "LIVE VERSION\n"
    assert not live.joinpath("agents", "planner.md").exists()
    assert "re-run with -Push or -Pull to apply" in r.stdout


def test_dry_run_reports_pending_changes(tree):
    r = run_sync(tree, "-DryRun")
    assert "create -> agents\\planner.md" in r.stdout


# --- push (vault -> live) ----------------------------------------------------

def test_push_overwrites_live_with_vault(tree):
    run_sync(tree, "-Push")
    assert (tree / "live" / "CLAUDE.md").read_text(encoding="utf-8") == "VAULT VERSION\n"


def test_push_creates_new_file_in_subdirectory(tree):
    run_sync(tree, "-Push")
    assert (tree / "live" / "agents" / "planner.md").read_text(encoding="utf-8") == "new agent\n"


def test_push_keeps_no_backup_copies(tree):
    """Backups were removed by design -- git history is the safety net."""
    run_sync(tree, "-Push")
    assert not (tree / "live" / "backups").exists()
    assert "no backup copies are kept by design" in run_sync(tree, "-Push").stdout


# --- pull (live -> vault) ----------------------------------------------------

def test_pull_copies_live_into_vault(tree):
    run_sync(tree, "-Pull")
    assert (tree / "harness" / "claude" / "CLAUDE.md").read_text(encoding="utf-8") == "LIVE VERSION\n"


def test_pull_leaves_live_untouched(tree):
    run_sync(tree, "-Pull")
    assert (tree / "live" / "CLAUDE.md").read_text(encoding="utf-8") == "LIVE VERSION\n"


def test_pull_captures_live_only_file(tree):
    run_sync(tree, "-Pull")
    assert (tree / "harness" / "claude" / "agents" / "handwritten.md").exists()


# --- build artifacts are not vault material ----------------------------------

def test_pull_skips_pycache_directory(tree):
    """Observed 2026-08-24: a pull wanted to vault 8 compiled files alongside one
    hand-edited doc. Bytecode is regenerated, never authored -- it must not enter
    the vault, where it would then be pushed back out forever."""
    write(tree / "live" / "hooks" / "__pycache__" / "log_event.cpython-310.pyc", "BYTECODE\n")
    run_sync(tree, "-Pull")
    assert not (tree / "harness" / "claude" / "hooks" / "__pycache__").exists()


def test_pull_skips_loose_bytecode_by_extension(tree):
    """A .pyc/.pyo outside a __pycache__ dir is still an artifact."""
    write(tree / "live" / "hooks" / "stale.pyc", "BYTECODE\n")
    write(tree / "live" / "hooks" / "stale.pyo", "BYTECODE\n")
    run_sync(tree, "-Pull")
    vault_hooks = tree / "harness" / "claude" / "hooks"
    assert not (vault_hooks / "stale.pyc").exists()
    assert not (vault_hooks / "stale.pyo").exists()


def test_pull_still_captures_python_source(tree):
    """The filter must catch bytecode only -- real .py hooks are vault material."""
    write(tree / "live" / "hooks" / "log_event.py", "print('hook')\n")
    write(tree / "live" / "hooks" / "__pycache__" / "log_event.cpython-310.pyc", "BYTECODE\n")
    run_sync(tree, "-Pull")
    src = tree / "harness" / "claude" / "hooks" / "log_event.py"
    assert src.read_text(encoding="utf-8") == "print('hook')\n"


def test_push_skips_pycache_directory(tree):
    """Same filter, other direction: a vault that somehow holds bytecode does not
    spray it back into the live tree."""
    write(tree / "harness" / "claude" / "hooks" / "__pycache__" / "old.cpython-310.pyc", "BYTECODE\n")
    run_sync(tree, "-Push")
    assert not (tree / "live" / "hooks" / "__pycache__").exists()


# --- reduction guard ---------------------------------------------------------

def test_push_holds_back_a_reduction(tmp_path: Path):
    """Live newer AND smaller = a slop cut. Pushing would re-inflate it."""
    write(tmp_path / "harness" / "claude" / "CLAUDE.md", "x" * 5000, age=86400)
    write(tmp_path / "live" / "CLAUDE.md", "x" * 1000)

    r = run_sync(tmp_path, "-Push")

    assert "HOLD" in r.stdout
    assert "held: 1" in r.stdout
    assert (tmp_path / "live" / "CLAUDE.md").read_text(encoding="utf-8") == "x" * 1000


def test_guard_allows_growth_when_live_is_older(tmp_path: Path):
    """Vault newer -> normal update, no hold."""
    write(tmp_path / "live" / "CLAUDE.md", "old small\n", age=86400)
    write(tmp_path / "harness" / "claude" / "CLAUDE.md", "new bigger content\n")

    r = run_sync(tmp_path, "-Push")

    assert "HOLD" not in r.stdout
    assert (tmp_path / "live" / "CLAUDE.md").read_text(encoding="utf-8") == "new bigger content\n"


def test_guard_allows_newer_live_that_grew(tmp_path: Path):
    """Newer but LARGER live file is not a reduction, so it is not protected."""
    write(tmp_path / "harness" / "claude" / "CLAUDE.md", "small\n", age=86400)
    write(tmp_path / "live" / "CLAUDE.md", "much larger live content here\n")

    r = run_sync(tmp_path, "-Push")

    assert "HOLD" not in r.stdout
    assert (tmp_path / "live" / "CLAUDE.md").read_text(encoding="utf-8") == "small\n"


def test_guard_does_not_protect_unlisted_files(tmp_path: Path):
    """Only CLAUDE.md/AGENTS.md/SOUL.md carry reductions; agents/ files do not."""
    write(tmp_path / "harness" / "claude" / "agents" / "a.md", "x" * 5000, age=86400)
    write(tmp_path / "live" / "agents" / "a.md", "x" * 10)

    r = run_sync(tmp_path, "-Push")

    assert "HOLD" not in r.stdout
    assert (tmp_path / "live" / "agents" / "a.md").read_text(encoding="utf-8") == "x" * 5000


# --- hash skip ---------------------------------------------------------------

def test_identical_file_is_skipped(tree):
    r = run_sync(tree, "-Push")
    assert "unchanged: 1" in r.stdout


def test_second_push_is_a_noop(tree):
    run_sync(tree, "-Push")
    assert "changed: 0" in run_sync(tree, "-Push").stdout


# --- never delete ------------------------------------------------------------

def test_push_never_deletes_live_only_file(tree):
    run_sync(tree, "-Push")
    assert (tree / "live" / "agents" / "handwritten.md").read_text(encoding="utf-8") == "do not delete me\n"


def test_empty_vault_deletes_nothing(tmp_path: Path):
    (tmp_path / "harness" / "claude").mkdir(parents=True)
    write(tmp_path / "live" / "CLAUDE.md", "precious\n")

    r = run_sync(tmp_path, "-Push")

    assert r.returncode == 0, r.stderr
    assert (tmp_path / "live" / "CLAUDE.md").read_text(encoding="utf-8") == "precious\n"


# --- settings.json is never flat-copied --------------------------------------

def test_settings_json_never_copied_on_push(tree):
    r = run_sync(tree, "-Push")
    assert (tree / "live" / "settings.json").read_text(encoding="utf-8") == '{"from":"live","merged":true}\n'
    assert "merge target" in r.stdout


def test_settings_json_never_copied_on_pull(tree):
    run_sync(tree, "-Pull")
    assert (tree / "harness" / "claude" / "settings.json").read_text(encoding="utf-8") == '{"from":"vault"}\n'


# --- install delegation ------------------------------------------------------

def test_install_dry_run_delegates_to_setup(tree):
    r = run_sync(tree, "-Install", "-DryRun")
    assert "plugin/install.py --target claude" in r.stdout
    assert "single convergence command" in r.stdout


# --- guard rails -------------------------------------------------------------

def test_push_and_pull_are_mutually_exclusive(tree):
    r = run_sync(tree, "-Push", "-Pull")
    assert r.returncode == 1
    assert "mutually exclusive" in r.stdout


def test_missing_vault_exits_nonzero(tmp_path: Path):
    (tmp_path / "live").mkdir(parents=True)
    (tmp_path / "harness").mkdir(parents=True)
    r = run_sync(tmp_path)
    assert r.returncode == 1
    assert "vault not found" in r.stdout


def test_missing_live_tree_exits_nonzero(tmp_path: Path):
    (tmp_path / "harness" / "claude").mkdir(parents=True)
    r = run_sync(tmp_path)
    assert r.returncode == 1
    assert "live tree not found" in r.stdout
