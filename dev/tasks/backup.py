from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch
from pathlib import Path

from dev.config import BackupPolicy, BackupTarget, Config, load_config
from dev.json_types import JSONObject, JSONValue
from dev.messages import error, info, success
from dev.repo_resolution import (
    ResolvedRepoTarget,
    configured_repo_targets,
    inferred_repo_targets,
    resolve_repo_target,
    resolve_repo_targets,
)
from dev.repo_status import RepoStatusRecord
from dev.service_db import note_backup_attempt, record_backup_run, update_backup_repo_summary
from dev.service_support import service_paths_for_workspace

_DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    ".DS_Store",
    "Thumbs.db",
    ".gradle",
    ".gradle/**",
    "build",
    "build/**",
    "dist",
    "dist/**",
    "node_modules",
    "node_modules/**",
    ".venv",
    ".venv/**",
    ".mypy_cache",
    ".mypy_cache/**",
    ".pytest_cache",
    ".pytest_cache/**",
    "__pycache__",
    "__pycache__/**",
    ".idea",
    ".idea/**",
    ".tmp",
    ".tmp/**",
    "tmp",
    "tmp/**",
    "*.bak",
)
_DEFAULT_EXCLUDE_IF_PRESENT: tuple[str, ...] = ("CACHEDIR.TAG", ".nobackup")


@dataclass(frozen=True)
class BackupRunResult:
    repo_name: str
    backup_target_name: str
    action: str
    ok: bool
    message: str
    snapshot_id: str | None = None

    def to_json(self) -> JSONObject:
        return {
            "repoName": self.repo_name,
            "backupTarget": self.backup_target_name,
            "action": self.action,
            "ok": self.ok,
            "message": self.message,
            "snapshotId": self.snapshot_id,
        }


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _restic_binary() -> str:
    restic = shutil.which("restic")
    if restic is None:
        raise ValueError("restic is not installed. Install it first, for example with `brew install restic`.")
    return restic


def _workspace_root(config: Config) -> Path:
    workspace_root = config.workspace_root
    if workspace_root is None:
        raise ValueError("Workspace root is not available in config.")
    return workspace_root.resolve()


def _service_paths(config: Config):
    workspace_root = config.workspace_root
    if workspace_root is None:
        return None
    return service_paths_for_workspace(workspace_root.resolve())


def _relative_repo_path(workspace_root: Path, repo_root: Path) -> str:
    try:
        return repo_root.resolve().relative_to(workspace_root).as_posix()
    except ValueError as ex:
        raise ValueError(f"Repo path {repo_root} is not under workspace root {workspace_root}") from ex


def _backup_host(workspace_root: Path) -> str:
    return workspace_root.name or "workspace"


def _quoted(value: str) -> str:
    return shlex.quote(value)


def _effective_ssh_key(target: BackupTarget, config: Config) -> str | None:
    if target.ssh_key is not None and target.ssh_key.strip():
        return str(Path(target.ssh_key).expanduser())
    github_ssh_key = config.github_ssh_key
    if github_ssh_key is not None and github_ssh_key.strip():
        return str(Path(github_ssh_key).expanduser())
    return None


def _sftp_command(target: BackupTarget, config: Config) -> str:
    ssh_parts = ["ssh"]
    ssh_key = _effective_ssh_key(target, config)
    if ssh_key is not None:
        ssh_parts.extend(["-i", ssh_key, "-o", "IdentitiesOnly=yes"])
    ssh_parts.extend(
        [
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=60",
            "-o",
            "ServerAliveCountMax=10",
            f"{target.user}@{target.host}",
            "-s",
            "sftp",
        ]
    )
    return " ".join(_quoted(part) for part in ssh_parts)


