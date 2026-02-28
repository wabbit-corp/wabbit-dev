from pathlib import Path

import pytest

from dev.build_order import toposort_projects
from dev.config import Dependency, OwnershipType, Project, ProjectDependencyTarget, PythonProject


def _project_dep(name: str) -> Dependency:
    return Dependency(scope=None, target=ProjectDependencyTarget(project=name))


def _make_project(name: str, deps: list[Dependency] | None = None) -> PythonProject:
    return PythonProject(
        path=Path(name),
        name=name,
        version=None,
        description=None,
        authors=[],
        license=None,
        github_repo=None,
        requires_python=None,
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        application=None,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=False,
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=deps or [],
    )


def test_toposort_projects_for_target_includes_dependency_closure_in_order() -> None:
    projects: dict[str, Project] = {
        "core": _make_project("core"),
        "utils": _make_project("utils", [_project_dep("core")]),
        "app": _make_project("app", [_project_dep("utils")]),
        "unrelated": _make_project("unrelated"),
    }

    selected = toposort_projects(projects, target_project="app")

    assert selected == ["core", "utils", "app"]


def test_toposort_projects_for_unknown_target_fails() -> None:
    projects: dict[str, Project] = {"core": _make_project("core")}

    with pytest.raises(ValueError, match="Unknown project"):
        toposort_projects(projects, target_project="missing")


def test_toposort_projects_detects_cycles() -> None:
    projects: dict[str, Project] = {
        "a": _make_project("a", [_project_dep("b")]),
        "b": _make_project("b", [_project_dep("a")]),
    }

    with pytest.raises(ValueError, match="Cyclic project dependency detected"):
        toposort_projects(projects, target_project="a")


def test_toposort_projects_without_target_returns_all_in_defined_order() -> None:
    projects: dict[str, Project] = {
        "b": _make_project("b"),
        "a": _make_project("a"),
        "c": _make_project("c"),
    }

    selected = toposort_projects(projects)

    assert selected == ["b", "a", "c"]


def test_toposort_projects_fails_for_unknown_dependency() -> None:
    projects: dict[str, Project] = {
        "app": _make_project("app", [_project_dep("missing")]),
    }

    with pytest.raises(ValueError, match="depends on unknown project"):
        toposort_projects(projects, target_project="app")
