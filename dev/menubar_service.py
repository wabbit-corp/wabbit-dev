from __future__ import annotations

import argparse
import sys
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
from dev.repo_status import collect_repo_status_records
from dev.service_support import (
    MonitorSnapshot,
    build_monitor_snapshot,
    format_dirty_age,
    icon_for_snapshot,
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

        self.refresh_(None)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            float(interval_seconds),
            self,
            objc.selector(self.refresh_, signature=b"v@:@"),
            None,
            True,
        )
        return self

    def _snapshot(self) -> MonitorSnapshot:
        config = load_config(self.workspace_root)
        repo_statuses = collect_repo_status_records(config)
        snapshot = build_monitor_snapshot(self.workspace_root, repo_statuses)
        write_monitor_snapshot(self.paths, snapshot)
        return snapshot

    def _set_title(self, snapshot: MonitorSnapshot) -> None:
        button = self.status_item.button()
        if button is None:
            return
        button.setTitle_(icon_for_snapshot(snapshot))
        tooltip = (
            f"{snapshot.workspace_name}: {snapshot.dirty_repo_count}/{snapshot.total_repo_count} dirty, "
            f"checked {snapshot.checked_at.isoformat()}"
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
        self._add_disabled_item(f"Last check: {snapshot.checked_at.strftime('%H:%M:%S')}")
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
            objc.selector(self.refresh_, signature=b"v@:@"),
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

    def refresh_(self, _sender) -> None:
        try:
            snapshot = self._snapshot()
        except Exception as ex:
            button = self.status_item.button()
            if button is not None:
                button.setTitle_("🔴 !")
                button.setToolTip_(f"dev repo monitor failed: {ex}")
            self.menu.removeAllItems()
            self._add_disabled_item(f"Refresh failed: {ex}")
            self.menu.addItem_(NSMenuItem.separatorItem())
            quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Quit",
                objc.selector(self.quit_, signature=b"v@:@"),
                "",
            )
            quit_item.setTarget_(self)
            self.menu.addItem_(quit_item)
            print(f"dev menubar service refresh failed: {ex}", file=sys.stderr)
            return

        self._set_title(snapshot)
        self._rebuild_menu(snapshot)

    def quit_(self, _sender) -> None:
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
