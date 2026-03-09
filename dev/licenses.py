from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import jinja2

import dev.io


@dataclass(frozen=True)
class LicenseDefinition:
    key: str
    template_file: str
    python_spdx: str
    display_name: str


SUPPORTED_LICENSES: tuple[LicenseDefinition, ...] = (
    LicenseDefinition("AGPL", "AGPL.md", "AGPL-3.0-or-later", "GNU Affero General Public License v3.0 or later"),
    LicenseDefinition("CC0", "CC0.md", "CC0-1.0", "Creative Commons Zero v1.0 Universal"),
    LicenseDefinition("MIT", "MIT.md", "MIT", "MIT License"),
    LicenseDefinition("BSD", "BSD.md", "BSD-3-Clause", "BSD 3-Clause License"),
    LicenseDefinition("GPLv3", "GPLv3.md", "GPL-3.0-only", "GNU General Public License v3.0 only"),
)

_LICENSES_BY_KEY: dict[str, LicenseDefinition] = {item.key: item for item in SUPPORTED_LICENSES}
SUPPORTED_LICENSE_KEYS: tuple[str, ...] = tuple(item.key for item in SUPPORTED_LICENSES)

_LICENSE_ALIASES: dict[str, str] = {
    **{item.key.lower(): item.key for item in SUPPORTED_LICENSES},
    "agplv3": "AGPL",
    "agpl-3.0": "AGPL",
    "agpl-3.0-or-later": "AGPL",
    "cc0-1.0": "CC0",
    "bsd-3-clause": "BSD",
    "gpl3": "GPLv3",
    "gpl-3.0": "GPLv3",
    "gpl-3.0-only": "GPLv3",
    "gpl-3.0-or-later": "GPLv3",
}


def canonicalize_license_key(license_key: str | None) -> str | None:
    if license_key is None:
        return None

    normalized = license_key.strip()
    if not normalized:
        return None

    if normalized in _LICENSES_BY_KEY:
        return normalized

    return _LICENSE_ALIASES.get(normalized.lower(), normalized)


def python_spdx_for_license(license_key: str | None) -> str | None:
    normalized = canonicalize_license_key(license_key)
    if normalized is None:
        return None

    definition = _LICENSES_BY_KEY.get(normalized)
    if definition is None:
        return normalized
    return definition.python_spdx


def license_display_name(license_key: str | None) -> str | None:
    normalized = canonicalize_license_key(license_key)
    if normalized is None:
        return None

    definition = _LICENSES_BY_KEY.get(normalized)
    if definition is None:
        return normalized
    return definition.display_name


def cla_primary_license_reference(license_key: str | None) -> str:
    display_name = license_display_name(license_key)
    spdx_identifier = python_spdx_for_license(license_key)

    if display_name is None:
        return "the project's configured open-source license"
    if spdx_identifier is None or spdx_identifier == display_name:
        return display_name
    return f"{display_name} ({spdx_identifier})"


def load_license_texts(licenses_dir: Path) -> dict[str, str]:
    return {item.key: dev.io.read_text_file(licenses_dir / item.template_file) for item in SUPPORTED_LICENSES}


class LicenseProjectLike(Protocol):
    name: str
    description: str | None
    authors: list[str]
    copyright_holder: str | None
    copyright_year_start: int | None


def _normalize_author_name(author: str) -> str:
    value = author.strip()
    if "<" in value:
        value = value.split("<", 1)[0].strip()
    return value


def _default_copyright_holder(authors: list[str]) -> str:
    normalized_authors: list[str] = []
    for author in authors:
        normalized = _normalize_author_name(author)
        if normalized:
            normalized_authors.append(normalized)
    if not normalized_authors:
        return "Wabbit Corporation"
    if len(normalized_authors) == 1:
        return normalized_authors[0]
    return ", ".join(normalized_authors)


def _copyright_holder(authors: list[str], explicit_holder: str | None) -> str:
    if explicit_holder is not None and explicit_holder.strip():
        return explicit_holder.strip()
    return _default_copyright_holder(authors)


def _copyright_year_text(*, current_year: int, year_start: int | None) -> str:
    if year_start is None or year_start == current_year:
        return str(current_year)
    if year_start > current_year:
        raise ValueError(f"copyright year start {year_start} is after current year {current_year}")
    return f"{year_start}-{current_year}"


def _standardize_license_template_text(template_text: str) -> str:
    replacements = {
        "<year>": "{{ copyright_year }}",
        "[year]": "{{ copyright_year }}",
        "<owner>": "{{ copyright_holder }}",
        "<copyright holder>": "{{ copyright_holder }}",
        "<copyright holders>": "{{ copyright_holder }}",
        "[copyright holder]": "{{ copyright_holder }}",
        "<name of author>": "{{ copyright_holder }}",
        "<program>": "{{ project_name }}",
        "<one line to give the program's name and a brief idea of what it does.>": "{{ project_header_line }}",
    }

    rendered = template_text
    for old, new in replacements.items():
        rendered = rendered.replace(old, new)
    return rendered


def render_license_text(
    template_text: str,
    *,
    project_name: str,
    project_description: str | None,
    project_authors: list[str],
    project_copyright_holder: str | None = None,
    project_copyright_year_start: int | None = None,
    current_year: int | None = None,
) -> str:
    year = current_year if current_year is not None else datetime.now().year
    header_line = project_name
    if isinstance(project_description, str) and project_description.strip():
        header_line = f"{project_name}: {project_description.strip()}"

    template = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(
        _standardize_license_template_text(template_text)
    )
    rendered = template.render(
        copyright_year=_copyright_year_text(current_year=year, year_start=project_copyright_year_start),
        copyright_holder=_copyright_holder(project_authors, project_copyright_holder),
        project_name=project_name,
        project_description=project_description or "",
        project_header_line=header_line,
    )
    return rendered.rstrip() + "\n"


def render_project_license(template_text: str, project: LicenseProjectLike, *, current_year: int | None = None) -> str:
    return render_license_text(
        template_text,
        project_name=project.name,
        project_description=project.description,
        project_authors=project.authors,
        project_copyright_holder=project.copyright_holder,
        project_copyright_year_start=project.copyright_year_start,
        current_year=current_year,
    )
