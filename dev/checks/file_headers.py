from __future__ import annotations

from pathlib import Path
import re

from dev.checks.base import FileCheck, FileContext, IssueType
from dev.licenses import python_spdx_for_license

E_INCORRECT_SPDX_HEADER = IssueType(
    "E_INCORRECT_SPDX_HEADER",
    "File is missing the expected SPDX header ({expected}).",
)

_SPDX_HEADER_RE = re.compile(
    r"^(?P<prefix>\s*(?://|#|--)\s*)SPDX-License-Identifier:\s*(?P<identifier>[^\s]+)\s*$"
)

_COMMENT_PREFIX_BY_SUFFIX: dict[str, str] = {
    ".c": "//",
    ".cc": "//",
    ".cpp": "//",
    ".cs": "//",
    ".fs": "//",
    ".fsi": "//",
    ".fsx": "//",
    ".h": "//",
    ".hpp": "//",
    ".java": "//",
    ".js": "//",
    ".jsx": "//",
    ".kt": "//",
    ".kts": "//",
    ".mjs": "//",
    ".purs": "--",
    ".py": "#",
    ".rs": "//",
    ".scala": "//",
    ".sh": "#",
    ".swift": "//",
    ".ts": "//",
    ".tsx": "//",
    ".zsh": "#",
}


def _relative_to_project(file_path: Path, project_path: Path) -> Path | None:
    try:
        return file_path.relative_to(project_path)
    except ValueError:
        pass

    try:
        return file_path.resolve().relative_to(project_path.resolve())
    except ValueError:
        return None


def _is_test_path(relative_path: Path) -> bool:
    posix = relative_path.as_posix()
    if posix.startswith("test/") or posix.startswith("tests/"):
        return True
    if not posix.startswith("src/"):
        return False

    parts = relative_path.parts
    if len(parts) < 2:
        return False

    source_set = parts[1]
    return source_set == "test" or source_set.endswith("Test")


def _is_supported_source_path(relative_path: Path) -> bool:
    posix = relative_path.as_posix()
    return posix.startswith("src/") or posix.startswith("test/") or posix.startswith("tests/")


def _comment_prefix_for_path(path: Path) -> str | None:
    return _COMMENT_PREFIX_BY_SUFFIX.get(path.suffix.lower())


def expected_spdx_identifier(ctx: FileContext) -> str | None:
    project = ctx.project
    if project is None:
        return None
    if getattr(getattr(project, "ownership", None), "value", None) != "wabbit":
        return None

    comment_prefix = _comment_prefix_for_path(ctx.path)
    if comment_prefix is None:
        return None

    relative_path = _relative_to_project(ctx.path, project.path)
    if relative_path is None or not _is_supported_source_path(relative_path):
        return None

    license_key = project.test_license if _is_test_path(relative_path) else project.license
    return python_spdx_for_license(license_key)


def _newline_for_text(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def _spdx_header_line(path: Path, identifier: str) -> str | None:
    prefix = _comment_prefix_for_path(path)
    if prefix is None:
        return None
    return f"{prefix} SPDX-License-Identifier: {identifier}"


def _find_existing_spdx_line(lines: list[str], *, start: int, stop: int) -> int | None:
    for index in range(start, min(stop, len(lines))):
        if _SPDX_HEADER_RE.match(lines[index].rstrip("\r\n")):
            return index
    return None


def render_spdx_fixed_text(path: Path, text: str, identifier: str) -> str:
    header_line = _spdx_header_line(path, identifier)
    if header_line is None:
        return text

    newline = _newline_for_text(text)
    lines = text.splitlines(keepends=True)
    insert_at = 1 if lines and lines[0].startswith("#!") else 0
    existing_index = _find_existing_spdx_line(lines, start=insert_at, stop=len(lines))

    if existing_index is not None:
        existing_line = lines[existing_index]
        if existing_line.rstrip("\r\n") == header_line:
            return text
        line_ending = "\r\n" if existing_line.endswith("\r\n") else "\n"
        lines[existing_index] = header_line + line_ending
        return "".join(lines)

    insertion: list[str] = [header_line + newline]
    if insert_at >= len(lines) or lines[insert_at].strip():
        insertion.append(newline)
    lines[insert_at:insert_at] = insertion
    return "".join(lines)


class SpdxHeaderCheck(FileCheck):
    def check(self, ctx: FileContext) -> None:
        if not ctx.is_file or not ctx.expected_properties.is_text:
            return

        expected = expected_spdx_identifier(ctx)
        if expected is None:
            return

        original = ctx.read_text(E_INCORRECT_SPDX_HEADER)
        fixed = render_spdx_fixed_text(ctx.path, original, expected)
        if fixed == original:
            return

        def fix() -> None:
            ctx.path.write_text(fixed, encoding="utf-8")

        line_number = 2 if original.startswith("#!") else 1
        ctx.add_issue(E_INCORRECT_SPDX_HEADER, line=line_number, fix=fix, expected=expected)


__all__ = [
    "E_INCORRECT_SPDX_HEADER",
    "SpdxHeaderCheck",
    "expected_spdx_identifier",
    "render_spdx_fixed_text",
]
