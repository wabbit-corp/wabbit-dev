from pathlib import Path
from types import SimpleNamespace
import sys


def _make_python_project(path: Path):
    from dev.config import OwnershipType, PythonProject

    return PythonProject(
        path=path,
        name="pkg",
        version=None,
        description=None,
        authors=[],
        license=None,
        github_repo=None,
        requires_python=None,
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        raw_features=[],
        resolved_features={},
        line_length=None,
        target_version=None,
        source_sets=[],
        test_paths=[],
        ruff_per_file_ignores={},
        deptry_package_map={},
        deptry_per_rule_ignores={},
        deptry_auto_map=False,
        importlinter_root_packages=[],
        importlinter_layers=[],
        importlinter_contracts=[],
        coverage_source=[],
        coverage_omit=[],
        coverage_fail_under=None,
        coverage_precision=None,
        coverage_branch=None,
        coverage_show_missing=None,
        coverage_skip_empty=None,
        coverage_xml_output=None,
        quarantine=False,
        publish=False,
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
    )


def test_setup_project_creates_directory_before_project_setup(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    from dev.config import PythonProject
    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "missing" / "pkg")
    called = False

    def fake_setup_python_project(ctx: object, python_project: PythonProject, interactive: bool = True) -> None:
        nonlocal called
        called = True
        assert python_project.path.exists()
        assert python_project.path.is_dir()

    monkeypatch.setattr(setup_module, "setup_python_project", fake_setup_python_project)

    ctx = SimpleNamespace(
        known_repo_names=[],
        mode=setup_module.RepoSetupMode.LOCAL,
        config=SimpleNamespace(
            default_git_user_email="test@example.com",
            default_git_user_name="Test User",
        ),
    )

    setup_module.setup_project(ctx, project, interactive=False)
    assert called
