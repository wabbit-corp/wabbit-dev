from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from dev.service_db import (
    load_backup_repo_summaries,
    load_dashboard_repo_cache,
    load_recent_dashboard_actions,
    load_recent_backup_runs,
    note_backup_attempt,
    record_dashboard_action,
    record_backup_run,
    save_dashboard_repo_cache,
    update_backup_repo_summary,
)
from dev.service_support import service_paths_for_workspace


def test_backup_summary_persists_to_service_db(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    repo_path = workspace_root / "app-wabbit-dev"
    repo_path.mkdir()
    paths = service_paths_for_workspace(workspace_root)

    attempted_at = datetime(2026, 4, 12, 18, 0, tzinfo=UTC)
    finished_at = attempted_at + timedelta(minutes=2)

    note_backup_attempt(paths, "app-wabbit-dev", repo_path, attempted_at=attempted_at)
    update_backup_repo_summary(
        paths,
        repo_name="app-wabbit-dev",
        repo_path=repo_path,
        last_attempted_at=attempted_at,
        last_finished_at=finished_at,
        last_success_at=finished_at,
        last_status="success",
        last_message="Backed up app-wabbit-dev to desktop-archive (abc123)",
        last_backup_target_name="desktop-archive",
        last_snapshot_id="abc123",
    )

    summaries = load_backup_repo_summaries(paths)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.repo_name == "app-wabbit-dev"
    assert summary.repo_path == repo_path.resolve()
    assert summary.last_attempted_at == attempted_at
    assert summary.last_finished_at == finished_at
    assert summary.last_success_at == finished_at
    assert summary.last_status == "success"
    assert summary.last_backup_target_name == "desktop-archive"
    assert summary.last_snapshot_id == "abc123"


def test_backup_run_history_is_saved_in_reverse_chronological_order(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    repo_path = workspace_root / "app-wabbit-dev"
    repo_path.mkdir()
    paths = service_paths_for_workspace(workspace_root)

    older_started_at = datetime(2026, 4, 12, 18, 0, tzinfo=UTC)
    older_finished_at = older_started_at + timedelta(minutes=1)
    newer_started_at = older_started_at + timedelta(hours=1)
    newer_finished_at = newer_started_at + timedelta(minutes=1)

    record_backup_run(
        paths,
        repo_name="app-wabbit-dev",
        repo_path=repo_path,
        backup_target_name="desktop-archive",
        action="push",
        reason="manual",
        ok=True,
        message="older",
        snapshot_id="old123",
        started_at=older_started_at,
        finished_at=older_finished_at,
    )
    record_backup_run(
        paths,
        repo_name="app-wabbit-dev",
        repo_path=repo_path,
        backup_target_name="desktop-archive",
        action="push",
        reason="service",
        ok=False,
        message="newer",
        snapshot_id=None,
        started_at=newer_started_at,
        finished_at=newer_finished_at,
    )

    history = load_recent_backup_runs(paths, limit=10)

    assert [entry.message for entry in history] == ["newer", "older"]
    assert history[0].ok is False
    assert history[1].snapshot_id == "old123"


def test_dashboard_repo_cache_round_trips_payload(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    repo_path = workspace_root / "app-wabbit-dev"
    repo_path.mkdir()
    paths = service_paths_for_workspace(workspace_root)
    updated_at = datetime(2026, 4, 12, 19, 0, tzinfo=UTC)

    save_dashboard_repo_cache(
        paths,
        repo_name="app-wabbit-dev",
        repo_path=repo_path,
        updated_at=updated_at,
        payload={
            "lastActionMessage": "app-wabbit-dev: committed local changes",
            "checkRun": {
                "kind": "check",
                "status": "success",
                "summary": "errors 0, warnings 0, info 3",
                "checkedAt": updated_at.isoformat(),
                "exitCode": 0,
                "detail": None,
            },
        },
    )

    entry = load_dashboard_repo_cache(paths, "app-wabbit-dev")

    assert entry is not None
    assert entry.repo_name == "app-wabbit-dev"
    assert entry.repo_path == repo_path.resolve()
    assert entry.updated_at == updated_at
    assert entry.payload["lastActionMessage"] == "app-wabbit-dev: committed local changes"


def test_dashboard_action_history_is_saved_in_reverse_chronological_order(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    repo_path = workspace_root / "app-wabbit-dev"
    repo_path.mkdir()
    paths = service_paths_for_workspace(workspace_root)

    older_finished_at = datetime(2026, 4, 12, 20, 0, tzinfo=UTC)
    newer_finished_at = older_finished_at + timedelta(minutes=5)

    record_dashboard_action(
        paths,
        repo_name="app-wabbit-dev",
        repo_path=repo_path,
        action_kind="check-run",
        action_source="user",
        status="success",
        message="errors 0, warnings 0, info 2",
        started_at=older_finished_at - timedelta(seconds=30),
        finished_at=older_finished_at,
    )
    record_dashboard_action(
        paths,
        repo_name="app-wabbit-dev",
        repo_path=repo_path,
        action_kind="push",
        action_source="user",
        status="error",
        message="push failed",
        started_at=None,
        finished_at=newer_finished_at,
    )

    history = load_recent_dashboard_actions(paths, repo_name="app-wabbit-dev", limit=10)

    assert [entry.message for entry in history] == ["push failed", "errors 0, warnings 0, info 2"]
    assert history[0].status == "error"
    assert history[1].action_kind == "check-run"
