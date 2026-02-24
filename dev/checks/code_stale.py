"""
* [ ] Remove Dead or Debug Code: Regularly purge any commented-out code, leftover debug print statements,
      or temporary test fragments before merging. These clutter the repository and can confuse new contributors.
* [x] Check for Very Old TODO/FIXME Comments: Identify TODO, FIXME, or similar marker
      comments that haven't been modified in a very long time (e.g., several years),
      as they might indicate forgotten tasks, dead code references, or obsolete information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

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

    def check(self, ctx: FileContext) -> None:
        if not ctx.path.is_file():
            return
        if not ctx.expected_properties.is_text:
            return

        try:
            mtime = ctx.path.stat().st_mtime
        except OSError:
            mtime = None

        text = ctx.read_text(E_STALE_TODO)

        for ln, line in enumerate(text.splitlines(), 1):
            if self.todo_re.search(line):
                if mtime is not None:
                    age_days = (datetime.now().timestamp() - mtime) / 86400.0
                    if age_days >= self.todo_age_days:
                        ctx.add_issue(E_STALE_TODO, line=ln)
                else:
                    ctx.add_issue(E_STALE_TODO, line=ln)


__all__ = [
    "StaleTodoAgeDaysCommand",
    "E_DEBUG_CODE",
    "E_STALE_TODO",
    "StaleCodeCheck",
]
