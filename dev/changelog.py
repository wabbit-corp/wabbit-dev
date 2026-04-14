from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CHANGELOG_MARKDOWN_FILE_NAMES: tuple[str, ...] = ("CHANGELOG.md",)
STANDARD_CHANGELOG_SECTION_RE = re.compile(
    r"^##\s+(?P<version>\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?)\s+-\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
MARKDOWN_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MARKDOWN_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
MARKDOWN_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
MARKDOWN_ITALIC_RE = re.compile(r"\*([^*]+)\*")


@dataclass(frozen=True)
class MarkdownChangelogSection:
    title: str
    body: str


def find_markdown_changelog(repo_root: Path) -> Path | None:
    for file_name in CHANGELOG_MARKDOWN_FILE_NAMES:
        candidate = repo_root / file_name
        if candidate.is_file():
            return candidate
    return None


def markdown_changelog_section_for_version(changelog_text: str, version_text: str) -> MarkdownChangelogSection | None:
    lines = changelog_text.splitlines()
    section_start = -1
    section_level = -1
    section_title = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        match = STANDARD_CHANGELOG_SECTION_RE.match(stripped)
        if match is None:
            continue
        if match.group("version") != version_text:
            continue
        section_start = index + 1
        section_level = 2
        section_title = stripped.removeprefix("## ").strip()
        break
    if section_start < 0:
        return None

    section_end = len(lines)
    for index in range(section_start, len(lines)):
        match = MARKDOWN_HEADING_RE.match(lines[index].strip())
        if match is None:
            continue
        if len(match.group(1)) <= section_level:
            section_end = index
            break

    body = "\n".join(lines[section_start:section_end]).strip()
    return MarkdownChangelogSection(title=section_title, body=body)


def _markdown_line_to_plain_text(line: str) -> str:
    text = re.sub(r"^(#{1,6})\s+", "", line.rstrip())
    text = MARKDOWN_LINK_RE.sub(lambda match: f"{match.group(1)} ({match.group(2)})", text)
    text = MARKDOWN_INLINE_CODE_RE.sub(lambda match: match.group(1), text)
    text = MARKDOWN_BOLD_RE.sub(lambda match: match.group(1), text)
    return MARKDOWN_ITALIC_RE.sub(lambda match: match.group(1), text)


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    collapsed: list[str] = []
    last_was_blank = False
    for raw_line in lines:
        line = raw_line.rstrip()
        is_blank = not line.strip()
        if is_blank and last_was_blank:
            continue
        collapsed.append(line)
        last_was_blank = is_blank
    while collapsed and not collapsed[0].strip():
        collapsed.pop(0)
    while collapsed and not collapsed[-1].strip():
        collapsed.pop()
    return collapsed


def render_markdown_section_as_plain_text(section: MarkdownChangelogSection) -> str | None:
    body_lines = _collapse_blank_lines([_markdown_line_to_plain_text(line) for line in section.body.splitlines()])
    if body_lines:
        return "\n".join(body_lines)
    return None


def resolve_repo_changelog_change_notes(*, repo_root: Path, project_version: str | None) -> str | None:
    if project_version is None:
        return None

    changelog_path = find_markdown_changelog(repo_root)
    if changelog_path is None:
        return None

    try:
        changelog_text = changelog_path.read_text(encoding="utf-8")
    except OSError:
        return None

    section = markdown_changelog_section_for_version(changelog_text, project_version)
    if section is None:
        return None
    return render_markdown_section_as_plain_text(section)


def resolve_intellij_change_notes(
    *,
    repo_root: Path,
    project_version: str | None,
    configured_change_notes: str | None,
) -> str | None:
    rendered = resolve_repo_changelog_change_notes(repo_root=repo_root, project_version=project_version)
    if rendered is not None and rendered.strip():
        return rendered.strip()

    if configured_change_notes is None:
        return None

    normalized = configured_change_notes.strip()
    if not normalized:
        return None
    return normalized


__all__ = [
    "MarkdownChangelogSection",
    "find_markdown_changelog",
    "markdown_changelog_section_for_version",
    "render_markdown_section_as_plain_text",
    "resolve_repo_changelog_change_notes",
    "resolve_intellij_change_notes",
]
