from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from dev.repo_status import oldest_dirty_timestamp_for_paths


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
