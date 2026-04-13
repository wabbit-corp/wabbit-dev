from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from dev.json_types import JSONObject, JSONValue
from dev.service_support import ServicePaths, ensure_service_dir

type SqlScalar = str | int | float | None

_CREATE_BACKUP_REPO_STATE_SQL = """
CREATE TABLE IF NOT EXISTS backup_repo_state (
    repo_name TEXT PRIMARY KEY,
    repo_path TEXT NOT NULL,
    last_attempted_at TEXT,
    last_finished_at TEXT,
    last_success_at TEXT,
    last_status TEXT,
    last_message TEXT,
    last_backup_target_name TEXT,
    last_snapshot_id TEXT
);
"""

_CREATE_BACKUP_RUN_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS backup_run_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_name TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    backup_target_name TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    ok INTEGER NOT NULL,
    message TEXT NOT NULL,
    snapshot_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);
"""

_CREATE_BACKUP_RUN_HISTORY_REPO_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_backup_run_history_repo_finished_at
ON backup_run_history(repo_name, finished_at DESC);
"""

_CREATE_DASHBOARD_REPO_CACHE_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_repo_cache (
    repo_name TEXT PRIMARY KEY,
    repo_path TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""

_CREATE_DASHBOARD_ACTION_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_action_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_name TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    action_kind TEXT NOT NULL,
    action_source TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT NOT NULL
);
"""

_CREATE_DASHBOARD_ACTION_HISTORY_REPO_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_dashboard_action_history_repo_finished_at
ON dashboard_action_history(repo_name, finished_at DESC);
"""


@dataclass(frozen=True)
class BackupRepoSummary:
    repo_name: str
    repo_path: Path
    last_attempted_at: datetime | None
    last_finished_at: datetime | None
    last_success_at: datetime | None
    last_status: str | None
    last_message: str | None
    last_backup_target_name: str | None
    last_snapshot_id: str | None


@dataclass(frozen=True)
class BackupRunHistoryEntry:
    entry_id: int
    repo_name: str
    repo_path: Path
    backup_target_name: str
    action: str
    reason: str
    ok: bool
    message: str
    snapshot_id: str | None
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True)
class DashboardRepoCacheEntry:
    repo_name: str
    repo_path: Path
    updated_at: datetime
    payload: JSONObject


@dataclass(frozen=True)
class DashboardActionHistoryEntry:
    entry_id: int
    repo_name: str
    repo_path: Path
    action_kind: str
    action_source: str
    status: str
    message: str
    started_at: datetime | None
    finished_at: datetime


def _connect(paths: ServicePaths) -> sqlite3.Connection:
    ensure_service_dir(paths)
    connection = sqlite3.connect(paths.database_file, timeout=60)
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    with connection:
        connection.execute(_CREATE_BACKUP_REPO_STATE_SQL)
        connection.execute(_CREATE_BACKUP_RUN_HISTORY_SQL)
        connection.execute(_CREATE_BACKUP_RUN_HISTORY_REPO_INDEX_SQL)
        connection.execute(_CREATE_DASHBOARD_REPO_CACHE_SQL)
        connection.execute(_CREATE_DASHBOARD_ACTION_HISTORY_SQL)
        connection.execute(_CREATE_DASHBOARD_ACTION_HISTORY_REPO_INDEX_SQL)
    return connection


def _isoformat_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_datetime(value: SqlScalar) -> datetime | None:
    match value:
        case None:
            return None
        case str(text):
            return datetime.fromisoformat(text)
        case _:
            return None


def _json_text(value: JSONValue) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _parse_json_object(value: SqlScalar) -> JSONObject | None:
    match value:
        case str(text):
            try:
                parsed: JSONValue = json.loads(text)
            except json.JSONDecodeError:
                return None
            match parsed:
                case dict() as payload:
                    return payload
                case _:
                    return None
        case _:
            return None


