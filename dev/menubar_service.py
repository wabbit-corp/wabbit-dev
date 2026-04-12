from __future__ import annotations

import argparse
import sys
import threading
import time
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

from dev.config import load_config
from dev.repo_resolution import configured_repo_targets
from dev.repo_status import collect_repo_status_record
from dev.service_support import (
    MonitorSnapshot,
    build_monitor_snapshot,
    format_dirty_age,
    format_local_timestamp,
    icon_for_snapshot,
    repo_check_spacing_seconds,
    service_paths_for_workspace,
    write_monitor_snapshot,
)


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
            repo_statuses.append(collect_repo_status_record(target))
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

    def _rebuild_menu(self, snapshot: MonitorSnapshot) -> None:
        self.menu.removeAllItems()
        self._add_disabled_item(
            f"{snapshot.workspace_name}: {snapshot.dirty_repo_count}/{snapshot.total_repo_count} dirty, "
            f"{snapshot.stale_repo_count} stale"
        )
        self._add_disabled_item(f"Last check: {format_local_timestamp(snapshot.checked_at)}")
        self.menu.addItem_(NSMenuItem.separatorItem())

        dirty_repos = [repo for repo in snapshot.repos if repo.is_dirty]
        if not dirty_repos:
            self._add_disabled_item("All repos clean")
        else:
            for repo in dirty_repos[:12]:
                counts = f"{repo.staged_count}/{repo.unstaged_count}/{repo.untracked_count}"
                age_text = format_dirty_age(repo.dirty_since)
                title = f"{repo.name} [{counts}] age {age_text}"
                if repo.error is not None:
                    title = f"{repo.name} [error] {repo.error}"
                self._add_disabled_item(title)
            if len(dirty_repos) > 12:
                self._add_disabled_item(f"... and {len(dirty_repos) - 12} more")

        self.menu.addItem_(NSMenuItem.separatorItem())

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
            self._add_disabled_item(f"Refresh failed: {last_error}")
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
            self._add_disabled_item(f"{self.workspace_root.name}: checking...")
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
