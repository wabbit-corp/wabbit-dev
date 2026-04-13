from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
import time

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from dev.config import Config, Project, load_config
from dev.git_env import configured_git_ssh, git_subprocess_env
from dev.repo_resolution import ResolvedRepoTarget, resolve_repo_target
from dev.tasks.setup import commit_repo_changes


@dataclass(frozen=True)
class RepoActionResult:
    ok: bool
    message: str


_MELD_SNAPSHOT_RETENTION_SECONDS = 48 * 60 * 60


def _resolve_target(workspace_root: Path, target_name: str) -> tuple[Config, ResolvedRepoTarget]:
    config = load_config(workspace_root)
    target = resolve_repo_target(target_name, config=config)
    return config, target


def _representative_project(config: Config, target: ResolvedRepoTarget) -> Project | None:
    projects = [
        config.defined_projects[project_id]
        for project_id in target.project_ids
        if project_id in config.defined_projects
    ]
    if not projects:
        return None
    for project in projects:
        if not project.quarantine:
            return project
    return projects[0]


def _configured_difftool_name(repo_root: Path) -> str | None:
    if shutil.which("meld") is not None:
        return "meld"

    result = subprocess.run(
        ["git", "config", "--get", "diff.tool"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    tool_name = result.stdout.strip()
    if tool_name:
        return tool_name
    if shutil.which("opendiff") is not None:
        return "opendiff"
    return None


def _cleanup_old_meld_snapshots(snapshot_root: Path) -> None:
    if not snapshot_root.is_dir():
        return
    cutoff = time.time() - _MELD_SNAPSHOT_RETENTION_SECONDS
    for child in snapshot_root.iterdir():
        try:
            child_stat = child.stat()
        except OSError:
            continue
        if child_stat.st_mtime >= cutoff:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


def _create_meld_snapshot_dir(repo_root: Path, config: Config) -> Path:
    snapshot_root = Path(tempfile.gettempdir()) / "dev-meld-diffs"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    _cleanup_old_meld_snapshots(snapshot_root)
    snapshot_dir = Path(tempfile.mkdtemp(prefix=f"{repo_root.name}-", dir=snapshot_root))
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=repo_root,
        env=git_subprocess_env(config),
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        return snapshot_dir

    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(snapshot_dir, filter="data")
    return snapshot_dir


def open_repo_in_difftool(workspace_root: Path, repo_root: Path) -> RepoActionResult:
    config = load_config(workspace_root)
    tool_name = _configured_difftool_name(repo_root)
    if tool_name == "meld":
        snapshot_dir = _create_meld_snapshot_dir(repo_root, config)
        command = ["meld", str(snapshot_dir), str(repo_root)]
    else:
        command = ["git", "difftool"]
        if tool_name is not None:
            command.extend(["--tool", tool_name])
        command.extend(["--dir-diff", "--no-prompt", "HEAD"])

    try:
        subprocess.Popen(
            command,
            cwd=repo_root,
            env=git_subprocess_env(config),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as ex:
        return RepoActionResult(ok=False, message=f"{repo_root.name}: failed to open difftool ({ex})")

    tool_summary = "meld" if tool_name == "meld" else (tool_name if tool_name is not None else "git difftool")
    return RepoActionResult(ok=True, message=f"{repo_root.name}: opened difftool ({tool_summary})")


def commit_repo_target(workspace_root: Path, target_name: str) -> RepoActionResult:
    config, target = _resolve_target(workspace_root, target_name)
    if config.openai_key is None:
        return RepoActionResult(
            ok=False,
            message=f"{target.name}: OpenAI key is required for commit generation",
        )

    project = _representative_project(config, target)
    if project is None:
        return RepoActionResult(ok=False, message=f"{target.name}: no project found for repo commit")

    try:
        repo = Repo(target.path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError) as ex:
        return RepoActionResult(ok=False, message=f"{target.name}: failed to open git repo ({ex})")

    try:
        dirty_before = repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=False)
        commit_repo_changes(
            project=project,
            repo=repo,
            openai_key=config.openai_key,
            interactive=False,
            add_files=True,
        )
        dirty_after = repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=False)
    finally:
        repo.close()

    if not dirty_before:
        return RepoActionResult(ok=True, message=f"{target.name}: nothing to commit")
    if dirty_after:
        return RepoActionResult(ok=False, message=f"{target.name}: commit finished but local changes remain")
    return RepoActionResult(ok=True, message=f"{target.name}: committed local changes")


def push_repo_target(workspace_root: Path, target_name: str) -> RepoActionResult:
    config, target = _resolve_target(workspace_root, target_name)

    try:
        repo = Repo(target.path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError) as ex:
        return RepoActionResult(ok=False, message=f"{target.name}: failed to open git repo ({ex})")

    try:
        with configured_git_ssh(repo.git, config):
            repo.git.push("origin", "master")
            repo.git.push(tags=True)
    except GitCommandError as ex:
        repo.close()
        return RepoActionResult(ok=False, message=f"{target.name}: push failed ({ex})")

    repo.close()
    return RepoActionResult(ok=True, message=f"{target.name}: pushed origin/master and tags")


__all__ = [
    "RepoActionResult",
    "commit_repo_target",
    "open_repo_in_difftool",
    "push_repo_target",
]
