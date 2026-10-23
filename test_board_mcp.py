"""test_board_mcp.py — tests for board_mcp.py through a real in-memory fastmcp client.

Spec: specs.db REQ #40, #41, #42, #43. Task: specs.db task #67; plan.md T4.
"""
import asyncio
import os
import subprocess
from pathlib import Path

import fastmcp
import pytest
from fastmcp.exceptions import ToolError

import board_mcp


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout


def call(name, **args):
    async def run():
        async with fastmcp.Client(board_mcp.mcp) as c:
            res = await c.call_tool(name, args)
            return res.data

    return asyncio.run(run())


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_KANBAN_DB", str(tmp_path / "db" / "board.db"))
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "T")
    git(root, "config", "user.email", "t@example.com")
    (root / "README.md").write_text("line one\n")
    git(root, "add", "-A")
    git(root, "commit", "-m", "init")
    return root


def setup_two(repo):
    f = call("create_feature", project_root=str(repo), session="A", title="F", request_text="r")
    a = call("add_story", project_root=str(repo), session="A", feature_id=f["id"],
             title="Story A", acceptance_checks=["check one"])
    b = call("add_story", project_root=str(repo), session="A", feature_id=f["id"],
             title="Story B", acceptance_checks=["check two"], depends_on=[a["id"]])
    return f, a, b


def branches(repo):
    return git(repo, "branch", "--list", "story/*").strip()


def commit_in(wt, name, text="x\n"):
    (Path(wt) / name).write_text(text)
    git(wt, "add", "-A")
    git(wt, "commit", "-m", f"add {name}")


def test_whoami_returns_pid():
    assert call("whoami")["pid"] == os.getpid()


def test_full_path(repo):
    f, a, b = setup_two(repo)
    assert a["next_action"] and b["depends_on"] == [a["id"]]
    claimed = call("claim_story", project_root=str(repo), session="A", story_id=a["id"])
    wt = Path(claimed["worktree_path"])
    assert wt.is_dir() and claimed["branch"] == "story/story-a"
    assert "story/story-a" in branches(repo)
    commit_in(wt, "feature_file.txt")
    sub = call("submit_story", project_root=str(repo), session="A", story_id=a["id"],
               verification_output="ALL CHECKS PASSED 7")
    assert sub["status"] == "in-review"
    packet = call("get_review_packet", project_root=str(repo), session="R", story_id=a["id"])
    assert "feature_file.txt" in packet["diff"]
    assert packet["acceptance_checks"] == ["check one"]
    assert "ALL CHECKS PASSED 7" in packet["verification_output"]
    assert packet["next_action"]
    done = call("accept_story", project_root=str(repo), session="R", story_id=a["id"])
    assert done["status"] == "done"
    assert (repo / "feature_file.txt").exists()
    assert git(repo, "log", "--merges", "--oneline").strip()
    assert not wt.exists()
    assert branches(repo) == ""
    cb = call("claim_story", project_root=str(repo), session="C", story_id=b["id"])
    assert cb["status"] == "in-progress" and Path(cb["worktree_path"]).is_dir()


def test_review_gate(repo):
    f, a, b = setup_two(repo)
    # B blocked by A: refused and leaves no branch
    with pytest.raises(ToolError):
        call("claim_story", project_root=str(repo), session="C", story_id=b["id"])
    assert branches(repo) == ""
    claimed = call("claim_story", project_root=str(repo), session="A", story_id=a["id"])
    commit_in(claimed["worktree_path"], "gate.txt")
    with pytest.raises(ToolError):
        call("submit_story", project_root=str(repo), session="A", story_id=a["id"],
             verification_output="   ")
    call("submit_story", project_root=str(repo), session="A", story_id=a["id"],
         verification_output="ok")
    for tool, extra in (("accept_story", {}), ("reject_story", {"note": "n"})):
        with pytest.raises(ToolError):
            call(tool, project_root=str(repo), session="A", story_id=a["id"], **extra)


def test_reject_with_and_without_note(repo):
    f, a, b = setup_two(repo)
    claimed = call("claim_story", project_root=str(repo), session="A", story_id=a["id"])
    commit_in(claimed["worktree_path"], "reject.txt")
    call("submit_story", project_root=str(repo), session="A", story_id=a["id"],
         verification_output="ok")
    with pytest.raises(ToolError):
        call("reject_story", project_root=str(repo), session="R", story_id=a["id"], note="")
    r = call("reject_story", project_root=str(repo), session="R", story_id=a["id"],
             note="fix the thing")
    assert r["status"] == "in-progress"
    listed = call("list_stories", project_root=str(repo), session="R", feature_id=f["id"])
    story = [s for s in listed["stories"] if s["id"] == a["id"]][0]
    assert story["review_note"] == "fix the thing"
    assert listed["feature_status"] == "in-progress" and listed["next_action"]


