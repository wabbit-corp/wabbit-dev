"""
* [x] Check that all UUIDs and ULIDs in the repos are unique.
"""

import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import List, Dict, Set, Optional, Any
from pathlib import Path

import pathspec

# Import necessary components from your new system
from dev.checks.base import ProjectCheck, Issue, IssueType, FileLocation, IntRangeSet, IssueList

# Assuming get_expected_file_properties exists and helps identify text files
# If not, we might need a simpler text file check.
from dev.file_properties import get_expected_file_properties

# Assuming a walk_files utility exists or we implement one
# from dev.io import walk_files # If you have this utility

# --- Constants ---

# "2ecbfb56-85d7-4e32-84cb-b2f175acf240" - Note: Captures the quotes
UUID_PATTERN = re.compile(
    r"(\"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\")"
)
# "01FY323KTHD29NRQC6D7BYBP51" - Note: Captures the quotes. Adjusted regex slightly to avoid ^LI inside character class if unintended.
# If you specifically want to exclude L and I, it should be outside: "[A-Z0-9][A-Z0-9^LI]*" pattern is complex.
# Assuming Crockford's Base32 alphabet for ULID (no I, L, O, U). Let's refine the pattern.
# Crockford's alphabet: 0123456789ABCDEFGHJKMNPQRSTVWXYZ (excludes I, L, O, U)
ULID_CROCKFORD_CHARS = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# Match "01" followed by 24 Crockford Base32 characters
ULID_PATTERN = re.compile(rf"(\"01[{ULID_CROCKFORD_CHARS}]{{24}}\")")

# Combine source file extensions (can be refined based on project needs)
# Using a frozenset for immutability and slightly faster lookups
SOURCE_FILE_EXTENSIONS = frozenset(
    [
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".groovy",
        ".gradle",
        ".clj",
        ".cljs",
        ".cljc",
        ".edn",
        ".yaml",
        ".yml",
        ".xml",
        ".json",
        ".properties",
        ".md",
        ".txt",
        ".sh",
        ".bat",
        ".cmd",
        ".ps1",
        ".py",
        ".rb",
        ".pl",
        ".php",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".ts",
        ".js",
        ".html",
        ".css",
        ".scss",
        ".less",
        ".sass",
        ".php",
        ".php3",
        ".php4",
        ".php5",
        ".php7",
    ]
)

# Consider standard ignore patterns if your framework supports them (e.g., .gitignore)
# For simplicity, replicating basic ignore logic if needed.
DEFAULT_IGNORE_DIRS: Set[str] = {
    ".git",
    ".gradle",
    ".idea",
    "build",
    "target",
    "node_modules",
}
DEFAULT_IGNORE_FILES: Set[str] = {".DS_Store", "Thumbs.db", "desktop.ini"}

# --- Issue Types ---

E_DUPLICATE_IDENTIFIER = IssueType(
    "E_DUPLICATE_IDENTIFIER", "Duplicate identifier found."
)

# --- The Check ---


@dataclass(frozen=True)
class IgnoreContext:
    root: Path
    ignore: List[str] = field(default_factory=list)

    def with_ignore(self, ignore: List[str]) -> "IgnoreContext":
        return IgnoreContext(
            root=self.root,
            ignore=self.ignore + ignore,
        )

    @cached_property
    def spec(self) -> pathspec.PathSpec:
        from pathspec import PathSpec
        from pathspec.patterns.gitwildmatch import GitWildMatchPattern

        return PathSpec.from_lines(
            GitWildMatchPattern,
            self.ignore,
        )


def read_ignore_patterns(path: Path) -> List[str]:
    with path.open("rt", encoding="utf-8", errors="replace") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


