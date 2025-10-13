"""
* [x] Check for Hardcoded Secrets: Look for hardcoded secrets in scripts, configuration files,
      or source code. This includes API keys, passwords, and other sensitive information.
      Implemented by checking that there are no high-entropy strings that look like secrets.
* [x] Check for Hardcoded Absolute Paths: Look for hardcoded absolute file paths in scripts,
      configuration files, or source code (e.g., starting with C:\\, /home/, /Users/).
      These often break portability and should usually be replaced with relative paths,
      environment variables, or configuration lookups. /absolute/path/to/danger
* [x] Check for Hardcoded URLs: Look for hardcoded URLs in scripts, configuration files,
      or source code. This includes URLs to external services, APIs, and other resources.
* [x] Check for Hardcoded Credentials: Look for hardcoded credentials in scripts, configuration files,
      or source code. This includes usernames, passwords, and other sensitive information.
* [x] Check for Hardcoded Internal Hostnames/IPs: Scan configuration files, scripts, and
      documentation for hardcoded internal network details like specific server hostnames
      (e.g., internal-db.prod.local) or private IP address ranges that shouldn't be exposed
      or hardcoded.
"""

import re
import math
import os
from pathlib import Path
from typing import List, Set, Optional, Tuple, Pattern

# Import necessary components from your base framework
# (Adjust the import path if necessary)
from dev.checks.base import (
    FileCheck,
    Issue,
    IssueType,
    Severity,
    FileLocation,
    IntRangeSet,
    FileContext,
    IssueList,
)

# Assuming get_expected_file_properties exists and helps identify text files
# If not, we might need a simpler text file check.
from dev.file_properties import get_expected_file_properties, ExpectedFileProperties

# --- Constants ---

# Character sets for entropy calculation
BASE64_CHARS: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
HEX_CHARS: str = "1234567890abcdefABCDEF"
DEFAULT_NON_SECRET_SEQUENCES: Set[str] = {
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789",
    "1234567890abcdef",
    "1234567890ABCDEF",
    "4b825dc642cb6eb9a060e54bf8d69288fbee4904",  # Empty tree SHA (git)
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz",  # Base58
}

# Default configuration values (inspired by trufflehog defaults)
DEFAULT_MIN_SECRET_LENGTH = 20
DEFAULT_B64_ENTROPY_THRESHOLD = 4.5
DEFAULT_HEX_ENTROPY_THRESHOLD = 3.0
DISABLE_ENTROPY_CHECK_FRAGMENT = "<NO_ENTROPY_CHECK>"
ENABLE_ENTROPY_CHECK_FRAGMENT = "</NO_ENTROPY_CHECK>"

# Regex to find potential URLs. This is a common but not exhaustive pattern.
# It looks for common schemes or www. and captures characters typical in URLs.
DEFAULT_URL_REGEX: Pattern[str] = re.compile(
    r"""\b((?:https?|ftp|file|wss?|git|ssh)://|www\.|ftp\.)[-a-zA-Z0-9+&@#/%?=~_()|!:,.;]*[-a-zA-Z0-9+&@#/%=~_()|]""",
    re.IGNORECASE,
)

