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
from bisect import bisect_right
from re import Pattern

# Import necessary components from your base framework
# (Adjust the import path if necessary)
from dev.checks.base import (
    FileCheck,
    FileContext,
    IssueType,
)

# Assuming get_expected_file_properties exists and helps identify text files
# If not, we might need a simpler text file check.
from dev.file_properties import (
    CommentStyle,
    get_comment_style_for_file,
)

# ----------------------------
# Comment handling (core)
# ----------------------------


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent [start, end) spans."""
    if not spans:
        return []
    spans = sorted(spans)
    merged: list[tuple[int, int]] = []
    cs, ce = spans[0]
    for s, e in spans[1:]:
        if s <= ce:  # overlap or adjacent
            ce = max(ce, e)
        else:
            merged.append((cs, ce))
            cs, ce = s, e
    merged.append((cs, ce))
    return merged


def _compute_comment_spans(text: str, style: CommentStyle | None) -> list[tuple[int, int]]:
    """
    Quote-aware scan to compute comment spans for a given file based on CommentStyle.
    Produces [start, end) ranges in *absolute* indices over the file text.
    Handles:
      - line comments per style.line_markers (to EOL, including the newline)
      - block comments per style.block_markers (/* ... */, <!-- ... -->, etc.)
      - rudimentary string handling: ', ", Python ''' and \""" with backslash escaping
    """
    if not style:
        return []

    line_markers: tuple[str, ...] = tuple(sorted(style.line_markers, key=len, reverse=True))
    block_markers: tuple[tuple[str, str], ...] = tuple(
        sorted(style.block_markers, key=lambda p: len(p[0]), reverse=True)
    )

    spans: list[tuple[int, int]] = []
    n = len(text)
    i = 0

    in_single = False
    in_double = False
    in_triple_single = False
    in_triple_double = False

    in_block = False
    current_block_end = ""
    block_start_idx = -1

    def _in_any_quote() -> bool:
        return in_single or in_double or in_triple_single or in_triple_double

    while i < n:
        # Inside block comment: consume until its terminator.
        if in_block:
            if current_block_end and text.startswith(current_block_end, i):
                # Close block
                spans.append((block_start_idx, i + len(current_block_end)))
                i += len(current_block_end)
                in_block = False
                current_block_end = ""
                block_start_idx = -1
                continue
            i += 1
            continue

        # Handle triple quotes first (Python)
        if not _in_any_quote():
            if text.startswith("'''", i):
                in_triple_single = True
                i += 3
                continue
            if text.startswith('"""', i):
                in_triple_double = True
                i += 3
                continue
        elif in_triple_single:
            if text.startswith("'''", i):
                in_triple_single = False
                i += 3
                continue
            i += 1
            continue
        elif in_triple_double:
            if text.startswith('"""', i):
                in_triple_double = False
                i += 3
                continue
            i += 1
            continue

        # Simple quotes with backslash escapes
        ch = text[i]
        if ch == "'" and not in_double:
            if i == 0 or text[i - 1] != "\\":
                in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            if i == 0 or text[i - 1] != "\\":
                in_double = not in_double
            i += 1
            continue

        if _in_any_quote():
            i += 1
            continue

        # Try to open a block comment
        opened = False
        for start, end in block_markers:
            if text.startswith(start, i):
                in_block = True
                current_block_end = end
                block_start_idx = i
                i += len(start)
                opened = True
                break
        if opened:
            continue

        # Try to open a line comment (to end-of-line)
        for lm in line_markers:
            if text.startswith(lm, i):
                eol = text.find("\n", i)
                if eol == -1:
                    eol = n
                else:
                    eol = eol + 1  # include newline so subsequent line offsets are natural
                spans.append((i, eol))
                i = eol
                opened = True
                break
        if opened:
            continue

        i += 1

    return _merge_spans(spans)


def _position_in_spans_checker(spans: list[tuple[int, int]]):
    """
    Return a predicate pos -> bool that is O(log N) using bisect, assuming merged non-overlapping spans.
    """
    if not spans:
        return lambda _: False
    starts = [s for s, _ in spans]
    ends = [e for _, e in spans]

    def _inside(pos: int) -> bool:
        idx = bisect_right(starts, pos) - 1
        return idx >= 0 and pos < ends[idx]

    return _inside


