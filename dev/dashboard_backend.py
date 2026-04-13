from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import redirect_stdout
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import io
import json
from json import JSONDecodeError
from pathlib import Path
from queue import Empty, Queue
import threading
import urllib.error
import urllib.request

from dev.config import Config, Project, load_config
from dev.json_types import JSONObject, JSONValue
from dev.repo_resolution import ResolvedRepoTarget, configured_repo_targets
from dev.repo_status import RepoStatusRecord, collect_repo_status_record
from dev.service_actions import (
    RepoActionResult,
    commit_repo_target,
    open_repo_in_difftool,
    push_repo_target,
)
from dev.service_db import (
    BackupRepoSummary,
    load_backup_repo_summaries,
    load_backup_repo_summary,
    load_dashboard_repo_caches,
    record_dashboard_action,
    save_dashboard_repo_cache,
)
from dev.service_support import MonitorRepoState, ServicePaths, repo_check_spacing_seconds, service_paths_for_workspace
from dev.tasks.build import build
from dev.tasks.check import check_main
from dev.tasks.docs_check import docs_check, docs_snippets
from dev.tasks.project_versions import ProjectVersionReport, build_project_version_report
from dev.tasks.publish import determine_publish_target
from dev.tasks.release_verify import release_verify

_VERSIONS_REFRESH_AFTER = timedelta(minutes=30)
_GITHUB_REFRESH_AFTER = timedelta(minutes=20)
_SPOT_CHECK_REFRESH_AFTER = timedelta(minutes=90)
_DOCS_CHECK_REFRESH_AFTER = timedelta(minutes=120)
_DOCS_SNIPPETS_REFRESH_AFTER = timedelta(minutes=180)
_JOB_IDLE_TIMEOUT_SECONDS = 0.25

type CommandStatus = str
type TaskReportArg = None | bool | int | float | str | list[str] | tuple[str, ...]