# Regex for absolute paths
# Unix-like: starts with / or ~
# Windows: C:\, C:/, \\server\share, //server/share
DEFAULT_ABS_PATH_REGEX: Pattern[str] = re.compile(
    r"""
    (?:
        (?:\b[a-zA-Z]:[\\/])| # Windows drive letter like C:\ or C:/
        (?:\\\\|//)[^\\/:\s]+[\\/][^\\/:\s]+| # UNC paths like \\server\share or //server/share
        (?:\b/(?:usr|mnt|home|root|etc)(?:/[^/\0\s]+)*[/]?)| # Unix-like absolute paths starting with /
        (?:~[/a-zA-Z0-9_.-]+) # Unix-like home directory paths like ~/documents
    )
    (?<![:\w]) # Negative lookbehind to avoid matching parts of URLs like http://
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Regex for common credential keywords
# Looks for keywords followed by assignment or quoted strings
# This is a basic heuristic and can have false positives/negatives
DEFAULT_CREDENTIAL_KEYWORDS_REGEX: Pattern[str] = re.compile(
    r"""
    (?i) # Case-insensitive
    (?:password|passwd|pwd|secret|token|api_key|apikey|access_key|private_key|client_secret|secret_key|bearer|auth) # Keywords
    \s*[:=]\s* # Assignment operators (colon or equals)
    ['"]? # Optional quote
    (?P<credential_value>[^'"\s]{8,}) # Credential value (at least 8 chars, not quotes or spaces)
    ['"]? # Optional closing quote
    """,
    re.VERBOSE,
)
# More specific patterns can be added, e.g. for AWS keys, etc.

# Regex for private IP addresses
PRIVATE_IP_REGEX: Pattern[str] = re.compile(
    r"""
    \b(?:
        10\.(?:[0-9]{1,3}\.){2}[0-9]{1,3}| # 10.0.0.0/8
        172\.(?:1[6-9]|2[0-9]|3[0-1])\.(?:[0-9]{1,3}\.){1}[0-9]{1,3}| # 172.16.0.0/12
        192\.168\.(?:[0-9]{1,3}\.){1}[0-9]{1,3}| # 192.168.0.0/16
        127\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}| # 127.0.0.0/8 (localhost)
        169\.254\.(?:[0-9]{1,3}\.){1}[0-9]{1,3}| # 169.254.0.0/16 (link-local)
        fc00::/7 | # IPv6 Unique Local Addresses
        fe80::/10   # IPv6 Link-Local Addresses
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Regex for common internal hostname patterns
INTERNAL_HOSTNAME_REGEX: Pattern[str] = re.compile(
    r"""
    \b(?:
        # [\w.-]+\.(?:internal|local|lan|corp|dev|test|stage|prod)(?:\.[\w-]+)*| # *.internal, *.local, etc.
        localhost| # localhost
        ip-[\d-]+ # AWS EC2 private hostnames like ip-10-0-1-23
    )\b
    (?!(?:\.[a-zA-Z]{2,63})) # Negative lookahead to avoid matching FQDNs like server.local.com if .local is part of domain
    """,
    re.VERBOSE | re.IGNORECASE,
)

# --- Issue Type ---

E_HIGH_ENTROPY_STRING = IssueType(
    "70090355-d433-443d-ab92-121a7ffe8125",
    "Found potential secret (Type: {type}, Entropy: {entropy:.3f}) in '{filename}'.",
)

E_ENTROPY_CHECK_READ_ERROR = IssueType(
    "367b0401-9f24-478b-a509-3de67d9efab4",
    "Could not read '{filename}' during entropy check: {error}.",
)

E_HARDCODED_ABSOLUTE_PATH = IssueType(
    "a1b0c2d3-e4f5-4a5b-8c9d-0e1f2a3b4c5d",
    "Found hardcoded absolute path: '{path_found}' in '{filename}'."
)

E_HARDCODED_URL = IssueType(
    "b1c2d3e4-f5a6-4b5c-9d0e-1f2a3b4c5d6e",
    "Found hardcoded URL: '{url_found}' in '{filename}'. Consider making it configurable."
)

E_HARDCODED_CREDENTIAL = IssueType(
    "c2d3e4f5-a6b7-4c5d-9e0f-1a2b3c4d5e6f",
    "Found potential hardcoded credential near keyword '{keyword}' in '{filename}'."
)

E_HARDCODED_INTERNAL_HOSTNAME_IP = IssueType(
    "d3e4f5a6-b7c8-4d5e-9f0a-1b2c3d4e5f6a",
    "Found hardcoded internal hostname or IP address: '{host_or_ip}' in '{filename}'."
)

E_GENERIC_READ_ERROR = IssueType(
    "e4f5a6b7-c8d9-4e5f-a0b1-2c3d4e5f6a7b",
    "Could not read '{filename}' during check: {error}."
)

# --- FileCheck Implementation ---


class HighEntropyStringCheck(FileCheck):
    """
    Scans text files for high entropy strings (potential secrets) like Base64 or Hex,
    while attempting to ignore strings that are part of URLs.
    """

    def __init__(
        self,
        min_length: int = DEFAULT_MIN_SECRET_LENGTH,
        b64_entropy_threshold: float = DEFAULT_B64_ENTROPY_THRESHOLD,
        hex_entropy_threshold: float = DEFAULT_HEX_ENTROPY_THRESHOLD,
        url_regex: re.Pattern = DEFAULT_URL_REGEX,
        base64_chars: str = BASE64_CHARS,
        hex_chars: str = HEX_CHARS,
        non_secret_sequences: Set[str] = DEFAULT_NON_SECRET_SEQUENCES,
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
        self.non_secret_sequences = non_secret_sequences

        # Compile regex for Base64 and Hex strings based on min_length and char sets
        # Use re.escape to handle special characters like '+' and '/' in BASE64_CHARS
        self.b64_regex = re.compile(
            f"[{re.escape(self.base64_chars)}]{{{self.min_length},}}"
        )
        self.hex_regex = re.compile(f"[{self.hex_chars}]{{{self.min_length},}}")

    def _shannon_entropy(self, data: str, iterator: str) -> float:
        """
        Calculates the Shannon entropy for a given string based on allowed characters.
        """
        if not data:
            return 0.0
        entropy: float = 0.0
        data_len = float(len(data))  # Use float for division

        char_counts = {}
        for char in data:
            char_counts[char] = char_counts.get(char, 0) + 1

        # Use only characters from the specified iterator set found in the data
        for char in iterator:
            count = char_counts.get(char, 0)
            if count > 0:
                p_x = float(count) / data_len
                entropy -= p_x * math.log(p_x, 2)  # log base 2 for Shannon entropy
        return entropy

    def _check_overlap(
        self, secret_start: int, secret_end: int, url_spans: List[Tuple[int, int]]
    ) -> bool:
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
            with path.open("rt", encoding="utf-8", errors="strict") as f:
                is_enabled = True
                for line in f:
                    line_number += 1
                    original_line = (
                        line.strip()
                    )  # Keep for context if needed, but avoid putting in issue data by default

                    if not is_enabled:
                        # Skip lines if entropy check is disabled
                        continue

                    if DISABLE_ENTROPY_CHECK_FRAGMENT in line:
                        is_enabled = False
                    elif ENABLE_ENTROPY_CHECK_FRAGMENT in line:
                        is_enabled = True

                    # 1. Find all URL spans in the current line
                    url_spans = [
                        (m.start(), m.end()) for m in self.url_regex.finditer(line)
                    ]

                    # 2. Find potential Base64 strings
                    for match in self.b64_regex.finditer(line):
                        string = match.group(0)
                        start, end = match.span()

                        # 3. Check overlap with URLs
                        if self._check_overlap(start, end, url_spans):
                            continue  # Skip if likely part of a URL

                        for non_secret in self.non_secret_sequences:
                            if non_secret in string:
                                # Remove non-secret sequences from the string
                                string = string.replace(non_secret, "")

                        # 4. Calculate entropy
                        b64_entropy = self._shannon_entropy(string, self.base64_chars)

                        # 5. Check threshold and report
                        if b64_entropy > self.b64_threshold:
                            issues.append(
                                E_HIGH_ENTROPY_STRING.make(
                                    filename=path.name,  # Just filename for brevity
                                    type="Base64",
                                    entropy=b64_entropy,
                                    # Avoid including 'secret=string' directly in data for security
                                    # Consider adding line_preview=original_line[:100] if context needed
                                ).at(path, line=line_number)
                            )
                            # Don't check the same string multiple times if nested B64 patterns match
                            # Breaking here might miss overlapping valid secrets, careful
                            # break

                    # 6. Find potential Hex strings
                    for match in self.hex_regex.finditer(line):
                        string = match.group(0)
                        start, end = match.span()

                        # 7. Check overlap with URLs
                        if self._check_overlap(start, end, url_spans):
                            continue  # Skip if likely part of a URL

                        for non_secret in self.non_secret_sequences:
                            if non_secret in string:
                                # Remove non-secret sequences from the string
                                string = string.replace(non_secret, "")

                        # 8. Calculate entropy
                        hex_entropy = self._shannon_entropy(string, self.hex_chars)

                        # 9. Check threshold and report
                        if hex_entropy > self.hex_threshold:
                            issues.append(
                                E_HIGH_ENTROPY_STRING.make(
                                    filename=path.name, type="Hex", entropy=hex_entropy
                                ).at(path, line=line_number)
                            )
                            # break # Optional break

        except (IOError, OSError) as e:
            issues.append(
                E_ENTROPY_CHECK_READ_ERROR.make(
                    filename=path.name, error=f"I/O error: {e}"
                ).at(path)
            )
        except UnicodeDecodeError as e:
            issues.append(
                E_ENTROPY_CHECK_READ_ERROR.make(
                    filename=path.name, error=f"UTF-8 decode error: {e}"
                ).at(path)
            )
        except Exception as e:  # Catch unexpected errors during file processing
            issues.append(
                E_ENTROPY_CHECK_READ_ERROR.make(
                    filename=path.name, error=f"Unexpected error: {e}"
                ).at(path)
            )

        return issues.issues


# --- Example Usage (Conceptual) ---
# checker = HighEntropyStringCheck(min_length=20, b64_entropy_threshold=4.5)
# file_to_check = Path("./path/to/some/file.txt")
# list_of_issues = checker.check(file_to_check)
# for issue in list_of_issues:
#      print(f"[{issue.issue_type.severity.value}] {issue.issue_type.message.format(**(issue.data or {}))} @ {issue.location.path}:{issue.location.lines}")

class HardcodedAbsolutePathCheck(FileCheck):
    """
    Scans text files for hardcoded absolute paths.
    """

    def __init__(self, abs_path_regex: Pattern[str] = DEFAULT_ABS_PATH_REGEX, url_regex: Pattern[str] = DEFAULT_URL_REGEX):
        self.abs_path_regex = abs_path_regex
        self.url_regex = url_regex

    def _is_part_of_url(self, path_match: re.Match, line: str) -> bool:
        """Checks if the found path is likely part of a URL."""
        for url_match in self.url_regex.finditer(line):
            if url_match.start() <= path_match.start() and url_match.end() >= path_match.end():
                # Check if the scheme is 'file://' specifically for paths
                if path_match.group(0).startswith('/') and "file://" in url_match.group(0)[:path_match.start() + 7]: # crude check
                    return False # It's a file URI, so it IS an absolute path issue.
                return True
        return False

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        issues = IssueList()
        if not path.is_file():
            return []
        props = get_expected_file_properties(path) or ExpectedFileProperties()
        if not props.is_text:
            return []

        line_number = 0
        try:
            with path.open("rt", encoding="utf-8", errors="strict") as f:
                for line in f:
                    line_number += 1
                    # Skip comment lines for common comment types to reduce FPs
                    stripped_line = line.strip()
                    if stripped_line.startswith("#") or stripped_line.startswith("//") or stripped_line.startswith("--") or stripped_line.startswith(";") or stripped_line.startswith("/*") or stripped_line.startswith("*"):
                        if not ("file://" in stripped_line and self.abs_path_regex.search(stripped_line)): # allow file:// in comments for now
                             continue


                    for match in self.abs_path_regex.finditer(line):
                        found_path = match.group(0)
                        # Further filter: avoid very short paths like "/" unless it's clearly problematic
                        if len(found_path) < 3 and found_path == "/": # Example: avoid flagging single "/"
                            if not re.search(r"\s/\s", line): # only flag "/" if it is standalone, not e.g. "foo / bar"
                                continue

                        # Avoid flagging paths within URLs (e.g. example.com/some/path)
                        if self._is_part_of_url(match, line):
                            continue

                        # Avoid flagging if it is part of an XML namespace or similar constructs
                        if "xmlns:" in line or " xlink:" in line or " DTD " in line:
                            if "/" in found_path and not found_path.startswith("/"): # e.g. schema/foo
                                continue

                        # Avoid flagging markdown link definitions like `[text](/abs/path)` if path is clearly a link target
                        if re.search(rf"\[[^\]]+\]\({re.escape(found_path)}\)", line):
                            continue


                        issues.append(
                            E_HARDCODED_ABSOLUTE_PATH.make(
                                filename=path.name, path_found=found_path
                            ).at(path, line=line_number) # , col=match.start() + 1
                        )
        except (IOError, OSError) as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"I/O error: {e}"
                ).at(path)
            )
        except UnicodeDecodeError as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"UTF-8 decode error: {e}"
                ).at(path)
            )
        except Exception as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"Unexpected error: {e}"
                ).at(path)
            )
        return issues.issues


