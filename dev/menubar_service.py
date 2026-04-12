from __future__ import annotations

import argparse
import sys
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject, NSTimer

from dev.config import Config, load_config
from dev.dashboard_process import ensure_dashboard_server
from dev.repo_resolution import ResolvedRepoTarget, configured_repo_targets
from dev.repo_status import collect_repo_status_record, refresh_remote_tracking
from dev.service_actions import commit_repo_target, open_repo_in_difftool, push_repo_target
from dev.service_support import (
    MonitorRepoState,
    MonitorSnapshot,
    build_monitor_snapshot,
    format_dirty_age,
    format_local_timestamp,
    format_tracking_status,
    icon_for_snapshot,
    repo_check_spacing_seconds,
    service_paths_for_workspace,
    write_monitor_snapshot,
)

TRACKING_REFRESH_AFTER = timedelta(minutes=30)
MIN_TRACKING_FETCH_SPACING_SECONDS = 45.0


@dataclass(frozen=True)
class RepoMenuAction:
    kind: str
    repo_name: str
    repo_path: Path


class DirtyRepoMenuApp(NSObject):
    def initWithWorkspaceRoot_intervalSeconds_(self, workspace_root: str, interval_seconds: int):  # type: ignore[override]
        self = objc.super(DirtyRepoMenuApp, self).init()
        if self is None:
            return None

        self.workspace_root = Path(workspace_root).resolve()
        self.interval_seconds = interval_seconds
        self.paths = service_paths_for_workspace(self.workspace_root)
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.menu = NSMenu.alloc().init()
        self.status_item.setMenu_(self.menu)
        button = self.status_item.button()
        if button is not None:
            button.setTitle_("🟢")
            button.setToolTip_(f"dev repo monitor: {self.workspace_root.name}")

        self._snapshot_lock = threading.Lock()
        self._latest_snapshot: MonitorSnapshot | None = None
        self._last_error: str | None = None
        self._busy_repo_actions: dict[str, str] = {}
        self._last_action_message: str | None = None
        self._tracking_attempted_at_by_repo: dict[str, datetime] = {}
        self._tracking_refreshed_at_by_repo: dict[str, datetime] = {}
        self._last_tracking_fetch_attempt_at: datetime | None = None
        self._menu_actions: dict[int, RepoMenuAction] = {}
        self._next_menu_action_tag = 1
        self._stop_event = threading.Event()
        self._refresh_requested = threading.Event()
        self._worker = threading.Thread(target=self._run_monitor_loop, name="dev-menubar-monitor", daemon=True)
        self._worker.start()

        self._render_current_state()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0,
            self,
            objc.selector(self.tick_, signature=b"v@:@"),
            None,
            True,
        )
        return self

    def _run_monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._scan_workspace_once()
            except Exception as ex:
                with self._snapshot_lock:
                    self._last_error = str(ex)
                if self._wait_for_next_step(1.0):
                    continue

    def _scan_workspace_once(self) -> None:
        config = load_config(self.workspace_root)
        targets = configured_repo_targets(config)
        if not targets:
            snapshot = build_monitor_snapshot(self.workspace_root, [])
            write_monitor_snapshot(self.paths, snapshot)
            with self._snapshot_lock:
                self._latest_snapshot = snapshot
                self._last_error = None
            self._wait_for_next_step(float(self.interval_seconds))
            return

        spacing_seconds = repo_check_spacing_seconds(self.interval_seconds, len(targets))
        repo_statuses = []

        for index, target in enumerate(targets):
            if self._stop_event.is_set():
                return
            started_at = time.monotonic()
            tracking_refreshed_at = self._maybe_refresh_tracking(config, target)
            repo_status = collect_repo_status_record(target)
            if tracking_refreshed_at is not None:
                repo_status = replace(repo_status, tracking_refreshed_at=tracking_refreshed_at)
            repo_statuses.append(repo_status)
            if index == len(targets) - 1:
                continue
            elapsed = time.monotonic() - started_at
            wait_seconds = max(0.0, spacing_seconds - elapsed)
            if self._wait_for_next_step(wait_seconds):
                return

        snapshot = build_monitor_snapshot(self.workspace_root, repo_statuses)
        write_monitor_snapshot(self.paths, snapshot)
        with self._snapshot_lock:
            self._latest_snapshot = snapshot
            self._last_error = None

    def _wait_for_next_step(self, seconds: float) -> bool:
        if self._stop_event.is_set():
            return True
        if seconds <= 0:
            return self._stop_event.is_set()

        deadline = time.monotonic() + seconds
        while not self._stop_event.is_set():
            if self._refresh_requested.is_set():
                self._refresh_requested.clear()
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._refresh_requested.wait(timeout=min(remaining, 0.25))
        return True

    def _current_state(self) -> tuple[MonitorSnapshot | None, str | None]:
        with self._snapshot_lock:
            return self._latest_snapshot, self._last_error

    def _action_state(self) -> tuple[dict[str, str], str | None]:
        with self._snapshot_lock:
            return dict(self._busy_repo_actions), self._last_action_message

    def _maybe_refresh_tracking(self, config: Config, target: ResolvedRepoTarget) -> datetime | None:
        now = datetime.now(UTC)
        with self._snapshot_lock:
            last_attempt = self._tracking_attempted_at_by_repo.get(target.name)
            last_refreshed = self._tracking_refreshed_at_by_repo.get(target.name)
            last_global_attempt = self._last_tracking_fetch_attempt_at

        if last_attempt is not None and (now - last_attempt) < TRACKING_REFRESH_AFTER:
            return last_refreshed
        if (
            last_global_attempt is not None
            and (now - last_global_attempt).total_seconds() < MIN_TRACKING_FETCH_SPACING_SECONDS
        ):
            return last_refreshed

        attempted_at = datetime.now(UTC)
        with self._snapshot_lock:
            self._tracking_attempted_at_by_repo[target.name] = attempted_at
            self._last_tracking_fetch_attempt_at = attempted_at

        if not refresh_remote_tracking(target, config=config):
            return last_refreshed

        refreshed_at = datetime.now(UTC)
        with self._snapshot_lock:
            self._tracking_refreshed_at_by_repo[target.name] = refreshed_at
        return refreshed_at

    def _set_title(self, snapshot: MonitorSnapshot) -> None:
        button = self.status_item.button()
        if button is None:
            return
        button.setTitle_(icon_for_snapshot(snapshot))
        tooltip = (
            f"{snapshot.workspace_name}: {snapshot.dirty_repo_count}/{snapshot.total_repo_count} dirty, "
            f"checked {format_local_timestamp(snapshot.checked_at)}"
        )
        button.setToolTip_(tooltip)

    def _add_disabled_item(self, title: str) -> None:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
        item.setEnabled_(False)
        self.menu.addItem_(item)

    def _reset_menu_actions(self) -> None:
        self._menu_actions = {}
        self._next_menu_action_tag = 1

    def _register_menu_action(self, action: RepoMenuAction) -> int:
        tag = self._next_menu_action_tag
        self._next_menu_action_tag += 1
        self._menu_actions[tag] = action
        return tag

    def _create_repo_action_item(self, title: str, action: RepoMenuAction, *, enabled: bool) -> NSMenuItem:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title,
            objc.selector(self.repoAction_, signature=b"v@:@"),
            "",
        )
        item.setTarget_(self)
        item.setTag_(self._register_menu_action(action))
        item.setEnabled_(enabled)
        return item

    def _top_level_repo_title(self, repo: MonitorRepoState, busy_action: str | None) -> str:
        counts = f"{repo.staged_count}/{repo.unstaged_count}/{repo.untracked_count}"
        age_text = format_dirty_age(repo.dirty_since)
        title = f"{repo.name} [{counts}] age {age_text}"
        if repo.error is not None:
            return f"{repo.name} [error] {repo.error}"
        if repo.upstream_name is not None:
            ahead_count = repo.ahead_count if repo.ahead_count is not None else 0
            behind_count = repo.behind_count if repo.behind_count is not None else 0
            if ahead_count > 0 or behind_count > 0:
                title = f"{title} up {ahead_count}/down {behind_count}"
        if busy_action is not None:
            title = f"{title} [{busy_action}]"
        return title

    def _build_repo_submenu(self, repo: MonitorRepoState, busy_action: str | None) -> NSMenu:
        submenu = NSMenu.alloc().init()

        path_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(str(repo.path), None, "")
        path_item.setEnabled_(False)
        submenu.addItem_(path_item)

        dirty_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Dirty: staged {repo.staged_count}, unstaged {repo.unstaged_count}, untracked {repo.untracked_count}",
            None,
            "",
        )
        dirty_item.setEnabled_(False)
        submenu.addItem_(dirty_item)

        tracking_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Tracking: {format_tracking_status(repo)}",
            None,
            "",
        )
        tracking_item.setEnabled_(False)
        submenu.addItem_(tracking_item)

        refreshed_text = (
            format_local_timestamp(repo.tracking_refreshed_at)
            if repo.tracking_refreshed_at is not None
            else "not yet refreshed by service"
        )
        refreshed_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Upstream fetch: {refreshed_text}",
            None,
            "",
        )
        refreshed_item.setEnabled_(False)
        submenu.addItem_(refreshed_item)

        if busy_action is not None:
            busy_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"Working: {busy_action}", None, "")
            busy_item.setEnabled_(False)
            submenu.addItem_(busy_item)

        submenu.addItem_(NSMenuItem.separatorItem())

        actions_enabled = busy_action is None
        submenu.addItem_(
            self._create_repo_action_item(
                "Open in difftool",
                RepoMenuAction(kind="difftool", repo_name=repo.name, repo_path=repo.path),
                enabled=actions_enabled,
            )
        )
        submenu.addItem_(
            self._create_repo_action_item(
                "Commit local changes",
                RepoMenuAction(kind="commit", repo_name=repo.name, repo_path=repo.path),
                enabled=actions_enabled,
            )
        )

        push_title = "Push committed history"
        if repo.upstream_name is not None:
            ahead_count = repo.ahead_count if repo.ahead_count is not None else 0
            behind_count = repo.behind_count if repo.behind_count is not None else 0
            push_title = f"Push committed history ({ahead_count} ahead, {behind_count} behind)"
        submenu.addItem_(
            self._create_repo_action_item(
                push_title,
                RepoMenuAction(kind="push", repo_name=repo.name, repo_path=repo.path),
                enabled=actions_enabled,
            )
        )

        return submenu

    def _rebuild_menu(self, snapshot: MonitorSnapshot) -> None:
        self.menu.removeAllItems()
        self._reset_menu_actions()
        busy_repo_actions, last_action_message = self._action_state()
        self._add_disabled_item(
            f"{snapshot.workspace_name}: {snapshot.dirty_repo_count}/{snapshot.total_repo_count} dirty, "
            f"{snapshot.stale_repo_count} stale"
        )
        self._add_disabled_item(f"Last check: {format_local_timestamp(snapshot.checked_at)}")
        if last_action_message is not None:
            self._add_disabled_item(f"Last action: {last_action_message}")
        self.menu.addItem_(NSMenuItem.separatorItem())

        dirty_repos = [repo for repo in snapshot.repos if repo.is_dirty]
        if not dirty_repos:
            self._add_disabled_item("All repos clean")
        else:
            for repo in dirty_repos[:12]:
                busy_action = busy_repo_actions.get(repo.name)
                title = self._top_level_repo_title(repo, busy_action)
                if repo.error is not None:
                    self._add_disabled_item(title)
                    continue
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
                item.setSubmenu_(self._build_repo_submenu(repo, busy_action))
                self.menu.addItem_(item)
            if len(dirty_repos) > 12:
                self._add_disabled_item(f"... and {len(dirty_repos) - 12} more")

        self.menu.addItem_(NSMenuItem.separatorItem())

        dashboard_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Dashboard",
            objc.selector(self.openDashboard_, signature=b"v@:@"),
            "",
        )
        dashboard_item.setTarget_(self)
        self.menu.addItem_(dashboard_item)

        refresh_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Refresh now",
            objc.selector(self.refreshNow_, signature=b"v@:@"),
            "",
        )
        refresh_item.setTarget_(self)
        self.menu.addItem_(refresh_item)

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit",
            objc.selector(self.quit_, signature=b"v@:@"),
            "",
        )
        quit_item.setTarget_(self)
        self.menu.addItem_(quit_item)

    def _render_current_state(self) -> None:
        snapshot, last_error = self._current_state()
        if last_error is not None:
            button = self.status_item.button()
            if button is not None:
                button.setTitle_("🔴 !")
                button.setToolTip_(f"dev repo monitor failed: {last_error}")
            self.menu.removeAllItems()
            self._reset_menu_actions()
            self._add_disabled_item(f"Refresh failed: {last_error}")
            self.menu.addItem_(NSMenuItem.separatorItem())
            dashboard_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Open Dashboard",
                objc.selector(self.openDashboard_, signature=b"v@:@"),
                "",
            )
            dashboard_item.setTarget_(self)
            self.menu.addItem_(dashboard_item)
            self.menu.addItem_(NSMenuItem.separatorItem())
            quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Quit",
                objc.selector(self.quit_, signature=b"v@:@"),
                "",
            )
            quit_item.setTarget_(self)
            self.menu.addItem_(quit_item)
            return

        if snapshot is None:
            button = self.status_item.button()
            if button is not None:
                button.setTitle_("🟢")
                button.setToolTip_(f"dev repo monitor: {self.workspace_root.name} (checking...)")
            self.menu.removeAllItems()
            self._reset_menu_actions()
            self._add_disabled_item(f"{self.workspace_root.name}: checking...")
            self.menu.addItem_(NSMenuItem.separatorItem())
            dashboard_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Open Dashboard",
                objc.selector(self.openDashboard_, signature=b"v@:@"),
                "",
            )
            dashboard_item.setTarget_(self)
            self.menu.addItem_(dashboard_item)
            self.menu.addItem_(NSMenuItem.separatorItem())
            quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Quit",
                objc.selector(self.quit_, signature=b"v@:@"),
                "",
            )
            quit_item.setTarget_(self)
            self.menu.addItem_(quit_item)
            return

        self._set_title(snapshot)
        self._rebuild_menu(snapshot)

    def tick_(self, _sender) -> None:
        self._render_current_state()

    def refreshNow_(self, _sender) -> None:
        self._refresh_requested.set()
        self._render_current_state()

    def openDashboard_(self, _sender) -> None:
        with self._snapshot_lock:
            self._last_action_message = "dashboard: opening"
        worker = threading.Thread(
            target=self._run_open_dashboard,
            name="dev-menubar-dashboard",
            daemon=True,
        )
        worker.start()
        self._render_current_state()

    def repoAction_(self, sender) -> None:
        action = self._menu_actions.get(sender.tag())
        if action is None:
            return

        with self._snapshot_lock:
            if action.repo_name in self._busy_repo_actions:
                return
            self._busy_repo_actions[action.repo_name] = action.kind
            self._last_action_message = f"{action.repo_name}: {action.kind} started"

        worker = threading.Thread(
            target=self._run_repo_action,
            args=(action,),
            name=f"dev-menubar-{action.kind}-{action.repo_name}",
            daemon=True,
        )
        worker.start()
        self._render_current_state()

    def _run_repo_action(self, action: RepoMenuAction) -> None:
        try:
            match action.kind:
                case "difftool":
                    result = open_repo_in_difftool(self.workspace_root, action.repo_path)
                case "commit":
                    result = commit_repo_target(self.workspace_root, action.repo_name)
                case "push":
                    result = push_repo_target(self.workspace_root, action.repo_name)
                case _:
                    raise ValueError(f"Unknown repo action: {action.kind}")
        except Exception as ex:
            result_message = f"{action.repo_name}: {action.kind} failed ({ex})"
        else:
            result_message = result.message

        with self._snapshot_lock:
            self._busy_repo_actions.pop(action.repo_name, None)
            self._last_action_message = result_message

        self._refresh_requested.set()

    def _run_open_dashboard(self) -> None:
        try:
            result = ensure_dashboard_server(self.workspace_root, interval_seconds=self.interval_seconds, open_browser=True)
            result_message = result.message
        except Exception as ex:
            result_message = f"dashboard: failed ({ex})"

        with self._snapshot_lock:
            self._last_action_message = result_message

        self._refresh_requested.set()

    def quit_(self, _sender) -> None:
        self._stop_event.set()
        self._refresh_requested.set()
        app = NSApplication.sharedApplication()
        app.terminate_(None)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m dev.menubar_service")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--interval-seconds", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "darwin":
        print("dev menubar service supports macOS only.", file=sys.stderr)
        return 1

    args = _parse_args(sys.argv[1:] if argv is None else argv)
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = DirtyRepoMenuApp.alloc().initWithWorkspaceRoot_intervalSeconds_(
        args.workspace_root,
        args.interval_seconds,
    )
    if delegate is None:
        print("Failed to initialize menubar service.", file=sys.stderr)
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
