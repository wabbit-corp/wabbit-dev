from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from dev.repo_status import RepoStatusRecord
from dev.service_support import (
    STALE_DIRTY_AFTER,
    build_monitor_snapshot,
    format_local_timestamp,
    icon_for_snapshot,
    repo_check_spacing_seconds,
)


def test_build_monitor_snapshot_marks_stale_dirty_repos_red(tmp_path: Path) -> None:
    checked_at = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)
    repo_path = (tmp_path / "alpha").resolve()
    oldest_dirty_timestamp = checked_at - STALE_DIRTY_AFTER - timedelta(minutes=5)

    snapshot = build_monitor_snapshot(
        tmp_path,
        [
            RepoStatusRecord(
                name="alpha",
                path=repo_path,
                staged_changes=("README.md",),
                unstaged_changes=(),
                untracked_files=(),
                oldest_dirty_timestamp=oldest_dirty_timestamp,
            )
        ],
        checked_at=checked_at,
    )

    assert snapshot.dirty_repo_count == 1
    assert snapshot.stale_repo_count == 1
    assert snapshot.error_repo_count == 0
    assert snapshot.color == "red"
    assert snapshot.repos[0].dirty_since == oldest_dirty_timestamp
    assert icon_for_snapshot(snapshot) == "🔴 1"


def test_build_monitor_snapshot_uses_oldest_dirty_timestamp_from_repo_status(tmp_path: Path) -> None:
    checked_at = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)
    repo_path = (tmp_path / "beta").resolve()
    oldest_dirty_timestamp = checked_at - timedelta(hours=2, minutes=30)

    snapshot = build_monitor_snapshot(
        tmp_path,
        [
            RepoStatusRecord(
                name="beta",
                path=repo_path,
                staged_changes=(),
                unstaged_changes=("src/main.py",),
                untracked_files=(),
                oldest_dirty_timestamp=oldest_dirty_timestamp,
            )
        ],
        checked_at=checked_at,
    )

    assert snapshot.dirty_repo_count == 1
    assert snapshot.stale_repo_count == 0
    assert snapshot.color == "yellow"
    assert snapshot.repos[0].dirty_since == oldest_dirty_timestamp


def test_build_monitor_snapshot_sorts_dirty_repos_oldest_first(tmp_path: Path) -> None:
    checked_at = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)
    oldest = checked_at - timedelta(hours=9)
    newer = checked_at - timedelta(hours=1)

    snapshot = build_monitor_snapshot(
        tmp_path,
        [
            RepoStatusRecord(
                name="newer",
                path=(tmp_path / "newer").resolve(),
                staged_changes=("README.md",),
                unstaged_changes=(),
                untracked_files=(),
                oldest_dirty_timestamp=newer,
            ),
            RepoStatusRecord(
                name="clean",
                path=(tmp_path / "clean").resolve(),
                staged_changes=(),
                unstaged_changes=(),
                untracked_files=(),
            ),
            RepoStatusRecord(
                name="older",
                path=(tmp_path / "older").resolve(),
                staged_changes=(),
                unstaged_changes=("src/main.py",),
                untracked_files=(),
                oldest_dirty_timestamp=oldest,
            ),
        ],
        checked_at=checked_at,
    )

    assert [repo.name for repo in snapshot.repos] == ["older", "newer", "clean"]
    assert snapshot.color == "red"


def test_build_monitor_snapshot_clean_workspace_is_green(tmp_path: Path) -> None:
    snapshot = build_monitor_snapshot(tmp_path, [])

    assert snapshot.dirty_repo_count == 0
    assert snapshot.stale_repo_count == 0
    assert snapshot.error_repo_count == 0
    assert snapshot.color == "green"
    assert icon_for_snapshot(snapshot) == "🟢"


def test_format_local_timestamp_uses_requested_timezone() -> None:
    timestamp = datetime(2026, 4, 12, 16, 30, tzinfo=UTC)
    toronto = timezone(timedelta(hours=-4), name="EDT")

    assert format_local_timestamp(timestamp, timezone=toronto) == "2026-04-12 12:30:00 EDT"


def test_repo_check_spacing_seconds_spreads_interval_across_repo_count() -> None:
    assert repo_check_spacing_seconds(60, 3) == 20.0


def test_repo_check_spacing_seconds_has_small_positive_floor() -> None:
    assert repo_check_spacing_seconds(1, 100) == 0.1
