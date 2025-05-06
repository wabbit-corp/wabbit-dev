import abc
from typing import Any, Dict, List, Optional, Mapping, Union, Callable, ClassVar
from dataclasses import dataclass, field
from pathlib import Path
import enum
import uuid

from dev.intrangeset import IntRangeSet


@dataclass(frozen=True)
class FileLocation:
    path: Path
    lines: Optional[IntRangeSet] = None

    def __add__(self, other: 'FileLocation') -> 'FileLocation':
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


@dataclass(frozen=True)
class IssueType:
    """
    Represents a type of issue.
    """
    id: str
    message: str
    severity: Severity = Severity.ERROR

    def __post_init__(self):
        # Verify that the ID is a valid UUID
        if not isinstance(self.id, str):
            raise ValueError(f"Invalid ID: {self.id}")
        try:
            uuid.UUID(self.id)
        except ValueError:
            raise ValueError(f"Invalid UUID: {self.id}")

    def make(self, **kwargs) -> 'Issue':
        """
        Creates an Issue of this type.
        """
        return Issue(self, data=kwargs)

    def at(self, path: Path, line: int | None = None) -> 'Issue':
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

    def fixable(self, fix: Callable[[], None]) -> 'Issue':
        """
        Marks the issue as fixable.
        """
        self.fix = fix
        return self
    
    def at(self, path: Path, line: int | None = None) -> 'Issue':
        """
        Returns an Issue with the specified path.
        """
        
        if self.location is None:
            self.location = FileLocation(path, IntRangeSet([line]) if line else None)
        else:
            if self.location.path != path:
                raise ValueError("Cannot change the path of an existing issue.")
            if line is not None:
                self.location.lines = (self.location.lines or IntRangeSet([])) + IntRangeSet([line])
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
            if self.issues[-1] == issue: return
            if self.issues[-1].issue_type == issue.issue_type and self.issues[-1].data == issue.data:
                self.issues[-1].location = self.issues[-1].location + issue.location
                return
        self.issues.append(issue)

    def __iter__(self):
        """
        Returns an iterator over the issues.
        """
        return iter(self.issues)

    def extend(self, issues: List[Issue] | 'IssueList') -> None:
        """
        Adds multiple issues to the list.
        """
        if isinstance(issues, IssueList):
            for issue in issues.issues:
                self.append(issue)
        else:
            self.issues.extend(issues)


class CoarseProjectType(enum.Enum):
    """
    Enum for different project types.
    """
    APPLICATION = "application" # e.g., web app, CLI tool
    LIBRARY = "library" # e.g., Python package, Java library
    AGENT = "agent" # e.g., jvm agent -- something that attaches to an application
    DATA = "data" # e.g., data files, datasets


class CoarseFileScope(enum.Enum):
    """
    Enum for different file scopes.
    """
    MAIN = "main" # e.g., main source directory
    TEST = "test" # e.g., test files, test directory
    BUILD_CONFIG = "config" # e.g., configuration files
    BUILD_TEMP = "build" # e.g., temporary build files (NOT config files)


@dataclass(frozen=True)
class FileContext:
    project_type: CoarseProjectType | None = None
    file_scope: CoarseFileScope | None = None



class RepoCheck(abc.ABC):
    @abc.abstractmethod
    def check(self, path: Path, project: Any) -> List[Issue]:
        raise NotImplementedError()
    

class ProjectCheck(abc.ABC):
    @abc.abstractmethod
    def check(self, path: Path) -> List[Issue]:
        raise NotImplementedError()


class FileCheck(abc.ABC):
    @abc.abstractmethod
    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        raise NotImplementedError()


class DirectoryCheck(abc.ABC):
    @abc.abstractmethod
    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        raise NotImplementedError()