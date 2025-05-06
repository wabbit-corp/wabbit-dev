# -*- coding: utf-8 -*-
from dev.checks.base import FileCheck, Issue, Severity, IssueType, FileContext, CoarseFileScope, IssueList, CoarseProjectType
from dataclasses import dataclass, field # Added field
from typing import List, Optional, Dict, Any
import enum

from pathlib import Path
import re
import unicodedata # Needed for Unicode checks

from dev.file_properties import ExpectedFileProperties, get_expected_file_properties


CHUNK_BYTE_SIZE = 1024 * 1024 # 1 MB

class LineEnding(enum.Enum):
    CRLF = b'\r\n'
    LF   = b'\n'
    CR   = b'\r'


def get_line_ending_counts(file: Path) -> Dict[LineEnding, int]:
    crlf_count = 0
    lf_count = 0
    cr_count = 0

    STATE_OUTSIDE = 0
    STATE_CR = 1
    STATE_LF = 2

    state = STATE_OUTSIDE

    def update(byte: bytes):
        nonlocal crlf_count, lf_count, cr_count, state
        if state == STATE_OUTSIDE:
            if byte == b'\r': state = STATE_CR
            elif byte == b'\n': state = STATE_LF
            else: return
        elif state == STATE_CR:
            if byte == b'\r': 
                cr_count += 1
            elif byte == b'\n': 
                crlf_count += 1
                state = STATE_OUTSIDE
            else:
                cr_count += 1
                state = STATE_OUTSIDE
        elif state == STATE_LF:
            if byte == b'\r':
                lf_count += 1
                state = STATE_CR
            elif byte == b'\n':
                lf_count += 1
                state = STATE_LF
            else:
                lf_count += 1
                state = STATE_OUTSIDE
        else:
            raise ValueError("Invalid state")

    with file.open('rb') as f:
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
        LineEnding.CR: cr_count
    }


def get_line_ending(file: Path) -> Optional[LineEnding]:
    counts = get_line_ending_counts(file)
    crlf_count = counts[LineEnding.CRLF]
    lf_count = counts[LineEnding.LF]
    cr_count = counts[LineEnding.CR]
    _, _, result = max((lf_count, 3, LineEnding.LF), (crlf_count, 2, LineEnding.CRLF), (cr_count, 1, LineEnding.CR), key=lambda x: (x[0], x[1]))
    return result


def fix_no_newline(file: Path) -> None:
    nl = get_line_ending(file)
    with file.open('rb') as f:
        content = f.read()
    if not content.endswith(nl.value):
        with file.open('ab') as f:
            f.write(nl.value)


def fix_line_endings(file: Path, target_ending: LineEnding) -> None:
    with file.open('rb') as f:
        content = f.read()
    # Convert line endings to LF
    if target_ending == LineEnding.LF:
        content = content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    elif target_ending == LineEnding.CR:
        content = content.replace(b'\r\n', b'\r').replace(b'\n', b'\r')
    elif target_ending == LineEnding.CRLF:
        content = re.sub(b'(?:\r\n|\r|\n)', b'\r\n', content)
    with file.open('wb') as f:
        f.write(content)


def fix_trailing_whitespace(file: Path) -> None:
    nl = get_line_ending(file).value.decode('utf-8')
    with file.open('rt', encoding='utf-8') as f:
        lines = f.readlines()
    # Remove trailing whitespace from each line
    with file.open('wt', encoding='utf-8') as f:
        for line in lines:
            f.write(line.rstrip() + nl)


MAX_CODE_LINE_LENGTH = 200 # Default maximum line length for code files


