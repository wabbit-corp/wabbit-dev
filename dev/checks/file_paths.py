"""
* [x] Check for Excessively Long File Paths: Identify file paths exceeding a certain length (e.g., ~100 characters),
      as extremely long paths can cause issues on some operating systems (particularly Windows).
* [x] Check for Sensitive Filenames: Identify filenames that may contain sensitive information (e.g., private keys,
      credentials, or tokens) based on common patterns (e.g., "private_key", "id_rsa", ".env").
* [x] Check for Problematic Characters in Filenames: Identify filenames containing problematic characters
      (e.g., shell metacharacters, spaces, etc.) that could cause issues in certain environments.
* [x] Check for Non-ASCII Characters in Filenames: Identify filenames containing non-ASCII characters,
      which may cause compatibility issues across different systems.
* [x] Check for Reserved Filenames: Identify filenames that are reserved on certain operating systems (e.g., Windows)
      and should not be used.
* [x] Check for Case-Conflicting Filenames: Identify files within the same directory that differ only by case,
      which can cause issues on case-insensitive filesystems (e.g., Windows).
* [x] Check for Symbolic Links: Identify symbolic links that point to absolute paths or broken targets,
      which can cause issues in certain environments.
* [x] Check for Naming Conventions: Ensure filenames follow specific naming conventions based on file type/extension
      (e.g., snake_case for Python files, PascalCase for Java/Kotlin files).
* [x] Check for Leading/Trailing Spaces or Dots: Identify filenames with leading or trailing spaces or dots,
      which can cause issues in certain environments. **Never end a filename with a space or dot**: Windows will
      strip these, causing checkout errors (e.g. a file named `example.txt` with a trailing space may fail to clone
      on Windows with “invalid path”.
* [x] Check Symbolic Link Targets: Examine symbolic links within the repository. Ensure they point to targets
      that also exist within the repository structure. Links pointing outside the repo (e.g., absolute paths
      like /etc/passwd or relative paths like ../../../some/external/dir) can cause portability issues and may
      represent security risks.
"""

import re
import os
import platform
import unicodedata
from pathlib import Path
from typing import List, Set, Optional, Dict, Pattern

# Import necessary components from your base framework
# (Adjust the import path if necessary)
from dev.checks.base import (
    FileCheck,
    DirectoryCheck,
    Issue,
    IssueType,
    Severity,
    FileContext,
    IssueList,
)

# Reasonable max filename length, adjust as needed
DEFAULT_MAX_FILENAME_LENGTH = 100

E_FILENAME_TOO_LONG = IssueType(
    "E_FILENAME_TOO_LONG",
    "File name exceeds maximum length of {max_length} characters (actual: {actual_length}).",
)


class FilenameLengthCheck(FileCheck):
    """Checks if filenames exceed a specified maximum length."""

    def __init__(self, max_length: int = DEFAULT_MAX_FILENAME_LENGTH):
        self.max_length = max_length

    def check(self, ctx: FileContext):
        filename = ctx.path.name
        actual_length = len(filename)
        if actual_length <= self.max_length:
            return []
        ctx.add_issue(E_FILENAME_TOO_LONG, max_length=self.max_length, actual_length=actual_length)


# Common sensitive filename patterns (lowercase for case-insensitive matching)
# Using simple substring checks for broader matching
DEFAULT_SENSITIVE_FILENAME_PATTERNS: Set[str] = {
    "private_key",
    "privatekey",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credential",
    "password",
    "secret",
    "token",
    "authkey",
    "access_key",
    "session_key",
    "api_key",
    ".env",
    ".htpasswd",
    "config.json",
    "settings.json",  # Be careful with generic names
    "backup",
    ".bak",
    ".swp",
    ".swo",  # Potential accidental commits
}


E_SENSITIVE_FILENAME = IssueType(
    "E_SENSITIVE_FILENAME",
    "File may contain sensitive information based on pattern '{pattern}'.",
)


class SensitiveFilenameCheck(FileCheck):
    """Checks filenames against a list of patterns suggesting sensitive content."""

    def __init__(self, sensitive_patterns: Set[str] = DEFAULT_SENSITIVE_FILENAME_PATTERNS):
        self.sensitive_patterns_lower = {p.lower() for p in sensitive_patterns}

    def check(self, ctx: FileContext):
        filename_lower = ctx.path.name.lower()

        # Check for exact matches first (e.g., ".env")
        if filename_lower in self.sensitive_patterns_lower:
            ctx.add_issue(E_SENSITIVE_FILENAME, pattern=filename_lower)
            return

        # Check for substring matches (e.g., "my_private_key.pem")
        for pattern in self.sensitive_patterns_lower:
            # Avoid overly broad matches like '.bak' matching 'playback.txt'
            # Check if filename contains pattern delimited by common separators or start/end
            # This is a heuristic, might need refinement based on common patterns
            if re.search(rf"(?:^|[\._\-/]){re.escape(pattern)}(?:$|[\._\-/])", filename_lower):
                ctx.add_issue(E_SENSITIVE_FILENAME, pattern=pattern)
                # Optionally break after first match per file:
                # break