class HardcodedUrlCheck(FileCheck):
    """
    Scans text files for hardcoded URLs.
    """

    def __init__(self, url_regex: Pattern[str] = DEFAULT_URL_REGEX, allowed_domains: Optional[Set[str]] = None):
        self.url_regex = url_regex
        self.allowed_domains = allowed_domains if allowed_domains else set()
        # Add common public/documentation domains that are usually fine to hardcode
        self.allowed_domains.update({
            "www.w3.org", "xml.apache.org", "schemas.xmlsoap.org", "json-schema.org",
            "example.com", "example.org", "example.net", "localhost", "127.0.0.1"
        })


    def _get_domain(self, url_string: str) -> Optional[str]:
        try:
            # Simplified domain extraction
            protocol_end = url_string.find("://")
            if protocol_end == -1:
                if url_string.startswith("www."):
                    start = 4
                else: # no protocol, no www. -> might be a relative path or not a full URL we care about here
                    return None # or treat as non-standard URL
            else:
                start = protocol_end + 3

            path_start = url_string.find("/", start)
            if path_start == -1:
                domain_port = url_string[start:]
            else:
                domain_port = url_string[start:path_start]

            # Remove port if present
            port_start = domain_port.find(":")
            if port_start != -1:
                return domain_port[:port_start].lower()
            return domain_port.lower()
        except Exception:
            return None # Could not parse domain

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        issues = IssueList()
        if not path.is_file():
            return []
        props = get_expected_file_properties(path) or ExpectedFileProperties()
        if not props.is_text:
            return []

        line_number = 0
        try:
            with path.open("rt", encoding="utf-8", errors="strict") as f:
                for line in f:
                    line_number += 1
                    # Skip comment lines for common comment types if desired for less noise
                    stripped_line = line.strip()
                    if stripped_line.startswith("#") or stripped_line.startswith("//") or stripped_line.startswith("--") or stripped_line.startswith(";") or stripped_line.startswith("/*") or stripped_line.startswith("*"):
                         # However, URLs in comments can still be sensitive or point to internal resources.
                         # For now, let's check them but one might add a config to skip comments.
                         pass


                    for match in self.url_regex.finditer(line):
                        url_found = match.group(0)

                        # Skip if it's a 'file://' URL, as that's an absolute path issue
                        if url_found.startswith("file://"):
                            continue

                        domain = self._get_domain(url_found)
                        if domain and domain in self.allowed_domains:
                            continue

                        # Avoid flagging URLs that are part of typical documentation or link markdowns
                        # if it's clearly a markdown link, it's often intentional.
                        # e.g. [text](http://example.com) or <http://example.com>
                        if re.search(rf"\[[^\]]+\]\({re.escape(url_found)}\)", line) or \
                           re.search(rf"<({re.escape(url_found)})>", line):
                           # Could add more context checks here, e.g., if line is purely a comment
                           # For now, if it's a markdown link, assume it's for documentation
                           pass # Still report, but one might want to filter these based on severity or context


                        issues.append(
                            E_HARDCODED_URL.make(
                                filename=path.name, url_found=url_found
                            ).at(path, line=line_number) #, col=match.start() + 1
                        )
        except (IOError, OSError) as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"I/O error: {e}"
                ).at(path)
            )
        except UnicodeDecodeError as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"UTF-8 decode error: {e}"
                ).at(path)
            )
        except Exception as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"Unexpected error: {e}"
                ).at(path)
            )
        return issues.issues