class UniqueIdentifiersCheck(ProjectCheck):
    """
    Checks for duplicate UUIDs and ULIDs (enclosed in double quotes) across
    all source files within a project.
    """

    def __init__(
        self,
        ignore_dirs: Optional[Set[str]] = None,
        ignore_files: Optional[Set[str]] = None,
    ):
        """
        Initializes the check.
        Args:
            ignore_dirs: Set of directory names to ignore during the scan. Defaults to common build/VCS dirs.
            ignore_files: Set of file names to ignore during the scan. Defaults to common system files.
        """
        self.ignore_dirs = (
            ignore_dirs if ignore_dirs is not None else DEFAULT_IGNORE_DIRS
        )
        self.ignore_files = (
            ignore_files if ignore_files is not None else DEFAULT_IGNORE_FILES
        )
        # Precompile regex patterns (already done at module level)
        self.uuid_pattern = UUID_PATTERN
        self.ulid_pattern = ULID_PATTERN

    def _is_locally_ignored(self, path: Path, root_path: Path) -> bool:
        """Check if a path should be ignored by local static rules."""
        if path.name in self.ignore_files:
            return True

        try:
            # Check if any part of the relative path is an ignored directory name
            relative_parts = path.relative_to(root_path).parts
            for part in relative_parts:
                if part in self.ignore_dirs:
                    return True
        except ValueError:
            # path might not be relative to root_path, shouldn't happen with rglob
            pass

        return False

    def _is_pathspec_ignored(self, path: Path, ignore_ctx: IgnoreContext) -> bool:
        try:
            rel_path = path.relative_to(ignore_ctx.root)
        except ValueError:
            return False
        return ignore_ctx.spec.match_file(str(rel_path))

    def check(self, path: Path, project: Any) -> List[Issue]:
        """
        Scans the project at the given path for duplicate identifiers.

        Args:
            path: The root path of the project to check.

        Returns:
            A list of Issues found.
        """
        if not path.is_dir():
            # Or raise ValueError? Returning empty list seems reasonable.
            return []

        seen_ulids: Dict[str, FileLocation] = {}
        seen_uuids: Dict[str, FileLocation] = {}
        issues = IssueList()  # Use IssueList for potential merging later if needed

        def scan_file(file_path: Path, ignore_ctx: IgnoreContext | None) -> None:
            if self._is_locally_ignored(file_path, path):
                return
            if ignore_ctx is not None and self._is_pathspec_ignored(file_path, ignore_ctx):
                return

            # Check file extension - Skip non-source/text files
            if file_path.suffix.lower() not in SOURCE_FILE_EXTENSIONS:
                return

            # Skip files that are explicitly classified as binary.
            props = get_expected_file_properties(file_path)
            if props is not None and props.is_binary:
                return

            # Read with replacement so isolated bad bytes do not abort the full scan.
            try:
                with file_path.open("rt", encoding="utf-8", errors="replace") as fin:
                    for line_nr_zero_based, line_text in enumerate(fin):
                        line_nr = line_nr_zero_based + 1
                        current_location = FileLocation(file_path, IntRangeSet([line_nr]))

                        # Find UUIDs
                        for match in self.uuid_pattern.finditer(line_text):
                            uuid_val = match.group(1)
                            if uuid_val in seen_uuids:
                                first_loc = seen_uuids[uuid_val]
                                issues.append(
                                    E_DUPLICATE_IDENTIFIER.make(
                                        identifier=uuid_val,
                                        first_location=f"{first_loc.path.relative_to(path)}:{first_loc.lines}",
                                    ).at(file_path, line=line_nr)
                                )
                            else:
                                seen_uuids[uuid_val] = current_location

                        # Find ULIDs
                        for match in self.ulid_pattern.finditer(line_text):
                            ulid_val = match.group(1)
                            if ulid_val in seen_ulids:
                                first_loc = seen_ulids[ulid_val]
                                issues.append(
                                    E_DUPLICATE_IDENTIFIER.make(
                                        identifier=ulid_val,
                                        first_location=f"{first_loc.path.relative_to(path)}:{first_loc.lines}",
                                    ).at(file_path, line=line_nr)
                                )
                            else:
                                seen_ulids[ulid_val] = current_location
            except OSError:
                return

        def walk_dir(dir_path: Path, ignore_ctx: IgnoreContext | None) -> None:
            if self._is_locally_ignored(dir_path, path):
                return
            if ignore_ctx is not None and self._is_pathspec_ignored(dir_path, ignore_ctx):
                return

            next_ctx = ignore_ctx
            if (dir_path / ".git").exists():
                next_ctx = IgnoreContext(
                    root=dir_path,
                    ignore=["/.git"],
                )

            gitignore_path = dir_path / ".gitignore"
            if gitignore_path.exists() and next_ctx is not None:
                next_ctx = next_ctx.with_ignore(read_ignore_patterns(gitignore_path))

            checkignore_path = dir_path / ".checkignore"
            if checkignore_path.exists():
                if next_ctx is None:
                    next_ctx = IgnoreContext(
                        root=dir_path,
                        ignore=["/.git"],
                    )
                next_ctx = next_ctx.with_ignore(read_ignore_patterns(checkignore_path))

            for child in sorted(dir_path.iterdir()):
                if child.is_dir():
                    walk_dir(child, next_ctx)
                elif child.is_file():
                    scan_file(child, next_ctx)

        walk_dir(path, None)

        return issues.issues  # Return the raw list of issues


# --- Example Usage (Conceptual) ---
# checker = UniqueIdentifiersCheck()
# project_root = Path("./my_gradle_project")
# list_of_issues = checker.check(project_root)
# for issue in list_of_issues:
#     # Process issues (print, log, etc.)
#     print(f"[{issue.issue_type.severity.value}] {issue.issue_type.message.format(**issue.data)} @ {issue.location.path}:{issue.location.lines}")