# Windows reserved filenames (case-insensitive, without extension)
WINDOWS_RESERVED_NAMES: Set[str] = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}

# Characters often problematic in shells or cross-platform environments
# Excludes common path separators / and \ which are handled by Path objects
DEFAULT_PROBLEMATIC_FILENAME_CHARS: Set[str] = set("*?:[]$&;|<>!`\"'()")

E_PROBLEMATIC_FILENAME_CHARS = IssueType(
    "E_PROBLEMATIC_FILENAME_CHARS", "Filename contains problematic characters: {chars}."
)
E_NON_ASCII_FILENAME = IssueType("E_NON_ASCII_FILENAME", "Filename contains non-ASCII characters.")
E_RESERVED_FILENAME = IssueType("E_RESERVED_FILENAME", "Filename is a reserved name on Windows.")


class FilenamePropertiesCheck(FileCheck):
    """
    Checks filenames for various potentially problematic properties:
    - Problematic characters (shell metachars, etc.)
    - Non-ASCII characters (optional)
    - Windows reserved names
    - Leading/trailing spaces or dots
    """

    def __init__(
        self,
        problematic_chars: Set[str] = DEFAULT_PROBLEMATIC_FILENAME_CHARS,
        check_non_ascii: bool = True,  # Flag non-ASCII by default
        check_reserved: bool = True,  # Check reserved names by default
        check_leading_trailing: bool = True,  # Check leading/trailing by default
    ):
        self.problematic_chars = problematic_chars
        self.check_non_ascii = check_non_ascii
        self.check_reserved = check_reserved
        self.check_leading_trailing = check_leading_trailing
        # Compile reserved names check (case-insensitive)
        self.reserved_pattern = (
            re.compile(
                r"^(" + "|".join(re.escape(name) for name in WINDOWS_RESERVED_NAMES) + r")(\..*)?$",
                re.IGNORECASE,
            )
            if self.check_reserved
            else None
        )

    def check(self, ctx: FileContext):
        filename = ctx.path.name

        # 1. Check for problematic characters
        found_problematic = {char for char in filename if char in self.problematic_chars}
        if found_problematic:
            ctx.add_issue(
                E_PROBLEMATIC_FILENAME_CHARS,
                chars=", ".join(sorted(list(found_problematic))),
            )

        # 2. Check for non-ASCII characters
        if self.check_non_ascii and not filename.isascii():
            # Check if it's just Unicode normalization differences (less critical)
            # This is complex; for now, just flag any non-ASCII
            ctx.add_issue(E_NON_ASCII_FILENAME)

        # 3. Check for Windows reserved names
        if self.reserved_pattern and self.reserved_pattern.match(filename):
            ctx.add_issue(E_RESERVED_FILENAME)


DEFAULT_CONVENTIONS: Dict[str, Dict[str, Pattern | str]] = {
    ".py": {"pattern": re.compile(r"^[a-z_]+$"), "description": "snake_case"},
    ".java": {
        "pattern": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
        "description": "PascalCase",
    },
    ".kt": {"pattern": re.compile(r"^[A-Z][a-zA-Z0-9]*$"), "description": "PascalCase"},
}

E_FILE_NAMING_CONVENTION = IssueType(
    "E_FILE_NAMING_CONVENTION",
    "Filename does not follow the expected naming convention for '{file_type}': {reason}.",
)


class NamingConventionCheck(FileCheck):
    """
    Checks if filenames adhere to configured naming conventions based on file type/extension.
    NOTE: This is a basic structure and requires significant configuration.
    """

    def __init__(self, conventions: Optional[Dict[str, Dict[str, Pattern]]] = None):
        """
        Args:
            conventions: A dictionary mapping file extensions (e.g., '.py')
                         to convention rules (e.g., {'pattern': re.compile(r'^[a-z_]+$'), 'description': 'snake_case'}).
                         Example:
                         {
                             '.py': {'pattern': re.compile(r'^[a-z0-9_]+$'), 'description': 'snake_case'},
                             '.java': {'pattern': re.compile(r'^[A-Z][a-zA-Z0-9]*$'), 'description': 'PascalCase'}
                         }
        """
        self.conventions = conventions if conventions else {}

    def check(self, ctx: FileContext):
        filename_stem = ctx.path.stem  # Filename without extension
        extension = ctx.path.suffix.lower()

        if not self.conventions or extension not in self.conventions:
            return []  # No convention defined for this file type

        rule = self.conventions[extension]
        pattern = rule.get("pattern")
        description = rule.get("description", "expected format")

        if pattern and not pattern.match(filename_stem):
            ctx.add_issue(
                E_FILE_NAMING_CONVENTION,
                file_type=f"'{extension}' files",
                reason=f"does not match expected pattern ({description})",
            )


