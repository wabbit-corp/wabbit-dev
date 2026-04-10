from __future__ import annotations

from pathlib import Path

from dev.config import OwnershipType, Project


def _setup_target_for_project(project: Project) -> str:
    return project.project_id or str(project.path.resolve())


def _setup_target_for_repo_root(repo_root: Path) -> str:
    return str(repo_root.resolve())


def can_regenerate_with_setup(project: Project | None) -> bool:
    return project is not None and project.ownership == OwnershipType.WABBIT


def rerun_setup_for_project(project: Project) -> None:
    from dev.tasks.setup import setup
    from dev.tasks.setup_common import RepoSetupMode

    rc = setup(
        RepoSetupMode.DEV,
        interactive=False,
        projects=[_setup_target_for_project(project)],
    )
    if rc != 0:
        raise RuntimeError(f"dev setup failed for {_setup_target_for_project(project)!r}")


def rerun_setup_for_repo_root(repo_root: Path) -> None:
    from dev.tasks.setup import setup
    from dev.tasks.setup_common import RepoSetupMode

    rc = setup(
        RepoSetupMode.DEV,
        interactive=False,
        projects=[_setup_target_for_repo_root(repo_root)],
    )
    if rc != 0:
        raise RuntimeError(f"dev setup failed for {_setup_target_for_repo_root(repo_root)!r}")
