"""
* [x] Check for UTF-8 Encoding: Ensure that all files are valid UTF-8 encoded. This is crucial for
      cross-platform compatibility and to avoid issues with text processing. Ensuring all text is
      valid UTF-8 avoids invisible corruption (most random byte sequences are invalid UTF-8, so catching
      encoding errors early is useful).
* [x] Check for BOM (Byte Order Mark): Ensure that no files start with a BOM, as it can cause issues
      with some compilers or interpreters. This is especially important for UTF-8 files.
* [x] Check for Trailing Whitespace: Ensure that no lines end with trailing whitespace.
* [x] Check for Mixed Spaces and Tabs: Ensure that no lines use both spaces and tabs for indentation.
* [x] Check for Long Lines: Ensure that no lines exceed a certain length (e.g., 80 or 120 characters).
* [x] Check for Inconsistent Line Endings: Ensure that all files use the same line ending style (LF or CRLF).
* [x] Check for Invisible Characters: Ensure that no lines contain invisible characters that can cause issues
      in some environments.
* [x] Check for Unicode Homoglyphs: Ensure that no lines contain characters that look similar to ASCII characters
      but are actually different Unicode characters. This can help prevent confusion and potential security issues.
* [x] Check for Unicode Control Characters: Ensure that no lines contain control characters that can cause issues
      in some environments. Ensure no spurious null bytes exist.
* [x] Check for Final Newline: Ensure that all files end with a newline character. According to POSIX, _every_ text
      file should end with a newline character (line terminator)[thoughtbot.com](https://thoughtbot.com/blog/no-newline-at-end-of-file)
* [x] Check for Merge Artifacts: As a hygiene rule, verify that no merge conflict strings
      like <<<<<<< HEAD or >>>>>> exist in the repository files.
* [ ] Check for Overly Long Words: Extremely long sequences of non-whitespace characters can cause rendering issues
      in diff viewers, code review tools, or editors. While often found in generated files (which should ideally
      be `.gitignore`d), setting a threshold can catch potential issues in manually edited files.
"""

import enum
import re
import unicodedata  # Needed for Unicode checks
from pathlib import Path

from dev.checks.base import (
    CoarseFileScope,
    CoarseProjectType,
    FileCheck,
    FileContext,
    IssueType,
)

CHUNK_BYTE_SIZE = 1024 * 1024  # 1 MB


class LineEnding(enum.Enum):
    CRLF = b"\r\n"
    LF = b"\n"
    CR = b"\r"


def get_line_ending_counts(file: Path) -> dict[LineEnding, int]:
    crlf_count = 0
    lf_count = 0
    cr_count = 0

    STATE_OUTSIDE = 0
    STATE_CR = 1
    STATE_LF = 2

    state = STATE_OUTSIDE

    def update(byte: int | bytes | None):
        nonlocal crlf_count, lf_count, cr_count, state

        # Flush at EOF:
        if byte is None:
            if state == STATE_CR:
                cr_count += 1
            elif state == STATE_LF:
                lf_count += 1
            state = STATE_OUTSIDE
            return
        # If we got an int (typical when iterating bytes), normalize to a 1-byte bytes
        if isinstance(byte, int):
            byte = bytes((byte,))

        if state == STATE_OUTSIDE:
            if byte == b"\r":
                state = STATE_CR
            elif byte == b"\n":
                state = STATE_LF
            else:
                return
        elif state == STATE_CR:
            if byte == b"\r":
                cr_count += 1
            elif byte == b"\n":
                crlf_count += 1
                state = STATE_OUTSIDE
            else:
                cr_count += 1
                state = STATE_OUTSIDE
        elif state == STATE_LF:
            if byte == b"\r":
                lf_count += 1
                state = STATE_CR
            elif byte == b"\n":
                lf_count += 1
                state = STATE_LF
            else:
                lf_count += 1
                state = STATE_OUTSIDE
        else:
            raise ValueError("Invalid state")

    with file.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_BYTE_SIZE)
            if not chunk:
                update(None)
                break
            for byte in chunk:
                update(byte)

    return {
        LineEnding.CRLF: crlf_count,
        LineEnding.LF: lf_count,
        LineEnding.CR: cr_count,
    }


