"""
* [ ] Remove Dead or Debug Code: Regularly purge any commented-out code, leftover debug print statements,
      or temporary test fragments before merging. These clutter the repository and can confuse new contributors.
* [x] Check for Very Old TODO/FIXME Comments: Identify TODO, FIXME, or similar marker
      comments that haven't been modified in a very long time (e.g., several years),
      as they might indicate forgotten tasks, dead code references, or obsolete information.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from mu.typed import tag

from dev.base import ScriptCommandContext, TypedConfigCommandRegistration
from dev.checks.base import FileCheck, FileContext, IssueType

E_DEBUG_CODE = IssueType("E_DEBUG_CODE", "Possible leftover debug statement.")
E_STALE_TODO = IssueType("E_STALE_TODO", "Stale TODO/FIXME comment.")


@tag("checks/stale-todo/age-days")
@dataclass(frozen=True)
class StaleTodoAgeDaysCommand:
    age_days: int


class StaleCodeCheck(FileCheck):
    """Scan files for debug prints or stale TODO comments."""

    def __init__(self, todo_age_days: int = 365) -> None:
        self.todo_age_days = todo_age_days
        self.todo_re = re.compile(r"(TODO|FIXME)", re.IGNORECASE)
        # self.debug_re = re.compile(
        #     r"(//\s*console\.log|#\s*print\(|//\s*System\.out\.println)", re.IGNORECASE
        # )

    def register_script_commands(self, ctx: ScriptCommandContext) -> None:
        def stale_code_todo_age_days(val: int) -> int:
            self.todo_age_days = val
            return self.todo_age_days

        ctx.register(name="checks/stale-todo/age-days", func=stale_code_todo_age_days)

    def register_typed_config_commands(self) -> list[TypedConfigCommandRegistration]:
        def apply(command: object) -> None:
            assert isinstance(command, StaleTodoAgeDaysCommand), f"Unexpected command type: {type(command)}"
            self.todo_age_days = command.age_days

        return [
            TypedConfigCommandRegistration(
                command_type=StaleTodoAgeDaysCommand,
                apply=apply,
            )
        ]

    def _find_repo_root(self, path: Path) -> Path | None:
        current = path.resolve().parent if path.is_file() else path.resolve()
        for candidate in (current, *current.parents):
            if (candidate / ".git").exists():
                return candidate
        return None

    def _line_age_days_by_git_blame(
        self,
        path: Path,
        *,
        now_timestamp: float | None = None,
    ) -> dict[int, float] | None:
        repo_root = self._find_repo_root(path)
        if repo_root is None:
            return None

        resolved_repo_root = repo_root.resolve()
        resolved_path = path.resolve()
        try:
            relative_path = resolved_path.relative_to(resolved_repo_root)
        except ValueError:
            return None

        try:
            result = subprocess.run(
                ["git", "blame", "--line-porcelain", "--", relative_path.as_posix()],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None

        if result.returncode != 0:
            return None

        effective_now = time.time() if now_timestamp is None else now_timestamp
        ages_by_line: dict[int, float] = {}
        current_line_number: int | None = None
        current_author_time: int | None = None

        for raw_line in result.stdout.splitlines():
            if raw_line.startswith("\t"):
                if current_line_number is not None and current_author_time is not None:
                    ages_by_line[current_line_number] = (effective_now - current_author_time) / 86400.0
                current_line_number = None
                current_author_time = None
                continue

            if raw_line.startswith("author-time "):
                value = raw_line.removeprefix("author-time ").strip()
                try:
                    current_author_time = int(value)
                except ValueError:
                    current_author_time = None
                continue

            header_match = re.match(r"^[0-9a-f^]{4,}\s+\d+\s+(\d+)(?:\s+\d+)?$", raw_line)
            if header_match is not None:
                current_line_number = int(header_match.group(1))
                current_author_time = None

        return ages_by_line

    def check(self, ctx: FileContext) -> None:
        if not ctx.path.is_file():
            return
        if not ctx.expected_properties.is_text:
            return

        line_ages_by_blame = self._line_age_days_by_git_blame(ctx.path)
        try:
            mtime = ctx.path.stat().st_mtime
        except OSError:
            mtime = None

        text = ctx.read_text(E_STALE_TODO)

        for ln, line in enumerate(text.splitlines(), 1):
            if self.todo_re.search(line):
                age_days = line_ages_by_blame.get(ln) if line_ages_by_blame is not None else None
                if age_days is None and mtime is not None:
                    age_days = (time.time() - mtime) / 86400.0

                if age_days is None:
                    ctx.add_issue(E_STALE_TODO, line=ln)
                elif age_days >= self.todo_age_days:
                    ctx.add_issue(E_STALE_TODO, line=ln)


__all__ = [
    "StaleTodoAgeDaysCommand",
    "E_DEBUG_CODE",
    "E_STALE_TODO",
    "StaleCodeCheck",
]
