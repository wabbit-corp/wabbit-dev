import re
import os
import platform
import unicodedata
from pathlib import Path
from typing import List, Set, Optional, Dict, Pattern

# Import necessary components from your base framework
# (Adjust the import path if necessary)
from dev.checks.base import (
    FileCheck, DirectoryCheck, Issue, IssueType, Severity,
    FileLocation, IntRangeSet, FileContext, IssueList
)

# --- Configuration Defaults ---

# Reasonable max filename length, adjust as needed
DEFAULT_MAX_FILENAME_LENGTH = 100

# Common sensitive filename patterns (lowercase for case-insensitive matching)
# Using simple substring checks for broader matching
DEFAULT_SENSITIVE_FILENAME_PATTERNS: Set[str] = {
    "private_key", "privatekey", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credential", "password", "secret", "token", "authkey", "access_key",
    "session_key", "api_key", ".env", ".htpasswd", "config.json", "settings.json", # Be careful with generic names
    "backup", ".bak", ".swp", ".swo" # Potential accidental commits
}

# Characters often problematic in shells or cross-platform environments
# Excludes common path separators / and \ which are handled by Path objects
DEFAULT_PROBLEMATIC_FILENAME_CHARS: Set[str] = set("*?:[]$&;|<>!`\"'()")

# Windows reserved filenames (case-insensitive, without extension)
WINDOWS_RESERVED_NAMES: Set[str] = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

# --- Issue Types ---

E_FILENAME_TOO_LONG           = IssueType("5c59f469-ffc6-434f-b393-00fa5245cf26", "Filename '{filename}' exceeds maximum length of {max_length} characters (actual: {actual_length}).")
E_SENSITIVE_FILENAME          = IssueType("3b63d527-2492-470b-a362-9b3db764d4d4", "Filename '{filename}' may contain sensitive information based on pattern '{pattern}'.")
E_PROBLEMATIC_FILENAME_CHARS  = IssueType("7af2dbff-bafe-46fd-bac5-7592f5756386", "Filename '{filename}' contains problematic characters: {chars}.")
E_NON_ASCII_FILENAME          = IssueType("f8a3826a-6f80-4a16-b8c4-b5832292df7f", "Filename '{filename}' contains non-ASCII characters.")
E_RESERVED_FILENAME           = IssueType("608f10f7-9aa6-49ff-a3eb-324ecb1dca76", "Filename '{filename}' is a reserved name on Windows.")
E_FILE_NAMING_CONVENTION      = IssueType("517084de-43f8-43ea-a3e6-a98e8557b5ab", "Filename '{filename}' does not follow the expected naming convention for '{file_type}': {reason}.")
E_CASE_CONFLICTING_FILENAME   = IssueType("6c4b1ea3-46f1-4830-8b90-751d992b75d4", "Directory '{directory}' contains filenames differing only by case: {conflicting_files}.")
E_SYMLINK_POINTS_ABSOLUTE     = IssueType("f4138d57-061b-4f0a-8f76-12c5078a4e06", "Symbolic link '{link_name}' points to an absolute path '{target}'.")
E_SYMLINK_BROKEN              = IssueType("40fe9df5-cfa0-43cf-8fb0-15115ddced28", "Symbolic link '{link_name}' points to a non-existent target '{target}'.")
E_SYMLINK                     = IssueType("a53bf5c2-e650-47c8-b360-3bf4d8fee646", "Symbolic links are not allowed in repositories due to Windows issues.")

# --- FileCheck Implementations ---

class FilenameLengthCheck(FileCheck):
    """Checks if filenames exceed a specified maximum length."""
    def __init__(self, max_length: int = DEFAULT_MAX_FILENAME_LENGTH):
        self.max_length = max_length

    def check(self, path: Path, ctx: FileContext) -> List[Issue]:
        filename = path.name
        actual_length = len(filename)
        if actual_length <= self.max_length:
            return []
        return [E_FILENAME_TOO_LONG.make(
            filename=filename,
            max_length=self.max_length,
            actual_length=actual_length
        ).at(path)]


