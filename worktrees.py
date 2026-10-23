"""worktrees.py — one git worktree per story for the agentic-kanban feature board.

Spec: specs.db REQ #41 (story worktree lifecycle).
Task: specs.db task #66; plan.md T3.

Runs git through ``subprocess`` with argument lists (never ``shell=True``) and knows nothing
about the board's database. A story's worktree lives at ``<repo>/.worktrees/<slug>`` on branch
``story/<slug>``, cut from the repository's default branch.

Ignoring ``.worktrees/``: ``ensure_ignored`` appends the pattern to the repository's
``info/exclude`` (inside the git common directory) so no tracked file is edited.

Merge strategy: ``MERGE_ARGS`` is a merge commit (``--no-ff``). This is a default; the choice
between merge commit and squash is an open question recorded in playbook.md section 8.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

WORKTREE_DIR = ".worktrees"
BRANCH_PREFIX = "story/"
MERGE_ARGS = ("--no-ff",)


class WorktreeError(Exception):
    """A git operation was refused or failed; the message carries git's own output."""


def _git(repo: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL,
    )
    if check and proc.returncode != 0:
        raise WorktreeError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()} {proc.stdout.strip()}".strip()
        )
    return proc


def _branch_exists(repo: str, branch: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0


def default_branch(repo: str) -> str:
    """Return the repository's default branch name.

    Uses ``origin/HEAD`` when it exists, else ``main`` if that branch exists, else ``master``.

    Raises:
        WorktreeError: none of those exist.
    """
    proc = _git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    if proc.returncode == 0 and proc.stdout.strip():
        name = proc.stdout.strip()
        return name[len("origin/"):] if name.startswith("origin/") else name
    for name in ("main", "master"):
        if _branch_exists(repo, name):
            return name
    raise WorktreeError(f"no default branch (origin/HEAD, main, master) in {repo}")


def worktree_path(repo: str, slug: str) -> Path:
    """Return ``<repo>/.worktrees/<slug>`` without touching the filesystem."""
    return Path(repo) / WORKTREE_DIR / slug


def branch_name(slug: str) -> str:
    """Return ``story/<slug>``."""
    return BRANCH_PREFIX + slug


def ensure_ignored(repo: str) -> bool:
    """Make git ignore ``.worktrees/`` for this repository.

    Returns:
        True when the pattern was added, False when it was already present.
    """
    common = _git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    exclude = Path(common) / "info" / "exclude"
    pattern = WORKTREE_DIR + "/"
    text = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if pattern in (line.strip() for line in text.splitlines()):
        return False
    exclude.parent.mkdir(parents=True, exist_ok=True)
    prefix = "" if (not text or text.endswith("\n")) else "\n"
    exclude.write_text(text + prefix + pattern + "\n", encoding="utf-8")
    return True


def check_clean(repo: str) -> None:
    """Raise ``WorktreeError`` unless the main checkout is on the default branch with a clean
    tree (untracked files under ``.worktrees/`` do not count as dirty)."""
    default = default_branch(repo)
    current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if current != default:
        raise WorktreeError(f"main checkout is on '{current}', expected '{default}'")
    status = _git(repo, "status", "--porcelain").stdout.splitlines()
    prefix = "?? " + WORKTREE_DIR + "/"
    dirty = [line for line in status if not line.startswith(prefix)]
    if dirty:
        raise WorktreeError("main checkout is dirty:\n" + "\n".join(dirty))


def create(repo: str, slug: str) -> tuple[str, Path]:
    """Create the story's worktree and branch from the default branch.

    Calls ``check_clean`` and ``ensure_ignored`` first.

    Returns:
        ``(branch, path)``.

    Raises:
        WorktreeError: the tree is dirty, the branch or path already exists, or git fails.
            A failed create leaves no branch and no directory behind.
    """
    check_clean(repo)
    ensure_ignored(repo)
    branch = branch_name(slug)
    path = worktree_path(repo, slug)
    if _branch_exists(repo, branch):
        raise WorktreeError(f"branch '{branch}' already exists")
    if path.exists():
        raise WorktreeError(f"path already exists: {path}")
    _git(repo, "worktree", "add", "-b", branch, str(path), default_branch(repo))
    return branch, path


def diff(repo: str, slug: str) -> str:
    """Return the story branch's changes against the default branch (three-dot diff).

    This is what the reviewer reads.
    """
    return _git(repo, "diff", f"{default_branch(repo)}...{branch_name(slug)}").stdout


def check_ready_for_review(repo: str, slug: str) -> None:
    """Raise ``WorktreeError`` unless the story can be reviewed as submitted.

    Spec: specs.db REQ #42. Task: specs.db task #74 (plan.md T8b).

    Ready means the story branch has at least one commit ahead of the default branch and its
    worktree has no uncommitted or untracked-unignored files, so the reviewer's diff is the
    whole change. Observed 2026-10-13: Codex implementers submitted before committing and
    three reviews were rejected for an empty diff.

    Raises:
        WorktreeError: uncommitted changes (listed) or no commits ahead (named).
    """
    path = worktree_path(repo, slug)
    if path.exists():
        changes = _git(str(path), "status", "--porcelain").stdout.strip()
        if changes:
            raise WorktreeError(
                f"worktree {path} has uncommitted changes; commit them on the story branch, "
                f"then submit again:\n{changes}")
    default = default_branch(repo)
    ahead = _git(repo, "rev-list", "--count", f"{default}..{branch_name(slug)}").stdout.strip()
    if ahead == "0":
        raise WorktreeError(
            f"branch '{branch_name(slug)}' has no commits ahead of {default}; commit the work "
            f"in {path}, then submit again.")


def merge(repo: str, slug: str, message: str) -> str:
    """Merge the story branch into the default branch in the main checkout.

    Returns:
        The merge commit's sha.

    Raises:
        WorktreeError: the main checkout is dirty or off the default branch, or the merge
            conflicts. On conflict the merge is aborted so the checkout is exactly as before,
            and the error lists the conflicting paths.
    """
    check_clean(repo)
    branch = branch_name(slug)
    proc = _git(repo, "merge", *MERGE_ARGS, "-m", message, branch, check=False)
    if proc.returncode != 0:
        conflicts = _git(repo, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
        _git(repo, "merge", "--abort", check=False)
        raise WorktreeError(
            f"merge of '{branch}' failed; conflicting paths: {', '.join(conflicts) or '(none)'}\n"
            f"{proc.stdout.strip()} {proc.stderr.strip()}"
        )
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def remove(repo: str, slug: str, delete_unmerged_branch: bool = False) -> None:
    """Remove the story's worktree and delete its branch.

    Never forces. A worktree with uncommitted changes is refused. The branch is deleted with
    ``git branch -d`` (merged only); ``delete_unmerged_branch=True`` uses ``-D``, for cancel.

    Raises:
        WorktreeError: the worktree has uncommitted changes (the message lists them), or the
            branch is unmerged and ``delete_unmerged_branch`` is False.
    """
    branch = branch_name(slug)
    path = worktree_path(repo, slug)
    if path.exists():
        changes = _git(str(path), "status", "--porcelain").stdout.strip()
        if changes:
            raise WorktreeError(f"worktree {path} has uncommitted changes:\n{changes}")
    if not delete_unmerged_branch:
        merged = _git(repo, "merge-base", "--is-ancestor", branch, default_branch(repo), check=False)
        if merged.returncode != 0:
            raise WorktreeError(f"branch '{branch}' is not merged into {default_branch(repo)}")
    if path.exists():
        _git(repo, "worktree", "remove", str(path))
    _git(repo, "branch", "-D" if delete_unmerged_branch else "-d", branch)