# Broader URL regex: includes scheme-relative URLs (//example.com/...), and avoids trailing quotes/parens.
DEFAULT_URL_REGEX: Pattern[str] = re.compile(
    r"""
    \b(
        (?:https?|wss?|ftp|file|git|ssh)://
      | //[A-Za-z0-9][A-Za-z0-9.-]+\.[A-Za-z]{2,63}(?::\d+)?(?:/[^\s<>"')]+)?
      | www\.
      | ftp\.
    )[^\s<>"']*[^\s<>"'.,);]
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Regex for absolute paths
# - Windows drives: C:\ or C:/
# - Windows UNC: \\server\share   (intentionally NOT matching //server/share to avoid XPath/URL FPs)
# - Unix-like: selected roots (kept conservative), or home paths requiring a slash
DEFAULT_ABS_PATH_REGEX: Pattern[str] = re.compile(
    r"""
    (?:
        # Windows drive letter like C:\ or C:/
        \b[a-zA-Z]:[\\/][^\s"'<>()]+

      | # Windows UNC with backslashes only (avoid // to prevent URL/XPath FPs)
        \\\\                                   # leading backslashes
        (?![abfnrtv0'"xuU.])                   # NOT typical escape starts or '\.'
        (?!u[0-9A-Fa-f]{4}\b)                  # NOT a \uXXXX escape
        [A-Za-z0-9][A-Za-z0-9.-]{0,62}         # host: start alnum, then alnum, dot or hyphen
        [\\/]
        [A-Za-z0-9$][A-Za-z0-9._$-]{0,255}     # share: start alnum or $, then sane chars
        (?:[\\/][^\s"'<>()]+)?                 # optional tail

      | # Unix-like absolute paths from common roots
        \b/(?:usr|mnt|home|root|etc)(?:/[^\s"'<>()]+)*

      | # Home dir: ~ or ~user must be followed by a slash
        ~(?:[A-Za-z_][A-Za-z0-9_-]{0,31})?/[^\s"'<>()]+
    )
    """,
    re.VERBOSE,
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

    def __init__(
        self,
        abs_path_regex: Pattern[str] = DEFAULT_ABS_PATH_REGEX,
        url_regex: Pattern[str] = DEFAULT_URL_REGEX,
    ):
        self.abs_path_regex = abs_path_regex
        self.url_regex = url_regex

    def _is_part_of_url(self, path_match: re.Match, line: str) -> bool:
        """Treat the path as 'inside a URL' if its start sits inside any URL span,
        or immediately after (to tolerate a trailing quote/paren captured by the path regex).
        """
        ps, pe = path_match.start(), path_match.end()
        for um in self.url_regex.finditer(line):
            us, ue = um.start(), um.end()
            if (us <= ps <= ue) or (ps == ue and pe <= ue + 2 and line[ue:pe] in {"'", '"', ")", "]", ">", ";", ","}):
                # file:// is intentionally considered an absolute path issue
                if um.group(0).lower().startswith("file://"):
                    return False
                return True
        return False

    def check(self, ctx: FileContext):
        if not ctx.path.is_file():
            return
        if not ctx.expected_properties.is_text:
            return
        if ctx.path.suffix.lower() in {
            ".md",
            ".markdown",
            ".txt",
            ".rst",
            ".json",
            ".yaml",
            ".yml",
        }:
            return
        if ctx.path.name.lower() in {"dockerfile"}:
            return
        if ctx.path.suffix.lower() in {".ipynb"}:
            return

        text = ctx.read_text(E_HARDCODED_ABSOLUTE_PATH)
        comment_style = get_comment_style_for_file(ctx.path)
        comment_spans = _compute_comment_spans(text, comment_style)
        is_in_comment = _position_in_spans_checker(comment_spans)

        # Use keepends=True so we can compute absolute offsets correctly
        offset = 0
        for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
            for match in self.abs_path_regex.finditer(line):
                found_path = match.group(0)
                # Skip anything inside comments (per policy: paths allowed in comments)
                abs_start = offset + match.start()
                if is_in_comment(abs_start):
                    continue

                # Further filter: avoid very short paths like "/" unless it's clearly problematic
                if len(found_path) < 3 and found_path == "/":  # Example: avoid flagging single "/"
                    if not re.search(r"\s/\s", line):  # only flag "/" if it is standalone, not e.g. "foo / bar"
                        continue

                # Avoid flagging paths within URLs (e.g. example.com/some/path)
                if self._is_part_of_url(match, line):
                    continue

                # Avoid flagging if it is part of an XML namespace or similar constructs
                if "xmlns:" in line or " xlink:" in line or " DTD " in line:
                    if "/" in found_path and not found_path.startswith("/"):  # e.g. schema/foo
                        continue

                # Avoid flagging markdown link definitions like `[text](/abs/path)` if path is clearly a link target
                if re.search(rf"\[[^\]]+\]\({re.escape(found_path)}\)", line):
                    continue

                ctx.add_issue(E_HARDCODED_ABSOLUTE_PATH, path_found=found_path, line=line_number)

            offset += len(line)


E_HARDCODED_URL = IssueType("E_HARDCODED_URL", "Found hardcoded URL: '{url_found}'.")


class HardcodedUrlCheck(FileCheck):
    """
    Scans text files for hardcoded URLs.
    """

    def __init__(
        self,
        url_regex: Pattern[str] = DEFAULT_URL_REGEX,
        allowed_domains: set[str] | None = None,
    ):
        self.url_regex = url_regex
        self.allowed_domains = allowed_domains if allowed_domains else set()
        # Add common public/documentation domains that are usually fine to hardcode
        self.allowed_domains.update(
            {
                "www.w3.org",
                "xml.apache.org",
                "schemas.xmlsoap.org",
                "json-schema.org",
                "example.com",
                "example.org",
                "example.net",
                "localhost",
                "127.0.0.1",
            }
        )

    def _get_domain(self, url_string: str) -> str | None:
        try:
            # Simplified domain extraction
            protocol_end = url_string.find("://")
            if protocol_end == -1:
                if url_string.startswith("www."):
                    start = 4
                else:  # no protocol, no www. -> might be a relative path or not a full URL we care about here
                    return None  # or treat as non-standard URL
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
            return None  # Could not parse domain

    def check(self, ctx: FileContext):
        if not ctx.path.is_file():
            return
        if not ctx.expected_properties.is_text:
            return
        if ctx.path.suffix.lower() in {
            ".md",
            ".markdown",
            ".txt",
            ".rst",
            ".json",
            ".yaml",
            ".yml",
        }:
            return

        comment_style = get_comment_style_for_file(ctx.path)
        text = ctx.read_text(E_HARDCODED_URL)

        comment_spans = _compute_comment_spans(text, comment_style)
        is_in_comment = _position_in_spans_checker(comment_spans)

        offset = 0
        for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
            for match in self.url_regex.finditer(line):
                url_found = match.group(0)
                # Skip anything inside comments (per policy: URLs allowed in comments)
                abs_start = offset + match.start()
                if is_in_comment(abs_start):
                    continue

                # Skip if it's a 'file://' URL, as that's an absolute path issue
                if url_found.startswith("file://"):
                    continue

                domain = self._get_domain(url_found)
                if domain and domain in self.allowed_domains:
                    continue

                # Avoid flagging URLs that are part of typical documentation or link markdowns
                # if it's clearly a markdown link, it's often intentional.
                # e.g. [text](http://example.com) or <http://example.com>
                if re.search(rf"\[[^\]]+\]\({re.escape(url_found)}\)", line) or re.search(
                    rf"<({re.escape(url_found)})>", line
                ):
                    # Could add more context checks here, e.g., if line is purely a comment
                    # For now, if it's a markdown link, assume it's for documentation
                    pass  # Still report, but one might want to filter these based on severity or context

                ctx.add_issue(E_HARDCODED_URL, url_found=url_found, line=line_number)

            offset += len(line)


E_HARDCODED_INTERNAL_HOSTNAME_IP = IssueType(
    "E_HARDCODED_INTERNAL_HOSTNAME_IP",
    "Hardcoded internal hostname or IP address: '{host_or_ip}'.",
)


class HardcodedInternalHostnameIpCheck(FileCheck):
    """
    Scans text files for hardcoded internal hostnames and IP addresses.
    """

    def __init__(
        self,
        ip_regex: Pattern[str] = PRIVATE_IP_REGEX,
        hostname_regex: Pattern[str] = INTERNAL_HOSTNAME_REGEX,
        url_regex: Pattern[str] = DEFAULT_URL_REGEX,
        allowed_ips: set[str] | None = None,
        allowed_hostnames: set[str] | None = None,
    ):
        self.ip_regex = ip_regex
        self.hostname_regex = hostname_regex
        self.url_regex = url_regex  # To avoid flagging hostnames/IPs that are part of a public URL's path
        self.allowed_ips = allowed_ips if allowed_ips else {"127.0.0.1", "::1"}  # localhost is often fine
        self.allowed_hostnames = allowed_hostnames if allowed_hostnames else {"localhost"}

    def _is_part_of_url_path(self, found_item: str, line: str) -> bool:
        """Checks if the found item is part of a path in a non-internal URL"""
        for url_match in self.url_regex.finditer(line):
            url_string = url_match.group(0).lower()
            # If the URL itself starts with an internal scheme or typical internal markers, it's not a public URL path
            if any(
                marker in url_string
                for marker in [
                    "http://localhost",
                    "http://127.0.0.1",
                    ".internal",
                    ".local",
                    "file://",
                ]
            ):
                continue  # This URL itself might be an issue, but not for *this* check if item is inside it

            # Check if the found item is in the path part of a general URL
            # A bit simplistic: assumes `found_item` is not the domain itself
            schema_end = url_string.find("://")
            if schema_end != -1:
                domain_part_end = url_string.find("/", schema_end + 3)
                if domain_part_end != -1 and found_item in url_string[domain_part_end:]:
                    # Make sure 'found_item' is not the domain of the URL
                    if not url_string[schema_end + 3 :].startswith(found_item):
                        return True
        return False

    def check(self, ctx: FileContext):
        if not ctx.path.is_file():
            return
        if not ctx.expected_properties.is_text:
            return

        if ctx.path.suffix.lower() in {".md", ".markdown", ".txt"}:
            return

        text = ctx.read_text(E_HARDCODED_INTERNAL_HOSTNAME_IP)
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped_line = line.strip()
            if (
                stripped_line.startswith("#")
                or stripped_line.startswith("//")
                or stripped_line.startswith("--")
                or stripped_line.startswith(";")
                or stripped_line.startswith("/*")
                or stripped_line.startswith("*")
            ):
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

                ctx.add_issue(
                    E_HARDCODED_INTERNAL_HOSTNAME_IP,
                    host_or_ip=ip_found,
                    line=line_number,
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

                ctx.add_issue(
                    E_HARDCODED_INTERNAL_HOSTNAME_IP,
                    host_or_ip=hostname_found,
                    line=line_number,
                )
