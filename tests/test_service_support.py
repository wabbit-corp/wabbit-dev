from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from dev.repo_status import RepoStatusRecord, RepoTrackingState
from dev.service_support import (
    STALE_DIRTY_AFTER,
    build_monitor_snapshot,
    format_local_timestamp,
    format_tracking_status,
    icon_for_snapshot,
    load_dashboard_snapshot_summary,
    load_monitor_snapshot,
    repo_check_spacing_seconds,
    service_paths_for_workspace,
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


def test_build_monitor_snapshot_carries_tracking_state(tmp_path: Path) -> None:
    checked_at = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)
    refreshed_at = checked_at - timedelta(minutes=7)

    snapshot = build_monitor_snapshot(
        tmp_path,
        [
            RepoStatusRecord(
                name="tracked",
                path=(tmp_path / "tracked").resolve(),
                staged_changes=("README.md",),
                unstaged_changes=(),
                untracked_files=(),
                oldest_dirty_timestamp=checked_at - timedelta(minutes=15),
                tracking=RepoTrackingState(
                    branch_name="master",
                    upstream_name="origin/master",
                    ahead_count=2,
                    behind_count=1,
                ),
                tracking_refreshed_at=refreshed_at,
            )
        ],
        checked_at=checked_at,
    )

    repo = snapshot.repos[0]
    assert repo.branch_name == "master"
    assert repo.upstream_name == "origin/master"
    assert repo.ahead_count == 2
    assert repo.behind_count == 1
    assert repo.tracking_refreshed_at == refreshed_at
    assert format_tracking_status(repo) == "master vs origin/master: ahead 2, behind 1"


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


def test_load_monitor_snapshot_accepts_legacy_repo_entries_without_tracking_fields(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    paths = service_paths_for_workspace(workspace_root)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.state_file.write_text(
        json.dumps(
            {
                "workspaceRoot": str(workspace_root),
                "workspaceName": workspace_root.name,
                "checkedAt": "2026-04-12T16:00:00+00:00",
                "totalRepoCount": 1,
                "dirtyRepoCount": 1,
                "staleRepoCount": 0,
                "errorRepoCount": 0,
                "color": "yellow",
                "repos": [
                    {
                        "name": "legacy",
                        "path": str((workspace_root / "legacy").resolve()),
                        "stagedCount": 1,
                        "unstagedCount": 0,
                        "untrackedCount": 0,
                        "dirty": True,
                        "dirtySince": "2026-04-12T15:45:00+00:00",
                        "error": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = load_monitor_snapshot(paths)

    assert snapshot is not None
    assert snapshot.repos[0].name == "legacy"
    assert snapshot.repos[0].upstream_name is None
    assert snapshot.repos[0].tracking_refreshed_at is None


def test_service_paths_for_workspace_include_dashboard_artifacts(tmp_path: Path) -> None:
    paths = service_paths_for_workspace(tmp_path / "workspace")

    assert paths.dashboard_pid_file.name == "dashboard.pid.json"
    assert paths.dashboard_stdout_log.name == "dashboard.stdout.log"
    assert paths.dashboard_stderr_log.name == "dashboard.stderr.log"


def test_load_dashboard_snapshot_summary_reads_dashboard_state(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    paths = service_paths_for_workspace(workspace_root)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.dashboard_state_file.write_text(
        json.dumps(
            {
                "workspaceRoot": str(workspace_root),
                "workspaceName": workspace_root.name,
                "updatedAt": "2026-04-12T16:10:00+00:00",
                "intervalSeconds": 60,
                "dirtyRepoCount": 2,
                "publishableRepoCount": 3,
                "repos": [
                    {"name": "alpha"},
                    {"name": "beta"},
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = load_dashboard_snapshot_summary(paths)

    assert summary is not None
    assert summary.workspace_name == "workspace"
    assert summary.dirty_repo_count == 2
    assert summary.publishable_repo_count == 3
    assert summary.repo_count == 2


def test_repo_check_spacing_seconds_spreads_interval_across_repo_count() -> None:
    assert repo_check_spacing_seconds(60, 3) == 20.0


def test_repo_check_spacing_seconds_has_small_positive_floor() -> None:
    assert repo_check_spacing_seconds(1, 100) == 0.1
