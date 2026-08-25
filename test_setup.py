"""Unit tests for setup.py — installer helpers.

Covers MCP entry projection per harness, skill-store seeding, and the
discovery functions (interpreter, retrieve-skills server, harnesses).

All tests monkeypatch module globals (SKILL_STORE, HARNESS_ROOT, HARNESSES)
onto tmp_path so nothing touches the real ~/.skills, ~/.claude, or the
harness manifest.toml.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import setup as harness_setup
from setup import (
    build_mcp_entry,
    copy_core_skills,
    detect_harnesses,
    find_python,
    find_retrieve_skills_server,
)

PYTHON = "C:/fake/python.exe"


@pytest.fixture
def fake_python():
    """Pin the interpreter so entry construction is deterministic."""
    with patch("setup.find_python", return_value=PYTHON):
        yield PYTHON


@pytest.fixture
def skill_store(tmp_path, monkeypatch):
    store = tmp_path / "skills-store"
    monkeypatch.setattr(harness_setup, "SKILL_STORE", store)
    return store


def _make_source(root: Path, names) -> Path:
    """Build a source skill store containing `names`, each with a SKILL.md."""
    src = root / "source"
    for n in names:
        d = src / n
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {n}\n", encoding="utf-8")
    return src


# ─── build_mcp_entry: HTTP servers ───────────────────────────────────────────


def test_retrieve_skills_claude_is_bare_http_url(fake_python):
    assert build_mcp_entry("retrieve-skills", Path("/srv"), "claude") == {
        "url": "http://127.0.0.1:8765/mcp"
    }


def test_retrieve_skills_kiro_adds_disabled_false(fake_python):
    assert build_mcp_entry("retrieve-skills", Path("/srv"), "kiro") == {
        "url": "http://127.0.0.1:8765/mcp",
        "disabled": False,
    }


def test_retrieve_skills_opencode_uses_streamable_http(fake_python):
    assert build_mcp_entry("retrieve-skills", Path("/srv"), "opencode") == {
        "type": "streamable-http",
        "url": "http://127.0.0.1:8765/mcp",
        "enabled": True,
    }


def test_memory_index_uses_port_8055_not_8765(fake_python):
    assert build_mcp_entry("memory-index", Path("/srv"), "claude") == {
        "url": "http://127.0.0.1:8055/mcp"
    }
    assert build_mcp_entry("memory-index", Path("/srv"), "opencode") == {
        "type": "streamable-http",
        "url": "http://127.0.0.1:8055/mcp",
        "enabled": True,
    }


# ─── build_mcp_entry: stdio server ───────────────────────────────────────────


def test_todo_claude_is_stdio_with_args_list(fake_python, tmp_path):
    script = str(tmp_path / "todo_mcp.py")
    assert build_mcp_entry("todo", tmp_path, "claude") == {
        "type": "stdio",
        "command": PYTHON,
        "args": [script],
    }


def test_todo_opencode_folds_command_and_script_into_one_list(fake_python, tmp_path):
    script = str(tmp_path / "todo_mcp.py")
    assert build_mcp_entry("todo", tmp_path, "opencode") == {
        "type": "local",
        "command": [PYTHON, script],
        "enabled": True,
    }


def test_todo_kiro_omits_type_and_uses_disabled(fake_python, tmp_path):
    script = str(tmp_path / "todo_mcp.py")
    assert build_mcp_entry("todo", tmp_path, "kiro") == {
        "command": PYTHON,
        "args": [script],
        "disabled": False,
    }


def test_unknown_server_name_returns_empty_dict(fake_python, tmp_path):
    assert build_mcp_entry("no-such-server", tmp_path, "claude") == {}


# ─── copy_core_skills ────────────────────────────────────────────────────────


def test_installs_core_skill_from_explicit_source(tmp_path, skill_store):
    name = harness_setup.CORE_SKILLS[0]
    src = _make_source(tmp_path, [name])

    assert copy_core_skills(src) == 1
    assert (skill_store / name / "SKILL.md").read_text(encoding="utf-8") == f"# {name}\n"


def test_writes_store_readme_describing_reindex_endpoint(tmp_path, skill_store):
    src = _make_source(tmp_path, [harness_setup.CORE_SKILLS[0]])
    copy_core_skills(src)

    readme = (skill_store / "README.md").read_text(encoding="utf-8")
    assert "Shared Skill Store" in readme
    assert "http://127.0.0.1:8765/reindex" in readme


def test_does_not_overwrite_a_customized_skill(tmp_path, skill_store):
    name = harness_setup.CORE_SKILLS[0]
    src = _make_source(tmp_path, [name])
    existing = skill_store / name
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("CUSTOM", encoding="utf-8")

    # Still counted as installed, but content is preserved.
    assert copy_core_skills(src) == 1
    assert (existing / "SKILL.md").read_text(encoding="utf-8") == "CUSTOM"


def test_ignores_source_dirs_that_are_not_core_skills(tmp_path, skill_store):
    src = _make_source(tmp_path, [harness_setup.CORE_SKILLS[0], "not-a-core-skill"])
    copy_core_skills(src)

    assert not (skill_store / "not-a-core-skill").exists()


def test_returns_zero_when_no_source_store_is_discoverable(
    tmp_path, skill_store, monkeypatch
):
    empty_home = tmp_path / "home"
    empty_home.mkdir()
    monkeypatch.setattr(harness_setup.Path, "home", staticmethod(lambda: empty_home))
    monkeypatch.setattr(harness_setup, "HARNESS_ROOT", tmp_path / "no-harness")

    assert copy_core_skills(tmp_path / "missing") == 0


# ─── find_retrieve_skills_server ─────────────────────────────────────────────


def test_finds_server_under_harness_root(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_setup, "HARNESS_ROOT", tmp_path)
    d = tmp_path / "retrieve-skills"
    d.mkdir()
    (d / "server.py").write_text("", encoding="utf-8")

    assert find_retrieve_skills_server() == d


def test_directory_without_server_py_is_not_a_match(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_setup, "HARNESS_ROOT", tmp_path)
    monkeypatch.setattr(harness_setup, "SKILL_STORE", tmp_path / "store")
    empty_home = tmp_path / "home"
    empty_home.mkdir()
    monkeypatch.setattr(harness_setup.Path, "home", staticmethod(lambda: empty_home))
    (tmp_path / "retrieve-skills").mkdir()  # exists, but has no server.py

    assert find_retrieve_skills_server() is None


# ─── detect_harnesses ────────────────────────────────────────────────────────


def test_detect_returns_only_harnesses_present_on_disk(tmp_path, monkeypatch):
    present = tmp_path / "present"
    present.mkdir()
    (present / "settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        harness_setup,
        "HARNESSES",
        {
            "here": {"root": present, "detect": "settings.json"},
            "gone": {"root": tmp_path / "absent", "detect": "settings.json"},
        },
    )

    assert list(detect_harnesses()) == ["here"]


def test_detect_requires_the_marker_file_not_just_the_root(tmp_path, monkeypatch):
    root = tmp_path / "root-only"
    root.mkdir()
    monkeypatch.setattr(
        harness_setup, "HARNESSES", {"x": {"root": root, "detect": "settings.json"}}
    )

    assert detect_harnesses() == {}


# ─── find_python ─────────────────────────────────────────────────────────────


def test_uses_manifest_runtime_interpreter_when_it_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_setup, "HARNESS_ROOT", tmp_path)
    exe = Path(sys.executable).as_posix()
    (tmp_path / "manifest.toml").write_text(
        f'[runtime]\npython = "{exe}"\n', encoding="utf-8"
    )

    assert find_python() == exe


def test_falls_back_when_manifest_interpreter_is_missing_from_disk(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(harness_setup, "HARNESS_ROOT", tmp_path)
    (tmp_path / "manifest.toml").write_text(
        '[runtime]\npython = "C:/nonexistent/python.exe"\n', encoding="utf-8"
    )

    assert find_python() == sys.executable


def test_falls_back_when_no_manifest_is_present(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_setup, "HARNESS_ROOT", tmp_path)

    assert find_python() == sys.executable
