import sys
from collections import OrderedDict
from pathlib import Path

import pytest


def _load_build_order_module():
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    import dev.build_order as build_order_module

    return build_order_module


class _FakeProject:
    def __init__(self, name: str, resolved_dependencies: list[object] | None = None) -> None:
        self.name = name
        self.resolved_dependencies = resolved_dependencies or []


def _project_dep(name: str):
    from dev.config import Dependency, ProjectDependencyTarget

    return Dependency(scope=None, target=ProjectDependencyTarget(project=name))


def test_toposort_projects_for_target_includes_dependency_closure_in_order() -> None:
    build_order_module = _load_build_order_module()

    projects = OrderedDict(
        [
            ("core", _FakeProject("core")),
            ("utils", _FakeProject("utils", [_project_dep("core")])),
            ("app", _FakeProject("app", [_project_dep("utils")])),
            ("unrelated", _FakeProject("unrelated")),
        ]
    )

    selected = build_order_module.toposort_projects(projects, target_project="app")

    assert selected == ["core", "utils", "app"]


def test_toposort_projects_for_unknown_target_fails() -> None:
    build_order_module = _load_build_order_module()

    projects = OrderedDict([("core", _FakeProject("core"))])

    with pytest.raises(ValueError, match="Unknown project"):
        build_order_module.toposort_projects(projects, target_project="missing")


def test_toposort_projects_detects_cycles() -> None:
    build_order_module = _load_build_order_module()

    projects = OrderedDict(
        [
            ("a", _FakeProject("a", [_project_dep("b")])),
            ("b", _FakeProject("b", [_project_dep("a")])),
        ]
    )

    with pytest.raises(ValueError, match="Cyclic project dependency detected"):
        build_order_module.toposort_projects(projects, target_project="a")


def test_toposort_projects_without_target_returns_all_in_defined_order() -> None:
    build_order_module = _load_build_order_module()

    projects = OrderedDict(
        [
            ("b", _FakeProject("b")),
            ("a", _FakeProject("a")),
            ("c", _FakeProject("c")),
        ]
    )

    selected = build_order_module.toposort_projects(projects)

    assert selected == ["b", "a", "c"]


def test_toposort_projects_fails_for_unknown_dependency() -> None:
    build_order_module = _load_build_order_module()

    projects = OrderedDict(
        [
            ("app", _FakeProject("app", [_project_dep("missing")])),
        ]
    )

    with pytest.raises(ValueError, match="depends on unknown project"):
        build_order_module.toposort_projects(projects, target_project="app")
