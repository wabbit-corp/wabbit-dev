# pyright: reportImportCycles=false

from __future__ import annotations

import abc
import enum
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from dev.base import Module

# Assuming get_expected_file_properties exists and helps identify text files
# If not, we might need a simpler text file check.
from dev.file_properties import ExpectedFileProperties, get_expected_file_properties
from dev.intrangeset import IntRangeSet

if TYPE_CHECKING:
    from dev.config import Project


@dataclass(frozen=True)
class FileLocation:
    path: Path
    lines: IntRangeSet | None = None

    def __add__(self, other: FileLocation) -> FileLocation:
        """
        Combines two FileLocations.
        """
        if self.path != other.path:
            raise ValueError("Cannot combine different file locations.")

        if self.lines is None and other.lines is None:
            return FileLocation(self.path, None)

        left_lines = self.lines if self.lines is not None else IntRangeSet.empty
        right_lines = other.lines if other.lines is not None else IntRangeSet.empty
        combined_lines = left_lines + right_lines
        return FileLocation(self.path, combined_lines)


class Severity(enum.Enum):
    """
    Severity levels for checks.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


_KNOWN_TYPES: set[str] = set()


def known_issue_types() -> frozenset[str]:
    return frozenset(_KNOWN_TYPES)


@dataclass(frozen=True)
class IssueType:
    """
    Represents a type of issue.
    """

    id: str
    message: str
    severity: Severity = Severity.ERROR

    def __post_init__(self) -> None:
        # Verify that the ID is a valid IssueType Id
        if not self.id.startswith("E_"):
            raise ValueError(f"IssueType ID must start with 'E_': {self.id}")
        # Error ids must be [A-Z0-9_]
        for c in self.id:
            if not (c.isupper() or c.isdigit() or c == "_"):
                raise ValueError(f"IssueType ID must contain only uppercase letters, digits, or underscores: {self.id}")
        # Register the issue type
        if self.id in _KNOWN_TYPES:
            raise ValueError(f"Duplicate IssueType ID: {self.id}")
        _KNOWN_TYPES.add(self.id)

    def make(self, **kwargs: object) -> Issue:
        """
        Creates an Issue of this type.
        """
        return Issue(self, data=kwargs)

    def at(self, path: Path, line: int | None = None) -> Issue:
        """
        Returns an Issue with the specified path.
        """
        return Issue(self).at(path, line=line)


@dataclass
class Issue:
    """
    Represents an issue found during a check.
    """

    issue_type: IssueType
    data: Mapping[str, object] | None = None
    location: FileLocation | None = None
    fix: Callable[[], None] | None = None

    def fixable(self, fix: Callable[[], None]) -> Issue:
        """
        Marks the issue as fixable.
        """
        self.fix = fix
        return self

    def at(self, path: Path, line: int | None = None) -> Issue:
        """
        Returns an Issue with the specified path.
        """

        if self.location is None:
            self.location = FileLocation(path, IntRangeSet([line]) if line is not None else None)
            return self

        if self.location.path != path:
            raise ValueError("Cannot change the path of an existing issue.")
        if line is not None:
            existing_lines = self.location.lines if self.location.lines is not None else IntRangeSet.empty
            self.location = FileLocation(path, existing_lines + IntRangeSet([line]))
        return self


@dataclass
class IssueList:
    """
    Represents a list of issues found during a check.
    """

    issues: list[Issue] = field(default_factory=list)

    def append(self, issue: Issue) -> None:
        """
        Adds an issue to the list.
        """
        if self.issues:
            if self.issues[-1] == issue:
                return
            if self.issues[-1].issue_type == issue.issue_type and self.issues[-1].data == issue.data:
                if self.issues[-1].location and issue.location:
                    if self.issues[-1].location.path != issue.location.path:
                        return

                    self.issues[-1].location = self.issues[-1].location + issue.location
        self.issues.append(issue)

    def __iter__(self) -> Iterator[Issue]:
        """
        Returns an iterator over the issues.
        """
        return iter(self.issues)

    def extend(self, issues: list[Issue] | IssueList) -> None:
        """
        Adds multiple issues to the list.
        """
        if isinstance(issues, IssueList):
            for issue in issues.issues:
                self.append(issue)
        else:
            self.issues.extend(issues)


class CheckFailedWithReportedIssues(Exception):
    """
    Exception raised when a check fails with reported issues.
    """

    def __init__(self) -> None:
        super().__init__("Check failed with reported issues.")


class CoarseProjectType(enum.Enum):
    """
    Enum for different project types.
    """

    APPLICATION = "application"  # e.g., web app, CLI tool
    LIBRARY = "library"  # e.g., Python package, Java library
    AGENT = "agent"  # e.g., jvm agent -- something that attaches to an application
    DATA = "data"  # e.g., data files, datasets


class CoarseFileScope(enum.Enum):
    """
    Enum for different file scopes.
    """

    MAIN = "main"  # e.g., main source directory
    TEST = "test"  # e.g., test files, test directory
    BUILD_CONFIG = "config"  # e.g., configuration files
    BUILD_TEMP = "build"  # e.g., temporary build files (NOT config files)


class Check(Module, abc.ABC):
    pass


E_GENERIC_READ_ERROR = IssueType("E_GENERIC_READ_ERROR", "Could not read the file: {error} in {check_name}.")


INLINE_CHECK_IGNORE_RE = re.compile(
    r"(?:#|//|;|--|/\*|\*)\s*check:ignore\s+" r"(?P<issue_id>\*|E_[A-Z0-9_]+)" r"(?:\s+value=(?P<value>.*\S))?\s*$"
)


@dataclass(frozen=True)
class InlineFindingIgnoreRule:
    issue_id: str
    line_number: int
    value: str | None = None


@dataclass(frozen=True)
class ScopedFindingIgnoreRule:
    issue_id: str
    value: str


@dataclass(frozen=True)
class ScopedReadSuppressions:
    config_ignores: tuple[ScopedFindingIgnoreRule, ...] = ()


def _issue_id_matches(rule_issue_id: str, issue_id: str) -> bool:
    return rule_issue_id == "*" or rule_issue_id == issue_id


def _mask_text_preserve_newlines(text: str) -> str:
    return "".join(ch if ch in ("\n", "\r") else " " for ch in text)


def _mask_value_occurrences(text: str, value: str) -> str:
    if value == "":
        return text

    chars = list(text)
    start = 0
    value_len = len(value)
    while True:
        idx = text.find(value, start)
        if idx == -1:
            break
        end = idx + value_len
        for i in range(idx, end):
            if chars[i] not in ("\n", "\r"):
                chars[i] = " "
        start = idx + 1
    return "".join(chars)


def parse_inline_finding_ignore_rules(text: str) -> list[InlineFindingIgnoreRule]:
    rules: list[InlineFindingIgnoreRule] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = INLINE_CHECK_IGNORE_RE.search(line)
        if match is None:
            continue
        value = match.group("value")
        if value is not None:
            value = value.strip()
            if value == "":
                value = None
        rules.append(
            InlineFindingIgnoreRule(
                issue_id=match.group("issue_id"),
                line_number=line_number,
                value=value,
            )
        )
    return rules


def apply_scoped_read_suppressions(
    text: str,
    issue_type: IssueType,
    suppressions: ScopedReadSuppressions | None = None,
) -> str:
    masked_text = text

    inline_rules = parse_inline_finding_ignore_rules(text)
    if inline_rules:
        lines = masked_text.splitlines(keepends=True)
        for rule in inline_rules:
            if not _issue_id_matches(rule.issue_id, issue_type.id):
                continue
            line_index = rule.line_number - 1
            if line_index < 0 or line_index >= len(lines):
                continue
            if rule.value is None:
                lines[line_index] = _mask_text_preserve_newlines(lines[line_index])
            elif rule.value in lines[line_index]:
                lines[line_index] = _mask_value_occurrences(lines[line_index], rule.value)
        masked_text = "".join(lines)

    if suppressions is not None:
        for config_rule in suppressions.config_ignores:
            if not _issue_id_matches(config_rule.issue_id, issue_type.id):
                continue
            if config_rule.value == "":
                continue
            masked_text = _mask_value_occurrences(masked_text, config_rule.value)

    return masked_text


@dataclass(frozen=True)
class FileContext:
    check_name: str
    path: Path
    issues: IssueList = field(default_factory=IssueList)
    project: Project | None = None
    project_type: CoarseProjectType | None = None
    file_scope: CoarseFileScope | None = None
    scoped_read_suppressions: ScopedReadSuppressions | None = None

    def add_issue(
        self,
        tpe: IssueType,
        line: int | None = None,
        fix: Callable[[], None] | None = None,
        **kwargs: object,
    ) -> None:
        issue = tpe.make(**kwargs).at(self.path, line=line)
        if fix:
            issue.fix = fix
        self.issues.append(issue)

    @property
    def is_file(self) -> bool:
        return self.path.is_file()

    @property
    def expected_properties(self) -> ExpectedFileProperties:
        props = get_expected_file_properties(self.path)
        if props is None:
            return ExpectedFileProperties()
        return props

    def read_text(self: FileContext, issue_type: IssueType | None = None) -> str:
        try:
            text = self.path.read_text(encoding="utf-8")
            if issue_type is None:
                return text
            return apply_scoped_read_suppressions(
                text,
                issue_type,
                suppressions=self.scoped_read_suppressions,
            )
        except OSError as e:
            self.issues.append(
                E_GENERIC_READ_ERROR.make(error=f"I/O error: {e}", check_name=self.check_name).at(self.path)
            )
            raise CheckFailedWithReportedIssues() from e
        except UnicodeDecodeError as e:
            self.issues.append(
                E_GENERIC_READ_ERROR.make(error=f"UTF-8 decode error: {e}", check_name=self.check_name).at(self.path)
            )
            raise CheckFailedWithReportedIssues() from e
        except Exception as e:
            self.issues.append(
                E_GENERIC_READ_ERROR.make(error=f"Unexpected error: {e}", check_name=self.check_name).at(self.path)
            )
            raise CheckFailedWithReportedIssues() from e


class FileCheck(Check):
    @abc.abstractmethod
    def check(self, ctx: FileContext) -> None:
        raise NotImplementedError()


class RepoCheck(Check):
    @abc.abstractmethod
    def check(self, path: Path, project: Project | None) -> list[Issue]:
        raise NotImplementedError()


class RootCheck(Check):
    @abc.abstractmethod
    def check(self, path: Path, project: Project | None) -> list[Issue]:
        raise NotImplementedError()


class ProjectCheck(Check):
    @abc.abstractmethod
    def check(self, path: Path, project: Project | None) -> list[Issue]:
        raise NotImplementedError()


class DirectoryCheck(Check):
    @abc.abstractmethod
    def check(self, ctx: FileContext) -> None:
        raise NotImplementedError()