def _parse_backup_repo_summary_row(row: tuple[SqlScalar, ...]) -> BackupRepoSummary | None:
    if len(row) != 9:
        return None
    match row:
        case (
            str(repo_name),
            str(repo_path),
            last_attempted_at_raw,
            last_finished_at_raw,
            last_success_at_raw,
            last_status_raw,
            last_message_raw,
            last_backup_target_name_raw,
            last_snapshot_id_raw,
        ):
            last_status: str | None
            match last_status_raw:
                case None:
                    last_status = None
                case str(status_text):
                    last_status = status_text
                case _:
                    last_status = None

            last_message: str | None
            match last_message_raw:
                case None:
                    last_message = None
                case str(message_text):
                    last_message = message_text
                case _:
                    last_message = None

            last_backup_target_name: str | None
            match last_backup_target_name_raw:
                case None:
                    last_backup_target_name = None
                case str(target_text):
                    last_backup_target_name = target_text
                case _:
                    last_backup_target_name = None

            last_snapshot_id: str | None
            match last_snapshot_id_raw:
                case None:
                    last_snapshot_id = None
                case str(snapshot_text):
                    last_snapshot_id = snapshot_text
                case _:
                    last_snapshot_id = None

            return BackupRepoSummary(
                repo_name=repo_name,
                repo_path=Path(repo_path),
                last_attempted_at=_parse_datetime(last_attempted_at_raw),
                last_finished_at=_parse_datetime(last_finished_at_raw),
                last_success_at=_parse_datetime(last_success_at_raw),
                last_status=last_status,
                last_message=last_message,
                last_backup_target_name=last_backup_target_name,
                last_snapshot_id=last_snapshot_id,
            )
        case _:
            return None


def _parse_backup_run_history_row(row: tuple[SqlScalar, ...]) -> BackupRunHistoryEntry | None:
    if len(row) != 11:
        return None
    match row:
        case (
            int(entry_id),
            str(repo_name),
            str(repo_path),
            str(backup_target_name),
            str(action),
            str(reason),
            int(ok_int),
            str(message),
            snapshot_id_raw,
            str(started_at_text),
            str(finished_at_text),
        ):
            snapshot_id: str | None
            match snapshot_id_raw:
                case None:
                    snapshot_id = None
                case str(snapshot_text):
                    snapshot_id = snapshot_text
                case _:
                    snapshot_id = None

            return BackupRunHistoryEntry(
                entry_id=entry_id,
                repo_name=repo_name,
                repo_path=Path(repo_path),
                backup_target_name=backup_target_name,
                action=action,
                reason=reason,
                ok=ok_int != 0,
                message=message,
                snapshot_id=snapshot_id,
                started_at=datetime.fromisoformat(started_at_text),
                finished_at=datetime.fromisoformat(finished_at_text),
            )
        case _:
            return None


def _parse_dashboard_repo_cache_row(row: tuple[SqlScalar, ...]) -> DashboardRepoCacheEntry | None:
    if len(row) != 4:
        return None
    match row:
        case (
            str(repo_name),
            str(repo_path),
            str(updated_at_text),
            payload_raw,
        ):
            payload = _parse_json_object(payload_raw)
            if payload is None:
                return None
            return DashboardRepoCacheEntry(
                repo_name=repo_name,
                repo_path=Path(repo_path),
                updated_at=datetime.fromisoformat(updated_at_text),
                payload=payload,
            )
        case _:
            return None


def _parse_dashboard_action_history_row(row: tuple[SqlScalar, ...]) -> DashboardActionHistoryEntry | None:
    if len(row) != 9:
        return None
    match row:
        case (
            int(entry_id),
            str(repo_name),
            str(repo_path),
            str(action_kind),
            str(action_source),
            str(status),
            str(message),
            started_at_raw,
            str(finished_at_text),
        ):
            return DashboardActionHistoryEntry(
                entry_id=entry_id,
                repo_name=repo_name,
                repo_path=Path(repo_path),
                action_kind=action_kind,
                action_source=action_source,
                status=status,
                message=message,
                started_at=_parse_datetime(started_at_raw),
                finished_at=datetime.fromisoformat(finished_at_text),
            )
        case _:
            return None


