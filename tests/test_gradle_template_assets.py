from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "template_name",
    [
        "subproject-build.gradle.kts.jinja2",
        "subproject-build-kmp.gradle.kts.jinja2",
    ],
)
def test_gradle_templates_do_not_embed_placeholder_dokka_source_url(template_name: str) -> None:
    template_path = Path(__file__).resolve().parents[2] / "data-repo-template" / "gradle-files" / template_name
    content = template_path.read_text(encoding="utf-8")

    assert "https://example.com/src" not in content
    assert "dokka_source_link_remote_url" in content
    assert "company_legal_name" in content
