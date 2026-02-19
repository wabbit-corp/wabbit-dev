from pathlib import Path
import sys

import pytest


def _make_gradle_project(
    *,
    group_name: str | None = "com.example",
    version: str | None = "1.2.3",
):
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    from dev.config import GradleProject, OwnershipType, Version

    return GradleProject(
        path=Path("/tmp/sample"),
        group_name=group_name,
        name="sample",
        version=Version.parse(version) if version else None,
        description=None,
        authors=[],
        license=None,
        quarantine=False,
        publish=False,
        github_repo=None,
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
    )


def test_gradle_project_artifact_name_uses_configured_group() -> None:
    project = _make_gradle_project(group_name="io.example", version="2.0.1")

    assert project.artifact_name == "io.example:sample:2.0.1"


def test_gradle_project_artifact_name_requires_group_name() -> None:
    project = _make_gradle_project(group_name="", version="1.0.0")

    with pytest.raises(ValueError, match="missing group_name"):
        _ = project.artifact_name


def test_gradle_project_artifact_name_requires_version() -> None:
    project = _make_gradle_project(group_name="io.example", version=None)

    with pytest.raises(ValueError, match="missing version"):
        _ = project.artifact_name
