from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dev.service_db import BackupRepoSummary
from dev.dashboard_backend import (
    DashboardRepoState,
    _backup_state_from_summary,
    _clear_matching_failure_message,
    _empty_monitor_state,
    _merge_cached_repo_state,
    _overall_registry_visibility,
    _release_project_state,
    _registry_status,
    _sanitize_cached_last_action_message,
)
from dev.tasks.project_versions import (
    GitState,
    GitWorkingTreeState,
    LatestTagState,
    ProjectVersionReport,
    RegistrySnapshot,
    VersionDiagnostic,
)


def test_registry_status_is_ok_when_current_version_exists_in_registry() -> None:
    status = _registry_status(
        "2.0.0",
        "maven-central",
        "one.wabbit:kotlin-web-wayback",
        "2.0.0",
        ("1.0.0", "2.0.0"),
        (),
    )

    assert status.status == "ok"


def test_registry_status_is_error_when_registry_has_no_versions() -> None:
    status = _registry_status(
        "0.0.1",
        "jitpack",
        "com.github.wabbit-corp:kotlin-web-jitpack",
        None,
        (),
        (),
    )

    assert status.status == "error"


def test_registry_status_is_warn_when_registry_is_outdated() -> None:
    status = _registry_status(
        "2.0.0",
        "pypi",
        "lang-mu",
        "1.9.0",
        ("1.8.0", "1.9.0"),
        (),
    )

    assert status.status == "warn"


def test_overall_registry_visibility_prefers_ok_then_warn_then_error() -> None:
    ok_status = _registry_status("2.0.0", "maven-central", "pkg", "2.0.0", ("2.0.0",), ())
    warn_status = _registry_status("2.0.0", "jitpack", "pkg", "1.9.0", ("1.9.0",), ())
    error_status = _registry_status("2.0.0", "nuget", "pkg", None, (), ())

    assert _overall_registry_visibility((error_status,)) == "unknown"
    assert _overall_registry_visibility((warn_status, error_status)) == "missing"
    assert _overall_registry_visibility((ok_status, warn_status, error_status)) == "published"


def test_merge_cached_repo_state_drops_running_command_states() -> None:
    repo = DashboardRepoState(
        name="app-wabbit-dev",
        path=Path("/tmp/app-wabbit-dev"),
        repo_id=":app-wabbit-dev",
        project_ids=("app-wabbit-dev",),
        publishable_project_ids=("app-wabbit-dev",),
        docs_project_ids=("app-wabbit-dev",),
        github_repo="wabbit-corp/app-wabbit-dev",
        monitor=_empty_monitor_state("app-wabbit-dev", Path("/tmp/app-wabbit-dev")),
    )

    merged = _merge_cached_repo_state(
        repo,
        {
            "lastActionMessage": "app-wabbit-dev: committed local changes",
            "spotCheck": {
                "kind": "spot-check",
                "status": "success",
                "summary": "errors 0, warnings 0, info 1",
                "checkedAt": "2026-04-12T20:00:00+00:00",
                "exitCode": 0,
                "detail": None,
            },
            "checkRun": {
                "kind": "check",
                "status": "running",
                "summary": "Running...",
                "startedAt": "2026-04-12T20:01:00+00:00",
            },
        },
    )

    assert merged.last_action_message == "app-wabbit-dev: committed local changes"
    assert merged.spot_check is not None
    assert merged.spot_check.status == "success"
    assert merged.check_run is None


def test_backup_state_from_summary_preserves_latest_backup_metadata() -> None:
    attempted_at = datetime(2026, 4, 12, 20, 0, tzinfo=UTC)
    finished_at = attempted_at
    summary = BackupRepoSummary(
        repo_name="app-wabbit-dev",
        repo_path=Path("/tmp/app-wabbit-dev"),
        last_attempted_at=attempted_at,
        last_finished_at=finished_at,
        last_success_at=finished_at,
        last_status="success",
        last_message="Backed up app-wabbit-dev to desktop-archive (abc123)",
        last_backup_target_name="desktop-archive",
        last_snapshot_id="abc123",
    )

    backup = _backup_state_from_summary(summary)

    assert backup is not None
    assert backup.status == "success"
    assert backup.target_name == "desktop-archive"
    assert backup.snapshot_id == "abc123"
    assert backup.success_at == finished_at


def test_release_project_state_returns_structured_release_data() -> None:
    checked_at = datetime(2026, 4, 12, 21, 0, tzinfo=UTC)
    report = ProjectVersionReport(
        project_id="kotlin-web-wayback",
        project_path=Path("/tmp/kotlin-web-wayback"),
        repo_root=Path("/tmp/kotlin-web-wayback"),
        current_version="2.0.0",
        publish_target="maven-central",
        registries=(
            RegistrySnapshot(
                name="maven-central",
                package="one.wabbit:kotlin-web-wayback",
                latest="2.0.0",
                versions=("1.0.0", "2.0.0"),
                diagnostics=(VersionDiagnostic(source="maven-central", message="ok"),),
            ),
        ),
        git_state=GitState(
            branch="master",
            remote="origin",
            remote_branch="master",
            remote_head="origin/master",
            unpushed_commits=2,
            remote_only_commits=0,
            latest_tag=LatestTagState(tag="v2.0.0", version="2.0.0", commits_after=3),
            working_tree=GitWorkingTreeState(entries=()),
        ),
        versions=(),
        diagnostics=(VersionDiagnostic(source="git-upstream", message="ahead 2"),),
    )

    release_state = _release_project_state(report, checked_at=checked_at)

    assert release_state.project_id == "kotlin-web-wayback"
    assert release_state.publish_target == "maven-central"
    assert release_state.registry_visible == "published"
    assert release_state.latest_tag == "v2.0.0"
    assert release_state.commits_after_tag == 3
    assert release_state.unpushed_commits == 2
    assert release_state.checked_at == checked_at
    assert release_state.diagnostics == ("git-upstream: ahead 2",)


def test_clear_matching_failure_message_only_clears_same_job_kind() -> None:
    assert _clear_matching_failure_message("versions failed: boom", "versions") is None
    assert _clear_matching_failure_message("github failed: boom", "versions") == "github failed: boom"
    assert _clear_matching_failure_message("manual commit complete", "versions") == "manual commit complete"


def test_sanitize_cached_last_action_message_drops_background_refresh_failures() -> None:
    assert _sanitize_cached_last_action_message("versions failed: boom") is None
    assert _sanitize_cached_last_action_message("github failed: boom") is None
    assert _sanitize_cached_last_action_message("commit failed: boom") == "commit failed: boom"
