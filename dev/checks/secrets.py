'''
* [x] Check for Hardcoded Secrets: Look for hardcoded secrets in scripts, configuration files,
      or source code. This includes API keys, passwords, and other sensitive information.
      Implemented by checking that there are no high-entropy strings that look like secrets.
* [ ] Check for Hardcoded Absolute Paths: Look for hardcoded absolute file paths in scripts,
      configuration files, or source code (e.g., starting with C:\, /home/, /Users/).
      These often break portability and should usually be replaced with relative paths,
      environment variables, or configuration lookups. /absolute/path/to/danger
* [ ] Check for Hardcoded URLs: Look for hardcoded URLs in scripts, configuration files,
      or source code. This includes URLs to external services, APIs, and other resources.
* [ ] Check for Hardcoded Credentials: Look for hardcoded credentials in scripts, configuration files,
      or source code. This includes usernames, passwords, and other sensitive information.
* [ ] Check for Hardcoded Internal Hostnames/IPs: Scan configuration files, scripts, and
      documentation for hardcoded internal network details like specific server hostnames
      (e.g., internal-db.prod.local) or private IP address ranges that shouldn't be exposed
      or hardcoded.
'''

import re
import math
import os
from pathlib import Path
from typing import List, Set, Optional, Tuple

# Import necessary components from your base framework
# (Adjust the import path if necessary)
from dev.checks.base import (
    FileCheck, Issue, IssueType, Severity,
    FileLocation, IntRangeSet, FileContext, IssueList
)
# Assuming get_expected_file_properties exists and helps identify text files
# If not, we might need a simpler text file check.
from dev.file_properties import get_expected_file_properties, ExpectedFileProperties

# --- Constants ---

# Character sets for entropy calculation
BASE64_CHARS: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
HEX_CHARS: str    = "1234567890abcdefABCDEF"

# Default configuration values (inspired by trufflehog defaults)
DEFAULT_MIN_SECRET_LENGTH = 20
DEFAULT_B64_ENTROPY_THRESHOLD = 4.5
DEFAULT_HEX_ENTROPY_THRESHOLD = 3.0

# Regex to find potential URLs. This is a common but not exhaustive pattern.
# It looks for common schemes or www. and captures characters typical in URLs.
DEFAULT_URL_REGEX = re.compile(
    r"""\b((?:https?|ftp|file)://|www\.|ftp\.)[-a-zA-Z0-9+&@#/%?=~_|!:,.;]*[-a-zA-Z0-9+&@#/%=~_|]""",
    re.IGNORECASE
)

# --- Issue Type ---

E_HIGH_ENTROPY_STRING = IssueType("70090355-d433-443d-ab92-121a7ffe8125", "Found potential secret (Type: {type}, Entropy: {entropy:.3f}) in '{filename}'.")

E_ENTROPY_CHECK_READ_ERROR = IssueType(
    "367b0401-9f24-478b-a509-3de67d9efab4",
    "Could not read '{filename}' during entropy check: {error}.",
)

# --- FileCheck Implementation ---

