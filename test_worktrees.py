"""test_worktrees.py — real-git tests for worktrees.py.

Spec: specs.db REQ #41 (story worktree lifecycle). Task: specs.db task #66.
"""
import subprocess
from pathlib import Path

import pytest

import worktrees as wt


def git(cwd, *args):
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def make_repo(tmp_path, branch="main", commit=True, name="repo"):
    repo = tmp_path / name
    repo.mkdir()
    git(repo, "init", "-b", branch)
    git(repo, "config", "user.name", "T")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    if commit:
        (repo / "a.txt").write_text("one\ntwo\nthree\n")
        git(repo, "add", "a.txt")
        git(repo, "commit", "-m", "init")
    return repo


def commit_file(cwd, name, text, msg="c"):
    (Path(cwd) / name).write_text(text)
    git(cwd, "add", name)
    git(cwd, "commit", "-m", msg)


def branches(repo):
    return git(repo, "branch", "--list").split()


def test_default_branch_main_and_master(tmp_path):
    assert wt.default_branch(str(make_repo(tmp_path))) == "main"
    assert wt.default_branch(str(make_repo(tmp_path, "master", name="r2"))) == "master"


def test_default_branch_no_commits(tmp_path):
    with pytest.raises(wt.WorktreeError):
        wt.default_branch(str(make_repo(tmp_path, commit=False)))


def test_ensure_ignored(tmp_path):
    repo = str(make_repo(tmp_path))
    assert wt.ensure_ignored(repo) is True
    assert wt.ensure_ignored(repo) is False
    wt.create(repo, "s1")
    assert ".worktrees" not in git(repo, "status", "--porcelain")
    assert not (Path(repo) / ".gitignore").exists()
    assert git(repo, "diff", "--name-only") == ""


def test_create(tmp_path):
    repo = str(make_repo(tmp_path))
    branch, path = wt.create(repo, "alpha")
    assert branch == "story/alpha"
    assert path == Path(repo) / ".worktrees" / "alpha"
    assert path.is_dir()
    assert git(path, "rev-parse", "--abbrev-ref", "HEAD") == "story/alpha"


def test_create_duplicate(tmp_path):
    repo = str(make_repo(tmp_path))
    wt.create(repo, "alpha")
    before = branches(repo)
    with pytest.raises(wt.WorktreeError):
        wt.create(repo, "alpha")
    assert branches(repo) == before


def test_create_dirty(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("dirty\n")
    before = branches(str(repo))
    with pytest.raises(wt.WorktreeError):
        wt.create(str(repo), "beta")
    assert branches(str(repo)) == before
    assert not (repo / ".worktrees" / "beta").exists()


def test_diff(tmp_path):
    repo = str(make_repo(tmp_path))
    _, p1 = wt.create(repo, "one")
    wt.create(repo, "two")
    commit_file(p1, "new_file.txt", "x\n")
    assert "new_file.txt" in wt.diff(repo, "one")
    assert "new_file.txt" not in wt.diff(repo, "two")


def test_merge(tmp_path):
    repo = str(make_repo(tmp_path))
    _, p = wt.create(repo, "one")
    commit_file(p, "new_file.txt", "x\n")
    sha = wt.merge(repo, "one", "merge one")
    assert sha == git(repo, "rev-parse", "HEAD")
    assert (Path(repo) / "new_file.txt").exists()
    assert sha[:7] in git(repo, "log", "--merges", "--format=%H")  or sha in git(repo, "log", "--merges", "--format=%H")


def test_merge_conflict(tmp_path):
    repo = str(make_repo(tmp_path))
    _, p = wt.create(repo, "one")
    commit_file(p, "a.txt", "one\nSTORY\nthree\n")
    commit_file(repo, "a.txt", "one\nMAIN\nthree\n")
    head = git(repo, "rev-parse", "HEAD")
    with pytest.raises(wt.WorktreeError) as e:
        wt.merge(repo, "one", "m")
    assert "a.txt" in str(e.value)
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "rev-parse", "HEAD") == head


def test_remove_after_merge(tmp_path):
    repo = str(make_repo(tmp_path))
    _, p = wt.create(repo, "one")
    commit_file(p, "n.txt", "x\n")
    wt.merge(repo, "one", "m")
    wt.remove(repo, "one")
    assert not p.exists()
    assert "story/one" not in branches(repo)


def test_remove_uncommitted(tmp_path):
    repo = str(make_repo(tmp_path))
    _, p = wt.create(repo, "one")
    (p / "scratch.txt").write_text("u\n")
    with pytest.raises(wt.WorktreeError) as e:
        wt.remove(repo, "one", delete_unmerged_branch=True)
    assert "scratch.txt" in str(e.value)
    assert p.exists()


def test_remove_unmerged(tmp_path):
    repo = str(make_repo(tmp_path))
    _, p = wt.create(repo, "one")
    commit_file(p, "n.txt", "x\n")
    with pytest.raises(wt.WorktreeError):
        wt.remove(repo, "one")
    assert "story/one" in branches(repo)
    wt.remove(repo, "one", delete_unmerged_branch=True)
    assert "story/one" not in branches(repo)
    assert not p.exists()


def test_three_slugs_coexist(tmp_path):
    repo = str(make_repo(tmp_path))
    for s in ("a", "b", "c"):
        wt.create(repo, s)
    for s in ("a", "b", "c"):
        assert (Path(repo) / ".worktrees" / s).is_dir()
        assert f"story/{s}" in branches(repo)
