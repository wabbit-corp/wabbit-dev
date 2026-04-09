from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dev.config import GradleProject, OwnershipType, Version
from dev.project_layout import (
    SetupOwnedPathMatcher,
    TransientPathMatcher,
    cleanup_misplaced_legal_files,
    find_misplaced_legal_files,
)


@dataclass
class _FakeProject:
    path: Path
    ownership: OwnershipType
    test_license: str | None = None
    repo_root: Path | None = None

    @property
    def effective_repo_root(self) -> Path:
        return self.repo_root or self.path


def _make_gradle_project(path: Path, *, repo_root: Path | None = None, test_license: str | None = None) -> GradleProject:
    return GradleProject(
        path=path,
        group_name="one.wabbit",
        name=path.name,
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license="MIT",
        quarantine=False,
        publish=False,
        github_repo=None,
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        platforms=["jvm", "linuxX64"],
        source_set_dependencies={},
        repo_root=repo_root,
        test_license=test_license,
    )


def test_find_misplaced_legal_files_flags_nested_non_test_legal_docs(tmp_path: Path) -> None:
    project = _FakeProject(path=tmp_path, ownership=OwnershipType.WABBIT, test_license="LicenseRef-Wabbit-Public-Test-License")
    (tmp_path / "LICENSE.md").write_text("root\n", encoding="utf-8")
    (tmp_path / "legal" / "cla" / "v1.0.0").mkdir(parents=True)
    (tmp_path / "legal" / "cla" / "v1.0.0" / "CLA.md").write_text("cla\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "LICENSE.md").write_text("test\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "LICENSE.md").write_text("stale\n", encoding="utf-8")
    (tmp_path / "nested" / "CLA.md").write_text("stale\n", encoding="utf-8")

    misplaced = find_misplaced_legal_files(tmp_path, [project])

    assert [path.relative_to(tmp_path).as_posix() for path in misplaced] == [
        "nested/CLA.md",
        "nested/LICENSE.md",
    ]


def test_cleanup_misplaced_legal_files_deletes_files_and_empty_directories(tmp_path: Path) -> None:
    project = _FakeProject(path=tmp_path, ownership=OwnershipType.WABBIT)
    stale_dir = tmp_path / "old" / "legal"
    stale_dir.mkdir(parents=True)
    stale_file = stale_dir / "CODE_OF_CONDUCT.md"
    stale_file.write_text("stale\n", encoding="utf-8")

    cleaned = cleanup_misplaced_legal_files(tmp_path, [project])

    assert cleaned == [stale_file]
    assert not stale_file.exists()
    assert not stale_dir.exists()


def test_find_misplaced_legal_files_allows_gradle_kmp_test_roots_in_subprojects(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    child = repo_root / "kmp-lib"
    (child / "src" / "commonTest").mkdir(parents=True)
    (child / "src" / "commonTest" / "LICENSE.md").write_text("test\n", encoding="utf-8")
    (child / "src" / "androidUnitTest").mkdir(parents=True)
    (child / "src" / "androidUnitTest" / "LICENSE.md").write_text("test\n", encoding="utf-8")
    (child / "CLA.md").write_text("stale\n", encoding="utf-8")

    root_project = _make_gradle_project(repo_root, test_license="LicenseRef-Wabbit-Public-Test-License")
    child_project = _make_gradle_project(
        child,
        repo_root=repo_root,
        test_license="LicenseRef-Wabbit-Public-Test-License",
    )

    misplaced = find_misplaced_legal_files(repo_root, [root_project, child_project])

    assert [path.relative_to(repo_root).as_posix() for path in misplaced] == ["kmp-lib/CLA.md"]


def test_setup_owned_path_matcher_matches_expected_test_license_outputs(tmp_path: Path) -> None:
    project = _FakeProject(
        path=tmp_path,
        ownership=OwnershipType.WABBIT,
        test_license="LicenseRef-Wabbit-Public-Test-License-1.1",
    )
    (tmp_path / "LICENSES").mkdir()
    extra_license = tmp_path / "LICENSES" / "LicenseRef-Wabbit-Public-Test-License-1.1.md"
    extra_license.write_text("test license\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    test_copy = tmp_path / "tests" / "LICENSE.md"
    test_copy.write_text("test license\n", encoding="utf-8")
    ordinary_file = tmp_path / "notes.txt"
    ordinary_file.write_text("notes\n", encoding="utf-8")

    matcher = SetupOwnedPathMatcher(tmp_path, projects=[project])

    assert matcher.matches(extra_license, is_dir=False) is True
    assert matcher.matches(test_copy, is_dir=False) is True
    assert matcher.matches(ordinary_file, is_dir=False) is False


def test_setup_owned_path_matcher_matches_fully_generated_directories(tmp_path: Path) -> None:
    generated_dir = tmp_path / ".github" / "ISSUE_TEMPLATE"
    generated_dir.mkdir(parents=True)
    (generated_dir / "bug_report.yml").write_text(
        "# Generated by app-wabbit-dev setup. Do not edit by hand.\n# managed-integrity-v1: 11111111\n",
        encoding="utf-8",
    )
    (generated_dir / "feature_request.yml").write_text(
        "# Generated by app-wabbit-dev setup. Do not edit by hand.\n# managed-integrity-v1: 11111111\n",
        encoding="utf-8",
    )
    ordinary_dir = tmp_path / "docs"
    ordinary_dir.mkdir()
    (ordinary_dir / "README.md").write_text("manual\n", encoding="utf-8")

    matcher = SetupOwnedPathMatcher(tmp_path, projects=[])

    assert matcher.matches(generated_dir, is_dir=True) is True
    assert matcher.matches(ordinary_dir, is_dir=True) is False


def test_find_misplaced_legal_files_allows_repo_root_legal_files_without_root_project(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    child = repo_root / "lib"
    child.mkdir(parents=True)
    (repo_root / "LICENSE.md").write_text("license\n", encoding="utf-8")
    (repo_root / "legal" / "cla" / "v1.0.0").mkdir(parents=True)
    (repo_root / "legal" / "cla" / "v1.0.0" / "CLA.md").write_text("cla\n", encoding="utf-8")

    child_project = _make_gradle_project(child, repo_root=repo_root)

    misplaced = find_misplaced_legal_files(repo_root, [child_project])

    assert misplaced == []


def test_transient_path_matcher_skips_tmp_and_backup_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    tmp_dir = repo_root / "tmp-release"
    tmp_dir.mkdir()
    tmp_file = repo_root / "tmp.notes.txt"
    tmp_file.write_text("tmp\n", encoding="utf-8")
    bak_file = repo_root / "notes.txt.bak"
    bak_file.write_text("bak\n", encoding="utf-8")

    matcher = TransientPathMatcher(repo_root, projects=[])

    assert matcher.matches(tmp_dir, is_dir=True) is True
    assert matcher.matches(tmp_file, is_dir=False) is True
    assert matcher.matches(bak_file, is_dir=False) is True


def test_transient_path_matcher_skips_project_build_temp_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    project = _make_gradle_project(repo_root)
    build_file = repo_root / "build" / "generated" / "trace.bin"
    build_file.parent.mkdir(parents=True)
    build_file.write_text("x\n", encoding="utf-8")

    matcher = TransientPathMatcher(repo_root, projects=[project])

    assert matcher.matches(build_file, is_dir=False) is True
