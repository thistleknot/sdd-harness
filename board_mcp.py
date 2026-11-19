"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| REGISTER | Expose board operations as stdio FastMCP tools | [mandatory] | R1 |
| CLAIM | Check transition, create worktree, then record assignment | [mandatory] | R2 |
| SUBMIT | Verify worktree readiness and bind output to branch HEAD | [mandatory] | R3 |
| REVIEW | Return packet only while current branch HEAD matches receipt | [mandatory] | R3 |
| ACCEPT | Recheck receipt, merge verified branch, remove worktree, mark done | [mandatory] | R3 |
| CANCEL | Check transition, remove worktree, then mark cancelled | [mandatory] | R2 |

Spec: specs.db REQ #40-#43; task #67.

R1: Each tool shall take explicit project_root and caller session and return next_action.
R2: A refused lifecycle action shall leave Git unchanged.
R3: IF branch HEAD differs from its submitted receipt or receipt is legacy, THEN packet retrieval and acceptance shall refuse.
CLOSED: Review packets do not include implementer conversation; verification evidence is the submitted output bound to a commit.
Preconditions: project_root resolves inside a Git repository; board and worktree stores are available.
Failure modes: board and worktree rule failures map to ToolError and preserve story state.

This stdio server sequences board.py lifecycle state and worktrees.py Git operations without model calls.
"""
from __future__ import annotations

import contextlib
import json
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

    Require: caller owns the in-progress story and its worktree is ready for review.
    Guarantee: the receipt stores verification output with the exact current worktree HEAD.
    Maintain: a refused submission leaves story state unchanged.
    Assert: no uncommitted or empty-diff revision is submitted.

    Refused (ToolError) when the story branch has no commits ahead of the default branch or
    its worktree has uncommitted changes, so a reviewer never gets an empty or partial diff
    (REQ #42, task #74).
    """
    with _session(project_root) as (conn, key, repo):
        board.check_transition(conn, key, story_id, "submit", session)
        worktrees.check_ready_for_review(repo, board.get_story(conn, key, story_id)["slug"])
        verified_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=board.get_story(conn, key, story_id)["worktree_path"],
            capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL,
        ).stdout.strip()
        if not verified_head:
            raise ToolError("Cannot submit review without a committed branch revision.")
        return board.submit_story(conn, key, story_id, session, verification_output, verified_head)


@mcp.tool
def get_review_packet(project_root: str, session: str, story_id: int) -> dict:
    """Return what a reviewer may see: the story's diff, its acceptance checks and the
    recorded verification output. Never the implementer's conversation.

    Returns:
        ``{"story_id", "title", "acceptance_checks", "verification_output", "verified_head",
        "submitted_at", "diff", "next_action"}``.

    Require: story is in-review and has a revision-bound submitted receipt.
    Guarantee: packet diff, check output and HEAD all describe the same branch revision.
    Maintain: reviewer output excludes implementer conversation.
    Assert: current branch HEAD equals the receipt before returning data.

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
            "SELECT at, detail FROM event WHERE story_id=? AND project_key=? AND kind='submitted' "
            "ORDER BY id DESC LIMIT 1",
            (story_id, key),
        ).fetchone()
        if row is None:
            raise ToolError("No verification receipt exists. Reject and resubmit the story.")
        try:
            receipt = json.loads(row["detail"])
            verified_head = receipt["verified_head"]
            verification_output = receipt["output"]
        except (TypeError, ValueError, KeyError):
            raise ToolError("Verification receipt has no revision identity. Reject and resubmit the story.")
        branch_head = subprocess.run(
            ["git", "-C", repo, "rev-parse", story["branch"]],
            capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL,
        ).stdout.strip()
        if branch_head != verified_head:
            raise ToolError(
                f"Branch advanced after verification ({verified_head[:12]} -> {branch_head[:12]}). "
                "Reject, update, and resubmit before review."
            )
        return {
            "story_id": story_id,
            "title": story["title"],
            "acceptance_checks": story["acceptance_checks"],
            "verification_output": verification_output,
            "verified_head": verified_head,
            "submitted_at": row["at"],
            "diff": worktrees.diff(repo, story["slug"]),
            "next_action": story["next_action"],
        }


@mcp.tool
def accept_story(project_root: str, session: str, story_id: int) -> dict:
    """Accept an in-review story: merge its branch, remove its worktree, mark it done.

    Require: caller is an independent reviewer and the branch HEAD matches its receipt.
    Guarantee: only a revision with matching verification evidence is merged.
    Maintain: a refused merge leaves the story in-review.
    Assert: receipt and branch revision are checked before merge.

    Raises:
        fastmcp.exceptions.ToolError: the caller is the assignee, the story is not in-review,
            the verification receipt is missing/stale, or the merge conflicts (the story then stays in-review).
    """
    with _session(project_root) as (conn, key, repo):
        board.check_transition(conn, key, story_id, "accept", session)
        story = board.get_story(conn, key, story_id)
        receipt_row = conn.execute(
            "SELECT detail FROM event WHERE story_id=? AND project_key=? AND kind='submitted' "
            "ORDER BY id DESC LIMIT 1",
            (story_id, key),
        ).fetchone()
        try:
            verified_head = json.loads(receipt_row["detail"])["verified_head"]
        except (TypeError, ValueError, KeyError):
            raise ToolError("No revision-bound verification receipt exists. Reject and resubmit the story.")
        branch_head = subprocess.run(
            ["git", "-C", repo, "rev-parse", story["branch"]],
            capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL,
        ).stdout.strip()
        if branch_head != verified_head:
            raise ToolError(
                f"Branch advanced after verification ({verified_head[:12]} -> {branch_head[:12]}). "
                "Refresh the packet and reject before accepting."
            )
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
