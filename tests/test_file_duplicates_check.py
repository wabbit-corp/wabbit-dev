from __future__ import annotations

from pathlib import Path

from dev.checks.file_duplicates import (
    E_DUPLICATE_DIRECTORY_TREE,
    E_DUPLICATE_FILE,
    DuplicateFilesCheck,
)


def test_duplicate_files_check_reports_duplicate_files(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()

    duplicate_left = left / "a.txt"
    duplicate_right = right / "b.txt"
    duplicate_left.write_text("same\n", encoding="utf-8")
    duplicate_right.write_text("same\n", encoding="utf-8")

    issues = DuplicateFilesCheck().check(tmp_path, None)

    file_issue = next(issue for issue in issues if issue.issue_type == E_DUPLICATE_FILE)
    assert file_issue.location is not None
    assert file_issue.location.path == duplicate_left.resolve()
    assert file_issue.data == {
        "duplicate_count": 2,
        "duplicate_paths": f"{duplicate_left.resolve()}, {duplicate_right.resolve()}",
        "total_size": 10,
        "per_file_size": 5,
        "other_paths": [str(duplicate_right.resolve())],
    }


def test_duplicate_files_check_reports_duplicate_directory_trees(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    (left / "nested").mkdir(parents=True)
    (right / "nested").mkdir(parents=True)

    (left / "a.txt").write_text("alpha\n", encoding="utf-8")
    (right / "a.txt").write_text("alpha\n", encoding="utf-8")
    (left / "nested" / "b.txt").write_text("beta\n", encoding="utf-8")
    (right / "nested" / "b.txt").write_text("beta\n", encoding="utf-8")

    issues = DuplicateFilesCheck().check(tmp_path, None)

    tree_issue = next(issue for issue in issues if issue.issue_type == E_DUPLICATE_DIRECTORY_TREE)
    assert tree_issue.location is not None
    assert tree_issue.location.path == left.resolve()
    assert tree_issue.data == {
        "duplicate_count": 2,
        "duplicate_paths": f"{left.resolve()}, {right.resolve()}",
        "tree_size": 11,
        "file_count": 2,
        "directory_count": 2,
        "match_kind": "strong",
        "other_paths": [str(right.resolve())],
    }
