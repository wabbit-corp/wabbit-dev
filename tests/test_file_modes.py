from __future__ import annotations

from pathlib import Path

import pytest

from dev.checks import file_modes
from dev.checks.base import FileContext


def test_find_and_process_files_does_not_delete_ds_store_without_fix(tmp_path: Path) -> None:
    ds_store = tmp_path / ".DS_Store"
    ds_store.write_text("metadata\n", encoding="utf-8")

    suspicious_files, fixed_count, error_count = file_modes.find_and_process_files(str(tmp_path), fix_files=False)

    assert suspicious_files == []
    assert fixed_count == 0
    assert error_count == 0
    assert ds_store.exists()


def test_find_and_process_files_handles_ds_store_delete_errors_in_fix_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ds_store = tmp_path / ".DS_Store"
    ds_store.write_text("metadata\n", encoding="utf-8")

    def fail_remove(path: str) -> None:
        raise PermissionError(f"cannot remove {path}")

    monkeypatch.setattr(file_modes.os, "remove", fail_remove)

    suspicious_files, fixed_count, error_count = file_modes.find_and_process_files(str(tmp_path), fix_files=True)

    assert suspicious_files == []
    assert fixed_count == 0
    assert error_count == 1
    assert ds_store.exists()


def test_suspicious_executable_file_mode_check_reports_and_fixes_file(tmp_path: Path) -> None:
    target = tmp_path / "suspicious.txt"
    target.write_text("echo hi\n", encoding="utf-8")
    target.chmod(0o755)

    ctx = FileContext(check_name="SuspiciousExecutableFileModeCheck", path=target)

    file_modes.SuspiciousExecutableFileModeCheck().check(ctx)

    issues = list(ctx.issues)
    assert [issue.issue_type for issue in issues] == [file_modes.E_SUSPICIOUS_EXECUTABLE_FILE_MODE]
    issue = issues[0]
    assert issue.fix is not None

    issue.fix()

    assert not file_modes.is_executable(str(target))