def _restic_prefix(target: BackupTarget, config: Config, *, json_output: bool) -> list[str]:
    repository = f"sftp::{target.path}"
    command = [
        _restic_binary(),
        "--repo",
        repository,
        "--compression",
        target.compression,
        "--option",
        f"sftp.command={_sftp_command(target, config)}",
    ]
    match (target.password_file, target.password_command):
        case (str() as password_file, _):
            command.extend(["--password-file", str(Path(password_file).expanduser())])
        case (None, str() as password_command):
            command.extend(["--password-command", password_command])
        case _:
            raise ValueError(
                f"Backup target {target.name} needs either :passwordFile or :passwordCommand in config."
            )
    if json_output:
        command.append("--json")
    return command


def _run_restic(
    command: list[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _ensure_repository_initialized(target: BackupTarget, config: Config) -> None:
    probe = _run_restic(_restic_prefix(target, config, json_output=True) + ["snapshots", "--latest", "1"])
    if probe.returncode == 0:
        return
    if probe.returncode != 10:
        raise ValueError(
            f"Failed to access backup target {target.name}: {probe.stderr.strip() or probe.stdout.strip() or 'unknown error'}"
        )
    init_result = _run_restic(_restic_prefix(target, config, json_output=False) + ["init"])
    if init_result.returncode != 0:
        raise ValueError(
            f"Failed to initialize backup target {target.name}: "
            f"{init_result.stderr.strip() or init_result.stdout.strip() or 'unknown error'}"
        )


def _matching_backup_policy(config: Config, repo_name: str, repo_relative_path: str) -> BackupPolicy | None:
    policy = config.backup_policy
    if policy is None:
        return None
    candidate_values = (repo_name, repo_relative_path)
    if not any(fnmatch(candidate, pattern) for pattern in policy.include_repos for candidate in candidate_values):
        return None
    if any(fnmatch(candidate, pattern) for pattern in policy.exclude_repos for candidate in candidate_values):
        return None
    return policy


def _selected_backup_targets(
    config: Config,
    *,
    repo_name: str,
    repo_relative_path: str,
    backup_target_name: str | None,
    require_policy_match: bool,
) -> list[BackupTarget]:
    if backup_target_name is not None:
        target = config.backup_targets.get(backup_target_name)
        if target is None:
            raise ValueError(f"Unknown backup target: {backup_target_name}")
        return [target]

    policy = _matching_backup_policy(config, repo_name, repo_relative_path)
    if policy is None:
        if require_policy_match:
            raise ValueError(f"No backup policy applies to {repo_name}.")
        if len(config.backup_targets) == 1:
            return [next(iter(config.backup_targets.values()))]
        raise ValueError(f"No backup target selected for {repo_name}.")

    targets: list[BackupTarget] = []
    for target_name in policy.target_names:
        target = config.backup_targets.get(target_name)
        if target is None:
            raise ValueError(f"Backup policy references unknown target: {target_name}")
        targets.append(target)
    return targets


def _repo_excludes(policy: BackupPolicy | None) -> tuple[str, ...]:
    if policy is None:
        return _DEFAULT_EXCLUDE_PATTERNS
    return _DEFAULT_EXCLUDE_PATTERNS + policy.exclude


def _repo_exclude_if_present(policy: BackupPolicy | None) -> tuple[str, ...]:
    if policy is None:
        return _DEFAULT_EXCLUDE_IF_PRESENT
    return _DEFAULT_EXCLUDE_IF_PRESENT + policy.exclude_if_present


def _snapshot_subpath(repo_relative_path: str) -> str:
    normalized = repo_relative_path.strip()
    if normalized in {"", "."}:
        return "/"
    return f"/{normalized.lstrip('/')}"


def _repo_snapshot_tags(
    *,
    workspace_root: Path,
    repo_name: str,
    repo_root: Path,
    reason: str,
    dirty: bool,
) -> list[str]:
    tags = [
        f"workspace:{workspace_root.name}",
        f"repo:{repo_name}",
        f"reason:{reason}",
        f"dirty:{str(dirty).lower()}",
    ]
    try:
        from git import Repo

        repo = Repo(repo_root, search_parent_directories=True)
        try:
            tags.append(f"head:{repo.head.commit.hexsha[:12]}")
        finally:
            repo.close()
    except Exception:
        pass
    return tags


def _parse_backup_summary(stdout: str) -> str | None:
    snapshot_id: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parsed: JSONValue = json.loads(line)
        match parsed:
            case {"message_type": "summary", "snapshot_id": str(summary_snapshot_id)}:
                snapshot_id = summary_snapshot_id
            case _:
                continue
    return snapshot_id


def _parse_snapshot_list(stdout: str) -> list[JSONObject]:
    parsed: JSONValue = json.loads(stdout)
    match parsed:
        case list() as values:
            snapshots: list[JSONObject] = []
            for value in values:
                match value:
                    case dict() as snapshot:
                        snapshots.append(snapshot)
                    case _:
                        continue
            return snapshots
        case _:
            raise ValueError("Expected JSON snapshot array from restic.")


def _latest_snapshot_id(
    target: BackupTarget,
    config: Config,
    *,
    repo_name: str,
    repo_root: Path,
) -> str | None:
    workspace_root = _workspace_root(config)
    command = _restic_prefix(target, config, json_output=True) + [
        "snapshots",
        "--latest",
        "1",
        "--host",
        _backup_host(workspace_root),
        "--tag",
        f"workspace:{workspace_root.name}",
        "--tag",
        f"repo:{repo_name}",
        "--path",
        str(repo_root.resolve()),
    ]
    result = _run_restic(command)
    if result.returncode == 10:
        return None
    if result.returncode != 0:
        raise ValueError(
            f"Failed to list snapshots for {repo_name} on {target.name}: "
            f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )
    snapshots = _parse_snapshot_list(result.stdout)
    if not snapshots:
        return None
    match snapshots[0]:
        case {"id": str(snapshot_id)}:
            return snapshot_id
        case _:
            return None


def push_resolved_repo_backup(
    config: Config,
    resolved_target: ResolvedRepoTarget,
    *,
    backup_target_name: str | None,
    reason: str,
    dry_run: bool,
) -> list[BackupRunResult]:
    workspace_root = _workspace_root(config)
    repo_root = resolved_target.path.resolve()
    repo_relative_path = _relative_repo_path(workspace_root, repo_root)
    policy = _matching_backup_policy(config, resolved_target.name, repo_relative_path)
    selected_targets = _selected_backup_targets(
        config,
        repo_name=resolved_target.name,
        repo_relative_path=repo_relative_path,
        backup_target_name=backup_target_name,
        require_policy_match=backup_target_name is None,
    )
    dirty = False
    try:
        from git import Repo

        repo = Repo(repo_root, search_parent_directories=True)
        try:
            dirty = repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=False)
        finally:
            repo.close()
    except Exception:
        dirty = False

    results: list[BackupRunResult] = []
    for selected_target in selected_targets:
        command = _restic_prefix(selected_target, config, json_output=True) + [
            "backup",
            repo_relative_path,
            "--host",
            _backup_host(workspace_root),
            "--skip-if-unchanged",
        ]
        if policy is None or policy.exclude_caches:
            command.append("--exclude-caches")
        if policy is None or policy.include_git:
            pass
        else:
            command.extend(["--exclude", f"{repo_relative_path}/.git", "--exclude", f"{repo_relative_path}/.git/**"])
        for exclude_pattern in _repo_excludes(policy):
            command.extend(["--exclude", f"{repo_relative_path}/{exclude_pattern}"])
        for marker in _repo_exclude_if_present(policy):
            command.extend(["--exclude-if-present", marker])
        for tag in _repo_snapshot_tags(
            workspace_root=workspace_root,
            repo_name=resolved_target.name,
            repo_root=repo_root,
            reason=reason,
            dirty=dirty,
        ):
            command.extend(["--tag", tag])

        if dry_run:
            results.append(
                BackupRunResult(
                    repo_name=resolved_target.name,
                    backup_target_name=selected_target.name,
                    action="push",
                    ok=True,
                    message=f"Dry run: would back up {resolved_target.name} to {selected_target.name}",
                )
            )
            continue

        try:
            _ensure_repository_initialized(selected_target, config)
        except Exception as ex:
            results.append(
                BackupRunResult(
                    repo_name=resolved_target.name,
                    backup_target_name=selected_target.name,
                    action="push",
                    ok=False,
                    message=str(ex),
                )
            )
            continue

        result = _run_restic(command, cwd=workspace_root)
        if result.returncode not in {0, 3}:
            results.append(
                BackupRunResult(
                    repo_name=resolved_target.name,
                    backup_target_name=selected_target.name,
                    action="push",
                    ok=False,
                    message=(
                        f"Backup failed for {resolved_target.name} -> {selected_target.name}: "
                        f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
                    ),
                )
            )
            continue

        snapshot_id = _parse_backup_summary(result.stdout)
        message = (
            f"Backed up {resolved_target.name} to {selected_target.name}"
            if snapshot_id is None
            else f"Backed up {resolved_target.name} to {selected_target.name} ({snapshot_id[:12]})"
        )
        results.append(
            BackupRunResult(
                repo_name=resolved_target.name,
                backup_target_name=selected_target.name,
                action="push",
                ok=True,
                message=message,
                snapshot_id=snapshot_id,
            )
        )
    return results


def restore_resolved_repo_backup(
    config: Config,
    resolved_target: ResolvedRepoTarget,
    *,
    backup_target_name: str | None,
    snapshot: str,
    into: Path,
    dry_run: bool,
) -> BackupRunResult:
    workspace_root = _workspace_root(config)
    repo_root = resolved_target.path.resolve()
    repo_relative_path = _relative_repo_path(workspace_root, repo_root)
    selected_targets = _selected_backup_targets(
        config,
        repo_name=resolved_target.name,
        repo_relative_path=repo_relative_path,
        backup_target_name=backup_target_name,
        require_policy_match=False,
    )
    if backup_target_name is None and len(selected_targets) != 1:
        target_names = ", ".join(target.name for target in selected_targets)
        return BackupRunResult(
            repo_name=resolved_target.name,
            backup_target_name="",
            action="restore",
            ok=False,
            message=(
                f"Multiple backup targets apply to {resolved_target.name}: {target_names}. "
                "Pass --target <NAME> to choose which snapshot source to restore from."
            ),
        )
    selected_target = selected_targets[0]

    try:
        _ensure_repository_initialized(selected_target, config)
    except Exception as ex:
        return BackupRunResult(
            repo_name=resolved_target.name,
            backup_target_name=selected_target.name,
            action="restore",
            ok=False,
            message=str(ex),
        )

    snapshot_id = snapshot
    if snapshot == "latest":
        try:
            latest_snapshot = _latest_snapshot_id(
                selected_target,
                config,
                repo_name=resolved_target.name,
                repo_root=repo_root,
            )
        except Exception as ex:
            return BackupRunResult(
                repo_name=resolved_target.name,
                backup_target_name=selected_target.name,
                action="restore",
                ok=False,
                message=str(ex),
            )
        if latest_snapshot is None:
            return BackupRunResult(
                repo_name=resolved_target.name,
                backup_target_name=selected_target.name,
                action="restore",
                ok=False,
                message=f"No snapshot found for {resolved_target.name} on {selected_target.name}",
            )
        snapshot_id = latest_snapshot

    snapshot_reference = f"{snapshot_id}:{_snapshot_subpath(repo_relative_path)}"
    command = _restic_prefix(selected_target, config, json_output=False) + [
        "restore",
        snapshot_reference,
        "--target",
        str(into.resolve()),
    ]
    if dry_run:
        command.append("--dry-run")

    result = _run_restic(command)
    if result.returncode != 0:
        return BackupRunResult(
            repo_name=resolved_target.name,
            backup_target_name=selected_target.name,
            action="restore",
            ok=False,
            message=(
                f"Restore failed for {resolved_target.name} from {selected_target.name}: "
                f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
            ),
            snapshot_id=snapshot_id,
        )

    target_path = into.resolve() / repo_relative_path
    return BackupRunResult(
        repo_name=resolved_target.name,
        backup_target_name=selected_target.name,
        action="restore",
        ok=True,
        message=(
            f"Restored {resolved_target.name} from {selected_target.name} to {target_path}"
            if not dry_run
            else f"Dry run: would restore {resolved_target.name} from {selected_target.name} to {target_path}"
        ),
        snapshot_id=snapshot_id,
    )


def service_backup_due(
    config: Config,
    resolved_target: ResolvedRepoTarget,
    repo_status: RepoStatusRecord,
    *,
    last_attempted_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    workspace_root = _workspace_root(config)
    repo_relative_path = _relative_repo_path(workspace_root, resolved_target.path.resolve())
    policy = _matching_backup_policy(config, resolved_target.name, repo_relative_path)
    if policy is None or not policy.service_enabled:
        return False
    active_now = _now_utc() if now is None else now
    repo_started_at = repo_status.repo_started_at
    if repo_started_at is None:
        repo_path = repo_status.path if repo_status.path.exists() else resolved_target.path.resolve()
        try:
            repo_started_at = datetime.fromtimestamp(repo_path.stat().st_mtime, tz=UTC)
        except OSError:
            return False
    repo_age = active_now - repo_started_at
    if repo_age < timedelta(minutes=policy.service_age_minutes):
        return False
    if last_attempted_at is None:
        return True
    return active_now - last_attempted_at >= timedelta(minutes=policy.service_min_interval_minutes)


def _record_backup_results(
    config: Config,
    *,
    repo_name: str,
    repo_path: Path,
    reason: str,
    started_at: datetime,
    finished_at: datetime,
    results: list[BackupRunResult],
) -> None:
    paths = _service_paths(config)
    if paths is None:
        return

    summary_status = "success" if all(result.ok for result in results) else "error"
    summary_message = "; ".join(result.message for result in results)
    first_result = results[0] if len(results) == 1 else None
    last_success_at = finished_at if summary_status == "success" else None

    note_backup_attempt(paths, repo_name, repo_path, attempted_at=started_at)
    for result in results:
        record_backup_run(
            paths,
            repo_name=repo_name,
            repo_path=repo_path,
            backup_target_name=result.backup_target_name,
            action=result.action,
            reason=reason,
            ok=result.ok,
            message=result.message,
            snapshot_id=result.snapshot_id,
            started_at=started_at,
            finished_at=finished_at,
        )
    update_backup_repo_summary(
        paths,
        repo_name=repo_name,
        repo_path=repo_path,
        last_attempted_at=started_at,
        last_finished_at=finished_at,
        last_success_at=last_success_at,
        last_status=summary_status,
        last_message=summary_message,
        last_backup_target_name=first_result.backup_target_name if first_result is not None else None,
        last_snapshot_id=first_result.snapshot_id if first_result is not None else None,
    )


def _record_backup_exception(
    config: Config,
    *,
    repo_name: str,
    repo_path: Path,
    action: str,
    reason: str,
    started_at: datetime,
    finished_at: datetime,
    message: str,
) -> None:
    paths = _service_paths(config)
    if paths is None:
        return
    note_backup_attempt(paths, repo_name, repo_path, attempted_at=started_at)
    update_backup_repo_summary(
        paths,
        repo_name=repo_name,
        repo_path=repo_path,
        last_attempted_at=started_at,
        last_finished_at=finished_at,
        last_success_at=None,
        last_status="error",
        last_message=message,
        last_backup_target_name=None,
        last_snapshot_id=None,
    )
    record_backup_run(
        paths,
        repo_name=repo_name,
        repo_path=repo_path,
        backup_target_name="",
        action=action,
        reason=reason,
        ok=False,
        message=message,
        snapshot_id=None,
        started_at=started_at,
        finished_at=finished_at,
    )


def push(
    targets: list[str] | None = None,
    *,
    backup_target_name: str | None = None,
    dry_run: bool = False,
    json_output: bool = False,
    reason: str = "manual",
    emit_output: bool = True,
) -> int:
    config = load_config()
    requested_targets = list(targets or [])
    if not requested_targets:
        inferred_targets = inferred_repo_targets(config)
        requested_targets = list(inferred_targets) if inferred_targets is not None else ["."]

    if requested_targets == ["."]:
        resolved_targets = configured_repo_targets(config)
    else:
        if "." in requested_targets:
            error("`backup push .` cannot be combined with other targets.")
            return 1
        try:
            resolved_targets = resolve_repo_targets(requested_targets, config=config)
        except ValueError as ex:
            error(str(ex))
            return 1

    results: list[BackupRunResult] = []
    for resolved_target in resolved_targets:
        started_at = _now_utc()
        try:
            repo_results = push_resolved_repo_backup(
                config,
                resolved_target,
                backup_target_name=backup_target_name,
                reason=reason,
                dry_run=dry_run,
            )
        except Exception as ex:
            finished_at = _now_utc()
            message = str(ex)
            if not dry_run:
                _record_backup_exception(
                    config,
                    repo_name=resolved_target.name,
                    repo_path=resolved_target.path.resolve(),
                    action="push",
                    reason=reason,
                    started_at=started_at,
                    finished_at=finished_at,
                    message=message,
                )
            repo_results = [
                BackupRunResult(
                    repo_name=resolved_target.name,
                    backup_target_name="",
                    action="push",
                    ok=False,
                    message=message,
                )
            ]
        else:
            finished_at = _now_utc()
            if not dry_run:
                _record_backup_results(
                    config,
                    repo_name=resolved_target.name,
                    repo_path=resolved_target.path.resolve(),
                    reason=reason,
                    started_at=started_at,
                    finished_at=finished_at,
                    results=repo_results,
                )
        results.extend(repo_results)

    if json_output:
        payload: JSONObject = {"results": [result.to_json() for result in results]}
        print(json.dumps(payload, indent=2))
    elif emit_output:
        for result in results:
            if result.ok:
                success(result.message)
            else:
                error(result.message)

    return 0 if all(result.ok for result in results) else 1


def restore(
    target: str | None,
    *,
    backup_target_name: str | None,
    snapshot: str,
    into: str,
    dry_run: bool = False,
    json_output: bool = False,
) -> int:
    config = load_config()
    effective_target = target
    if effective_target is None:
        inferred_targets = inferred_repo_targets(config)
        match inferred_targets:
            case [str() as inferred_target]:
                effective_target = inferred_target
            case _:
                error("Could not infer a single repo target for restore; pass one explicitly.")
                return 1
    try:
        resolved_target = resolve_repo_target(effective_target, config=config)
    except ValueError as ex:
        error(str(ex))
        return 1

    started_at = _now_utc()
    try:
        result = restore_resolved_repo_backup(
            config,
            resolved_target,
            backup_target_name=backup_target_name,
            snapshot=snapshot,
            into=Path(into),
            dry_run=dry_run,
        )
    except Exception as ex:
        finished_at = _now_utc()
        message = str(ex)
        if not dry_run:
            _record_backup_exception(
                config,
                repo_name=resolved_target.name,
                repo_path=resolved_target.path.resolve(),
                action="restore",
                reason="manual",
                started_at=started_at,
                finished_at=finished_at,
                message=message,
            )
        result = BackupRunResult(
            repo_name=resolved_target.name,
            backup_target_name="",
            action="restore",
            ok=False,
            message=message,
        )
    else:
        finished_at = _now_utc()
        if not dry_run:
            _record_backup_results(
                config,
                repo_name=resolved_target.name,
                repo_path=resolved_target.path.resolve(),
                reason="manual",
                started_at=started_at,
                finished_at=finished_at,
                results=[result],
            )

    if json_output:
        payload: JSONObject = {"result": result.to_json()}
        print(json.dumps(payload, indent=2))
    elif result.ok:
        info(result.message)
    else:
        error(result.message)
    return 0 if result.ok else 1


__all__ = [
    "BackupRunResult",
    "push",
    "push_resolved_repo_backup",
    "restore",
    "restore_resolved_repo_backup",
    "service_backup_due",
]
