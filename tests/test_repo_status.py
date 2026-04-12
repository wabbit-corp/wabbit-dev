from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from dev.repo_status import local_tracking_state, oldest_dirty_timestamp_for_paths, status_lists


class _FakeGit:
    def __init__(self, output: str):
        self._output = output

    def status(self, *args: str) -> str:
        return self._output


class _FakeRepo:
    def __init__(self, output: str):
        self.git = _FakeGit(output)


def test_oldest_dirty_timestamp_for_paths_uses_oldest_existing_file(tmp_path: Path) -> None:
    older = tmp_path / "older.txt"
    newer = tmp_path / "newer.txt"
    older.write_text("older\n", encoding="utf-8")
    newer.write_text("newer\n", encoding="utf-8")

    older_timestamp = datetime(2026, 4, 11, 10, 0, tzinfo=UTC).timestamp()
    newer_timestamp = datetime(2026, 4, 12, 9, 0, tzinfo=UTC).timestamp()
    os.utime(older, (older_timestamp, older_timestamp))
    os.utime(newer, (newer_timestamp, newer_timestamp))

    result = oldest_dirty_timestamp_for_paths(tmp_path, ["newer.txt", "older.txt"])

    assert result == datetime.fromtimestamp(older_timestamp, tz=UTC)


def test_oldest_dirty_timestamp_for_paths_ignores_missing_files(tmp_path: Path) -> None:
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    tracked_timestamp = datetime(2026, 4, 12, 8, 0, tzinfo=UTC).timestamp()
    os.utime(tracked, (tracked_timestamp, tracked_timestamp))

    result = oldest_dirty_timestamp_for_paths(tmp_path, ["missing.txt", "tracked.txt"])

    assert result == datetime.fromtimestamp(tracked_timestamp, tz=UTC)


def test_oldest_dirty_timestamp_for_paths_returns_none_when_no_files_exist(tmp_path: Path) -> None:
    result = oldest_dirty_timestamp_for_paths(tmp_path, ["missing.txt"])

    assert result is None


def test_status_lists_reads_porcelain_branch_output() -> None:
    repo = _FakeRepo(
        "\n".join(
            [
                "## master...origin/master [ahead 2, behind 1]",
                " M src/dirty.py",
                "M  src/staged.py",
                "?? notes.txt",
            ]
        )
    )

    staged, unstaged, untracked = status_lists(repo)

    assert staged == ["src/staged.py"]
    assert unstaged == ["src/dirty.py"]
    assert untracked == ["notes.txt"]


def test_local_tracking_state_parses_branch_and_ahead_behind_counts() -> None:
    repo = _FakeRepo("## feature/demo...origin/feature/demo [ahead 3, behind 2]")

    tracking = local_tracking_state(repo)

    assert tracking.branch_name == "feature/demo"
    assert tracking.upstream_name == "origin/feature/demo"
    assert tracking.ahead_count == 3
    assert tracking.behind_count == 2


def test_local_tracking_state_handles_detached_head_without_upstream() -> None:
    repo = _FakeRepo("## HEAD (no branch)")

    tracking = local_tracking_state(repo)

    assert tracking.branch_name is None
    assert tracking.upstream_name is None
    assert tracking.ahead_count is None
    assert tracking.behind_count is None
