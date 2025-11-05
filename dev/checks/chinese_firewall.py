"""
* [x] Check for censored keywords in text files.
"""

import re
from typing import List, Set, Optional, Tuple, Pattern

from mu.exec import ExecutionContext

# Import necessary components from your base framework
# (Adjust the import path if necessary)
from dev.checks.base import (
    FileCheck,
    IssueType,
    FileContext,
)

E_CENSORED_KEYWORD = IssueType(
    "E_CENSORED_KEYWORD",
    "Found censored keyword '{keyword}'.",
)


class CensoredKeywords(FileCheck):
    error_on: set[str]
    error_on_regex: re.Pattern[str]

    def __init__(self, error_on: Optional[Set[str]] = None):
        if error_on is None:
            error_on = set()
        self.error_on = error_on

        self._update_error_on_regex()

    def _update_error_on_regex(self) -> None:
        if not self.error_on:
            pattern = r"a^"  # Matches nothing
        else:
            pattern = (
                r"\b("
                + "|".join(re.escape(keyword) for keyword in self.error_on)
                + r")\b"
            )
        self.error_on_regex = re.compile(pattern, re.IGNORECASE)

    def register_script_commands(self, ctx: ExecutionContext) -> None:
        def censored_words_error_on(val: set[str]) -> set[str]:
            self.error_on = val
            self._update_error_on_regex()
            return self.error_on

        ctx.register(
            name="checks/censored-words/error-on", func=censored_words_error_on
        )

    def check(self, ctx: FileContext):
        if not ctx.path.is_file():
            return None
        if not ctx.expected_properties.is_text:
            return None

        for line_number, line in enumerate(
            ctx.read_text(E_CENSORED_KEYWORD).splitlines()
        ):
            for match in self.error_on_regex.finditer(line):
                keyword_found = match.group(0)
                ctx.add_issue(
                    E_CENSORED_KEYWORD, line=line_number, keyword=keyword_found
                )
