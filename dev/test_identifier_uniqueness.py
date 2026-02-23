from __future__ import annotations

from pathlib import Path

from dev.checks.identifier_uniqueness import UniqueIdentifiersCheck


def test_identifier_uniqueness_handles_non_utf8_bytes(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()

    # Invalid UTF-8 byte (0xB1) in a source-like file extension.
    (project_path / "broken.php").write_bytes(b'<?php $x = "\xb1"; ?>\n')

    issues = UniqueIdentifiersCheck().check(project_path, project=None)
    assert issues == []


def test_identifier_uniqueness_still_reports_duplicates(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()

    duplicate = '"2ecbfb56-85d7-4e32-84cb-b2f175acf240"'
    (project_path / "a.py").write_text(f"x = {duplicate}\n", encoding="utf-8")
    (project_path / "b.py").write_text(f"y = {duplicate}\n", encoding="utf-8")

    issues = UniqueIdentifiersCheck().check(project_path, project=None)
    assert len(issues) == 1
    assert issues[0].issue_type.id == "E_DUPLICATE_IDENTIFIER"
    assert issues[0].location is not None
    assert issues[0].location.path == project_path / "b.py"


def test_identifier_uniqueness_respects_checkignore_without_repo(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / ".checkignore").write_text("*.py\n", encoding="utf-8")

    duplicate = '"2ecbfb56-85d7-4e32-84cb-b2f175acf240"'
    (project_path / "a.py").write_text(f"x = {duplicate}\n", encoding="utf-8")
    (project_path / "b.py").write_text(f"y = {duplicate}\n", encoding="utf-8")

    issues = UniqueIdentifiersCheck().check(project_path, project=None)
    assert issues == []


def test_identifier_uniqueness_checkignore_overrides_gitignore(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / ".git").mkdir()
    (project_path / ".gitignore").write_text("*.py\n", encoding="utf-8")
    (project_path / ".checkignore").write_text("!a.py\n", encoding="utf-8")

    duplicate = '"2ecbfb56-85d7-4e32-84cb-b2f175acf240"'
    (project_path / "a.py").write_text(f"x = {duplicate}\n", encoding="utf-8")
    (project_path / "b.txt").write_text(f"y = {duplicate}\n", encoding="utf-8")

    issues = UniqueIdentifiersCheck().check(project_path, project=None)
    assert len(issues) == 1
    assert issues[0].issue_type.id == "E_DUPLICATE_IDENTIFIER"
