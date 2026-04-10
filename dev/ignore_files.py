from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pathspec

type ExtraIgnorePredicate = Callable[[Path, bool], bool]

_CHECKIGNORE_ISSUE_RE = re.compile(
    r"^check:ignore\s+" r"(?P<issue_id>\*|E_[A-Z0-9_]+)\s+" r"(?P<pathspec>\S+)" r"(?:\s+(?P<matcher>.*\S))?\s*$"
)


@dataclass(frozen=True)
class CheckIgnoreIssueMatcher:
    value: str | None = None
    field_name: str | None = None
    field_value: str | None = None
    field_regex: str | None = None


@dataclass(frozen=True)
class CheckIgnoreIssueDirective:
    issue_id: str
    pathspec: str
    matcher: CheckIgnoreIssueMatcher | None = None


def is_checkignore_issue_directive(line: str) -> bool:
    return _CHECKIGNORE_ISSUE_RE.fullmatch(line.strip()) is not None


def parse_checkignore_issue_directive(line: str) -> CheckIgnoreIssueDirective | None:
    match = _CHECKIGNORE_ISSUE_RE.fullmatch(line.strip())
    if match is None:
        return None
    matcher_text = match.group("matcher")
    matcher: CheckIgnoreIssueMatcher | None = None
    if matcher_text is not None:
        matcher_text = matcher_text.strip()
        if matcher_text != "":
            if matcher_text.startswith("value="):
                value = matcher_text.removeprefix("value=").strip()
                matcher = CheckIgnoreIssueMatcher(value=value or None)
            elif "~" in matcher_text:
                field_name, field_regex = matcher_text.split("~", 1)
                field_name = field_name.strip()
                field_regex = field_regex.strip()
                if field_name == "" or field_regex == "":
                    return None
                matcher = CheckIgnoreIssueMatcher(
                    field_name=field_name,
                    field_regex=field_regex,
                )
            elif "=" in matcher_text:
                field_name, field_value = matcher_text.split("=", 1)
                field_name = field_name.strip()
                field_value = field_value.strip()
                if field_name == "" or field_value == "":
                    return None
                matcher = CheckIgnoreIssueMatcher(
                    field_name=field_name,
                    field_value=field_value,
                )
            else:
                return None
    return CheckIgnoreIssueDirective(
        issue_id=match.group("issue_id"),
        pathspec=match.group("pathspec"),
        matcher=matcher,
    )


def read_ignore_patterns(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.strip().startswith("#") and not is_checkignore_issue_directive(line)
    ]


def read_checkignore_issue_directives(path: Path) -> list[CheckIgnoreIssueDirective]:
    if not path.is_file():
        return []

    directives: list[CheckIgnoreIssueDirective] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        directive = parse_checkignore_issue_directive(raw_line)
        if directive is not None:
            directives.append(directive)
    return directives


class IgnoreMatcher:
    def __init__(
        self,
        root: Path,
        *,
        extra_predicates: Sequence[ExtraIgnorePredicate] = (),
    ) -> None:
        self.root = root.resolve()
        self._extra_predicates = tuple(extra_predicates)
        self._specs_by_dir: dict[Path, pathspec.PathSpec | None] = {}

    def _spec_for_dir(self, directory: Path) -> pathspec.PathSpec | None:
        resolved_dir = directory.resolve()
        cached = self._specs_by_dir.get(resolved_dir)
        if cached is not None or resolved_dir in self._specs_by_dir:
            return cached

        patterns: list[str] = []
        if resolved_dir == self.root:
            patterns.append("/.git")
        patterns.extend(read_ignore_patterns(resolved_dir / ".gitignore"))
        patterns.extend(read_ignore_patterns(resolved_dir / ".checkignore"))

        if not patterns:
            self._specs_by_dir[resolved_dir] = None
            return None

        spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.gitwildmatch.GitWildMatchPattern,
            patterns,
        )
        self._specs_by_dir[resolved_dir] = spec
        return spec

    def matches(self, path: Path | str, *, is_dir: bool) -> bool:
        absolute_path = Path(path)
        if not absolute_path.is_absolute():
            absolute_path = absolute_path.absolute()
        absolute_path = absolute_path.resolve()
        try:
            absolute_path.relative_to(self.root)
        except ValueError:
            return False

        if absolute_path == self.root:
            return False

        for predicate in self._extra_predicates:
            if predicate(absolute_path, is_dir):
                return True

        ignored = False
        current_dir = absolute_path.parent

        while True:
            try:
                current_dir.relative_to(self.root)
            except ValueError:
                break
            spec = self._spec_for_dir(current_dir)
            if spec is not None:
                relative = absolute_path.relative_to(current_dir).as_posix()
                candidate = relative + "/" if is_dir and not relative.endswith("/") else relative
                result = spec.check_file(candidate)
                if result.index is not None:
                    ignored = bool(result.include)
            if current_dir == self.root:
                break
            current_dir = current_dir.parent

        return ignored

    def __call__(self, path: str, is_dir: bool) -> bool:
        return self.matches(path, is_dir=is_dir)