class SensitiveFilenameCheck(FileCheck):
    """Checks filenames against a list of patterns suggesting sensitive content."""
    def __init__(self, sensitive_patterns: Set[str] = DEFAULT_SENSITIVE_FILENAME_PATTERNS):
        # Store lowercase patterns for case-insensitive matching
        self.sensitive_patterns_lower = {p.lower() for p in sensitive_patterns}

    def check(self, path: Path, ctx: FileContext) -> List[Issue]:
        issues = IssueList()
        filename_lower = path.name.lower()

        # Check for exact matches first (e.g., ".env")
        if filename_lower in self.sensitive_patterns_lower:
             issues.append(E_SENSITIVE_FILENAME.make(
                 filename=path.name,
                 pattern=filename_lower # The matched pattern
             ).at(path))
             return issues.issues # Report once per file if exact match found

        # Check for substring matches (e.g., "my_private_key.pem")
        for pattern in self.sensitive_patterns_lower:
            # Avoid overly broad matches like '.bak' matching 'playback.txt'
            # Check if filename contains pattern delimited by common separators or start/end
            # This is a heuristic, might need refinement based on common patterns
            if re.search(rf'(?:^|[\._\-/]){re.escape(pattern)}(?:$|[\._\-/])', filename_lower):
                 issues.append(E_SENSITIVE_FILENAME.make(
                     filename=path.name,
                     pattern=pattern
                 ).at(path))
                 # Optionally break after first match per file:
                 # break

        return issues.issues


class FilenamePropertiesCheck(FileCheck):
    """
    Checks filenames for various potentially problematic properties:
    - Problematic characters (shell metachars, etc.)
    - Non-ASCII characters (optional)
    - Windows reserved names
    - Leading/trailing spaces or dots
    """
    def __init__(self,
                 problematic_chars: Set[str] = DEFAULT_PROBLEMATIC_FILENAME_CHARS,
                 check_non_ascii: bool = True, # Flag non-ASCII by default
                 check_reserved: bool = True, # Check reserved names by default
                 check_leading_trailing: bool = True # Check leading/trailing by default
                ):
        self.problematic_chars = problematic_chars
        self.check_non_ascii = check_non_ascii
        self.check_reserved = check_reserved
        self.check_leading_trailing = check_leading_trailing
        # Compile reserved names check (case-insensitive)
        self.reserved_pattern = re.compile(
            r'^(' + '|'.join(re.escape(name) for name in WINDOWS_RESERVED_NAMES) + r')(\..*)?$',
            re.IGNORECASE
        ) if self.check_reserved else None

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        issues = IssueList()
        filename = path.name

        # 1. Check for problematic characters
        found_problematic = {char for char in filename if char in self.problematic_chars}
        if found_problematic:
            issues.append(E_PROBLEMATIC_FILENAME_CHARS.make(
                filename=filename,
                chars=', '.join(sorted(list(found_problematic)))
            ).at(path))

        # 2. Check for non-ASCII characters
        if self.check_non_ascii and not filename.isascii():
             # Check if it's just Unicode normalization differences (less critical)
             # This is complex; for now, just flag any non-ASCII
             issues.append(E_NON_ASCII_FILENAME.make(filename=filename).at(path))

        # 3. Check for Windows reserved names
        if self.reserved_pattern and self.reserved_pattern.match(filename):
            issues.append(E_RESERVED_FILENAME.make(filename=filename).at(path))

        return issues.issues


DEFAULT_CONVENTIONS: Dict[str, Dict[str, Pattern]] = {
    '.py': {'pattern': re.compile(r'^[a-z_]+$'), 'description': 'snake_case'},
    '.java': {'pattern': re.compile(r'^[A-Z][a-zA-Z0-9]*$'), 'description': 'PascalCase'},
    '.kt': {'pattern': re.compile(r'^[A-Z][a-zA-Z0-9]*$'), 'description': 'PascalCase'},
}


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

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        issues = IssueList()
        filename_stem = path.stem # Filename without extension
        extension = path.suffix.lower()

        if not self.conventions or extension not in self.conventions:
            return [] # No convention defined for this file type

        rule = self.conventions[extension]
        pattern = rule.get('pattern')
        description = rule.get('description', 'expected format')

        if pattern and not pattern.match(filename_stem):
            issues.append(W_NAMING_CONVENTION_VIOLATION.make(
                filename=path.name,
                file_type=f"'{extension}' files",
                reason=f"does not match expected pattern ({description})"
            ).at(path))

        # Add more complex convention checks here if needed (e.g., based on FileContext)

        return issues.issues