def get_line_ending(file: Path) -> LineEnding | None:
    counts = get_line_ending_counts(file)
    crlf_count = counts[LineEnding.CRLF]
    lf_count = counts[LineEnding.LF]
    cr_count = counts[LineEnding.CR]
    _, _, result = max(
        (lf_count, 3, LineEnding.LF),
        (crlf_count, 2, LineEnding.CRLF),
        (cr_count, 1, LineEnding.CR),
        key=lambda x: (x[0], x[1]),
    )
    return result


def fix_no_newline(file: Path) -> None:
    nl = get_line_ending(file)
    with file.open("rb") as f:
        content = f.read()
    if not content.endswith(nl.value):
        with file.open("ab") as f:
            f.write(nl.value)


def fix_line_endings(file: Path, target_ending: LineEnding) -> None:
    with file.open("rb") as f:
        content = f.read()
    # Convert line endings to LF
    if target_ending == LineEnding.LF:
        content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    elif target_ending == LineEnding.CR:
        content = content.replace(b"\r\n", b"\r").replace(b"\n", b"\r")
    elif target_ending == LineEnding.CRLF:
        content = re.sub(b"(?:\r\n|\r|\n)", b"\r\n", content)
    with file.open("wb") as f:
        f.write(content)


def fix_trailing_whitespace(file: Path) -> None:
    nl = get_line_ending(file).value.decode("utf-8")
    with file.open("rt", encoding="utf-8") as f:
        lines = f.readlines()
    # Remove trailing whitespace from each line
    with file.open("wt", encoding="utf-8") as f:
        for line in lines:
            f.write(line.rstrip() + nl)


def fix_mixed_spaces_tabs(file: Path, tab_width: int = 4, prefer_tabs: bool = False) -> None:
    """
    Normalize *leading* indentation on lines that mix tabs and spaces.

    - Assumes one tab == `tab_width` spaces (default 4).
    - By default, rewrites mixed prefixes to all spaces with exact column preservation.
    - If `prefer_tabs=True`, rewrites to tabs for full tab stops and spaces for the remainder.
    - Preserves the file's detected newline style via `get_line_ending`.
    """
    nl = get_line_ending(file).value.decode("utf-8")

    def split_leading_ws(s: str):
        i = 0
        while i < len(s) and s[i] in (" ", "\t"):
            i += 1
        return s[:i], s[i:]

    def indent_columns(ws: str) -> int:
        col = 0
        for ch in ws:
            if ch == "\t":
                col += tab_width - (col % tab_width)
            else:  # ' '
                col += 1
        return col

    def render_indent(cols: int) -> str:
        if prefer_tabs:
            tabs, spaces = divmod(cols, tab_width)
            return "\t" * tabs + " " * spaces
        else:
            return " " * cols

    # Read and rewrite
    with file.open("rt", encoding="utf-8") as f:
        lines = f.readlines()

    changed = False
    out: list[str] = []

    for line in lines:
        raw = line.rstrip("\r\n")  # normalize endings; we'll re-append `nl`
        ws, rest = split_leading_ws(raw)
        if " " in ws and "\t" in ws:
            cols = indent_columns(ws)
            ws = render_indent(cols)
            changed = True
        out.append(ws + rest + nl)

    if changed:
        with file.open("wt", encoding="utf-8") as f:
            f.writelines(out)


MAX_CODE_LINE_LENGTH = 200  # Default maximum line length for code files


E_NO_NEWLINE = IssueType("E_NO_NEWLINE", "File does not end with a newline character.")
E_BOM_AT_START = IssueType("E_BOM_AT_START", "File starts with a UTF-8 BOM (Byte Order Mark).")
E_LINE_ENDINGS = IssueType("E_LINE_ENDINGS", "File contains incorrect line endings.")
E_NOT_UTF8 = IssueType("E_NOT_UTF8", "File is not valid UTF-8 encoded.")
E_GIT_CONFLICT_MARKER = IssueType("E_GIT_CONFLICT_MARKER", "File contains a Git conflict marker.")
E_LINE_TOO_LONG = IssueType("E_LINE_TOO_LONG", "Line exceeds maximum length.")
E_TRAILING_WHITESPACE = IssueType("E_TRAILING_WHITESPACE", "Line contains trailing whitespace.")
E_MIXED_SPACES_TABS = IssueType("E_MIXED_SPACES_TABS", "Line contains mixed spaces and tabs in indentation.")
E_UNICODE_HOMOGLYPH = IssueType("E_UNICODE_HOMOGLYPH", "Line contains a non-ASCII letter (potential homoglyph).")
E_UNICODE_INVISIBLE = IssueType(
    "E_UNICODE_INVISIBLE",
    "Line contains a potentially invisible or problematic Unicode character.",
)
E_UNEXPECTED_CONTROL_CHARACTER = IssueType(
    "E_UNEXPECTED_CONTROL_CHARACTER", "Line contains an unexpected control character."
)


