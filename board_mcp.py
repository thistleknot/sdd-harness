"""board_mcp.py — the agentic-kanban MCP server.

Spec: specs.db REQ #40 (story lifecycle), #41 (worktree lifecycle), #42 (independent review
gate), #43 (server shape and project keying).
Task: specs.db task #67; plan.md T4.

A stdio FastMCP server named ``agentic-kanban``. It sequences ``board.py`` (state) and
``worktrees.py`` (git) and makes no LLM calls. Every tool takes ``project_root`` (any
directory inside the repository, including a story's worktree) and ``session`` (the caller's
identity). Every reply is a dict that includes ``next_action``.

Order of effects, so a refused action leaves git untouched:
    claim   check_transition -> worktrees.create -> board.claim_story
            (a failure after create removes the new worktree)
    accept  check_transition -> worktrees.merge  -> worktrees.remove -> board.accept_story
            (a merge conflict leaves the story in-review and raises ToolError)
    cancel  check_transition -> worktrees.remove(delete_unmerged_branch=True)
            -> board.cancel_story

The database file is ``$AGENTIC_KANBAN_DB`` when set, else ``board.DEFAULT_DB``.
Run with ``python board_mcp.py`` (stdio).
"""
from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import board
import worktrees

mcp = FastMCP("agentic-kanban")


def repo_root(project_root: str) -> str:
    """Return the main checkout directory of the repository containing ``project_root``.

    It is the parent of ``git rev-parse --path-format=absolute --git-common-dir``, so a path
    inside a story's worktree resolves to the main checkout, where merges happen.

    Raises:
        fastmcp.exceptions.ToolError: ``project_root`` is not inside a git repository.
    """
    if not Path(project_root).is_dir():
        raise ToolError(f"{project_root!r} is not a directory; pass a directory inside a git repository.")
    proc = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=project_root, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ToolError(f"{project_root!r} is not inside a git repository; run from a git checkout.")
    return str(Path(proc.stdout.strip()).parent)


@contextlib.contextmanager
def _session(project_root: str):
    """Yield ``(conn, key, repo)``; map board and worktree errors to ToolError."""
    repo = repo_root(project_root)
    conn = None
    try:
        key = board.project_key(project_root)
        conn = board.connect(os.environ.get("AGENTIC_KANBAN_DB") or board.DEFAULT_DB)
        yield conn, key, repo
    except (board.BoardError, worktrees.WorktreeError) as exc:
        raise ToolError(str(exc)) from exc
    finally:
        if conn is not None:
            conn.close()


@mcp.tool
def whoami() -> dict:
    """Return ``{"pid": <this server process id>}``.

    Lets a test or a live session discover whether two callers share one server process
    (plan.md open question: does a subagent get its own stdio process?).
    """
    return {"pid": os.getpid(), "next_action": "Use pid to compare server processes between sessions."}


@mcp.tool
def create_feature(project_root: str, session: str, title: str, request_text: str) -> dict:
    """Create a feature on this project's board.

    Returns:
        The feature row plus ``next_action`` telling the caller to add stories.
    """
    with _session(project_root) as (conn, key, _repo):
        feature = board.create_feature(conn, key, title, request_text)
    feature["next_action"] = "Add stories to this feature with add_story, giving acceptance_checks for each."
    return feature


@mcp.tool
def add_story(
    project_root: str,
    session: str,
    feature_id: int,
    title: str,
    acceptance_checks: list[str],
    depends_on: list[int] | None = None,
) -> dict:
    """Add a story in ``todo`` to a feature.

    Returns:
        The story row plus ``next_action``.

    Raises:
        fastmcp.exceptions.ToolError: any ``board.BoardError`` (message unchanged).
    """
    with _session(project_root) as (conn, key, _repo):
        return board.add_story(conn, key, feature_id, title, acceptance_checks, depends_on or [])


@mcp.tool
def list_stories(project_root: str, session: str, feature_id: int | None = None) -> dict:
    """List this project's stories, optionally of one feature.

    Returns:
        ``{"stories": [...], "feature_status": <str or None>, "next_action": <str>}``.
    """
    with _session(project_root) as (conn, key, _repo):
        stories = board.list_stories(conn, key, feature_id)
        status = board.feature_status(conn, key, feature_id) if feature_id is not None else None
    if not stories:
        action = "No stories yet; add one with add_story."
    else:
        action = "Claim a ready todo story with claim_story, or review one that is in-review."
    return {"stories": stories, "feature_status": status, "next_action": action}


@mcp.tool
def claim_story(project_root: str, session: str, story_id: int) -> dict:
    """Claim a ready story: create its worktree and branch and record the caller as assignee.

    Returns:
        The story row, including ``worktree_path`` and ``branch``, plus ``next_action``.

    Raises:
        fastmcp.exceptions.ToolError: a ``board.BoardError`` or ``worktrees.WorktreeError``.
            A refused claim leaves no worktree and no branch.
    """
    with _session(project_root) as (conn, key, repo):
        board.check_transition(conn, key, story_id, "claim", session)
        slug = board.get_story(conn, key, story_id)["slug"]
        branch, path = worktrees.create(repo, slug)
        try:
            return board.claim_story(conn, key, story_id, session, branch, str(path))
        except BaseException:
            worktrees.remove(repo, slug, delete_unmerged_branch=True)
            raise


@mcp.tool
def submit_story(project_root: str, session: str, story_id: int, verification_output: str) -> dict:
    """Submit an in-progress story for review with the output of its acceptance checks.

    Refused (ToolError) when the story branch has no commits ahead of the default branch or
    its worktree has uncommitted changes, so a reviewer never gets an empty or partial diff
    (REQ #42, task #74).
    """
    with _session(project_root) as (conn, key, repo):
        board.check_transition(conn, key, story_id, "submit", session)
        worktrees.check_ready_for_review(repo, board.get_story(conn, key, story_id)["slug"])
        return board.submit_story(conn, key, story_id, session, verification_output)