def note_backup_attempt(
    paths: ServicePaths,
    repo_name: str,
    repo_path: Path,
    *,
    attempted_at: datetime,
) -> None:
    connection = _connect(paths)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO backup_repo_state (
                    repo_name,
                    repo_path,
                    last_attempted_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(repo_name) DO UPDATE SET
                    repo_path = excluded.repo_path,
                    last_attempted_at = excluded.last_attempted_at
                """,
                (
                    repo_name,
                    str(repo_path.resolve()),
                    attempted_at.isoformat(),
                ),
            )
    finally:
        connection.close()


def record_backup_run(
    paths: ServicePaths,
    *,
    repo_name: str,
    repo_path: Path,
    backup_target_name: str,
    action: str,
    reason: str,
    ok: bool,
    message: str,
    snapshot_id: str | None,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    connection = _connect(paths)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO backup_run_history (
                    repo_name,
                    repo_path,
                    backup_target_name,
                    action,
                    reason,
                    ok,
                    message,
                    snapshot_id,
                    started_at,
                    finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo_name,
                    str(repo_path.resolve()),
                    backup_target_name,
                    action,
                    reason,
                    1 if ok else 0,
                    message,
                    snapshot_id,
                    started_at.isoformat(),
                    finished_at.isoformat(),
                ),
            )
    finally:
        connection.close()


def update_backup_repo_summary(
    paths: ServicePaths,
    *,
    repo_name: str,
    repo_path: Path,
    last_attempted_at: datetime,
    last_finished_at: datetime,
    last_success_at: datetime | None,
    last_status: str,
    last_message: str,
    last_backup_target_name: str | None,
    last_snapshot_id: str | None,
) -> None:
    connection = _connect(paths)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO backup_repo_state (
                    repo_name,
                    repo_path,
                    last_attempted_at,
                    last_finished_at,
                    last_success_at,
                    last_status,
                    last_message,
                    last_backup_target_name,
                    last_snapshot_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_name) DO UPDATE SET
                    repo_path = excluded.repo_path,
                    last_attempted_at = excluded.last_attempted_at,
                    last_finished_at = excluded.last_finished_at,
                    last_success_at = excluded.last_success_at,
                    last_status = excluded.last_status,
                    last_message = excluded.last_message,
                    last_backup_target_name = excluded.last_backup_target_name,
                    last_snapshot_id = excluded.last_snapshot_id
                """,
                (
                    repo_name,
                    str(repo_path.resolve()),
                    last_attempted_at.isoformat(),
                    last_finished_at.isoformat(),
                    _isoformat_or_none(last_success_at),
                    last_status,
                    last_message,
                    last_backup_target_name,
                    last_snapshot_id,
                ),
            )
    finally:
        connection.close()