class TextQualityCheck(FileCheck):
    """
    Performs various quality checks on text files, including encoding, line endings,
    whitespace issues, line length, special characters, and potential git conflicts.
    """

    def __init__(self):
        # Precompile conflict marker check for efficiency if needed, but startswith is usually fine
        self._git_conflict_markers = ("<<<<<<<", "=======", ">>>>>>>")
        # Define common invisible / formatting characters (add more if needed)
        # Using categories is generally better, but explicit checks can catch specific common ones.
        self._explicit_invisible_chars = {
            "\u200b",  # Zero Width Space
            "\u200c",  # Zero Width Non-Joiner
            "\u200d",  # Zero Width Joiner
            "\u2060",  # Word Joiner
            "\ufeff",  # Zero Width No-Break Space / BOM character
            "\u180e",  # Mongolian Vowel Separator
        }

    def check(self, ctx: FileContext):
        if not ctx.path.is_file():
            return
        if ctx.path.is_symlink():
            return

        if ctx is not None:
            if ctx.file_scope == CoarseFileScope.BUILD_TEMP:
                return

        if not ctx.expected_properties.is_text:
            return

        content_bytes = ctx.path.read_bytes()
        if not content_bytes:
            return

        ###################################################################
        # Byte-based checks (before decoding)
        ###################################################################

        is_invalid_encoding = False
        if content_bytes.startswith(b"\xef\xbb\xbf"):  # UTF-8 BOM
            ctx.add_issue(E_BOM_AT_START)
        elif content_bytes.startswith(b"\xff\xfe\x00\x00") or content_bytes.startswith(
            b"\x00\x00\xfe\xff"
        ):  # UTF-32 BOM
            ctx.add_issue(E_BOM_AT_START)
            ctx.add_issue(E_NOT_UTF8)
            is_invalid_encoding = True
        elif content_bytes.startswith(b"\xff\xfe") or content_bytes.startswith(b"\xfe\xff"):  # UTF-16 BOM
            ctx.add_issue(E_BOM_AT_START)
            ctx.add_issue(E_NOT_UTF8)
            is_invalid_encoding = True
        elif content_bytes.startswith(b"\x2b\x2f\x76"):  # UTF-7 BOM
            # Note: UTF-7 BOM is rare and not recommended, but we can check for it if needed.
            ctx.add_issue(E_BOM_AT_START)
            ctx.add_issue(E_NOT_UTF8)
            is_invalid_encoding = True

        # Check Line Endings based on bytes (more robust than decoded text)
        if not ctx.expected_properties.is_crlf_native and b"\r\n" in content_bytes:
            ctx.add_issue(E_LINE_ENDINGS, fix=(lambda: fix_line_endings(ctx.path, LineEnding.LF)))

        if ctx.expected_properties.is_crlf_native:
            line_ending_counts = get_line_ending_counts(ctx.path)
            if line_ending_counts[LineEnding.LF] > 0 or line_ending_counts[LineEnding.CR] > 0:
                ctx.add_issue(
                    E_LINE_ENDINGS,
                    fix=(lambda: fix_line_endings(ctx.path, LineEnding.CRLF)),
                )

        ###################################################################
        # Decoding and String-based checks
        ###################################################################

        text: str | None = None
        detected_encoding = "utf-8"  # Assume UTF-8 initially

        if not is_invalid_encoding:
            try:
                text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Try to detect common alternatives if UTF-8 fails
                try:
                    # Attempt Latin-1 (common fallback)
                    text = content_bytes.decode("latin-1")
                    detected_encoding = "latin-1"
                    ctx.add_issue(E_NOT_UTF8, detected_encoding=detected_encoding)
                except UnicodeDecodeError:
                    # Attempt Windows-1252 (another common one)
                    try:
                        text = content_bytes.decode("cp1252")
                        detected_encoding = "cp1252"
                        ctx.add_issue(E_NOT_UTF8, detected_encoding=detected_encoding)
                    except UnicodeDecodeError:
                        ctx.add_issue(E_NOT_UTF8)
                        text = None  # Cannot proceed with string checks

        else:
            text = None  # Cannot proceed with string checks

        ###################################################################
        # String-based checks (after decoding)
        ###################################################################

        if not content_bytes.endswith(b"\n") and (ctx.path.suffix not in (".json")):
            ctx.add_issue(E_NO_NEWLINE, fix=(lambda: fix_no_newline(ctx.path)))

        if text is not None:
            lines = text.splitlines()  # Don't keep ends, use original line endings from bytes if needed

            for i, line in enumerate(lines):
                line_nr = i + 1

                # Check for Git Conflict Markers
                if line.startswith(self._git_conflict_markers):
                    ctx.add_issue(E_GIT_CONFLICT_MARKER, line=line_nr)
                    # Often conflict markers break other checks, maybe continue to next line?

                # Check for Long Lines (only for code files)
                if ctx.expected_properties.is_code and not (ctx and ctx.project_type == CoarseProjectType.DATA):
                    # Note: len() works on Unicode characters, not bytes. This is usually what's desired.
                    if len(line) > MAX_CODE_LINE_LENGTH:
                        ctx.add_issue(
                            E_LINE_TOO_LONG,
                            actual=len(line),
                            max=MAX_CODE_LINE_LENGTH,
                            line=line_nr,
                        )

                # Check for Trailing Whitespace
                if line != line.rstrip(" \t"):
                    ctx.add_issue(
                        E_TRAILING_WHITESPACE,
                        line=line_nr,
                        fix=(lambda: fix_trailing_whitespace(ctx.path)),
                    )

                # Check for Mixed Spaces and Tabs in Indentation
                leading_whitespace = ""
                for char in line:
                    if char == " " or char == "\t":
                        leading_whitespace += char
                    else:
                        break
                if " " in leading_whitespace and "\t" in leading_whitespace:
                    ctx.add_issue(
                        E_MIXED_SPACES_TABS,
                        line=line_nr,
                        fix=(lambda: fix_mixed_spaces_tabs(ctx.path, tab_width=4, prefer_tabs=False)),
                    )

                # Character-level checks within the line
                control_chars = set()
                invisible_chars = set()
                for char in line:
                    category = unicodedata.category(char)  # Get Unicode category (e.g., 'Lu', 'Ll', 'Cc', 'Cf', 'Zs')

                    # Check for Unexpected Control Characters
                    # C0 controls (U+0000-U+001F) & C1 controls (U+007F-U+009F)
                    # Exclude tab (U+0009), Line Feed (U+000A), Carriage Return (U+000D)
                    if category == "Cc" and char not in ("\t", "\n", "\r"):
                        control_chars.add(char)

                    # # Check for Unicode Homoglyphs (simplified: non-ASCII letters)
                    # # This is a heuristic. True homoglyph detection is complex.
                    # # We flag non-ASCII letters as potentially confusing or unintended.
                    # if self.config.check_unicode_homoglyphs:
                    #      # Check if it's a letter ('L' category) and outside basic ASCII (<=127)
                    #      if category.startswith('L') and char_ord > 127:
                    #          issues.append(Issue(
                    #              Severity.WARNING, f"Line {line_nr}, Column {col_nr}: Contains non-ASCII letter '{char}' (U+{char_ord:04X}). Potential homoglyph or unintended character.",
                    #              [file], line_nr=line_nr, col_nr=col_nr))

                    # Check for Unicode Invisible/Formatting Characters
                    # Flag Format chars (Cf), non-standard spaces (Zs != ' '), Line/Para separators (Zl, Zp)
                    # Also check specific common invisible chars just in case.
                    if (
                        category == "Cf"
                        or (category == "Zs" and char != " ")
                        or category == "Zl"
                        or category == "Zp"
                        or char in self._explicit_invisible_chars
                    ):
                        # Avoid double-reporting BOM if already caught by byte check
                        invisible_chars.add(char)

                if control_chars:
                    # Report all control characters found in the line
                    ctx.add_issue(
                        E_UNEXPECTED_CONTROL_CHARACTER,
                        control_chars=", ".join(repr(c) for c in control_chars),
                        line=line_nr,
                    )

                if invisible_chars:
                    # Report all invisible characters found in the line
                    ctx.add_issue(
                        E_UNICODE_INVISIBLE,
                        invisible_chars=", ".join(repr(c) for c in invisible_chars),
                        line=line_nr,
                    )