class HighEntropyStringCheck(FileCheck):
    """
    Scans text files for high entropy strings (potential secrets) like Base64 or Hex,
    while attempting to ignore strings that are part of URLs.
    """
    def __init__(self,
                 min_length: int = DEFAULT_MIN_SECRET_LENGTH,
                 b64_entropy_threshold: float = DEFAULT_B64_ENTROPY_THRESHOLD,
                 hex_entropy_threshold: float = DEFAULT_HEX_ENTROPY_THRESHOLD,
                 url_regex: re.Pattern = DEFAULT_URL_REGEX,
                 base64_chars: str = BASE64_CHARS,
                 hex_chars: str = HEX_CHARS
                ):
        """
        Initializes the check with configurable parameters.

        Args:
            min_length: Minimum length for a string to be considered.
            b64_entropy_threshold: Minimum Shannon entropy for Base64 strings.
            hex_entropy_threshold: Minimum Shannon entropy for Hex strings.
            url_regex: Compiled regex pattern to identify URLs to ignore.
            base64_chars: Character set for Base64 entropy calculation.
            hex_chars: Character set for Hex entropy calculation.
        """
        if min_length <= 0:
            raise ValueError("min_length must be positive")

        self.min_length = min_length
        self.b64_threshold = b64_entropy_threshold
        self.hex_threshold = hex_entropy_threshold
        self.url_regex = url_regex
        self.base64_chars = base64_chars
        self.hex_chars = hex_chars

        # Compile regex for Base64 and Hex strings based on min_length and char sets
        # Use re.escape to handle special characters like '+' and '/' in BASE64_CHARS
        self.b64_regex = re.compile(f"[{re.escape(self.base64_chars)}]{{{self.min_length},}}")
        self.hex_regex = re.compile(f"[{self.hex_chars}]{{{self.min_length},}}")

    def _shannon_entropy(self, data: str, iterator: str) -> float:
        """
        Calculates the Shannon entropy for a given string based on allowed characters.
        """
        if not data:
            return 0.0
        entropy: float = 0.0
        data_len = float(len(data)) # Use float for division

        char_counts = {}
        for char in data:
             char_counts[char] = char_counts.get(char, 0) + 1

        # Use only characters from the specified iterator set found in the data
        for char in iterator:
            count = char_counts.get(char, 0)
            if count > 0:
                p_x = float(count) / data_len
                entropy -= p_x * math.log(p_x, 2) # log base 2 for Shannon entropy
        return entropy

    def _check_overlap(self, secret_start: int, secret_end: int, url_spans: List[Tuple[int, int]]) -> bool:
        """Checks if the secret span overlaps with any of the URL spans."""
        for url_start, url_end in url_spans:
            # Check for any overlap:
            # Max of starts < Min of ends indicates overlap
            if max(secret_start, url_start) < min(secret_end, url_end):
                return True
        return False

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        """
        Performs the high-entropy string check on the given file.
        """
        issues = IssueList()

        # --- Pre-checks ---
        # 1. Skip non-files or symlinks (optional, could be handled by caller)
        if not path.is_file():
             return []
        # if path.is_symlink(): # Decide if you want to check symlinks
        #     return []

        # 2. Check if it's likely a text file (important for line-based processing)
        # Use framework's property check if available
        props = get_expected_file_properties(path) or ExpectedFileProperties()
        if not props.is_text:
             # Alternatively, implement a basic binary check here if needed
             # e.g., read first few KB, check for null bytes percentage
             return []

        # --- Main Processing ---
        line_number = 0
        try:
            with path.open('rt', encoding='utf-8', errors='strict') as f:
                for line in f:
                    line_number += 1
                    original_line = line.strip() # Keep for context if needed, but avoid putting in issue data by default

                    # 1. Find all URL spans in the current line
                    url_spans = [(m.start(), m.end()) for m in self.url_regex.finditer(line)]

                    # 2. Find potential Base64 strings
                    for match in self.b64_regex.finditer(line):
                        string = match.group(0)
                        start, end = match.span()

                        # 3. Check overlap with URLs
                        if self._check_overlap(start, end, url_spans):
                            continue # Skip if likely part of a URL

                        # 4. Calculate entropy
                        b64_entropy = self._shannon_entropy(string, self.base64_chars)

                        # 5. Check threshold and report
                        if b64_entropy > self.b64_threshold:
                            issues.append(E_HIGH_ENTROPY_STRING.make(
                                filename=path.name, # Just filename for brevity
                                type="Base64",
                                entropy=b64_entropy
                                # Avoid including 'secret=string' directly in data for security
                                # Consider adding line_preview=original_line[:100] if context needed
                            ).at(path, line=line_number))
                            # Don't check the same string multiple times if nested B64 patterns match
                            # Breaking here might miss overlapping valid secrets, careful
                            # break

                    # 6. Find potential Hex strings
                    for match in self.hex_regex.finditer(line):
                        string = match.group(0)
                        start, end = match.span()

                        # 7. Check overlap with URLs
                        if self._check_overlap(start, end, url_spans):
                            continue # Skip if likely part of a URL

                        # 8. Calculate entropy
                        hex_entropy = self._shannon_entropy(string, self.hex_chars)

                        # 9. Check threshold and report
                        if hex_entropy > self.hex_threshold:
                            issues.append(E_HIGH_ENTROPY_STRING.make(
                                filename=path.name,
                                type="Hex",
                                entropy=hex_entropy
                            ).at(path, line=line_number))
                            # break # Optional break

        except (IOError, OSError) as e:
             issues.append(E_ENTROPY_CHECK_READ_ERROR.make(filename=path.name, error=f"I/O error: {e}").at(path))
        except UnicodeDecodeError as e:
             issues.append(E_ENTROPY_CHECK_READ_ERROR.make(filename=path.name, error=f"UTF-8 decode error: {e}").at(path))
        except Exception as e: # Catch unexpected errors during file processing
             issues.append(E_ENTROPY_CHECK_READ_ERROR.make(filename=path.name, error=f"Unexpected error: {e}").at(path))

        return issues.issues


# --- Example Usage (Conceptual) ---
# checker = HighEntropyStringCheck(min_length=20, b64_entropy_threshold=4.5)
# file_to_check = Path("./path/to/some/file.txt")
# list_of_issues = checker.check(file_to_check)
# for issue in list_of_issues:
#      print(f"[{issue.issue_type.severity.value}] {issue.issue_type.message.format(**(issue.data or {}))} @ {issue.location.path}:{issue.location.lines}")
