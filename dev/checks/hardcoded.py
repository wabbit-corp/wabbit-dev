"""
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

from mu.exec import ExecutionContext

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
    E_GENERIC_READ_ERROR
)

# Assuming get_expected_file_properties exists and helps identify text files
# If not, we might need a simpler text file check.
from dev.file_properties import get_expected_file_properties, ExpectedFileProperties

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


E_HARDCODED_ABSOLUTE_PATH = IssueType("E_HARDCODED_ABSOLUTE_PATH", "Found hardcoded absolute path: '{path_found}'.")


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

    def check(self, ctx: FileContext):
        if not ctx.path.is_file(): return
        if not ctx.expected_properties.is_text: return
        if ctx.path.suffix.lower() in {".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml"}:
            return
        if ctx.path.name.lower() in {"dockerfile"}:
            return
        if ctx.path.suffix.lower() in {".ipynb"}:
            return

        text = ctx.read_text(E_HARDCODED_ABSOLUTE_PATH)

        for line_number, line in enumerate(text.splitlines(), start=1):
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

                ctx.add_issue(E_HARDCODED_ABSOLUTE_PATH, path_found=found_path, line=line_number)


E_HARDCODED_URL = IssueType("E_HARDCODED_URL", "Found hardcoded URL: '{url_found}'.")


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

    def check(self, ctx: FileContext):
        if not ctx.path.is_file(): return
        if not ctx.expected_properties.is_text: return
        if ctx.path.suffix.lower() in {".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml"}:
            return

        text = ctx.read_text(E_HARDCODED_URL)
        for line_number, line in enumerate(text.splitlines(), start=1):
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

                ctx.add_issue(E_HARDCODED_URL, url_found=url_found, line=line_number)


E_HARDCODED_CREDENTIAL = IssueType("E_HARDCODED_CREDENTIAL", "Found potential hardcoded credential near keyword '{keyword}'.")


class HardcodedCredentialCheck(FileCheck):
    """
    Scans text files for potential hardcoded credentials using keyword matching.
    This check is heuristic and may produce false positives or miss some credentials.
    """

    def __init__(self, credential_regex: Pattern[str] = DEFAULT_CREDENTIAL_KEYWORDS_REGEX):
        self.credential_regex = credential_regex
        # Keywords that, if found alongside credential keywords, might indicate a false positive (e.g., config option names)
        self.fp_indicators = {"example", "template", "default", "placeholder", "your_", "enter_", "_here", "config_"}


    def check(self, ctx: FileContext):
        if not ctx.is_file: return
        if not ctx.expected_properties.is_text: return

        text = ctx.read_text(E_HARDCODED_CREDENTIAL)
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped_line = line.strip().lower()

            # Skip common comment lines unless they look like active config
            if stripped_line.startswith("#") or stripped_line.startswith("//") or stripped_line.startswith("--") or stripped_line.startswith(";"):
                if not ("=" in stripped_line or ":" in stripped_line): # if no assignment, likely a real comment
                    continue

            # Basic check to avoid flagging the check's own definition or similar meta-code
            if "e_hardcoded_credential" in stripped_line or "default_credential_keywords_regex" in stripped_line:
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


                ctx.add_issue(E_HARDCODED_CREDENTIAL,
                    keyword=match.group(0).split(":")[0].split("=")[0].strip(),
                    line=line_number)


E_HARDCODED_INTERNAL_HOSTNAME_IP = IssueType("E_HARDCODED_INTERNAL_HOSTNAME_IP", "Hardcoded internal hostname or IP address: '{host_or_ip}'.")


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

    def check(self, ctx: FileContext):
        if not ctx.path.is_file(): return
        if not ctx.expected_properties.is_text: return

        if ctx.path.suffix.lower() in {".md", ".markdown", ".txt"}:
            return

        text = ctx.read_text(E_HARDCODED_INTERNAL_HOSTNAME_IP)
        for line_number, line in enumerate(text.splitlines(), start=1):
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

                ctx.add_issue(E_HARDCODED_INTERNAL_HOSTNAME_IP, host_or_ip=ip_found, line=line_number)

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

                ctx.add_issue(E_HARDCODED_INTERNAL_HOSTNAME_IP, host_or_ip=hostname_found, line=line_number)
