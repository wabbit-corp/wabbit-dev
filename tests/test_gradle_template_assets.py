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


@pytest.mark.parametrize(
    "template_name",
    [
        "subproject-build.gradle.kts.jinja2",
        "subproject-build-kmp.gradle.kts.jinja2",
    ],
)
def test_gradle_templates_auto_include_dokka_docs_assets(template_name: str) -> None:
    template_path = Path(__file__).resolve().parents[2] / "data-repo-template" / "gradle-files" / template_name
    content = template_path.read_text(encoding="utf-8")

    assert 'file("docs/dokka-module.md")' in content
    assert "dokkaModuleFile.exists()" in content
    assert "includes.from(dokkaModuleFile)" in content


@pytest.mark.parametrize(
    "template_name",
    [
        "subproject-build.gradle.kts.jinja2",
        "subproject-build-kmp.gradle.kts.jinja2",
    ],
)
def test_gradle_templates_skip_signing_for_maven_local_publish(template_name: str) -> None:
    template_path = Path(__file__).resolve().parents[2] / "data-repo-template" / "gradle-files" / template_name
    content = template_path.read_text(encoding="utf-8")

    assert "localPublishRequested" in content
    assert '"MavenLocal" in taskName' in content
    assert "tasks.withType<org.gradle.plugins.signing.Sign>().configureEach" in content
    assert "enabled = false" in content


@pytest.mark.parametrize(
    "template_name",
    [
        "subproject-build.gradle.kts.jinja2",
        "subproject-build-kmp.gradle.kts.jinja2",
    ],
)
def test_gradle_templates_enable_context_parameters_by_default(template_name: str) -> None:
    template_path = Path(__file__).resolve().parents[2] / "data-repo-template" / "gradle-files" / template_name
    content = template_path.read_text(encoding="utf-8")

    assert 'freeCompilerArgs.add("-Xcontext-parameters")' in content
    assert "-Xcontext-receivers" not in content
