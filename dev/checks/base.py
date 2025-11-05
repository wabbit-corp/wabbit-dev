import abc
from typing import Any, Dict, List, Optional, Mapping, Union, Callable, ClassVar
from dataclasses import dataclass, field
from pathlib import Path
import enum
import uuid

from dev.base import Module
from dev.intrangeset import IntRangeSet

# Assuming get_expected_file_properties exists and helps identify text files
# If not, we might need a simpler text file check.
from dev.file_properties import get_expected_file_properties, ExpectedFileProperties


@dataclass(frozen=True)
class FileLocation:
    path: Path
    lines: Optional[IntRangeSet] = None

    def __add__(self, other: "FileLocation") -> "FileLocation":
        """
        Combines two FileLocations.
        """
        if self.path != other.path:
            raise ValueError("Cannot combine different file locations.")

        combined_lines = (self.lines or []) + (other.lines or [])
        return FileLocation(self.path, combined_lines)


class Severity(enum.Enum):
    """
    Severity levels for checks.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


_KNOWN_TYPES = set()


@dataclass(frozen=True)
class IssueType:
    """
    Represents a type of issue.
    """

    id: str
    message: str
    severity: Severity = Severity.ERROR

    def __post_init__(self):
        # Verify that the ID is a valid IssueType Id
        if not isinstance(self.id, str):
            raise ValueError(f"Invalid ID: {self.id}")
        if not self.id.startswith("E_"):
            raise ValueError(f"IssueType ID must start with 'E_': {self.id}")
        # Error ids must be [A-Z0-9_]
        for c in self.id:
            if not (c.isupper() or c.isdigit() or c == "_"):
                raise ValueError(
                    f"IssueType ID must contain only uppercase letters, digits, or underscores: {self.id}"
                )
        # Register the issue type
        if self.id in _KNOWN_TYPES:
            raise ValueError(f"Duplicate IssueType ID: {self.id}")
        _KNOWN_TYPES.add(self.id)

    def make(self, **kwargs) -> "Issue":
        """
        Creates an Issue of this type.
        """
        return Issue(self, data=kwargs)

    def at(self, path: Path, line: int | None = None) -> "Issue":
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
    data: Mapping[str, Any] | None = None
    location: FileLocation | None = None
    fix: Callable[[], None] | None = None

    def fixable(self, fix: Callable[[], None]) -> "Issue":
        """
        Marks the issue as fixable.
        """
        self.fix = fix
        return self

    def at(self, path: Path, line: int | None = None) -> "Issue":
        """
        Returns an Issue with the specified path.
        """

        if self.location is None:
            self.location = FileLocation(path, IntRangeSet([line]) if line else None)
        else:
            if self.location.path != path:
                raise ValueError("Cannot change the path of an existing issue.")
            if line is not None:
                self.location.lines = (
                    self.location.lines or IntRangeSet([])
                ) + IntRangeSet([line])
        return self


@dataclass
class IssueList:
    """
    Represents a list of issues found during a check.
    """

    issues: List[Issue] = field(default_factory=list)

    def append(self, issue: Issue) -> None:
        """
        Adds an issue to the list.
        """
        if self.issues:
            if self.issues[-1] == issue:
                return
            if (
                self.issues[-1].issue_type == issue.issue_type
                and self.issues[-1].data == issue.data
            ):
                if self.issues[-1].location and issue.location:
                    if self.issues[-1].location.path != issue.location.path:
                        return

                    self.issues[-1].location = self.issues[-1].location + issue.location
        self.issues.append(issue)

    def __iter__(self):
        """
        Returns an iterator over the issues.
        """
        return iter(self.issues)

    def extend(self, issues: List[Issue] | "IssueList") -> None:
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


E_GENERIC_READ_ERROR = IssueType(
    "E_GENERIC_READ_ERROR", "Could not read the file: {error} in {check_name}."
)


@dataclass(frozen=True)
class FileContext:
    check_name: str
    path: Path
    issues: IssueList = field(default_factory=IssueList)
    project_type: CoarseProjectType | None = None
    file_scope: CoarseFileScope | None = None

    def add_issue(
        self,
        tpe: IssueType,
        line: int | None = None,
        fix: Callable[[], None] | None = None,
        **kwargs,
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

    def read_text(self: "FileContext", issue_type: IssueType | None = None) -> str:
        try:
            return self.path.read_text(encoding="utf-8")
        except (IOError, OSError) as e:
            self.issues.append(
                E_GENERIC_READ_ERROR.make(
                    error=f"I/O error: {e}", check_name=self.check_name
                ).at(self.path)
            )
            raise CheckFailedWithReportedIssues()
        except UnicodeDecodeError as e:
            self.issues.append(
                E_GENERIC_READ_ERROR.make(
                    error=f"UTF-8 decode error: {e}", check_name=self.check_name
                ).at(self.path)
            )
            raise CheckFailedWithReportedIssues()
        except Exception as e:
            self.issues.append(
                E_GENERIC_READ_ERROR.make(
                    error=f"Unexpected error: {e}", check_name=self.check_name
                ).at(self.path)
            )
            raise CheckFailedWithReportedIssues()


class FileCheck(Check):
    @abc.abstractmethod
    def check(self, ctx: FileContext):
        raise NotImplementedError()


class RepoCheck(Check):
    @abc.abstractmethod
    def check(self, path: Path, project: Any) -> List[Issue]:
        raise NotImplementedError()


class ProjectCheck(Check):
    @abc.abstractmethod
    def check(self, path: Path, project: Any) -> List[Issue]:
        raise NotImplementedError()


class DirectoryCheck(Check):
    @abc.abstractmethod
    def check(self, ctx: FileContext):
        raise NotImplementedError()
