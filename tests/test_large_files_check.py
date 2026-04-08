from __future__ import annotations

from pathlib import Path

from dev.checks.base import FileContext
from dev.checks.large_files import (
    E_CHECKED_IN_BINARY_DEPENDENCY,
    E_LARGE_FILE,
    CheckedInBinaryDependencyCheck,
    LargeFileCheck,
)


def test_large_file_check_reports_files_over_threshold(tmp_path: Path) -> None:
    target = tmp_path / "artifact.bin"
    target.write_bytes(b"12345")

    ctx = FileContext(check_name="LargeFileCheck", path=target)
    LargeFileCheck(max_size_bytes=4).check(ctx)

    assert [issue.issue_type for issue in ctx.issues] == [E_LARGE_FILE]
    assert ctx.issues.issues[0].data == {
        "size_bytes": 5,
        "max_size_bytes": 4,
    }


def test_large_file_check_ignores_files_within_threshold(tmp_path: Path) -> None:
    target = tmp_path / "small.txt"
    target.write_text("ok\n", encoding="utf-8")

    ctx = FileContext(check_name="LargeFileCheck", path=target)
    LargeFileCheck(max_size_bytes=16).check(ctx)

    assert list(ctx.issues) == []


def test_checked_in_binary_dependency_check_reports_vendor_binary_artifacts(tmp_path: Path) -> None:
    target = tmp_path / "libs" / "driver.jar"
    target.parent.mkdir()
    target.write_bytes(b"jar-bytes")

    ctx = FileContext(check_name="CheckedInBinaryDependencyCheck", path=target)
    CheckedInBinaryDependencyCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues] == [E_CHECKED_IN_BINARY_DEPENDENCY]


def test_checked_in_binary_dependency_check_ignores_regular_binaries_outside_dependency_dirs(tmp_path: Path) -> None:
    target = tmp_path / "build" / "app.jar"
    target.parent.mkdir()
    target.write_bytes(b"jar-bytes")

    ctx = FileContext(check_name="CheckedInBinaryDependencyCheck", path=target)
    CheckedInBinaryDependencyCheck().check(ctx)

    assert list(ctx.issues) == []