@dataclass(frozen=True)
class RepoCommandState:
    kind: str
    status: CommandStatus
    summary: str
    checked_at: datetime | None = None
    started_at: datetime | None = None
    exit_code: int | None = None
    detail: str | None = None

    def to_json(self) -> JSONObject:
        return {
            "kind": self.kind,
            "status": self.status,
            "summary": self.summary,
            "checkedAt": self.checked_at.isoformat() if self.checked_at is not None else None,
            "startedAt": self.started_at.isoformat() if self.started_at is not None else None,
            "exitCode": self.exit_code,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class GithubRepoState:
    checked_at: datetime | None = None
    ci_status: str | None = None
    ci_name: str | None = None
    ci_url: str | None = None
    latest_release_tag: str | None = None
    latest_release_url: str | None = None
    latest_release_published_at: datetime | None = None
    error: str | None = None

    def to_json(self) -> JSONObject:
        return {
            "checkedAt": self.checked_at.isoformat() if self.checked_at is not None else None,
            "ciStatus": self.ci_status,
            "ciName": self.ci_name,
            "ciUrl": self.ci_url,
            "latestReleaseTag": self.latest_release_tag,
            "latestReleaseUrl": self.latest_release_url,
            "latestReleasePublishedAt": (
                self.latest_release_published_at.isoformat() if self.latest_release_published_at is not None else None
            ),
            "error": self.error,
        }


@dataclass(frozen=True)
class BackupStatusState:
    attempted_at: datetime | None = None
    finished_at: datetime | None = None
    success_at: datetime | None = None
    status: str | None = None
    message: str | None = None
    target_name: str | None = None
    snapshot_id: str | None = None

    def to_json(self) -> JSONObject:
        return {
            "attemptedAt": self.attempted_at.isoformat() if self.attempted_at is not None else None,
            "finishedAt": self.finished_at.isoformat() if self.finished_at is not None else None,
            "successAt": self.success_at.isoformat() if self.success_at is not None else None,
            "status": self.status,
            "message": self.message,
            "targetName": self.target_name,
            "snapshotId": self.snapshot_id,
        }


@dataclass(frozen=True)
class RegistryStatusState:
    name: str
    package: str
    current_version: str | None
    latest: str | None
    status: str
    diagnostics: tuple[str, ...]

    def to_json(self) -> JSONObject:
        return {
            "name": self.name,
            "package": self.package,
            "currentVersion": self.current_version,
            "latest": self.latest,
            "status": self.status,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class ReleaseProjectState:
    project_id: str
    publish_target: str
    current_version: str | None
    registry_latest: str | None
    registry_names: tuple[str, ...]
    registry_visible: str
    registry_statuses: tuple[RegistryStatusState, ...]
    latest_tag: str | None
    latest_tag_version: str | None
    commits_after_tag: int | None
    unpushed_commits: int | None
    remote_only_commits: int | None
    dirty: bool
    staged_count: int
    unstaged_count: int
    untracked_count: int
    checked_at: datetime | None
    diagnostics: tuple[str, ...]

    def to_json(self) -> JSONObject:
        return {
            "projectId": self.project_id,
            "publishTarget": self.publish_target,
            "currentVersion": self.current_version,
            "registryLatest": self.registry_latest,
            "registryNames": list(self.registry_names),
            "registryVisible": self.registry_visible,
            "registryStatuses": [registry_status.to_json() for registry_status in self.registry_statuses],
            "latestTag": self.latest_tag,
            "latestTagVersion": self.latest_tag_version,
            "commitsAfterTag": self.commits_after_tag,
            "unpushedCommits": self.unpushed_commits,
            "remoteOnlyCommits": self.remote_only_commits,
            "dirty": self.dirty,
            "stagedCount": self.staged_count,
            "unstagedCount": self.unstaged_count,
            "untrackedCount": self.untracked_count,
            "checkedAt": self.checked_at.isoformat() if self.checked_at is not None else None,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class DashboardRepoState:
    name: str
    path: Path
    repo_id: str | None
    project_ids: tuple[str, ...]
    publishable_project_ids: tuple[str, ...]
    docs_project_ids: tuple[str, ...]
    github_repo: str | None
    monitor: MonitorRepoState
    backup: BackupStatusState | None = None
    release_projects: tuple[ReleaseProjectState, ...] = ()
    github: GithubRepoState | None = None
    spot_check: RepoCommandState | None = None
    docs_check: RepoCommandState | None = None
    docs_snippets: RepoCommandState | None = None
    check_run: RepoCommandState | None = None
    release_verify: RepoCommandState | None = None
    build: RepoCommandState | None = None
    last_action_message: str | None = None

    def to_json(self) -> JSONObject:
        payload: JSONObject = {
            "name": self.name,
            "path": str(self.path.resolve()),
            "repoId": self.repo_id,
            "projectIds": list(self.project_ids),
            "publishableProjectIds": list(self.publishable_project_ids),
            "docsProjectIds": list(self.docs_project_ids),
            "githubRepo": self.github_repo,
            "monitor": self.monitor.to_json(),
            "releaseProjects": [project.to_json() for project in self.release_projects],
            "lastActionMessage": self.last_action_message,
        }
        if self.backup is not None:
            payload["backup"] = self.backup.to_json()
        if self.github is not None:
            payload["github"] = self.github.to_json()
        if self.spot_check is not None:
            payload["spotCheck"] = self.spot_check.to_json()
        if self.docs_check is not None:
            payload["docsCheck"] = self.docs_check.to_json()
        if self.docs_snippets is not None:
            payload["docsSnippets"] = self.docs_snippets.to_json()
        if self.check_run is not None:
            payload["checkRun"] = self.check_run.to_json()
        if self.release_verify is not None:
            payload["releaseVerify"] = self.release_verify.to_json()
        if self.build is not None:
            payload["build"] = self.build.to_json()
        return payload


@dataclass(frozen=True)
class DashboardWorkspaceState:
    workspace_root: Path
    workspace_name: str
    updated_at: datetime
    interval_seconds: int
    repos: tuple[DashboardRepoState, ...]

    @property
    def dirty_repo_count(self) -> int:
        return sum(1 for repo in self.repos if repo.monitor.is_dirty)

    @property
    def publishable_repo_count(self) -> int:
        return sum(1 for repo in self.repos if repo.publishable_project_ids)

    def to_json(self) -> JSONObject:
        return {
            "workspaceRoot": str(self.workspace_root.resolve()),
            "workspaceName": self.workspace_name,
            "updatedAt": self.updated_at.isoformat(),
            "intervalSeconds": self.interval_seconds,
            "dirtyRepoCount": self.dirty_repo_count,
            "publishableRepoCount": self.publishable_repo_count,
            "repos": [repo.to_json() for repo in self.repos],
        }


@dataclass(frozen=True)
class _RepoDescriptor:
    target: ResolvedRepoTarget
    repo_id: str | None
    project_ids: tuple[str, ...]
    publishable_project_ids: tuple[str, ...]
    docs_project_ids: tuple[str, ...]
    github_repo: str | None


@dataclass(frozen=True)
class _DashboardJob:
    kind: str
    repo_name: str
    project_id: str | None = None
    source: str = "auto"


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _str_or_none(value: JSONValue | None) -> str | None:
    match value:
        case str(text):
            return text
        case _:
            return None


def _int_or_none(value: JSONValue | None) -> int | None:
    match value:
        case int(number):
            return number
        case _:
            return None


def _datetime_or_none(value: JSONValue | None) -> datetime | None:
    match value:
        case str(text):
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                return None
        case _:
            return None


def _string_tuple(value: JSONValue | None) -> tuple[str, ...]:
    match value:
        case list() as items:
            values: list[str] = []
            for item in items:
                match item:
                    case str(text):
                        values.append(text)
                    case _:
                        continue
            return tuple(values)
        case _:
            return ()


def _parse_repo_command_state(value: JSONValue | None) -> RepoCommandState | None:
    match value:
        case {
            "kind": str(kind),
            "status": str(status),
            "summary": str(summary),
        }:
            if status == "running":
                return None
            payload = value
            exit_code = _int_or_none(payload.get("exitCode"))
            return RepoCommandState(
                kind=kind,
                status=status,
                summary=summary,
                checked_at=_datetime_or_none(payload.get("checkedAt")),
                started_at=_datetime_or_none(payload.get("startedAt")),
                exit_code=exit_code,
                detail=_str_or_none(payload.get("detail")),
            )
        case _:
            return None


def _parse_github_repo_state(value: JSONValue | None) -> GithubRepoState | None:
    match value:
        case dict() as payload:
            return GithubRepoState(
                checked_at=_datetime_or_none(payload.get("checkedAt")),
                ci_status=_str_or_none(payload.get("ciStatus")),
                ci_name=_str_or_none(payload.get("ciName")),
                ci_url=_str_or_none(payload.get("ciUrl")),
                latest_release_tag=_str_or_none(payload.get("latestReleaseTag")),
                latest_release_url=_str_or_none(payload.get("latestReleaseUrl")),
                latest_release_published_at=_datetime_or_none(payload.get("latestReleasePublishedAt")),
                error=_str_or_none(payload.get("error")),
            )
        case _:
            return None


def _parse_registry_status_state(value: JSONValue) -> RegistryStatusState | None:
    match value:
        case {
            "name": str(name),
            "package": str(package),
            "status": str(status),
        }:
            payload = value
            return RegistryStatusState(
                name=name,
                package=package,
                current_version=_str_or_none(payload.get("currentVersion")),
                latest=_str_or_none(payload.get("latest")),
                status=status,
                diagnostics=_string_tuple(payload.get("diagnostics")),
            )
        case _:
            return None


def _parse_release_project_state(value: JSONValue) -> ReleaseProjectState | None:
    match value:
        case {
            "projectId": str(project_id),
            "publishTarget": str(publish_target),
            "registryVisible": str(registry_visible),
            "dirty": bool() as dirty,
            "stagedCount": int(staged_count),
            "unstagedCount": int(unstaged_count),
            "untrackedCount": int(untracked_count),
        }:
            payload = value
            registry_statuses_value = payload.get("registryStatuses")
            registry_statuses: list[RegistryStatusState] = []
            match registry_statuses_value:
                case list() as items:
                    for item in items:
                        parsed = _parse_registry_status_state(item)
                        if parsed is not None:
                            registry_statuses.append(parsed)
                case _:
                    pass
            return ReleaseProjectState(
                project_id=project_id,
                publish_target=publish_target,
                current_version=_str_or_none(payload.get("currentVersion")),
                registry_latest=_str_or_none(payload.get("registryLatest")),
                registry_names=_string_tuple(payload.get("registryNames")),
                registry_visible=registry_visible,
                registry_statuses=tuple(registry_statuses),
                latest_tag=_str_or_none(payload.get("latestTag")),
                latest_tag_version=_str_or_none(payload.get("latestTagVersion")),
                commits_after_tag=_int_or_none(payload.get("commitsAfterTag")),
                unpushed_commits=_int_or_none(payload.get("unpushedCommits")),
                remote_only_commits=_int_or_none(payload.get("remoteOnlyCommits")),
                dirty=dirty,
                staged_count=staged_count,
                unstaged_count=unstaged_count,
                untracked_count=untracked_count,
                checked_at=_datetime_or_none(payload.get("checkedAt")),
                diagnostics=_string_tuple(payload.get("diagnostics")),
            )
        case _:
            return None


def _cached_repo_payload(repo: DashboardRepoState) -> JSONObject:
    payload: JSONObject = {}
    if repo.release_projects:
        payload["releaseProjects"] = [project.to_json() for project in repo.release_projects]
    if repo.github is not None:
        payload["github"] = repo.github.to_json()
    if repo.spot_check is not None and repo.spot_check.status != "running":
        payload["spotCheck"] = repo.spot_check.to_json()
    if repo.docs_check is not None and repo.docs_check.status != "running":
        payload["docsCheck"] = repo.docs_check.to_json()
    if repo.docs_snippets is not None and repo.docs_snippets.status != "running":
        payload["docsSnippets"] = repo.docs_snippets.to_json()
    if repo.check_run is not None and repo.check_run.status != "running":
        payload["checkRun"] = repo.check_run.to_json()
    if repo.release_verify is not None and repo.release_verify.status != "running":
        payload["releaseVerify"] = repo.release_verify.to_json()
    if repo.build is not None and repo.build.status != "running":
        payload["build"] = repo.build.to_json()
    if repo.last_action_message is not None:
        payload["lastActionMessage"] = repo.last_action_message
    return payload


def _merge_cached_repo_state(repo: DashboardRepoState, payload: JSONObject) -> DashboardRepoState:
    release_projects_raw = payload.get("releaseProjects")
    release_projects: list[ReleaseProjectState] = []
    match release_projects_raw:
        case list() as items:
            for item in items:
                parsed = _parse_release_project_state(item)
                if parsed is not None:
                    release_projects.append(parsed)
        case _:
            pass

    return replace(
        repo,
        release_projects=tuple(release_projects),
        github=_parse_github_repo_state(payload.get("github")),
        spot_check=_parse_repo_command_state(payload.get("spotCheck")),
        docs_check=_parse_repo_command_state(payload.get("docsCheck")),
        docs_snippets=_parse_repo_command_state(payload.get("docsSnippets")),
        check_run=_parse_repo_command_state(payload.get("checkRun")),
        release_verify=_parse_repo_command_state(payload.get("releaseVerify")),
        build=_parse_repo_command_state(payload.get("build")),
        last_action_message=_str_or_none(payload.get("lastActionMessage")),
    )


def _command_started_at(repo: DashboardRepoState, field_name: str) -> datetime | None:
    match field_name:
        case "spot_check":
            command = repo.spot_check
        case "docs_check":
            command = repo.docs_check
        case "docs_snippets":
            command = repo.docs_snippets
        case "check_run":
            command = repo.check_run
        case "release_verify":
            command = repo.release_verify
        case "build":
            command = repo.build
        case _:
            return None
    return command.started_at if command is not None else None


def _command_result_message(command_state: RepoCommandState) -> str:
    detail = command_state.detail
    if detail is not None and detail.strip():
        return f"{command_state.summary}: {detail}"
    return command_state.summary


def _dashboard_summary_payload(snapshot: DashboardWorkspaceState) -> JSONObject:
    return {
        "workspaceRoot": str(snapshot.workspace_root.resolve()),
        "workspaceName": snapshot.workspace_name,
        "updatedAt": snapshot.updated_at.isoformat(),
        "dirtyRepoCount": snapshot.dirty_repo_count,
        "publishableRepoCount": snapshot.publishable_repo_count,
        "repoCount": len(snapshot.repos),
    }


def _monitor_state_from_status(status: RepoStatusRecord) -> MonitorRepoState:
    return MonitorRepoState(
        name=status.name,
        path=status.path.resolve(),
        staged_count=status.staged_count,
        unstaged_count=status.unstaged_count,
        untracked_count=status.untracked_count,
        error=status.error,
        dirty_since=status.oldest_dirty_timestamp,
        branch_name=status.tracking.branch_name if status.tracking is not None else None,
        upstream_name=status.tracking.upstream_name if status.tracking is not None else None,
        ahead_count=status.tracking.ahead_count if status.tracking is not None else None,
        behind_count=status.tracking.behind_count if status.tracking is not None else None,
        tracking_refreshed_at=status.tracking_refreshed_at,
    )


def _empty_monitor_state(name: str, path: Path) -> MonitorRepoState:
    return MonitorRepoState(
        name=name,
        path=path.resolve(),
        staged_count=0,
        unstaged_count=0,
        untracked_count=0,
    )


def _repo_sort_key(repo: DashboardRepoState) -> tuple[int, float, str]:
    if not repo.monitor.is_dirty:
        return (1, float("inf"), repo.name)
    if repo.monitor.dirty_since is None:
        return (0, float("inf"), repo.name)
    return (0, repo.monitor.dirty_since.timestamp(), repo.name)


def _command_is_due(command: RepoCommandState | None, *, now: datetime, refresh_after: timedelta) -> bool:
    if command is None or command.checked_at is None:
        return True
    if command.status == "running":
        return False
    return (now - command.checked_at) >= refresh_after


def _capture_json_report(
    task: Callable[..., int],
    /,
    *args: TaskReportArg,
    **kwargs: TaskReportArg,
) -> tuple[int, JSONObject]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = task(*args, **kwargs)
    raw_output = buffer.getvalue().strip()
    if not raw_output:
        return exit_code, {"error": "Task did not emit JSON output."}

    try:
        parsed: JSONValue = json.loads(raw_output)
    except JSONDecodeError as ex:
        return exit_code, {"error": f"Task emitted invalid JSON output: {ex}"}
    match parsed:
        case dict() as payload:
            return exit_code, payload
        case _:
            return exit_code, {"error": "Task emitted non-object JSON output."}


def _command_summary(
    kind: str,
    *,
    exit_code: int,
    status: CommandStatus,
    summary: str,
    detail: str | None,
    checked_at: datetime,
) -> RepoCommandState:
    return RepoCommandState(
        kind=kind,
        status=status,
        summary=summary,
        checked_at=checked_at,
        exit_code=exit_code,
        detail=detail,
    )


def _failed_command_state(kind: str, *, detail: str, checked_at: datetime) -> RepoCommandState:
    return RepoCommandState(
        kind=kind,
        status="error",
        summary="failed",
        checked_at=checked_at,
        detail=detail,
        exit_code=1,
    )


def _check_command_state(kind: str, payload: JSONObject, *, exit_code: int, checked_at: datetime) -> RepoCommandState:
    summary_value = payload.get("summary")
    error_value = payload.get("error")

    error_count = 0
    warning_count = 0
    info_count = 0
    fixed_count = 0
    match summary_value:
        case {
            "error": int(error_count_value),
            "warning": int(warning_count_value),
            "info": int(info_count_value),
            "fixed": int(fixed_count_value),
        }:
            error_count = error_count_value
            warning_count = warning_count_value
            info_count = info_count_value
            fixed_count = fixed_count_value
        case _:
            pass

    detail: str | None = None
    match error_value:
        case str(error_text):
            detail = error_text
        case _:
            detail = None

    status = "success"
    if error_count > 0 or exit_code != 0:
        status = "error"
    elif warning_count > 0:
        status = "warning"

    summary = f"errors {error_count}, warnings {warning_count}, info {info_count}"
    if fixed_count > 0:
        summary = f"{summary}, fixed {fixed_count}"
    return _command_summary(
        kind,
        exit_code=exit_code,
        status=status,
        summary=summary,
        detail=detail,
        checked_at=checked_at,
    )


def _docs_command_state(kind: str, payload: JSONObject, *, exit_code: int, checked_at: datetime) -> RepoCommandState:
    summary_value = payload.get("summary")
    error_count = 0
    warning_count = 0
    skipped_count = 0
    match summary_value:
        case {
            "error": int(error_count_value),
            "warning": int(warning_count_value),
            "skipped": int(skipped_count_value),
        }:
            error_count = error_count_value
            warning_count = warning_count_value
            skipped_count = skipped_count_value
        case _:
            pass

    detail: str | None = None
    match payload.get("error"):
        case str(error_text):
            detail = error_text
        case _:
            detail = None

    status = "success"
    if error_count > 0 or exit_code != 0:
        status = "error"
    elif warning_count > 0:
        status = "warning"
    elif skipped_count > 0:
        status = "skipped"

    return _command_summary(
        kind,
        exit_code=exit_code,
        status=status,
        summary=f"errors {error_count}, warnings {warning_count}, skipped {skipped_count}",
        detail=detail,
        checked_at=checked_at,
    )


def _result_counts(payload: JSONObject) -> tuple[int, int, int]:
    results = payload.get("results")
    success_count = 0
    skipped_count = 0
    failed_count = 0
    match results:
        case list() as items:
            for item in items:
                match item:
                    case {"status": str(status_value)}:
                        if status_value == "success":
                            success_count += 1
                        elif status_value == "skipped":
                            skipped_count += 1
                        elif status_value in {"failed", "error"}:
                            failed_count += 1
                    case _:
                        continue
        case _:
            pass
    return success_count, skipped_count, failed_count


def _simple_results_command_state(
    kind: str,
    payload: JSONObject,
    *,
    exit_code: int,
    checked_at: datetime,
) -> RepoCommandState:
    success_count, skipped_count, failed_count = _result_counts(payload)
    detail: str | None = None
    match payload.get("error"):
        case str(error_text):
            detail = error_text
        case _:
            detail = None

    status = "success"
    if failed_count > 0 or exit_code != 0:
        status = "error"
    elif skipped_count > 0 and success_count == 0:
        status = "skipped"

    return _command_summary(
        kind,
        exit_code=exit_code,
        status=status,
        summary=f"success {success_count}, skipped {skipped_count}, failed {failed_count}",
        detail=detail,
        checked_at=checked_at,
    )


def _registry_status(current_version: str | None, registry_name: str, package: str, latest: str | None, versions: tuple[str, ...], diagnostics: tuple[str, ...]) -> RegistryStatusState:
    if current_version is None:
        status = "unknown"
    elif current_version in versions:
        status = "ok"
    elif not versions:
        status = "error"
    else:
        status = "warn"

    return RegistryStatusState(
        name=registry_name,
        package=package,
        current_version=current_version,
        latest=latest,
        status=status,
        diagnostics=diagnostics,
    )


def _overall_registry_visibility(registry_statuses: tuple[RegistryStatusState, ...]) -> str:
    if not registry_statuses:
        return "unknown"
    if any(registry.status == "ok" for registry in registry_statuses):
        return "published"
    if any(registry.status == "warn" for registry in registry_statuses):
        return "missing"
    if any(registry.status == "error" for registry in registry_statuses):
        return "unknown"
    return "unknown"


def _release_project_state(report: ProjectVersionReport, *, checked_at: datetime) -> ReleaseProjectState:
    latest_tag = report.git_state.latest_tag
    primary_registry = report.registry
    diagnostics = tuple(f"{diagnostic.source}: {diagnostic.message}" for diagnostic in report.diagnostics)
    registry_statuses = tuple(
        _registry_status(
            report.current_version,
            registry.name,
            registry.package,
            registry.latest,
            registry.versions,
            tuple(f"{diagnostic.source}: {diagnostic.message}" for diagnostic in registry.diagnostics),
        )
        for registry in report.registries
    )


def _backup_state_from_summary(summary: BackupRepoSummary | None) -> BackupStatusState | None:
    if summary is None:
        return None
    return BackupStatusState(
        attempted_at=summary.last_attempted_at,
        finished_at=summary.last_finished_at,
        success_at=summary.last_success_at,
        status=summary.last_status,
        message=summary.last_message,
        target_name=summary.last_backup_target_name,
        snapshot_id=summary.last_snapshot_id,
    )
    return ReleaseProjectState(
        project_id=report.project_id,
        publish_target=report.publish_target,
        current_version=report.current_version,
        registry_latest=primary_registry.latest if primary_registry is not None else None,
        registry_names=tuple(registry.name for registry in report.registries),
        registry_visible=_overall_registry_visibility(registry_statuses),
        registry_statuses=registry_statuses,
        latest_tag=latest_tag.tag if latest_tag is not None else None,
        latest_tag_version=latest_tag.version if latest_tag is not None else None,
        commits_after_tag=latest_tag.commits_after if latest_tag is not None else None,
        unpushed_commits=report.git_state.unpushed_commits,
        remote_only_commits=report.git_state.remote_only_commits,
        dirty=not report.git_state.working_tree.clean,
        staged_count=report.git_state.working_tree.staged_count,
        unstaged_count=report.git_state.working_tree.unstaged_count,
        untracked_count=report.git_state.working_tree.untracked_count,
        checked_at=checked_at,
        diagnostics=diagnostics,
    )


def _github_headers(config: Config) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "wabbit-dev-dashboard",
    }
    token = config.github_token
    if token is not None and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


def _read_json_url(url: str, *, headers: dict[str, str]) -> JSONObject:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        parsed: JSONValue = json.loads(response.read().decode("utf-8"))
    match parsed:
        case dict() as payload:
            return payload
        case _:
            raise ValueError(f"Expected JSON object from {url}")


def _fetch_github_repo_state(config: Config, github_repo: str) -> GithubRepoState:
    checked_at = _now_utc()
    headers = _github_headers(config)

    ci_status: str | None = None
    ci_name: str | None = None
    ci_url: str | None = None
    latest_release_tag: str | None = None
    latest_release_url: str | None = None
    latest_release_published_at: datetime | None = None
    errors: list[str] = []

    runs_url = f"https://api.github.com/repos/{github_repo}/actions/runs?per_page=1"
    try:
        runs_payload = _read_json_url(runs_url, headers=headers)
        match runs_payload:
            case {"workflow_runs": [first_run, *_rest]}:
                match first_run:
                    case {
                        "name": str(run_name),
                        "status": str(run_status),
                        "html_url": str(run_url),
                    }:
                        ci_name = run_name
                        ci_url = run_url
                        conclusion_value: str | None
                        match first_run.get("conclusion"):
                            case str(conclusion_text):
                                conclusion_value = conclusion_text
                            case _:
                                conclusion_value = None
                        if run_status != "completed":
                            ci_status = "running"
                        elif conclusion_value == "success":
                            ci_status = "success"
                        elif conclusion_value is None:
                            ci_status = "unknown"
                        else:
                            ci_status = conclusion_value
                    case _:
                        errors.append("GitHub Actions payload missing workflow run fields.")
            case _:
                errors.append("GitHub Actions payload missing workflow runs.")
    except urllib.error.HTTPError as ex:
        errors.append(f"actions query failed: HTTP {ex.code}")
    except Exception as ex:
        errors.append(f"actions query failed: {ex}")

    release_url = f"https://api.github.com/repos/{github_repo}/releases/latest"
    try:
        release_payload = _read_json_url(release_url, headers=headers)
        match release_payload:
            case {
                "tag_name": str(tag_name),
                "html_url": str(release_html_url),
            }:
                latest_release_tag = tag_name
                latest_release_url = release_html_url
                match release_payload.get("published_at"):
                    case str(published_at_text):
                        latest_release_published_at = datetime.fromisoformat(
                            published_at_text.replace("Z", "+00:00")
                        )
                    case _:
                        latest_release_published_at = None
            case _:
                errors.append("latest release payload missing expected fields.")
    except urllib.error.HTTPError as ex:
        if ex.code != 404:
            errors.append(f"release query failed: HTTP {ex.code}")
    except Exception as ex:
        errors.append(f"release query failed: {ex}")

    return GithubRepoState(
        checked_at=checked_at,
        ci_status=ci_status,
        ci_name=ci_name,
        ci_url=ci_url,
        latest_release_tag=latest_release_tag,
        latest_release_url=latest_release_url,
        latest_release_published_at=latest_release_published_at,
        error="; ".join(errors) if errors else None,
    )


def _project_is_publishable(project: Project) -> bool:
    if project.quarantine or not project.publish:
        return False
    return determine_publish_target(project) != "skip"


def _repo_github_slug(projects: Sequence[Project]) -> str | None:
    slugs: list[str] = []
    for project in projects:
        github_repo = project.github_repo
        if github_repo is None:
            continue
        normalized = github_repo.strip()
        if not normalized:
            continue
        if normalized not in slugs:
            slugs.append(normalized)
    if not slugs:
        return None
    return slugs[0]


def _repo_descriptors(config: Config) -> tuple[_RepoDescriptor, ...]:
    descriptors: list[_RepoDescriptor] = []
    for target in configured_repo_targets(config):
        projects = [config.defined_projects[project_id] for project_id in target.project_ids if project_id in config.defined_projects]
        publishable_project_ids = tuple(
            project.project_id
            for project in projects
            if project.project_id is not None and _project_is_publishable(project)
        )
        docs_project_ids = tuple(
            project.project_id
            for project in projects
            if project.project_id is not None and project.docs_enabled
        )
        descriptors.append(
            _RepoDescriptor(
                target=target,
                repo_id=target.repo_id,
                project_ids=target.project_ids,
                publishable_project_ids=publishable_project_ids,
                docs_project_ids=docs_project_ids,
                github_repo=_repo_github_slug(projects),
            )
        )
    return tuple(descriptors)


def _initial_repo_state(descriptor: _RepoDescriptor) -> DashboardRepoState:
    return DashboardRepoState(
        name=descriptor.target.name,
        path=descriptor.target.path.resolve(),
        repo_id=descriptor.repo_id,
        project_ids=descriptor.project_ids,
        publishable_project_ids=descriptor.publishable_project_ids,
        docs_project_ids=descriptor.docs_project_ids,
        github_repo=descriptor.github_repo,
        monitor=_empty_monitor_state(descriptor.target.name, descriptor.target.path),
    )


class DashboardCoordinator:
    def __init__(self, workspace_root: Path, *, interval_seconds: int = 60):
        self.workspace_root = workspace_root.resolve()
        self.interval_seconds = interval_seconds
        self.paths: ServicePaths = service_paths_for_workspace(self.workspace_root)
        self._config = load_config(self.workspace_root)
        self._descriptors = _repo_descriptors(self._config)
        self._repo_states: dict[str, DashboardRepoState] = {
            descriptor.target.name: _initial_repo_state(descriptor) for descriptor in self._descriptors
        }
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._status_thread = threading.Thread(target=self._run_status_loop, name="dev-dashboard-status", daemon=True)
        self._job_thread = threading.Thread(target=self._run_job_loop, name="dev-dashboard-jobs", daemon=True)
        self._job_queue: Queue[_DashboardJob] = Queue()
        self._queued_job_keys: set[tuple[str, str, str | None]] = set()
        self._running_job_keys: set[tuple[str, str, str | None]] = set()
        self._updated_at = _now_utc()
        self._status_index = 0
        self._load_backup_summaries()
        self._load_persisted_repo_cache()

    def start(self) -> None:
        self._status_thread.start()
        self._job_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._refresh_event.set()
        self._status_thread.join(timeout=2.0)
        self._job_thread.join(timeout=2.0)

    def request_refresh(self) -> None:
        self._refresh_event.set()

    def snapshot(self) -> DashboardWorkspaceState:
        with self._lock:
            repos = tuple(sorted(self._repo_states.values(), key=_repo_sort_key))
            updated_at = self._updated_at
        return DashboardWorkspaceState(
            workspace_root=self.workspace_root,
            workspace_name=self.workspace_root.name or "workspace",
            updated_at=updated_at,
            interval_seconds=self.interval_seconds,
            repos=repos,
        )

    def run_difftool(self, repo_name: str) -> None:
        self._enqueue_job(_DashboardJob(kind="difftool", repo_name=repo_name, source="user"))

    def run_commit(self, repo_name: str) -> None:
        self._enqueue_job(_DashboardJob(kind="commit", repo_name=repo_name, source="user"))

    def run_push(self, repo_name: str) -> None:
        self._enqueue_job(_DashboardJob(kind="push", repo_name=repo_name, source="user"))

    def run_check(self, repo_name: str) -> None:
        self._enqueue_job(_DashboardJob(kind="check-run", repo_name=repo_name, source="user"))

    def run_docs_check(self, repo_name: str) -> None:
        self._enqueue_job(_DashboardJob(kind="docs-check", repo_name=repo_name, source="user"))

    def run_docs_snippets(self, repo_name: str) -> None:
        self._enqueue_job(_DashboardJob(kind="docs-snippets", repo_name=repo_name, source="user"))

    def run_docs_verify(self, repo_name: str) -> None:
        self.run_docs_check(repo_name)
        self.run_docs_snippets(repo_name)

    def run_security_check(self, repo_name: str) -> None:
        self._enqueue_job(_DashboardJob(kind="spot-check", repo_name=repo_name, source="user"))

    def run_release_verify(self, repo_name: str) -> None:
        self._enqueue_job(_DashboardJob(kind="release-verify", repo_name=repo_name, source="user"))

    def run_build(self, repo_name: str) -> None:
        self._enqueue_job(_DashboardJob(kind="build", repo_name=repo_name, source="user"))

    def _job_key(self, job: _DashboardJob) -> tuple[str, str, str | None]:
        return (job.repo_name, job.kind, job.project_id)

    def _enqueue_job(self, job: _DashboardJob) -> None:
        key = self._job_key(job)
        with self._lock:
            if key in self._queued_job_keys or key in self._running_job_keys:
                return
            self._queued_job_keys.add(key)
        self._job_queue.put(job)

    def _load_persisted_repo_cache(self) -> None:
        latest_updated_at: datetime | None = None
        for entry in load_dashboard_repo_caches(self.paths):
            repo = self._repo_states.get(entry.repo_name)
            if repo is None:
                continue
            if entry.repo_path != repo.path.resolve():
                continue
            self._repo_states[entry.repo_name] = _merge_cached_repo_state(repo, entry.payload)
            if latest_updated_at is None or entry.updated_at > latest_updated_at:
                latest_updated_at = entry.updated_at
        if latest_updated_at is not None:
            self._updated_at = latest_updated_at

    def _load_backup_summaries(self) -> None:
        for summary in load_backup_repo_summaries(self.paths):
            repo = self._repo_states.get(summary.repo_name)
            if repo is None:
                continue
            if summary.repo_path != repo.path.resolve():
                continue
            self._repo_states[summary.repo_name] = replace(repo, backup=_backup_state_from_summary(summary))

    def _persist_repo_cache(self, repo_name: str, *, updated_at: datetime) -> None:
        with self._lock:
            repo = self._repo_states.get(repo_name)
        if repo is None:
            return
        save_dashboard_repo_cache(
            self.paths,
            repo_name=repo.name,
            repo_path=repo.path,
            updated_at=updated_at,
            payload=_cached_repo_payload(repo),
        )

    def _record_action_history(
        self,
        job: _DashboardJob,
        *,
        status: str,
        message: str,
        started_at: datetime | None,
        finished_at: datetime,
    ) -> None:
        if job.source != "user":
            return
        with self._lock:
            repo = self._repo_states.get(job.repo_name)
        if repo is None:
            return
        record_dashboard_action(
            self.paths,
            repo_name=repo.name,
            repo_path=repo.path,
            action_kind=job.kind,
            action_source=job.source,
            status=status,
            message=message,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _run_status_loop(self) -> None:
        while not self._stop_event.is_set():
            descriptors = self._descriptors
            if not descriptors:
                self._wait_for_next_status_tick(1.0)
                continue

            descriptor = descriptors[self._status_index % len(descriptors)]
            self._status_index = (self._status_index + 1) % len(descriptors)
            try:
                status_record = collect_repo_status_record(descriptor.target)
                monitor_state = _monitor_state_from_status(status_record)
            except Exception as ex:
                monitor_state = replace(
                    _empty_monitor_state(descriptor.target.name, descriptor.target.path),
                    error=str(ex),
                )
            backup_state_loaded = False
            backup_state: BackupStatusState | None = None
            try:
                backup_state = _backup_state_from_summary(load_backup_repo_summary(self.paths, descriptor.target.name))
                backup_state_loaded = True
            except Exception:
                backup_state_loaded = False
            with self._lock:
                existing = self._repo_states[descriptor.target.name]
                effective_backup_state = backup_state if backup_state_loaded else existing.backup
                self._repo_states[descriptor.target.name] = replace(
                    existing,
                    monitor=monitor_state,
                    backup=effective_backup_state,
                )
                self._updated_at = _now_utc()
            self._write_state_file()
            self._maybe_enqueue_background_job(_now_utc())
            spacing_seconds = repo_check_spacing_seconds(self.interval_seconds, len(descriptors))
            if self._wait_for_next_status_tick(spacing_seconds):
                continue

    def _wait_for_next_status_tick(self, seconds: float) -> bool:
        if seconds <= 0:
            return self._refresh_event.is_set()
        deadline = _now_utc() + timedelta(seconds=seconds)
        while not self._stop_event.is_set():
            if self._refresh_event.is_set():
                self._refresh_event.clear()
                return True
            if _now_utc() >= deadline:
                return False
            self._refresh_event.wait(timeout=min(0.25, seconds))
        return True

    def _maybe_enqueue_background_job(self, now: datetime) -> None:
        snapshot = self.snapshot()

        for repo in snapshot.repos:
            if repo.publishable_project_ids:
                for project_id in repo.publishable_project_ids:
                    existing_release = next((item for item in repo.release_projects if item.project_id == project_id), None)
                    if existing_release is None or existing_release.checked_at is None:
                        self._enqueue_job(_DashboardJob(kind="versions", repo_name=repo.name, project_id=project_id))
                        return
                    if (now - existing_release.checked_at) >= _VERSIONS_REFRESH_AFTER:
                        self._enqueue_job(_DashboardJob(kind="versions", repo_name=repo.name, project_id=project_id))
                        return

            if repo.github_repo is not None:
                github_state = repo.github
                if github_state is None or github_state.checked_at is None:
                    self._enqueue_job(_DashboardJob(kind="github", repo_name=repo.name))
                    return
                if (now - github_state.checked_at) >= _GITHUB_REFRESH_AFTER:
                    self._enqueue_job(_DashboardJob(kind="github", repo_name=repo.name))
                    return

            if _command_is_due(repo.spot_check, now=now, refresh_after=_SPOT_CHECK_REFRESH_AFTER):
                self._enqueue_job(_DashboardJob(kind="spot-check", repo_name=repo.name))
                return

            if repo.docs_project_ids and _command_is_due(repo.docs_check, now=now, refresh_after=_DOCS_CHECK_REFRESH_AFTER):
                self._enqueue_job(_DashboardJob(kind="docs-check", repo_name=repo.name))
                return

            if repo.docs_project_ids and _command_is_due(
                repo.docs_snippets,
                now=now,
                refresh_after=_DOCS_SNIPPETS_REFRESH_AFTER,
            ):
                self._enqueue_job(_DashboardJob(kind="docs-snippets", repo_name=repo.name))
                return

    def _run_job_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._job_queue.get(timeout=_JOB_IDLE_TIMEOUT_SECONDS)
            except Empty:
                continue

            key = self._job_key(job)
            with self._lock:
                self._queued_job_keys.discard(key)
                self._running_job_keys.add(key)
            try:
                self._run_job(job)
            except Exception as ex:
                self._record_job_failure(job, str(ex))
            finally:
                with self._lock:
                    self._running_job_keys.discard(key)
                    self._updated_at = _now_utc()
                self._write_state_file()

    def _set_command_running(self, repo_name: str, field_name: str, kind: str) -> None:
        with self._lock:
            repo = self._repo_states[repo_name]
            running_state = RepoCommandState(
                kind=kind,
                status="running",
                summary="Running...",
                started_at=_now_utc(),
            )
            self._repo_states[repo_name] = replace(repo, **{field_name: running_state})

    def _set_last_action_message(self, repo_name: str, message: str, *, updated_at: datetime) -> None:
        with self._lock:
            repo = self._repo_states[repo_name]
            self._repo_states[repo_name] = replace(repo, last_action_message=message)
        self._persist_repo_cache(repo_name, updated_at=updated_at)

    def _set_command_result(
        self,
        job: _DashboardJob,
        *,
        field_name: str,
        command_state: RepoCommandState,
        updated_at: datetime,
    ) -> None:
        started_at: datetime | None
        with self._lock:
            repo = self._repo_states[job.repo_name]
            started_at = _command_started_at(repo, field_name)
            self._repo_states[job.repo_name] = replace(repo, **{field_name: command_state})
        self._persist_repo_cache(job.repo_name, updated_at=updated_at)
        self._record_action_history(
            job,
            status=command_state.status,
            message=_command_result_message(command_state),
            started_at=started_at,
            finished_at=updated_at,
        )

    def _record_job_failure(self, job: _DashboardJob, detail: str) -> None:
        checked_at = _now_utc()
        action_started_at: datetime | None = None
        should_persist_cache = False
        with self._lock:
            repo = self._repo_states[job.repo_name]
            match job.kind:
                case "github":
                    self._repo_states[job.repo_name] = replace(
                        repo,
                        github=GithubRepoState(checked_at=checked_at, error=detail),
                    )
                    should_persist_cache = True
                case "spot-check":
                    action_started_at = _command_started_at(repo, "spot_check")
                    self._repo_states[job.repo_name] = replace(
                        repo,
                        spot_check=_failed_command_state("spot-check", detail=detail, checked_at=checked_at),
                    )
                    should_persist_cache = True
                case "docs-check":
                    action_started_at = _command_started_at(repo, "docs_check")
                    self._repo_states[job.repo_name] = replace(
                        repo,
                        docs_check=_failed_command_state("docs-check", detail=detail, checked_at=checked_at),
                    )
                    should_persist_cache = True
                case "docs-snippets":
                    action_started_at = _command_started_at(repo, "docs_snippets")
                    self._repo_states[job.repo_name] = replace(
                        repo,
                        docs_snippets=_failed_command_state("docs-snippets", detail=detail, checked_at=checked_at),
                    )
                    should_persist_cache = True
                case "check-run":
                    action_started_at = _command_started_at(repo, "check_run")
                    self._repo_states[job.repo_name] = replace(
                        repo,
                        check_run=_failed_command_state("check", detail=detail, checked_at=checked_at),
                    )
                    should_persist_cache = True
                case "release-verify":
                    action_started_at = _command_started_at(repo, "release_verify")
                    self._repo_states[job.repo_name] = replace(
                        repo,
                        release_verify=_failed_command_state("release-verify", detail=detail, checked_at=checked_at),
                    )
                    should_persist_cache = True
                case "build":
                    action_started_at = _command_started_at(repo, "build")
                    self._repo_states[job.repo_name] = replace(
                        repo,
                        build=_failed_command_state("build", detail=detail, checked_at=checked_at),
                    )
                    should_persist_cache = True
                case _:
                    self._repo_states[job.repo_name] = replace(repo, last_action_message=f"{job.kind} failed: {detail}")
                    should_persist_cache = True
        if should_persist_cache:
            self._persist_repo_cache(job.repo_name, updated_at=checked_at)
        self._record_action_history(
            job,
            status="error",
            message=detail,
            started_at=action_started_at,
            finished_at=checked_at,
        )

    def _run_job(self, job: _DashboardJob) -> None:
        match job.kind:
            case "versions":
                if job.project_id is None:
                    return
                report = build_project_version_report(job.project_id, self._config)
                checked_at = _now_utc()
                release_state = _release_project_state(report, checked_at=checked_at)
                with self._lock:
                    repo = self._repo_states[job.repo_name]
                    updated_projects = [item for item in repo.release_projects if item.project_id != job.project_id]
                    updated_projects.append(release_state)
                    updated_projects.sort(key=lambda item: item.project_id)
                    self._repo_states[job.repo_name] = replace(repo, release_projects=tuple(updated_projects))
                self._persist_repo_cache(job.repo_name, updated_at=checked_at)
            case "github":
                descriptor = next((item for item in self._descriptors if item.target.name == job.repo_name), None)
                if descriptor is None or descriptor.github_repo is None:
                    return
                github_state = _fetch_github_repo_state(self._config, descriptor.github_repo)
                checked_at = _now_utc()
                with self._lock:
                    repo = self._repo_states[job.repo_name]
                    self._repo_states[job.repo_name] = replace(repo, github=github_state)
                self._persist_repo_cache(job.repo_name, updated_at=checked_at)
            case "spot-check":
                self._set_command_running(job.repo_name, "spot_check", "spot-check")
                exit_code, payload = _capture_json_report(
                    check_main,
                    job.repo_name,
                    None,
                    False,
                    bundles=("metadata", "security"),
                    json_output=True,
                )
                checked_at = _now_utc()
                command_state = _check_command_state("spot-check", payload, exit_code=exit_code, checked_at=checked_at)
                self._set_command_result(job, field_name="spot_check", command_state=command_state, updated_at=checked_at)
            case "docs-check":
                self._set_command_running(job.repo_name, "docs_check", "docs-check")
                exit_code, payload = _capture_json_report(
                    docs_check,
                    [job.repo_name],
                    semantic=False,
                    json_output=True,
                )
                checked_at = _now_utc()
                command_state = _docs_command_state("docs-check", payload, exit_code=exit_code, checked_at=checked_at)
                self._set_command_result(job, field_name="docs_check", command_state=command_state, updated_at=checked_at)
            case "docs-snippets":
                self._set_command_running(job.repo_name, "docs_snippets", "docs-snippets")
                exit_code, payload = _capture_json_report(
                    docs_snippets,
                    [job.repo_name],
                    verify=True,
                    json_output=True,
                )
                checked_at = _now_utc()
                command_state = _docs_command_state(
                    "docs-snippets",
                    payload,
                    exit_code=exit_code,
                    checked_at=checked_at,
                )
                self._set_command_result(
                    job,
                    field_name="docs_snippets",
                    command_state=command_state,
                    updated_at=checked_at,
                )
            case "check-run":
                self._set_command_running(job.repo_name, "check_run", "check")
                exit_code, payload = _capture_json_report(
                    check_main,
                    job.repo_name,
                    None,
                    False,
                    bundles=(),
                    json_output=True,
                )
                checked_at = _now_utc()
                command_state = _check_command_state("check", payload, exit_code=exit_code, checked_at=checked_at)
                self._set_command_result(job, field_name="check_run", command_state=command_state, updated_at=checked_at)
            case "release-verify":
                self._set_command_running(job.repo_name, "release_verify", "release-verify")
                exit_code, payload = _capture_json_report(
                    release_verify,
                    [job.repo_name],
                    json_output=True,
                )
                checked_at = _now_utc()
                command_state = _simple_results_command_state(
                    "release-verify",
                    payload,
                    exit_code=exit_code,
                    checked_at=checked_at,
                )
                self._set_command_result(
                    job,
                    field_name="release_verify",
                    command_state=command_state,
                    updated_at=checked_at,
                )
            case "build":
                self._set_command_running(job.repo_name, "build", "build")
                exit_code, payload = _capture_json_report(
                    build,
                    [job.repo_name],
                    json_output=True,
                )
                checked_at = _now_utc()
                command_state = _simple_results_command_state("build", payload, exit_code=exit_code, checked_at=checked_at)
                self._set_command_result(job, field_name="build", command_state=command_state, updated_at=checked_at)
            case "difftool":
                result = open_repo_in_difftool(self.workspace_root, self._repo_states[job.repo_name].path)
                finished_at = _now_utc()
                self._set_last_action_message(job.repo_name, result.message, updated_at=finished_at)
                self._record_action_history(
                    job,
                    status="success" if result.ok else "error",
                    message=result.message,
                    started_at=None,
                    finished_at=finished_at,
                )
            case "commit":
                result = commit_repo_target(self.workspace_root, job.repo_name)
                finished_at = _now_utc()
                self._set_last_action_message(job.repo_name, result.message, updated_at=finished_at)
                self._record_action_history(
                    job,
                    status="success" if result.ok else "error",
                    message=result.message,
                    started_at=None,
                    finished_at=finished_at,
                )
                self.request_refresh()
            case "push":
                result = push_repo_target(self.workspace_root, job.repo_name)
                finished_at = _now_utc()
                self._set_last_action_message(job.repo_name, result.message, updated_at=finished_at)
                self._record_action_history(
                    job,
                    status="success" if result.ok else "error",
                    message=result.message,
                    started_at=None,
                    finished_at=finished_at,
                )
                self.request_refresh()
            case _:
                finished_at = _now_utc()
                message = f"{job.kind}: unsupported job"
                self._set_last_action_message(job.repo_name, message, updated_at=finished_at)
                self._record_action_history(
                    job,
                    status="error",
                    message=message,
                    started_at=None,
                    finished_at=finished_at,
                )

    def _write_state_file(self) -> None:
        snapshot = self.snapshot()
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self.paths.dashboard_state_file.write_text(
            json.dumps(_dashboard_summary_payload(snapshot), indent=2) + "\n",
            encoding="utf-8",
        )


__all__ = [
    "BackupStatusState",
    "DashboardCoordinator",
    "DashboardRepoState",
    "DashboardWorkspaceState",
    "GithubRepoState",
    "RegistryStatusState",
    "ReleaseProjectState",
    "RepoCommandState",
]