class HardcodedCredentialCheck(FileCheck):
    """
    Scans text files for potential hardcoded credentials using keyword matching.
    This check is heuristic and may produce false positives or miss some credentials.
    """

    def __init__(self, credential_regex: Pattern[str] = DEFAULT_CREDENTIAL_KEYWORDS_REGEX):
        self.credential_regex = credential_regex
        # Keywords that, if found alongside credential keywords, might indicate a false positive (e.g., config option names)
        self.fp_indicators = {"example", "template", "default", "placeholder", "your_", "enter_", "_here", "config_"}


    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        issues = IssueList()
        if not path.is_file():
            return []
        props = get_expected_file_properties(path) or ExpectedFileProperties()
        if not props.is_text:
            return []

        line_number = 0
        try:
            with path.open("rt", encoding="utf-8", errors="strict") as f:
                for line in f:
                    line_number += 1
                    stripped_line = line.strip().lower()

                    # Skip common comment lines unless they look like active config
                    if stripped_line.startswith("#") or stripped_line.startswith("//") or stripped_line.startswith("--") or stripped_line.startswith(";"):
                        if not ("=" in stripped_line or ":" in stripped_line): # if no assignment, likely a real comment
                            continue

                    # Basic check to avoid flagging the check's own definition or similar meta-code
                    if "e_hardcoded_credential" in stripped_line or "default_credential_keywords_regex" in stripped_line:
                        continue
                    if DISABLE_ENTROPY_CHECK_FRAGMENT.lower() in stripped_line or ENABLE_ENTROPY_CHECK_FRAGMENT.lower() in stripped_line:
                        continue


                    for match in self.credential_regex.finditer(line):
                        keyword_match = match.group(0) # The whole match including keyword and value

                        # Attempt to reduce false positives
                        value_part = match.group("credential_value")
                        if value_part:
                            lower_value = value_part.lower()
                            if any(fp_ind in lower_value for fp_ind in self.fp_indicators) or \
                               any(fp_ind in line[:match.start()].lower() for fp_ind in self.fp_indicators): # check context before match too
                                continue
                            if lower_value in {"true", "false", "yes", "no", "null", "none", "''", '""'}: # common non-secret values
                                continue
                            if "password" in lower_value and "example" in line.lower(): # if "example password"
                                continue

                        # Heuristic: if the line contains variable placeholders like ${...} or <...>
                        if re.search(r"(\$\{.*?\})|(<.*?>)", line):
                            continue


                        issues.append(
                            E_HARDCODED_CREDENTIAL.make(
                                filename=path.name,
                                keyword=match.group(0).split(":")[0].split("=")[0].strip() # Extract keyword part
                            ).at(path, line=line_number) # , col=match.start() + 1
                        )
        except (IOError, OSError) as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"I/O error: {e}"
                ).at(path)
            )
        except UnicodeDecodeError as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"UTF-8 decode error: {e}"
                ).at(path)
            )
        except Exception as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"Unexpected error: {e}"
                ).at(path)
            )
        return issues.issues


