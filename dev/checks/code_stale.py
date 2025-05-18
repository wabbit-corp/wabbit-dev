"""
* [x] Remove Dead or Debug Code: Regularly purge any commented-out code, leftover debug print statements,
      or temporary test fragments before merging. These clutter the repository and can confuse new contributors.
      This rule can be partially automated by scanning for specific keywords (TODO, FIXME, console.log, etc.)
      and ensuring they are addressed or removed in production code. While not all TODO comments need removal,
      they should at least be tracked and not forgotten indefinitely.
* [x] Check for Very Old TODO/FIXME Comments: Identify TODO, FIXME, or similar marker
      comments that haven't been modified in a very long time (e.g., several years),
      as they might indicate forgotten tasks, dead code references, or obsolete information.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List

from dev.checks.base import FileCheck, IssueType, IssueList, FileContext


E_DEBUG_CODE = IssueType(
    "e077b2db-073b-465d-99a4-3c0e7ae44462",
    "Possible leftover debug statement: '{snippet}'.",
)

E_STALE_TODO = IssueType(
    "332cbb53-ffec-4d80-b2a1-b5a23abbce7a",
    "Stale TODO/FIXME comment: '{snippet}'.",
)


class StaleCodeCheck(FileCheck):
    """Scan files for debug prints or stale TODO comments."""

    def __init__(self, todo_age_days: int = 365) -> None:
        self.todo_age_days = todo_age_days
        self.todo_re = re.compile(r"(TODO|FIXME)", re.IGNORECASE)
        self.debug_re = re.compile(
            r"(console\.log|print\(|System\.out\.println)", re.IGNORECASE
        )

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List:
        if not path.is_file():
            return []

        issues = IssueList()

        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None

        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for ln, line in enumerate(f, 1):
                    if self.debug_re.search(line):
                        issues.append(
                            E_DEBUG_CODE.make(snippet=line.strip()[:40]).at(
                                path, line=ln
                            )
                        )
                    if self.todo_re.search(line):
                        if mtime is not None:
                            age_days = (datetime.now().timestamp() - mtime) / 86400.0
                            if age_days >= self.todo_age_days:
                                issues.append(
                                    E_STALE_TODO.make(snippet=line.strip()[:40]).at(
                                        path, line=ln
                                    )
                                )
                        else:
                            issues.append(
                                E_STALE_TODO.make(snippet=line.strip()[:40]).at(
                                    path, line=ln
                                )
                            )
        except OSError:
            pass

        return issues.issues
