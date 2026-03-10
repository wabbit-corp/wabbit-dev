from __future__ import annotations

from pathlib import Path


def _template_text(relative_path: str) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / relative_path).read_text(encoding="utf-8")


def test_gradle_docs_deploy_template_uses_gh_pages_publish() -> None:
    text = _template_text("data-repo-template/gradle-files/.github/workflows/docs-deploy.yml.jinja2")

    assert "actions/configure-pages@v5" in text
    assert "actions/upload-pages-artifact@v3" in text
    assert "actions/deploy-pages@v4" in text
    assert "peaceiris/actions-gh-pages@v4" not in text


def test_python_docs_deploy_template_uses_pages_artifact_publish() -> None:
    text = _template_text("data-repo-template/python-files/.github/workflows/docs-deploy.yml.jinja2")

    assert "actions/configure-pages@v5" in text
    assert "actions/upload-pages-artifact@v3" in text
    assert "actions/deploy-pages@v4" in text
    assert "peaceiris/actions-gh-pages@v4" not in text


def test_gradle_publish_workflows_do_not_force_optional_gpg_key_id() -> None:
    snapshot_text = _template_text("data-repo-template/gradle-files/.github/workflows/snapshot-publish.yml.jinja2")
    release_text = _template_text("data-repo-template/gradle-files/.github/workflows/release-publish.yml.jinja2")

    assert "ORG_GRADLE_PROJECT_signingInMemoryKeyId" not in snapshot_text
    assert "ORG_GRADLE_PROJECT_signingInMemoryKeyId" not in release_text


def test_gradle_snapshot_publish_template_skips_release_versions_on_push() -> None:
    text = _template_text("data-repo-template/gradle-files/.github/workflows/snapshot-publish.yml.jinja2")

    assert "Detect snapshot version" in text
    assert "Skip snapshot publish for release version" in text
    assert "snapshot_version_print_command" in text
    assert "steps.snapshot_version.outputs.is_snapshot" in text
