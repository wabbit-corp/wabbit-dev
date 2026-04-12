from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from dev.service_support import (
    DashboardPid,
    cleanup_stale_dashboard_pid,
    ensure_service_dir,
    load_dashboard_pid,
    process_is_alive,
    remove_dashboard_pid,
    service_paths_for_workspace,
    terminate_process,
)

_DASHBOARD_START_TIMEOUT_SECONDS = 8.0
_DASHBOARD_START_POLL_SECONDS = 0.1


@dataclass(frozen=True)
class DashboardOpenResult:
    ok: bool
    message: str
    url: str | None = None
    pid: int | None = None
    started: bool = False


def dashboard_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def _dashboard_process_command(workspace_root: Path, *, interval_seconds: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "dev.dashboard_server",
        "--workspace-root",
        str(workspace_root),
        "--interval-seconds",
        str(interval_seconds),
    ]


def _service_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _wait_for_dashboard_pid(
    workspace_root: Path,
    *,
    expected_pid: int,
    timeout_seconds: float,
) -> DashboardPid | None:
    paths = service_paths_for_workspace(workspace_root)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pid_info = load_dashboard_pid(paths)
        if (
            pid_info is not None
            and pid_info.pid == expected_pid
            and pid_info.port > 0
            and process_is_alive(expected_pid)
        ):
            return pid_info
        if not process_is_alive(expected_pid):
            return None
        time.sleep(_DASHBOARD_START_POLL_SECONDS)
    return None


def _open_browser(url: str) -> str:
    opened = webbrowser.open_new_tab(url)
    if opened:
        return f"Opened dashboard at {url}"
    return f"Dashboard is running at {url}"


def ensure_dashboard_server(
    workspace_root: Path,
    *,
    interval_seconds: int = 60,
    open_browser: bool = True,
) -> DashboardOpenResult:
    resolved_root = workspace_root.resolve()
    paths = service_paths_for_workspace(resolved_root)
    cleanup_stale_dashboard_pid(paths)

    existing = load_dashboard_pid(paths)
    if existing is not None and process_is_alive(existing.pid):
        url = dashboard_url(existing.port)
        message = _open_browser(url) if open_browser else f"Dashboard already running at {url}"
        return DashboardOpenResult(
            ok=True,
            message=message,
            url=url,
            pid=existing.pid,
            started=False,
        )

    ensure_service_dir(paths)
    with open(paths.dashboard_stdout_log, "a", encoding="utf-8") as stdout_log:
        with open(paths.dashboard_stderr_log, "a", encoding="utf-8") as stderr_log:
            process = subprocess.Popen(
                _dashboard_process_command(resolved_root, interval_seconds=interval_seconds),
                cwd=_service_project_root(),
                stdout=stdout_log,
                stderr=stderr_log,
                start_new_session=True,
            )

    pid_info = _wait_for_dashboard_pid(
        resolved_root,
        expected_pid=process.pid,
        timeout_seconds=_DASHBOARD_START_TIMEOUT_SECONDS,
    )
    if pid_info is None:
        remove_dashboard_pid(paths)
        return DashboardOpenResult(
            ok=False,
            message=(
                "Dashboard process exited before it reported a port. "
                f"See logs at {paths.dashboard_stdout_log} and {paths.dashboard_stderr_log}."
            ),
            pid=process.pid,
            started=False,
        )

    url = dashboard_url(pid_info.port)
    message = _open_browser(url) if open_browser else f"Dashboard started at {url}"
    return DashboardOpenResult(
        ok=True,
        message=message,
        url=url,
        pid=pid_info.pid,
        started=True,
    )


def stop_dashboard_server(workspace_root: Path) -> DashboardOpenResult:
    resolved_root = workspace_root.resolve()
    paths = service_paths_for_workspace(resolved_root)
    cleanup_stale_dashboard_pid(paths)
    pid_info = load_dashboard_pid(paths)
    if pid_info is None:
        return DashboardOpenResult(ok=False, message=f"No running dashboard found for {resolved_root}.")

    try:
        terminate_process(pid_info.pid)
    except OSError as ex:
        remove_dashboard_pid(paths)
        return DashboardOpenResult(ok=False, message=f"Dashboard pid {pid_info.pid} was not running cleanly: {ex}")

    remove_dashboard_pid(paths)
    return DashboardOpenResult(
        ok=True,
        message=f"Stopped dashboard for {resolved_root} (pid {pid_info.pid}).",
        pid=pid_info.pid,
        url=dashboard_url(pid_info.port),
    )


__all__ = [
    "DashboardOpenResult",
    "dashboard_url",
    "ensure_dashboard_server",
    "stop_dashboard_server",
]
