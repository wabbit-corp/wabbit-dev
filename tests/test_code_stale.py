from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from dev.checks.base import FileContext
from dev.checks.code_stale import E_STALE_TODO, StaleCodeCheck


def test_stale_code_check_uses_git_blame_line_age_when_repo_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "sample.py"
    path.write_text("# TODO old\n# TODO new\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    ctx = FileContext(check_name="StaleCodeCheck", path=path)

    now_timestamp = 2_000_000_000.0
    blame_output = "\n".join(
        [
            "aaaaaaaa 1 1 1",
            "author Old",
            "author-time 1",
            "summary old",
            "filename sample.py",
            "\t# TODO old",
            "bbbbbbbb 2 2 1",
            "author New",
            "author-time 1999999999",
            "summary new",
            "filename sample.py",
            "\t# TODO new",
            "",
        ]
    )

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=blame_output, stderr="")

    monkeypatch.setattr("dev.checks.code_stale.subprocess.run", fake_run)

    check = StaleCodeCheck(todo_age_days=30)
    monkeypatch.setattr(check, "_find_repo_root", lambda _path: tmp_path)

    line_ages = check._line_age_days_by_git_blame(path, now_timestamp=now_timestamp)
    assert line_ages is not None
    assert line_ages[1] > 30
    assert line_ages[2] < 30

    monkeypatch.setattr(check, "_line_age_days_by_git_blame", lambda _path: {1: 100.0, 2: 1.0})
    check.check(ctx)

    assert len(ctx.issues.issues) == 1
    issue = ctx.issues.issues[0]
    assert issue.issue_type == E_STALE_TODO
    assert issue.location is not None
    assert list(issue.location.lines or []) == [1]


def test_stale_code_check_falls_back_to_mtime_when_git_blame_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("# TODO old\n", encoding="utf-8")
    old_timestamp = time.time() - (400 * 86400)
    os.utime(path, (old_timestamp, old_timestamp))
    ctx = FileContext(check_name="StaleCodeCheck", path=path)

    check = StaleCodeCheck(todo_age_days=30)
    check.check(ctx)

    assert len(ctx.issues.issues) == 1
    issue = ctx.issues.issues[0]
    assert issue.issue_type == E_STALE_TODO
    assert issue.location is not None
    assert list(issue.location.lines or []) == [1]