class HardcodedInternalHostnameIpCheck(FileCheck):
    """
    Scans text files for hardcoded internal hostnames and IP addresses.
    """

    def __init__(
        self,
        ip_regex: Pattern[str] = PRIVATE_IP_REGEX,
        hostname_regex: Pattern[str] = INTERNAL_HOSTNAME_REGEX,
        url_regex: Pattern[str] = DEFAULT_URL_REGEX,
        allowed_ips: Optional[Set[str]] = None,
        allowed_hostnames: Optional[Set[str]] = None,
    ):
        self.ip_regex = ip_regex
        self.hostname_regex = hostname_regex
        self.url_regex = url_regex # To avoid flagging hostnames/IPs that are part of a public URL's path
        self.allowed_ips = allowed_ips if allowed_ips else {"127.0.0.1", "::1"} # localhost is often fine
        self.allowed_hostnames = allowed_hostnames if allowed_hostnames else {"localhost"}


    def _is_part_of_url_path(self, found_item: str, line: str) -> bool:
        """Checks if the found item is part of a path in a non-internal URL"""
        for url_match in self.url_regex.finditer(line):
            url_string = url_match.group(0).lower()
            # If the URL itself starts with an internal scheme or typical internal markers, it's not a public URL path
            if any(marker in url_string for marker in ["http://localhost", "http://127.0.0.1", ".internal", ".local", "file://"]):
                continue # This URL itself might be an issue, but not for *this* check if item is inside it

            # Check if the found item is in the path part of a general URL
            # A bit simplistic: assumes `found_item` is not the domain itself
            schema_end = url_string.find("://")
            if schema_end != -1:
                domain_part_end = url_string.find("/", schema_end + 3)
                if domain_part_end != -1 and found_item in url_string[domain_part_end:]:
                    # Make sure 'found_item' is not the domain of the URL
                    if not url_string[schema_end+3:].startswith(found_item):
                        return True
        return False

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List[Issue]:
        issues = IssueList()
        if not path.is_file():
            return []
        props = get_expected_file_properties(path) or ExpectedFileProperties()
        if not props.is_text:
            return []

        line_number = 0
        try:
            with path.open("rt", encoding="utf-8", errors="strict") as f:
                for line in f:
                    line_number += 1
                    stripped_line = line.strip()
                    if stripped_line.startswith("#") or stripped_line.startswith("//") or stripped_line.startswith("--") or stripped_line.startswith(";") or stripped_line.startswith("/*") or stripped_line.startswith("*"):
                         # IPs/hostnames in comments can still be sensitive.
                         pass

                    # Check for IPs
                    for match in self.ip_regex.finditer(line):
                        ip_found = match.group(0)
                        if ip_found in self.allowed_ips:
                            continue
                        if self._is_part_of_url_path(ip_found, line):
                            continue

                        # Avoid flagging IPs in common documentation/example patterns
                        if "example" in line.lower() and ("ip address" in line.lower() or "e.g." in line.lower()):
                            continue

                        issues.append(
                            E_HARDCODED_INTERNAL_HOSTNAME_IP.make(
                                filename=path.name, host_or_ip=ip_found
                            ).at(path, line=line_number) # , col=match.start() + 1
                        )

                    # Check for Hostnames
                    for match in self.hostname_regex.finditer(line):
                        hostname_found = match.group(0)
                        if hostname_found.lower() in self.allowed_hostnames:
                            continue
                        if self._is_part_of_url_path(hostname_found, line):
                            continue

                         # Avoid flagging hostnames in common documentation/example patterns
                        if "example" in line.lower() and ("hostname" in line.lower() or "e.g." in line.lower()):
                            continue
                        # Avoid flagging if it's part of an email address
                        if "@" + hostname_found in line:
                            continue


                        issues.append(
                            E_HARDCODED_INTERNAL_HOSTNAME_IP.make(
                                filename=path.name, host_or_ip=hostname_found
                            ).at(path, line=line_number) # , col=match.start() + 1
                        )
        except (IOError, OSError) as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"I/O error: {e}"
                ).at(path)
            )
        except UnicodeDecodeError as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"UTF-8 decode error: {e}"
                ).at(path)
            )
        except Exception as e:
            issues.append(
                E_GENERIC_READ_ERROR.make(
                    filename=path.name, error=f"Unexpected error: {e}"
                ).at(path)
            )
        return issues.issues
