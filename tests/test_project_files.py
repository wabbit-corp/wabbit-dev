from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dev.checks.project_files import (
    E_MISSING_CLA,
    E_MISSING_CLA_SIMPLE,
    E_MISSING_GITIGNORE,
    E_MISSING_LICENSE,
    GenericProjectStructureCheck,
)
from dev.config import DataProject, OwnershipType

_CANONICAL_BANNER = "![](./.meta/github-project-banner.png)"
_LEGACY_BANNER = '<img src=".banner.png"/>'


@dataclass
class _FakeProject:
    path: Path
    repo_root: Path
    ownership: OwnershipType = OwnershipType.WABBIT
    project_id: str | None = "demo"

    @property
    def effective_repo_root(self) -> Path:
        return self.repo_root


def test_generic_project_structure_check_does_not_require_repo_legal_files_in_subprojects(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    project_path = repo_root / "subproject"
    project_path.mkdir(parents=True)
    (project_path / "README.md").write_text(
        "\n".join(
            [
                _LEGACY_BANNER,
                '<img src="https://img.shields.io/example"/>',
                "## 🚀 Installation",
                "## 🚀 Usage",
                "## Licensing",
                "## Contributing",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (project_path / ".gitignore").write_text("build/\n", encoding="utf-8")

    issues = GenericProjectStructureCheck().check(
        project_path,
        _FakeProject(path=project_path, repo_root=repo_root),
    )

    issue_ids = {issue.issue_type.id for issue in issues}
    assert E_MISSING_LICENSE.id not in issue_ids
    assert E_MISSING_CLA.id not in issue_ids
    assert E_MISSING_CLA_SIMPLE.id not in issue_ids


def test_generic_project_structure_check_marks_generated_repo_files_fixable_for_wabbit_projects(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    (repo_root / "README.md").write_text(
        "\n".join(
            [
                _CANONICAL_BANNER,
                '<img src="https://img.shields.io/example"/>',
                "## 🚀 Installation",
                "## 🚀 Usage",
                "## Licensing",
                "## Contributing",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    issues = GenericProjectStructureCheck().check(
        repo_root,
        _FakeProject(path=repo_root, repo_root=repo_root),
    )

    fixable_ids = {issue.issue_type.id for issue in issues if issue.fix is not None}
    assert E_MISSING_LICENSE.id in fixable_ids
    assert E_MISSING_CLA.id in fixable_ids
    assert E_MISSING_CLA_SIMPLE.id in fixable_ids
    assert E_MISSING_GITIGNORE.id in fixable_ids


def test_generic_project_structure_check_does_not_require_license_or_cla_for_data_projects(tmp_path: Path) -> None:
    repo_root = tmp_path / "data-demo"
    repo_root.mkdir(parents=True)
    (repo_root / "README.md").write_text(
        "\n".join(
            [
                _CANONICAL_BANNER,
                '<img src="https://img.shields.io/example"/>',
                "## 🚀 Installation",
                "## 🚀 Usage",
                "## Licensing",
                "## Contributing",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / ".gitignore").write_text("generated/\n", encoding="utf-8")

    project = DataProject(
        path=repo_root,
        name="data-demo",
        description="Data repository",
        authors=[],
        quarantine=False,
        publish=False,
        license="AGPL",
        github_repo=None,
        ownership=OwnershipType.WABBIT,
        version=None,
        resolved_dependencies=[],
        project_id="data-demo",
    )

    issues = GenericProjectStructureCheck().check(repo_root, project)

    issue_ids = {issue.issue_type.id for issue in issues}
    assert E_MISSING_LICENSE.id not in issue_ids
    assert E_MISSING_CLA.id not in issue_ids
    assert E_MISSING_CLA_SIMPLE.id not in issue_ids


def test_generic_project_structure_check_accepts_legacy_banner_reference(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    (repo_root / "README.md").write_text(
        "\n".join(
            [
                _LEGACY_BANNER,
                '<img src="https://img.shields.io/example"/>',
                "## 🚀 Installation",
                "## 🚀 Usage",
                "## Licensing",
                "## Contributing",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / ".gitignore").write_text("generated/\n", encoding="utf-8")

    issues = GenericProjectStructureCheck().check(
        repo_root,
        _FakeProject(path=repo_root, repo_root=repo_root),
    )

    issue_ids = {issue.issue_type.id for issue in issues}
    assert "E_README_NO_BANNER" not in issue_ids