def test_submit_refused_without_commits_or_with_uncommitted_files(repo):
    """REQ #42: a reviewer is never handed an empty or partial diff."""
    f, a, b = setup_two(repo)
    claimed = call("claim_story", project_root=str(repo), session="A", story_id=a["id"])
    wt = Path(claimed["worktree_path"])
    args = dict(project_root=str(repo), session="A", story_id=a["id"], verification_output="ok")
    with pytest.raises(ToolError, match="no commits ahead"):
        call("submit_story", **args)
    (wt / "half.txt").write_text("not committed\n")
    with pytest.raises(ToolError, match="uncommitted"):
        call("submit_story", **args)
    # the story is still in-progress after both refusals
    listed = call("list_stories", project_root=str(repo), session="A", feature_id=f["id"])
    assert [s["status"] for s in listed["stories"] if s["id"] == a["id"]] == ["in-progress"]
    git(wt, "add", "half.txt")
    git(wt, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "half")
    assert call("submit_story", **args)["status"] == "in-review"


def test_accept_merge_conflict(repo):
    f, a, b = setup_two(repo)
    claimed = call("claim_story", project_root=str(repo), session="A", story_id=a["id"])
    wt = claimed["worktree_path"]
    commit_in(wt, "README.md", "story line\n")
    call("submit_story", project_root=str(repo), session="A", story_id=a["id"],
         verification_output="ok")
    (repo / "README.md").write_text("main line\n")
    git(repo, "commit", "-am", "main edit")
    head = git(repo, "rev-parse", "HEAD")
    with pytest.raises(ToolError):
        call("accept_story", project_root=str(repo), session="R", story_id=a["id"])
    listed = call("list_stories", project_root=str(repo), session="R")
    assert [s["status"] for s in listed["stories"]][0] == "in-review"
    assert git(repo, "rev-parse", "HEAD") == head
    assert (repo / "README.md").read_text() == "main line\n"


def test_cancel_dirty_and_clean(repo):
    f, a, b = setup_two(repo)
    claimed = call("claim_story", project_root=str(repo), session="A", story_id=a["id"])
    wt = Path(claimed["worktree_path"])
    (wt / "scratch_dirty.txt").write_text("u\n")
    with pytest.raises(ToolError, match="scratch_dirty.txt"):
        call("cancel_story", project_root=str(repo), session="A", story_id=a["id"], reason="r")
    assert wt.is_dir()
    (wt / "scratch_dirty.txt").unlink()
    c = call("cancel_story", project_root=str(repo), session="A", story_id=a["id"], reason="r")
    assert c["status"] == "cancelled"
    assert not wt.exists() and branches(repo) == ""
    # cancelling again is refused; cancelling an unclaimed todo works
    with pytest.raises(ToolError):
        call("cancel_story", project_root=str(repo), session="A", story_id=a["id"], reason="r")
    assert call("cancel_story", project_root=str(repo), session="A", story_id=b["id"],
                reason="r")["status"] == "cancelled"


def test_worktree_path_sees_same_board(repo):
    f, a, b = setup_two(repo)
    claimed = call("claim_story", project_root=str(repo), session="A", story_id=a["id"])
    from_main = call("list_stories", project_root=str(repo), session="A")
    from_wt = call("list_stories", project_root=claimed["worktree_path"], session="A")
    ids = [s["id"] for s in from_main["stories"]]
    assert ids == [a["id"], b["id"]]
    assert [s["id"] for s in from_wt["stories"]] == ids


def test_not_a_repo_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_KANBAN_DB", str(tmp_path / "b.db"))
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ToolError):
        call("list_stories", project_root=str(plain), session="A")


MCP_PLAN = """## Layer 1 - parallel
- [DONE] T1 First thing
  _Verify:_ run a
- [OPEN] T2 Second thing
  _Verify:_ run b

## Layer 2 - sequential
- [WIP] T3 Third thing
  _Verify:_ run c
- [BLOCKED] T4 Fourth thing
  _Verify:_ run d
  _Blocked:_ waiting
- [OPEN] T5 Fifth thing
  _Verify:_ run e
"""