@mcp.tool
def get_review_packet(project_root: str, session: str, story_id: int) -> dict:
    """Return what a reviewer may see: the story's diff, its acceptance checks and the
    recorded verification output. Never the implementer's conversation.

    Returns:
        ``{"story_id", "title", "acceptance_checks", "verification_output", "diff",
        "next_action"}``.

    Raises:
        fastmcp.exceptions.ToolError: the story is not in-review.
    """
    with _session(project_root) as (conn, key, repo):
        story = board.get_story(conn, key, story_id)
        if story["status"] != "in-review":
            raise board.BoardError(
                f"Story {story_id} is {story['status']}, not in-review. {story['next_action']}"
            )
        row = conn.execute(
            "SELECT detail FROM event WHERE story_id=? AND project_key=? AND kind='submitted' "
            "ORDER BY id DESC LIMIT 1",
            (story_id, key),
        ).fetchone()
        return {
            "story_id": story_id,
            "title": story["title"],
            "acceptance_checks": story["acceptance_checks"],
            "verification_output": row["detail"] if row else "",
            "diff": worktrees.diff(repo, story["slug"]),
            "next_action": story["next_action"],
        }


@mcp.tool
def accept_story(project_root: str, session: str, story_id: int) -> dict:
    """Accept an in-review story: merge its branch, remove its worktree, mark it done.

    Raises:
        fastmcp.exceptions.ToolError: the caller is the assignee, the story is not in-review,
            or the merge conflicts (the story then stays in-review).
    """
    with _session(project_root) as (conn, key, repo):
        board.check_transition(conn, key, story_id, "accept", session)
        story = board.get_story(conn, key, story_id)
        worktrees.merge(repo, story["slug"], f"Merge story/{story['slug']}: {story['title']}")
        worktrees.remove(repo, story["slug"])
        return board.accept_story(conn, key, story_id, session)


@mcp.tool
def reject_story(project_root: str, session: str, story_id: int, note: str) -> dict:
    """Reject an in-review story back to in-progress with the reviewer's note."""
    with _session(project_root) as (conn, key, _repo):
        board.check_transition(conn, key, story_id, "reject", session)
        return board.reject_story(conn, key, story_id, session, note)


@mcp.tool
def cancel_story(project_root: str, session: str, story_id: int, reason: str) -> dict:
    """Cancel a story and remove its worktree and branch.

    Raises:
        fastmcp.exceptions.ToolError: the worktree has uncommitted changes (they are listed and
            nothing is removed), or the story is already done or cancelled.
    """
    with _session(project_root) as (conn, key, repo):
        board.check_transition(conn, key, story_id, "cancel", session)
        story = board.get_story(conn, key, story_id)
        if story["branch"]:
            worktrees.remove(repo, story["slug"], delete_unmerged_branch=True)
        return board.cancel_story(conn, key, story_id, session, reason)


@mcp.tool
def add_lesson(project_root: str, session: str, story_id: int, text: str) -> dict:
    """Append a lesson to a story; it appears as a ``_Lessons:_`` line in the rendered plan.

    Spec: specs.db REQ #45. Task: specs.db task #72.

    The only way to add a lesson once plan.md is generated and read-only. Calls
    ``board.add_lesson``. Returns the story row plus ``next_action``.

    Raises:
        fastmcp.exceptions.ToolError: any ``board.BoardError`` (message unchanged).
    """
    with _session(project_root) as (conn, key, _repo):
        return board.add_lesson(conn, key, story_id, session, text)


@mcp.tool
def import_plan(project_root: str, session: str, plan_path: str, feature_title: str) -> dict:
    """Import a plan.md-format file into the board as one feature (once only).

    Spec: specs.db REQ #45. Task: specs.db task #72.

    Reads ``plan_path`` (relative paths resolve against the main checkout), calls
    ``board.import_plan``, and returns ``{"feature_id", "stories", "next_action"}``. Does not
    touch the file; making plan.md read-only is a manifest edit made after a verified import.

    Raises:
        fastmcp.exceptions.ToolError: the file is missing, the title was already imported, or
            ``board.import_plan`` refuses it.
    """
    with _session(project_root) as (conn, key, repo):
        path = Path(plan_path)
        if not path.is_absolute():
            path = Path(repo) / path
        if not path.is_file():
            raise ToolError(f"Plan file {str(path)!r} does not exist; pass the path of a plan.md file.")
        result = board.import_plan(conn, key, path.read_text(encoding="utf-8"), feature_title, session)
    result["next_action"] = "Claim a ready todo story with claim_story; render_plan regenerates the plan file."
    return result


@mcp.tool
def render_plan(
    project_root: str, session: str, feature_id: int, write_to: str | None = None
) -> dict:
    """Render a feature as plan.md-format markdown.

    Spec: specs.db REQ #45. Task: specs.db task #72.

    Returns:
        ``{"markdown": str, "written": str | None, "next_action": str}``. When ``write_to`` is
        given the markdown is also written there (UTF-8, LF), and only when it differs from
        the file's current bytes, so an unchanged board never touches the file.
    """
    with _session(project_root) as (conn, key, repo):
        markdown = board.render_plan(conn, key, feature_id)
    written = None
    if write_to:
        path = Path(write_to)
        if not path.is_absolute():
            path = Path(repo) / path
        data = markdown.encode("utf-8")
        if not path.is_file() or path.read_bytes() != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        written = str(path)
    return {
        "markdown": markdown,
        "written": written,
        "next_action": "The board is the source of truth; change story status through the board tools, then render again.",
    }


if __name__ == "__main__":
    mcp.run()
