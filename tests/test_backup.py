from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pytest import MonkeyPatch


def _load_from_temp_root(
    tmp_path: Path,
    root_clj: str,
    root_private_clj: str = '(github-token "dummy")\n',
):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.config import load_config

    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "root.clj").write_text(root_clj, encoding="utf-8")
    (tmp_path / "root.private.clj").write_text(root_private_clj, encoding="utf-8")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return load_config()
    finally:
        os.chdir(cwd)


def test_service_backup_due_respects_repo_age_and_min_interval(tmp_path: Path) -> None:
    from dev.repo_resolution import ResolvedRepoTarget
    from dev.repo_status import RepoStatusRecord
    from dev.tasks.backup import service_backup_due

    repo_path = tmp_path / "demo-repo"
    repo_path.mkdir()

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                "("
                'define-backup-target "desktop-archive" '
                '"restic-sftp" '
                '"100.79.145.10" '
                '"alexk" '
                '"/H:/restic/datatron" '
                ':passwordCommand "cat ~/.config/restic/datatron.pass")',
                "("
                'backup-policy ["desktop-archive"] '
                ":service true "
                ":serviceAgeMinutes 60 "
                ":serviceMinIntervalMinutes 180)",
                "",
            ]
        ),
    )

    target = ResolvedRepoTarget(name="demo-repo", path=repo_path)
    now = datetime(2026, 4, 12, 18, 0, tzinfo=UTC)
    repo_started_at = now - timedelta(minutes=90)
    repo_age_timestamp = repo_started_at.timestamp()
    os.utime(repo_path, (repo_age_timestamp, repo_age_timestamp))
    repo_status = RepoStatusRecord(
        name="demo-repo",
        path=repo_path,
        staged_changes=(),
        unstaged_changes=(),
        untracked_files=(),
        oldest_dirty_timestamp=None,
    )

    assert service_backup_due(config, target, repo_status, last_attempted_at=None, now=now) is True
    assert (
        service_backup_due(
            config,
            target,
            repo_status,
            last_attempted_at=now - timedelta(minutes=30),
            now=now,
        )
        is False
    )


def test_service_backup_due_skips_repo_until_repo_age_threshold(tmp_path: Path) -> None:
    from dev.repo_resolution import ResolvedRepoTarget
    from dev.repo_status import RepoStatusRecord
    from dev.tasks.backup import service_backup_due

    repo_path = tmp_path / "demo-repo"
    repo_path.mkdir()

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                "("
                'define-backup-target "desktop-archive" '
                '"restic-sftp" '
                '"100.79.145.10" '
                '"alexk" '
                '"/H:/restic/datatron" '
                ':passwordCommand "cat ~/.config/restic/datatron.pass")',
                "("
                'backup-policy ["desktop-archive"] '
                ":service true "
                ":serviceAgeMinutes 60 "
                ":serviceMinIntervalMinutes 180)",
                "",
            ]
        ),
    )

    target = ResolvedRepoTarget(name="demo-repo", path=repo_path)
    now = datetime(2026, 4, 12, 18, 0, tzinfo=UTC)
    repo_started_at = now - timedelta(minutes=15)
    repo_age_timestamp = repo_started_at.timestamp()
    os.utime(repo_path, (repo_age_timestamp, repo_age_timestamp))
    repo_status = RepoStatusRecord(
        name="demo-repo",
        path=repo_path,
        staged_changes=("README.md",),
        unstaged_changes=(),
        untracked_files=(),
        oldest_dirty_timestamp=now - timedelta(minutes=5),
    )

    assert service_backup_due(config, target, repo_status, last_attempted_at=None, now=now) is False


def test_restore_requires_explicit_target_when_multiple_backup_targets_apply(tmp_path: Path) -> None:
    from dev.repo_resolution import ResolvedRepoTarget
    from dev.tasks.backup import restore_resolved_repo_backup

    repo_path = tmp_path / "demo-repo"
    repo_path.mkdir()

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                "("
                'define-backup-target "desktop-a" '
                '"restic-sftp" '
                '"100.79.145.10" '
                '"alexk" '
                '"/H:/restic/a" '
                ':passwordCommand "cat ~/.config/restic/a.pass")',
                "("
                'define-backup-target "desktop-b" '
                '"restic-sftp" '
                '"100.79.145.10" '
                '"alexk" '
                '"/H:/restic/b" '
                ':passwordCommand "cat ~/.config/restic/b.pass")',
                '(backup-policy ["desktop-a" "desktop-b"])',
                "",
            ]
        ),
    )

    result = restore_resolved_repo_backup(
        config,
        ResolvedRepoTarget(name="demo-repo", path=repo_path),
        backup_target_name=None,
        snapshot="latest",
        into=tmp_path / "restore-root",
        dry_run=True,
    )

    assert result.ok is False
    assert "Pass --target <NAME>" in result.message


def test_snapshot_subpath_uses_repo_relative_layout() -> None:
    from dev.tasks.backup import _snapshot_subpath

    assert _snapshot_subpath("app-wabbit-dev") == "/app-wabbit-dev"
    assert _snapshot_subpath("nested/repo") == "/nested/repo"
    assert _snapshot_subpath(".") == "/"


def test_backup_push_dry_run_does_not_persist_service_state(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    from dev.config import Config
    from dev.repo_resolution import ResolvedRepoTarget
    from dev.service_support import service_paths_for_workspace
    from dev.tasks import backup as backup_task
    from dev.tasks.backup import BackupRunResult

    repo_path = tmp_path / "demo-repo"
    repo_path.mkdir()
    config = _load_from_temp_root(tmp_path, "\n")

    def fake_resolve_repo_targets(
        targets: list[str],
        *,
        config: Config | None = None,
    ) -> list[ResolvedRepoTarget]:
        assert targets == ["demo-repo"]
        return [ResolvedRepoTarget(name="demo-repo", path=repo_path)]

    def fake_push_resolved_repo_backup(
        config: Config,
        resolved_target: ResolvedRepoTarget,
        *,
        backup_target_name: str | None,
        reason: str,
        dry_run: bool,
    ) -> list[BackupRunResult]:
        assert resolved_target.name == "demo-repo"
        assert backup_target_name is None
        assert reason == "manual"
        assert dry_run is True
        return [
            BackupRunResult(
                repo_name="demo-repo",
                backup_target_name="desktop-archive",
                action="push",
                ok=True,
                message="Dry run: would back up demo-repo to desktop-archive",
            )
        ]

    monkeypatch.setattr(backup_task, "load_config", lambda: config)
    monkeypatch.setattr(backup_task, "resolve_repo_targets", fake_resolve_repo_targets)
    monkeypatch.setattr(backup_task, "push_resolved_repo_backup", fake_push_resolved_repo_backup)

    result = backup_task.push(["demo-repo"], dry_run=True, emit_output=False)

    assert result == 0
    assert service_paths_for_workspace(tmp_path).database_file.exists() is False