def test_import_render_plan_tools(repo):
    (repo / "plan.md").write_text(MCP_PLAN, encoding="utf-8")
    res = call("import_plan", project_root=str(repo), session="A",
               plan_path="plan.md", feature_title="P")
    assert sorted(res["stories"]) == ["T1", "T2", "T3", "T4", "T5"]
    with pytest.raises(ToolError):
        call("import_plan", project_root=str(repo), session="A",
             plan_path="plan.md", feature_title="P")
    with pytest.raises(ToolError):
        call("import_plan", project_root=str(repo), session="A",
             plan_path="missing.md", feature_title="Z")
    (repo / "empty.md").write_text("no tasks\n")
    with pytest.raises(ToolError):
        call("import_plan", project_root=str(repo), session="A",
             plan_path="empty.md", feature_title="E")
    out = repo / "out" / "plan.md"
    r1 = call("render_plan", project_root=str(repo), session="A",
              feature_id=res["feature_id"], write_to=str(out))
    assert "_Blocked:_ waiting" in r1["markdown"]
    assert out.read_bytes() == r1["markdown"].encode("utf-8")
    m1 = out.stat().st_mtime_ns
    r2 = call("render_plan", project_root=str(repo), session="A",
              feature_id=res["feature_id"], write_to=str(out))
    assert r2["markdown"] == r1["markdown"]
    assert out.stat().st_mtime_ns == m1
    assert out.read_bytes() == r1["markdown"].encode("utf-8")
    with pytest.raises(ToolError):
        call("render_plan", project_root=str(repo), session="A", feature_id=999)


def test_add_lesson_tool(repo):
    (repo / "plan.md").write_text(MCP_PLAN, encoding="utf-8")
    res = call("import_plan", project_root=str(repo), session="A",
               plan_path="plan.md", feature_title="P")
    assert call("render_plan", project_root=str(repo), session="A",
                feature_id=res["feature_id"])["markdown"] == MCP_PLAN
    story = call("add_lesson", project_root=str(repo), session="A",
                 story_id=res["stories"]["T2"], text="learned x")
    assert story["body"] == "  _Verify:_ run b\n  _Lessons:_ learned x"
    assert story["next_action"]
    md = call("render_plan", project_root=str(repo), session="A",
              feature_id=res["feature_id"])["markdown"]
    assert md == MCP_PLAN.replace("  _Verify:_ run b\n", "  _Verify:_ run b\n  _Lessons:_ learned x\n")
    with pytest.raises(ToolError):
        call("add_lesson", project_root=str(repo), session="A",
             story_id=res["stories"]["T2"], text="")
    with pytest.raises(ToolError):
        call("add_lesson", project_root=str(repo), session="A", story_id=999, text="x")


def test_real_stdio_server_runs_git_backed_tools(tmp_path):
    """Spawn board_mcp.py as a real stdio server and call tools that run git.

    The in-memory client shares the test process, so it never saw git children inherit the
    server's stdin pipe: over real stdio create_feature hung for 300 s in Codex until every
    git call got stdin=DEVNULL. Each call here has a 30 s ceiling, far above the ~0.1 s it takes.
    """
    import sys

    from fastmcp.client.transports import StdioTransport

    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-q", "-m", "init")
    env = dict(os.environ, AGENTIC_KANBAN_DB=str(tmp_path / "stdio.db"))
    server = str(Path(board_mcp.__file__).resolve())

    async def run():
        transport = StdioTransport(command=sys.executable, args=[server], env=env)
        async with fastmcp.Client(transport, timeout=30) as c:
            feat = (await c.call_tool("create_feature", {
                "project_root": str(repo), "session": "p", "title": "stdio", "request_text": "x"})).data
            story = (await c.call_tool("add_story", {
                "project_root": str(repo), "session": "p", "feature_id": feat["id"],
                "title": "one", "acceptance_checks": ["it works"]})).data
            claimed = (await c.call_tool("claim_story", {
                "project_root": str(repo), "session": "d", "story_id": story["id"]})).data
            listed = (await c.call_tool("list_stories", {
                "project_root": str(repo), "session": "d"})).data
            return feat, claimed, listed

    feat, claimed, listed = asyncio.run(run())
    assert feat["title"] == "stdio"
    assert claimed["status"] == "in-progress"
    assert Path(claimed["worktree_path"]).is_dir()
    assert [s["status"] for s in listed["stories"]] == ["in-progress"]
