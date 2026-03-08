from __future__ import annotations

from dataclasses import dataclass

import pytest

from dev.licenses import (
    SUPPORTED_LICENSE_KEYS,
    canonicalize_license_key,
    python_spdx_for_license,
    render_license_text,
    render_project_license,
)


def test_supported_license_keys_include_expected_defaults() -> None:
    assert SUPPORTED_LICENSE_KEYS == ("AGPL", "CC0", "MIT", "BSD", "GPLv3")


@pytest.mark.parametrize(
    ("license_key", "expected"),
    [
        ("AGPL", "AGPL"),
        ("AGPLv3", "AGPL"),
        ("agpl-3.0-or-later", "AGPL"),
        ("CC0", "CC0"),
        ("cc0-1.0", "CC0"),
        ("MIT", "MIT"),
        ("mit", "MIT"),
        ("BSD", "BSD"),
        ("bsd-3-clause", "BSD"),
        ("GPLv3", "GPLv3"),
        ("gpl-3.0", "GPLv3"),
    ],
)
def test_canonicalize_license_key(license_key: str, expected: str) -> None:
    assert canonicalize_license_key(license_key) == expected


@pytest.mark.parametrize(
    ("license_key", "expected"),
    [
        ("AGPL", "AGPL-3.0-or-later"),
        ("CC0", "CC0-1.0"),
        ("MIT", "MIT"),
        ("BSD", "BSD-3-Clause"),
        ("GPLv3", "GPL-3.0-only"),
        ("gpl-3.0", "GPL-3.0-only"),
    ],
)
def test_python_spdx_for_license(license_key: str, expected: str) -> None:
    assert python_spdx_for_license(license_key) == expected


def test_python_spdx_for_unknown_license_returns_trimmed_value() -> None:
    assert python_spdx_for_license("  custom-license  ") == "custom-license"


def test_render_license_text_replaces_standard_placeholders() -> None:
    template = "Copyright (c) {{ copyright_year }} {{ copyright_holder }}.\n"
    rendered = render_license_text(
        template,
        project_name="kotlin-base58",
        project_description="Base58 encoding for Kotlin",
        project_authors=["Alice Example <alice@example.com>"],
        current_year=2030,
    )
    assert rendered == "Copyright (c) 2030 Alice Example.\n"


def test_render_license_text_replaces_legacy_placeholders() -> None:
    template = "\n".join(
        [
            "<one line to give the program's name and a brief idea of what it does.>",
            "Copyright (C) <year>  <name of author>",
            "<program>  Copyright (C) <year>  <name of author>",
            "",
        ]
    )
    rendered = render_license_text(
        template,
        project_name="kotlin-base58",
        project_description="Base58 encoding for Kotlin",
        project_authors=["Alice Example <alice@example.com>"],
        current_year=2030,
    )
    assert "kotlin-base58: Base58 encoding for Kotlin" in rendered
    assert "Copyright (C) 2030  Alice Example" in rendered
    assert "kotlin-base58  Copyright (C) 2030  Alice Example" in rendered


@dataclass
class _FakeProject:
    name: str
    description: str | None
    authors: list[str]


def test_render_project_license_uses_default_holder_when_no_authors() -> None:
    project = _FakeProject(name="demo", description=None, authors=[])
    rendered = render_project_license(
        "Copyright (c) {{ copyright_year }} {{ copyright_holder }}.\n",
        project,
        current_year=2030,
    )
    assert rendered == "Copyright (c) 2030 Wabbit Corporation.\n"