class SymlinkTargetCheck(FileCheck):
    """Checks symbolic links for absolute paths or broken targets."""
    def __init__(self, check_absolute: bool = True, check_broken: bool = True):
        self.check_absolute = check_absolute
        self.check_broken = check_broken

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        issues = IssueList()
        if not path.is_symlink():
            return []

        try:
            target_path_str = os.readlink(str(path)) # Read link target as string
            target_path = Path(target_path_str) # Convert to Path

            # 1. Check if target is absolute
            if self.check_absolute and target_path.is_absolute():
                 issues.append(E_SYMLINK_POINTS_ABSOLUTE.make(
                     link_name=path.name,
                     target=target_path_str
                 ).at(path))

            # 2. Check if target exists (relative to the link's location)
            # Note: resolve() can fail if the link is broken deeper in the chain
            # exists() checks if the immediate target resolves correctly
            if self.check_broken:
                # Use os.path.exists which handles links correctly without full resolve
                # Construct the absolute path to the target based on the link's dir
                absolute_target = os.path.abspath(os.path.join(os.path.dirname(str(path)), target_path_str))
                if not os.path.lexists(absolute_target): # lexists checks link target without following
                     issues.append(E_SYMLINK_BROKEN.make(
                         link_name=path.name,
                         target=target_path_str
                     ).at(path))
                # More robust check: Check if path.resolve() works without error AND exists
                # try:
                #     resolved_target = path.resolve(strict=True) # strict=True raises error if broken
                #     if not resolved_target.exists(): # Double check after resolving
                #          # This case is less likely if strict=True works, but belt-and-suspenders
                #          issues.append(W_SYMLINK_BROKEN.make(link_name=path.name, target=target_path_str).at(path))
                # except (FileNotFoundError, RuntimeError): # RuntimeError on Windows for certain broken links
                #     issues.append(W_SYMLINK_BROKEN.make(link_name=path.name, target=target_path_str).at(path))


        except OSError as e:
            # Handle potential errors reading the link itself
            issues.append(Issue(
                IssueType("symlink-read-error", f"Could not read symbolic link '{path.name}': {e}", Severity.ERROR)
            ).at(path))
        except Exception as e: # Catch unexpected errors
             issues.append(Issue(
                IssueType("symlink-generic-error", f"Unexpected error checking symbolic link '{path.name}': {e}", Severity.ERROR)
            ).at(path))

        return issues.issues


# --- DirectoryCheck Implementation ---

class CaseConflictCheck(DirectoryCheck):
    """
    Checks for files within the same directory whose names differ only by case.
    """
    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        issues = IssueList()
        if not path.is_dir():
            return [] # Should not happen if called correctly, but check anyway

        filenames_lower_map: Dict[str, List[str]] = {}
        try:
            for item in path.iterdir():
                # Optional: Only check files, or check both files and dirs? Checking both seems safer.
                # if item.is_file():
                name = item.name
                name_lower = name.lower()
                if name_lower not in filenames_lower_map:
                    filenames_lower_map[name_lower] = []
                filenames_lower_map[name_lower].append(name)
        except OSError as e:
             issues.append(Issue(
                IssueType("dir-list-error", f"Could not list directory '{path}': {e}", Severity.ERROR)
             ).at(path)) # Associate error with the directory itself
             return issues.issues


        for name_lower, original_names in filenames_lower_map.items():
            if len(original_names) > 1:
                # Check if the names are actually different (e.g., "file.txt" and "File.txt")
                # If all names in the list are identical, it's not a case conflict (e.g., multiple links pointing to same target named identically)
                # However, iterdir should only list each entry once. So len > 1 implies different casing or identical names (less likely).
                # A set check confirms if there are truly different casings.
                if len(set(original_names)) > 1:
                    issues.append(E_CASE_CONFLICTING_FILENAME.make(
                        directory=path.name, # Or relative path if context available
                        conflicting_files=', '.join(sorted(original_names))
                    ).at(path)) # Issue associated with the directory

        return issues.issues

# --- Example Usage (Conceptual) ---
# file_checks: List[FileCheck] = [
#     FilenameLengthCheck(),
#     SensitiveFilenameCheck(),
#     FilenamePropertiesCheck(),
#     # NamingConventionCheck(conventions=...), # Needs config
#     SymlinkTargetCheck(),
# ]
# dir_checks: List[DirectoryCheck] = [
#     CaseConflictCheck(),
# ]

# project_root = Path('.')
# all_issues = IssueList()

# for item_path in project_root.rglob('*'): # Or use a more sophisticated walker
#     context = FileContext() # Determine context if possible
#     if item_path.is_file():
#         for checker in file_checks:
#             all_issues.extend(checker.check(item_path, context))
#     elif item_path.is_dir():
#          for checker in dir_checks:
#             all_issues.extend(checker.check(item_path, context))

# for issue in all_issues:
#      print(f"[{issue.issue_type.severity.value}] {issue.issue_type.message.format(**(issue.data or {}))} @ {issue.location.path}:{issue.location.lines}")