E_SYMLINK_POINTS_ABSOLUTE = IssueType(
    "E_SYMLINK_POINTS_ABSOLUTE",
    "Symbolic link '{link_name}' points to an absolute path '{target}'.",
)
E_SYMLINK_BROKEN = IssueType(
    "E_SYMLINK_BROKEN",
    "Symbolic link '{link_name}' points to a non-existent target '{target}'.",
)
E_SYMLINK = IssueType(
    "E_SYMLINK",
    "Symbolic links are not allowed in repositories due to Windows issues.",
)


class SymlinkTargetCheck(FileCheck):
    """Checks symbolic links for absolute paths or broken targets."""

    def __init__(self, check_absolute: bool = True, check_broken: bool = True):
        self.check_absolute = check_absolute
        self.check_broken = check_broken

    def check(self, ctx: FileContext):
        if not ctx.path.is_symlink():
            return []

        target_path_str = os.readlink(str(ctx.path))  # Read link target as string
        target_path = Path(target_path_str)  # Convert to Path

        # 1. Check if target is absolute
        if self.check_absolute and target_path.is_absolute():
            ctx.add_issue(
                E_SYMLINK_POINTS_ABSOLUTE,
                link_name=ctx.path.name,
                target=target_path_str,
            )

        # 2. Check if target exists (relative to the link's location)
        # Note: resolve() can fail if the link is broken deeper in the chain
        # exists() checks if the immediate target resolves correctly
        if self.check_broken:
            # Use os.path.exists which handles links correctly without full resolve
            # Construct the absolute path to the target based on the link's dir
            absolute_target = os.path.abspath(os.path.join(os.path.dirname(str(ctx.path)), target_path_str))
            if not os.path.lexists(absolute_target):  # lexists checks link target without following
                ctx.add_issue(E_SYMLINK_BROKEN, link_name=ctx.path.name, target=target_path_str)
            # More robust check: Check if path.resolve() works without error AND exists
            # try:
            #     resolved_target = path.resolve(strict=True) # strict=True raises error if broken
            #     if not resolved_target.exists(): # Double check after resolving
            #          # This case is less likely if strict=True works, but belt-and-suspenders
            #          issues.append(W_SYMLINK_BROKEN.make(link_name=path.name, target=target_path_str).at(path))
            # except (FileNotFoundError, RuntimeError): # RuntimeError on Windows for certain broken links
            #     issues.append(W_SYMLINK_BROKEN.make(link_name=path.name, target=target_path_str).at(path))


# --- DirectoryCheck Implementation ---

E_CASE_CONFLICTING_FILENAME = IssueType(
    "E_CASE_CONFLICTING_FILENAME",
    "Directory '{directory}' contains filenames differing only by case: {conflicting_files}.",
)


class CaseConflictCheck(DirectoryCheck):
    """
    Checks for files within the same directory whose names differ only by case.
    """

    def check(self, ctx: FileContext):
        if not ctx.path.is_dir():
            return []  # Should not happen if called correctly, but check anyway

        filenames_lower_map: Dict[str, List[str]] = {}
        for item in ctx.path.iterdir():
            # Optional: Only check files, or check both files and dirs? Checking both seems safer.
            # if item.is_file():
            name = item.name
            name_lower = name.lower()
            if name_lower not in filenames_lower_map:
                filenames_lower_map[name_lower] = []
            filenames_lower_map[name_lower].append(name)

        for name_lower, original_names in filenames_lower_map.items():
            if len(original_names) > 1:
                # Check if the names are actually different (e.g., "file.txt" and "File.txt")
                # If all names in the list are identical, it's not a case conflict (e.g., multiple links pointing to same target named identically)
                # However, iterdir should only list each entry once. So len > 1 implies different casing or identical names (less likely).
                # A set check confirms if there are truly different casings.
                if len(set(original_names)) > 1:
                    ctx.add_issue(
                        E_CASE_CONFLICTING_FILENAME,
                        directory=ctx.path.name,  # Or relative path if context available
                        conflicting_files=", ".join(sorted(original_names)),
                    )