E_NO_NEWLINE                   = IssueType("236fdabb-4175-4b0a-b2c7-a19e2857ce72", "File does not end with a newline character.")
E_BOM_AT_START                 = IssueType("369ebc23-b717-4e94-9309-929f62b89ab3", "File starts with a UTF-8 BOM (Byte Order Mark).")
E_LINE_ENDINGS                 = IssueType("78c8326e-ee99-4264-a033-01ddf56c9c9a", "File contains incorrect line endings.")
E_NOT_UTF8                     = IssueType("4aad4c2a-afa5-4180-8a3e-0a06bed3f792", "File is not valid UTF-8 encoded.")
E_GIT_CONFLICT_MARKER          = IssueType("6a4208e1-81be-4ffe-9d23-b2a0df8599e5", "File contains a Git conflict marker.")
E_LINE_TOO_LONG                = IssueType("7d522f57-f5b2-4214-bc6b-9d9859fe4495", "Line exceeds maximum length.")
E_TRAILING_WHITESPACE          = IssueType("9eba1063-bd3c-43ac-aad7-2fe93ad84110", "Line contains trailing whitespace.")
E_MIXED_SPACES_TABS            = IssueType("11d40202-3271-450f-a078-0270951d7bd5", "Line contains mixed spaces and tabs in indentation.")
E_UNEXPECTED_CONTROL_CHARACTER = IssueType("8cd4fac9-93e2-4ea9-899c-e618aa037f19", "Line contains an unexpected control character.")
E_UNICODE_HOMOGLYPH            = IssueType("074ce2f3-d932-4051-a219-750d7a9bec1a", "Line contains a non-ASCII letter (potential homoglyph).")
E_UNICODE_INVISIBLE            = IssueType("132134a3-7f21-4ca3-b9ac-f26da804392d", "Line contains a potentially invisible or problematic Unicode character.")


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
            '\u200B', # Zero Width Space
            '\u200C', # Zero Width Non-Joiner
            '\u200D', # Zero Width Joiner
            '\u2060', # Word Joiner
            '\uFEFF', # Zero Width No-Break Space / BOM character
            '\u180E', # Mongolian Vowel Separator
        }


    def check(self, file: Path, ctx: FileContext | None = None) -> List[Issue]:
        if not file.is_file(): return []
        if file.is_symlink(): return [] # Don't check symlinks directly

        if ctx is not None:
            if ctx.file_scope == CoarseFileScope.BUILD_TEMP:
                return []

        props = get_expected_file_properties(file) or ExpectedFileProperties()

        # Only perform text checks on files identified as text
        if not props.is_text:
            return []

        
        content_bytes = file.read_bytes()
        if not content_bytes: return [] # Skip empty files

        issues = IssueList()

        ###################################################################
        # Byte-based checks (before decoding)
        ###################################################################

        is_invalid_encoding = False
        if content_bytes.startswith(b"\xEF\xBB\xBF"): # UTF-8 BOM
            issues.append(E_BOM_AT_START.at(file))
        elif content_bytes.startswith(b"\xFF\xFE\x00\x00") or content_bytes.startswith(b"\x00\x00\xFE\xFF"): # UTF-32 BOM
            issues.append(E_BOM_AT_START.at(file))
            issues.append(E_NOT_UTF8.at(file)) # Not valid UTF-8
            is_invalid_encoding = True
        elif content_bytes.startswith(b"\xFF\xFE") or content_bytes.startswith(b"\xFE\xFF"): # UTF-16 BOM
            issues.append(E_BOM_AT_START.at(file))
            issues.append(E_NOT_UTF8.at(file)) # Not valid UTF-8
            is_invalid_encoding = True
        elif content_bytes.startswith(b"\x2B\x2F\x76"): # UTF-7 BOM
            # Note: UTF-7 BOM is rare and not recommended, but we can check for it if needed.
            issues.append(E_BOM_AT_START.at(file))
            issues.append(E_NOT_UTF8.at(file)) # Not valid UTF-8
            is_invalid_encoding = True

        # Check Line Endings based on bytes (more robust than decoded text)
        if not props.is_crlf_native and b'\r\n' in content_bytes:
            issues.append(E_LINE_ENDINGS.at(file).fixable(lambda: fix_line_endings(file, LineEnding.LF)))
        
        if props.is_crlf_native:
            line_ending_counts = get_line_ending_counts(file)
            if line_ending_counts[LineEnding.LF] > 0 or line_ending_counts[LineEnding.CR] > 0:
                issues.append(E_LINE_ENDINGS.at(file).fixable(lambda: fix_line_endings(file, LineEnding.CRLF)))
        

        ###################################################################
        # Decoding and String-based checks
        ###################################################################

        text: Optional[str] = None
        detected_encoding = "utf-8" # Assume UTF-8 initially

        if not is_invalid_encoding:
            try:
                text = content_bytes.decode('utf-8')
            except UnicodeDecodeError as e:
                # Try to detect common alternatives if UTF-8 fails
                try:
                    # Attempt Latin-1 (common fallback)
                    text = content_bytes.decode('latin-1')
                    detected_encoding = "latin-1"
                    issues.append(E_NOT_UTF8.make(detected_encoding=detected_encoding).at(file))
                except UnicodeDecodeError:
                    # Attempt Windows-1252 (another common one)
                    try:
                        text = content_bytes.decode('cp1252')
                        detected_encoding = "cp1252"
                        issues.append(E_NOT_UTF8.make(detected_encoding=detected_encoding).at(file))
                    except UnicodeDecodeError:
                        issues.append(E_NOT_UTF8.at(file))
                        text = None # Cannot proceed with string checks

        else:
            text = None # Cannot proceed with string checks


        ###################################################################
        # String-based checks (after decoding)
        ###################################################################

        if not content_bytes.endswith(b'\n') and (file.suffix not in ('.json')):
            issues.append(E_NO_NEWLINE.at(file).fixable(lambda: fix_no_newline(file)))
            

        if text is not None:
            lines = text.splitlines() # Don't keep ends, use original line endings from bytes if needed

            for i, line in enumerate(lines):
                line_nr = i + 1

                # Check for Git Conflict Markers
                if line.startswith(self._git_conflict_markers):
                    issues.append(E_GIT_CONFLICT_MARKER.at(file, line=line_nr))
                    # Often conflict markers break other checks, maybe continue to next line?

                # Check for Long Lines (only for code files)
                if props.is_code and not (ctx and ctx.project_type == CoarseProjectType.DATA):
                    # Note: len() works on Unicode characters, not bytes. This is usually what's desired.
                    if len(line) > MAX_CODE_LINE_LENGTH:
                        issues.append(E_LINE_TOO_LONG.make(actual=len(line), max=MAX_CODE_LINE_LENGTH).at(file, line=line_nr))

                # Check for Trailing Whitespace
                if line != line.rstrip(' \t'):
                    issues.append(E_TRAILING_WHITESPACE.at(file, line=line_nr).fixable(lambda: fix_trailing_whitespace(file)))

                # Check for Mixed Spaces and Tabs in Indentation
                leading_whitespace = ""
                for char in line:
                    if char == ' ' or char == '\t':
                        leading_whitespace += char
                    else:
                        break
                if ' ' in leading_whitespace and '\t' in leading_whitespace:
                    issues.append(E_MIXED_SPACES_TABS.at(file, line=line_nr))

                # Character-level checks within the line
                control_chars = set()
                invisible_chars = set()
                homoglyphs = set()
                for j, char in enumerate(line):
                    col_nr = j + 1
                    char_ord = ord(char)
                    category = unicodedata.category(char) # Get Unicode category (e.g., 'Lu', 'Ll', 'Cc', 'Cf', 'Zs')

                    # Check for Unexpected Control Characters
                    # C0 controls (U+0000-U+001F) & C1 controls (U+007F-U+009F)
                    # Exclude tab (U+0009), Line Feed (U+000A), Carriage Return (U+000D)
                    if category == 'Cc' and char not in ('\t', '\n', '\r'):
                        control_chars.add(char)

                    # # Check for Unicode Homoglyphs (simplified: non-ASCII letters)
                    # # This is a heuristic. True homoglyph detection is complex.
                    # # We flag non-ASCII letters as potentially confusing or unintended.
                    # if self.config.check_unicode_homoglyphs:
                    #      # Check if it's a letter ('L' category) and outside basic ASCII (<=127)
                    #      if category.startswith('L') and char_ord > 127:
                    #          issues.append(Issue(Severity.WARNING, f"Line {line_nr}, Column {col_nr}: Contains non-ASCII letter '{char}' (U+{char_ord:04X}). Potential homoglyph or unintended character.", [file], line_nr=line_nr, col_nr=col_nr))

                    # Check for Unicode Invisible/Formatting Characters
                    # Flag Format chars (Cf), non-standard spaces (Zs != ' '), Line/Para separators (Zl, Zp)
                    # Also check specific common invisible chars just in case.
                    if category == 'Cf' or \
                        (category == 'Zs' and char != ' ') or \
                        category == 'Zl' or \
                        category == 'Zp' or \
                        char in self._explicit_invisible_chars:
                            # Avoid double-reporting BOM if already caught by byte check
                            if char == '\uFEFF' and j == 0 and self.config.check_bom and content_bytes.startswith(b"\xEF\xBB\xBF"):
                                pass # Already reported as BOM
                            else:
                                invisible_chars.add(char)
                
                if control_chars:
                    # Report all control characters found in the line
                    issues.append(E_UNEXPECTED_CONTROL_CHARACTER.make(control_chars=', '.join(repr(c) for c in control_chars)).at(file, line=line_nr))

                if invisible_chars:
                    # Report all invisible characters found in the line
                    issues.append(E_UNICODE_INVISIBLE.make(invisible_chars=', '.join(repr(c) for c in invisible_chars)).at(file, line=line_nr))
                        

        return issues