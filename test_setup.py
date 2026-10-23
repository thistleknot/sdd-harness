"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| FIXTURE | Isolate manifest, projects, and skill-store writes under tmp_path | [mandatory] | R1 |
| PROVISION | Exercise uv command construction with a fake subprocess | [mandatory] | R2 |
| VERIFY | Assert F: environment paths and unchanged user-owned files | [mandatory] | R2, R3 |

R1: WHEN setup helpers run in tests, they MUST NOT mutate live user paths.
R2: MCP project environments and uv cache MUST come from runtime.mcp manifest settings.
R3: Skill installation MUST retain existing directories and non-MCP runtime selection.

CLOSED: Per-client MCP rendering in setup.py was removed because adapter.py already owns
the native projections and caused the exact format divergence under test.

Preconditions: pytest and TOML parsing are available.
Failure modes: wrong environment root, project lock omission, or user-skill overwrite fail tests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import setup as harness_setup
from setup import (
    copy_core_skills,
    detect_harnesses,
    find_python,
    find_retrieve_skills_server,
    mcp_runtime,
    provision_mcp_environments,
)

PYTHON = "C:/fake/python.exe"


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


def test_setup_covers_every_registered_adapter():
    """Require canonical target coverage; guarantee setup can select every MCP adapter."""
    import adapter

    assert set(harness_setup.HARNESSES) == set(adapter.TARGETS)


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


def test_mcp_runtime_resolves_projects_under_manifest_root(tmp_path, monkeypatch):
    (tmp_path / "mcp" / "todo").mkdir(parents=True)
    (tmp_path / "manifest.toml").write_text(
        '[runtime.mcp]\npython = "F:/base/python.exe"\n'
        'environments_dir = "F:/Python/mcp"\ncache_dir = "F:/Python/cache"\n'
        'tool_dir = "F:/Python/tools"\n'
        '[runtime.mcp.projects]\ntodo = "mcp/todo"\n'
        '[runtime.mcp.tools]\ngraphify = "graphifyy[mcp]==0.9.93"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(harness_setup, "HARNESS_ROOT", tmp_path)

    runtime = mcp_runtime()

    assert runtime["projects"] == {"todo": tmp_path / "mcp" / "todo"}
    assert runtime["environments_dir"] == "F:/Python/mcp"
    assert runtime["tools"] == {"graphify": "graphifyy[mcp]==0.9.93"}


def test_provision_syncs_locked_projects_to_manifest_environment(tmp_path, monkeypatch):
    project = tmp_path / "mcp" / "todo"
    project.mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname='todo'\n", encoding="utf-8")
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    base = tmp_path / "base-python.exe"
    base.touch()
    runtime = {
        "python": str(base),
        "environments_dir": str(tmp_path / "F" / "mcp"),
        "cache_dir": str(tmp_path / "F" / "cache"),
        "tool_dir": str(tmp_path / "F" / "tools"),
        "projects": {"todo": project},
        "tools": {"graphify": "graphifyy[mcp]==0.9.93"},
    }
    monkeypatch.setattr(harness_setup, "mcp_runtime", lambda: runtime)
    calls = []

    def fake_run(args, check, env):
        calls.append((args, check, env))
        if args[1] == "sync":
            environment = Path(env["UV_PROJECT_ENVIRONMENT"])
            (environment / "Scripts").mkdir(parents=True, exist_ok=True)
            (environment / "Scripts" / "python.exe").touch()
        else:
            tool_exe = Path(env["UV_TOOL_BIN_DIR"]) / "graphify.exe"
            tool_exe.parent.mkdir(parents=True, exist_ok=True)
            tool_exe.touch()

    monkeypatch.setattr(harness_setup.subprocess, "run", fake_run)

    installed = provision_mcp_environments()

    assert installed["todo"].startswith(str(tmp_path / "F" / "mcp"))
    assert calls[0][0][1:3] == ["sync", "--project"]
    assert calls[0][2]["UV_CACHE_DIR"] == str(tmp_path / "F" / "cache")
    assert "--tool-dir" not in calls[1][0]
    assert calls[1][2]["UV_TOOL_DIR"] == str(tmp_path / "F" / "tools")
    assert calls[1][2]["UV_TOOL_BIN_DIR"] == str(tmp_path / "F" / "tools" / "bin")
    assert installed["graphify"] == str(tmp_path / "F" / "tools" / "bin" / "graphify.exe")
