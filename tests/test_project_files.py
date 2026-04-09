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
from dev.config import OwnershipType


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
                '<img src=".banner.png"/>',
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
                '<img src=".banner.png"/>',
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
