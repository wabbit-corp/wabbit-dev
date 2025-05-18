'''
* [x] Check that all UUIDs and ULIDs in the repos are unique.
'''

import re
import abc
from typing import List, Dict, Tuple, Set, Optional, Any
from pathlib import Path

# Import necessary components from your new system
from dev.checks.base import (
    ProjectCheck, Issue, IssueType, Severity, FileLocation,
    IntRangeSet, CoarseProjectType, CoarseFileScope, FileContext, IssueList # Assuming these are in base or similar
)
# Assuming get_expected_file_properties exists and helps identify text files
# If not, we might need a simpler text file check.
from dev.file_properties import get_expected_file_properties, ExpectedFileProperties
# Assuming a walk_files utility exists or we implement one
# from dev.io import walk_files # If you have this utility

# --- Constants ---

# "2ecbfb56-85d7-4e32-84cb-b2f175acf240" - Note: Captures the quotes
UUID_PATTERN = re.compile(r"(\"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\")")
# "01FY323KTHD29NRQC6D7BYBP51" - Note: Captures the quotes. Adjusted regex slightly to avoid ^LI inside character class if unintended.
# If you specifically want to exclude L and I, it should be outside: "[A-Z0-9][A-Z0-9^LI]*" pattern is complex.
# Assuming Crockford's Base32 alphabet for ULID (no I, L, O, U). Let's refine the pattern.
# Crockford's alphabet: 0123456789ABCDEFGHJKMNPQRSTVWXYZ (excludes I, L, O, U)
ULID_CROCKFORD_CHARS = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# Match "01" followed by 24 Crockford Base32 characters
ULID_PATTERN = re.compile(rf"(\"01[{ULID_CROCKFORD_CHARS}]{{24}}\")")

# Combine source file extensions (can be refined based on project needs)
# Using a frozenset for immutability and slightly faster lookups
SOURCE_FILE_EXTENSIONS = frozenset([
    '.java', '.kt', '.kts', '.scala', '.groovy', '.gradle', '.clj', '.cljs', '.cljc', '.edn', '.yaml', '.yml', '.xml',
    '.json', '.properties', '.md', '.txt', '.sh', '.bat', '.cmd', '.ps1', '.py', '.rb', '.pl', '.php', '.c', '.cpp', '.h',
    '.hpp', '.cs', '.ts', '.js', '.html', '.css', '.scss', '.less', '.sass', '.php', '.php3', '.php4', '.php5', '.php7'
])

# Consider standard ignore patterns if your framework supports them (e.g., .gitignore)
# For simplicity, replicating basic ignore logic if needed.
DEFAULT_IGNORE_DIRS: Set[str] = {".git", ".gradle", ".idea", "build", "target", "node_modules"}
DEFAULT_IGNORE_FILES: Set[str] = {".DS_Store", "Thumbs.db", "desktop.ini"}

# --- Issue Types ---

E_DUPLICATE_IDENTIFIER = IssueType("7ac08480-1b54-43ca-ab8c-3e071eb098ff", "Duplicate identifier found.")

# --- The Check ---

class UniqueIdentifiersCheck(ProjectCheck):
    """
    Checks for duplicate UUIDs and ULIDs (enclosed in double quotes) across
    all source files within a project.
    """

    def __init__(self, ignore_dirs: Optional[Set[str]] = None, ignore_files: Optional[Set[str]] = None):
        """
        Initializes the check.
        Args:
            ignore_dirs: Set of directory names to ignore during the scan. Defaults to common build/VCS dirs.
            ignore_files: Set of file names to ignore during the scan. Defaults to common system files.
        """
        self.ignore_dirs = ignore_dirs if ignore_dirs is not None else DEFAULT_IGNORE_DIRS
        self.ignore_files = ignore_files if ignore_files is not None else DEFAULT_IGNORE_FILES
        # Precompile regex patterns (already done at module level)
        self.uuid_pattern = UUID_PATTERN
        self.ulid_pattern = ULID_PATTERN

    def _is_ignored(self, path: Path, root_path: Path) -> bool:
        """Check if a path should be ignored."""
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
        issues = IssueList() # Use IssueList for potential merging later if needed

        # Walk through all files in the project directory
        # Using rglob for simplicity, could use os.walk or a dedicated utility
        for file_path in path.rglob('*'):
            if not file_path.is_file():
                continue

            # Check if the file or its parent directories should be ignored
            if self._is_ignored(file_path, path):
                 continue

            # Check file extension - Skip non-source/text files
            if file_path.suffix.lower() not in SOURCE_FILE_EXTENSIONS:
                continue

            # Optional: Use get_expected_file_properties if available for a more robust text check
            # props = get_expected_file_properties(file_path) or ExpectedFileProperties()
            # if not props.is_text:
            #     continue

            # Read file content line by line
            with file_path.open('rt', encoding='utf-8', errors='strict') as fin:
                for line_nr_zero_based, line_text in enumerate(fin):
                    line_nr = line_nr_zero_based + 1 # Human-readable line number (1-based)
                    current_location = FileLocation(file_path, IntRangeSet([line_nr]))

                    # Find UUIDs
                    for match in self.uuid_pattern.finditer(line_text):
                        uuid_val = match.group(1)
                        if uuid_val in seen_uuids:
                            first_loc = seen_uuids[uuid_val]
                            issues.append(E_DUPLICATE_IDENTIFIER.make(
                                identifier=uuid_val,
                                first_location=f"{first_loc.path.relative_to(path)}:{first_loc.lines}" # Make location relative and nice
                            ).at(file_path, line=line_nr))
                        else:
                            seen_uuids[uuid_val] = current_location

                    # Find ULIDs
                    for match in self.ulid_pattern.finditer(line_text):
                        ulid_val = match.group(1)
                        if ulid_val in seen_ulids:
                            first_loc = seen_ulids[ulid_val]
                            issues.append(E_DUPLICATE_IDENTIFIER.make(
                                identifier=ulid_val,
                                first_location=f"{first_loc.path.relative_to(path)}:{first_loc.lines}" # Make location relative and nice
                            ).at(file_path, line=line_nr))
                        else:
                            seen_ulids[ulid_val] = current_location


        return issues.issues # Return the raw list of issues


# --- Example Usage (Conceptual) ---
# checker = UniqueIdentifiersCheck()
# project_root = Path("./my_gradle_project")
# list_of_issues = checker.check(project_root)
# for issue in list_of_issues:
#     # Process issues (print, log, etc.)
#     print(f"[{issue.issue_type.severity.value}] {issue.issue_type.message.format(**issue.data)} @ {issue.location.path}:{issue.location.lines}")