def load_backup_repo_summary(paths: ServicePaths, repo_name: str) -> BackupRepoSummary | None:
    connection = _connect(paths)
    try:
        cursor = connection.execute(
            """
            SELECT
                repo_name,
                repo_path,
                last_attempted_at,
                last_finished_at,
                last_success_at,
                last_status,
                last_message,
                last_backup_target_name,
                last_snapshot_id
            FROM backup_repo_state
            WHERE repo_name = ?
            """,
            (repo_name,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        row_values: tuple[SqlScalar, ...] = tuple(row)
        return _parse_backup_repo_summary_row(row_values)
    finally:
        connection.close()


def load_backup_repo_summaries(paths: ServicePaths) -> tuple[BackupRepoSummary, ...]:
    connection = _connect(paths)
    try:
        cursor = connection.execute(
            """
            SELECT
                repo_name,
                repo_path,
                last_attempted_at,
                last_finished_at,
                last_success_at,
                last_status,
                last_message,
                last_backup_target_name,
                last_snapshot_id
            FROM backup_repo_state
            ORDER BY repo_name ASC
            """
        )
        summaries: list[BackupRepoSummary] = []
        for row in cursor.fetchall():
            row_values: tuple[SqlScalar, ...] = tuple(row)
            summary = _parse_backup_repo_summary_row(row_values)
            if summary is not None:
                summaries.append(summary)
        return tuple(summaries)
    finally:
        connection.close()


def load_recent_backup_runs(paths: ServicePaths, *, limit: int = 20) -> tuple[BackupRunHistoryEntry, ...]:
    effective_limit = max(1, limit)
    connection = _connect(paths)
    try:
        cursor = connection.execute(
            """
            SELECT
                id,
                repo_name,
                repo_path,
                backup_target_name,
                action,
                reason,
                ok,
                message,
                snapshot_id,
                started_at,
                finished_at
            FROM backup_run_history
            ORDER BY finished_at DESC, id DESC
            LIMIT ?
            """,
            (effective_limit,),
        )
        entries: list[BackupRunHistoryEntry] = []
        for row in cursor.fetchall():
            row_values: tuple[SqlScalar, ...] = tuple(row)
            entry = _parse_backup_run_history_row(row_values)
            if entry is not None:
                entries.append(entry)
        return tuple(entries)
    finally:
        connection.close()


def save_dashboard_repo_cache(
    paths: ServicePaths,
    *,
    repo_name: str,
    repo_path: Path,
    updated_at: datetime,
    payload: JSONObject,
) -> None:
    connection = _connect(paths)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO dashboard_repo_cache (
                    repo_name,
                    repo_path,
                    updated_at,
                    payload_json
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(repo_name) DO UPDATE SET
                    repo_path = excluded.repo_path,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (
                    repo_name,
                    str(repo_path.resolve()),
                    updated_at.isoformat(),
                    _json_text(payload),
                ),
            )
    finally:
        connection.close()


def load_dashboard_repo_caches(paths: ServicePaths) -> tuple[DashboardRepoCacheEntry, ...]:
    connection = _connect(paths)
    try:
        cursor = connection.execute(
            """
            SELECT
                repo_name,
                repo_path,
                updated_at,
                payload_json
            FROM dashboard_repo_cache
            ORDER BY repo_name ASC
            """
        )
        entries: list[DashboardRepoCacheEntry] = []
        for row in cursor.fetchall():
            row_values: tuple[SqlScalar, ...] = tuple(row)
            entry = _parse_dashboard_repo_cache_row(row_values)
            if entry is not None:
                entries.append(entry)
        return tuple(entries)
    finally:
        connection.close()


def load_dashboard_repo_cache(paths: ServicePaths, repo_name: str) -> DashboardRepoCacheEntry | None:
    connection = _connect(paths)
    try:
        cursor = connection.execute(
            """
            SELECT
                repo_name,
                repo_path,
                updated_at,
                payload_json
            FROM dashboard_repo_cache
            WHERE repo_name = ?
            """,
            (repo_name,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        row_values: tuple[SqlScalar, ...] = tuple(row)
        return _parse_dashboard_repo_cache_row(row_values)
    finally:
        connection.close()


def record_dashboard_action(
    paths: ServicePaths,
    *,
    repo_name: str,
    repo_path: Path,
    action_kind: str,
    action_source: str,
    status: str,
    message: str,
    started_at: datetime | None,
    finished_at: datetime,
) -> None:
    connection = _connect(paths)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO dashboard_action_history (
                    repo_name,
                    repo_path,
                    action_kind,
                    action_source,
                    status,
                    message,
                    started_at,
                    finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo_name,
                    str(repo_path.resolve()),
                    action_kind,
                    action_source,
                    status,
                    message,
                    _isoformat_or_none(started_at),
                    finished_at.isoformat(),
                ),
            )
    finally:
        connection.close()


def load_recent_dashboard_actions(
    paths: ServicePaths,
    *,
    repo_name: str | None = None,
    limit: int = 20,
) -> tuple[DashboardActionHistoryEntry, ...]:
    effective_limit = max(1, limit)
    connection = _connect(paths)
    try:
        rows: list[tuple[SqlScalar, ...]]
        if repo_name is None:
            cursor = connection.execute(
                """
                SELECT
                    id,
                    repo_name,
                    repo_path,
                    action_kind,
                    action_source,
                    status,
                    message,
                    started_at,
                    finished_at
                FROM dashboard_action_history
                ORDER BY finished_at DESC, id DESC
                LIMIT ?
                """,
                (effective_limit,),
            )
            rows = [tuple(row) for row in cursor.fetchall()]
        else:
            cursor = connection.execute(
                """
                SELECT
                    id,
                    repo_name,
                    repo_path,
                    action_kind,
                    action_source,
                    status,
                    message,
                    started_at,
                    finished_at
                FROM dashboard_action_history
                WHERE repo_name = ?
                ORDER BY finished_at DESC, id DESC
                LIMIT ?
                """,
                (repo_name, effective_limit),
            )
            rows = [tuple(row) for row in cursor.fetchall()]

        entries: list[DashboardActionHistoryEntry] = []
        for row_values in rows:
            entry = _parse_dashboard_action_history_row(row_values)
            if entry is not None:
                entries.append(entry)
        return tuple(entries)
    finally:
        connection.close()


__all__ = [
    "BackupRepoSummary",
    "BackupRunHistoryEntry",
    "DashboardActionHistoryEntry",
    "DashboardRepoCacheEntry",
    "load_backup_repo_summaries",
    "load_backup_repo_summary",
    "load_dashboard_repo_cache",
    "load_dashboard_repo_caches",
    "load_recent_dashboard_actions",
    "load_recent_backup_runs",
    "note_backup_attempt",
    "record_dashboard_action",
    "record_backup_run",
    "save_dashboard_repo_cache",
    "update_backup_repo_summary",
]
