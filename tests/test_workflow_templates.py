from __future__ import annotations

import dev.io
from dev.tasks.setup_common import render_template
from dev.template_assets import repo_template_path


def _template_text(*parts: str) -> str:
    return repo_template_path(*parts).read_text(encoding="utf-8")


def test_gradle_docs_deploy_template_uses_gh_pages_publish() -> None:
    text = _template_text("gradle-files", ".github", "workflows", "docs-deploy.yml.jinja2")

    assert "actions/configure-pages@v5" in text
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in text
    assert "actions/setup-python@v5" in text
    assert "mkdocs==1.6.1" in text
    assert 'python3 scripts/build_pages_markdown_site.py --output-dir "$SITE_DIR/docs"' in text
    assert "actions/upload-pages-artifact@v4" in text
    assert "actions/deploy-pages@v4" in text
    assert "peaceiris/actions-gh-pages@v4" not in text


def test_gradle_docs_deploy_template_renders_without_jinja_runner_errors() -> None:
    template = dev.io.read_template(
        repo_template_path("gradle-files", ".github", "workflows", "docs-deploy.yml.jinja2"),
        strict=True,
    )

    text = render_template(
        template,
        java_version="21",
        needs_android=False,
        docs_build_command="./gradlew dokkaGenerate",
        docs_output_dir="build/dokka/html",
    )

    assert "${{ runner.temp }}/pages-site" in text


def test_gradle_docs_quality_template_builds_markdown_site() -> None:
    text = _template_text("gradle-files", ".github", "workflows", "docs-quality.yml.jinja2")

    assert "actions/setup-python@v5" in text
    assert "mkdocs==1.6.1" in text
    assert 'python3 scripts/build_pages_markdown_site.py --output-dir "$RUNNER_TEMP/pages-markdown"' in text


def test_python_docs_deploy_template_uses_pages_artifact_publish() -> None:
    text = _template_text("python-files", ".github", "workflows", "docs-deploy.yml.jinja2")

    assert "actions/configure-pages@v5" in text
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in text
    assert "actions/upload-pages-artifact@v4" in text
    assert "actions/deploy-pages@v4" in text
    assert "peaceiris/actions-gh-pages@v4" not in text


def test_repo_docs_deploy_template_builds_generated_repo_docs_site() -> None:
    text = _template_text("repo-files", ".github", "workflows", "docs-deploy.yml.jinja2")

    assert "actions/configure-pages@v5" in text
    assert "actions/upload-pages-artifact@v4" in text
    assert "actions/deploy-pages@v4" in text
    assert 'python3 scripts/build_repo_docs_site.py --mode deploy --output-dir "$RUNNER_TEMP/pages-site"' in text


def test_repo_docs_quality_template_runs_generated_repo_docs_site_builder() -> None:
    text = _template_text("repo-files", ".github", "workflows", "docs-quality.yml.jinja2")

    assert "actions/setup-python@v5" in text
    assert 'python3 scripts/build_repo_docs_site.py --mode quality --output-dir "$RUNNER_TEMP/pages-site"' in text


def test_gradle_publish_workflows_do_not_force_optional_gpg_key_id() -> None:
    snapshot_text = _template_text("gradle-files", ".github", "workflows", "snapshot-publish.yml.jinja2")
    release_text = _template_text("gradle-files", ".github", "workflows", "release-publish.yml.jinja2")

    assert "ORG_GRADLE_PROJECT_signingInMemoryKeyId" not in snapshot_text
    assert "ORG_GRADLE_PROJECT_signingInMemoryKeyId" not in release_text


def test_gradle_snapshot_publish_template_skips_release_versions_on_push() -> None:
    text = _template_text("gradle-files", ".github", "workflows", "snapshot-publish.yml.jinja2")

    assert "Detect snapshot version" in text
    assert "Skip snapshot publish for release version" in text
    assert "snapshot_version_print_command" in text
    assert "steps.snapshot_version.outputs.is_snapshot" in text


def test_gradle_release_publish_template_checks_tag_ref_type_explicitly() -> None:
    text = _template_text("gradle-files", ".github", "workflows", "release-publish.yml.jinja2")

    assert "git fetch --force --tags origin" in text
    assert "git for-each-ref \"refs/tags/${GITHUB_REF_NAME}\" --format='%(objecttype)'" in text
    assert 'git cat-file -t "${GITHUB_REF_NAME}"' not in text


def test_gradle_release_publish_template_uploads_github_release_assets() -> None:
    text = _template_text("gradle-files", ".github", "workflows", "release-publish.yml.jinja2")

    assert "softprops/action-gh-release@v2" in text
    assert "build/releases/*.zip" in text
    assert "build/releases/release-manifest.json" in text
    assert "build/releases/SHA256SUMS" in text
    assert "contents: write" in text


def test_gradle_workflow_templates_install_shell_test_dependencies() -> None:
    workflow_paths = (
        ("gradle-files", ".github", "workflows", "release-publish.yml.jinja2"),
        ("gradle-files", ".github", "workflows", "snapshot-publish.yml.jinja2"),
        ("gradle-files", ".github", "workflows", "docs-quality.yml.jinja2"),
        ("gradle-files", ".github", "workflows", "docs-deploy.yml.jinja2"),
        ("gradle-files", ".github", "workflows", "compiler-plugin-release-publish.yml.jinja2"),
        ("gradle-files", ".github", "workflows", "compiler-plugin-snapshot-publish.yml.jinja2"),
    )

    for path in workflow_paths:
        text = _template_text(*path)
        assert "Install shell test dependencies" in text
        assert "sudo apt-get install -y zsh" in text


def test_gradle_release_publish_template_renders_bundle_fields_without_jinja_errors() -> None:
    template = dev.io.read_template(
        repo_template_path("gradle-files", ".github", "workflows", "release-publish.yml.jinja2"),
        strict=True,
    )

    text = render_template(
        template,
        java_version="21",
        needs_android=False,
        version_print_command="./gradlew --quiet printVersion",
        snapshot_version_print_command="./gradlew --quiet printVersion",
        release_validation_command="./gradlew assertReleaseVersion",
        release_build_command="./gradlew build",
        release_publish_command="./gradlew publish",
        release_publish_step_name="Publish release",
        release_publish_env={"TOKEN": "${{ secrets.TOKEN }}"},
        release_bundle_projects_json='[{"projectId":"demo","assetSlug":"demo","bundleKind":"gradle-publications","archivePrefix":"publications","sourceDir":"build/publications"}]',
        snapshot_publish_command="./gradlew publishSnapshots",
        docs_build_command="./gradlew dokkaGenerate",
        docs_output_dir="build/dokka/html",
    )

    assert "Publish release" in text
    assert 'projects = json.loads(r\'\'\'' in text


def test_python_release_publish_template_builds_and_uploads_release_assets() -> None:
    text = _template_text("python-files", ".github", "workflows", "release-publish.yml.jinja2")

    assert "python -m build" in text
    assert "python -m twine upload dist/*" in text
    assert "softprops/action-gh-release@v2" in text
    assert "build/releases/*.zip" in text
    assert "build/releases/release-manifest.json" in text
    assert "build/releases/SHA256SUMS" in text


def test_python_release_publish_template_renders_without_jinja_errors() -> None:
    template = dev.io.read_template(
        repo_template_path("python-files", ".github", "workflows", "release-publish.yml.jinja2"),
        strict=True,
    )

    text = render_template(
        template,
        release_bundle_projects_json='[{"projectId":"demo","assetSlug":"demo","bundleKind":"python-dist","archivePrefix":"dist","sourceDir":"dist"}]',
    )

    assert 'projects = json.loads(r\'\'\'' in text


def test_compiler_plugin_publish_workflows_read_supported_kotlin_matrix_from_gradle_properties() -> None:
    release_text = _template_text("gradle-files", ".github", "workflows", "compiler-plugin-release-publish.yml.jinja2")
    snapshot_text = _template_text(
        "gradle-files", ".github", "workflows", "compiler-plugin-snapshot-publish.yml.jinja2"
    )

    assert "supportedKotlinVersions" in release_text
    assert "supportedKotlinVersions" in snapshot_text
    assert "determine-kotlin-matrix" in release_text
    assert "determine-kotlin-matrix" in snapshot_text


def test_compiler_plugin_publish_workflows_split_core_and_compiler_jobs() -> None:
    release_text = _template_text("gradle-files", ".github", "workflows", "compiler-plugin-release-publish.yml.jinja2")
    snapshot_text = _template_text(
        "gradle-files", ".github", "workflows", "compiler-plugin-snapshot-publish.yml.jinja2"
    )

    assert "publish-core:" in release_text
    assert "publish-compiler-plugin:" in release_text
    assert "github-release:" in release_text
    assert "repo_base_version_print_command" in release_text
    assert "compiler_release_publish_command" in release_text

    assert "publish-core:" in snapshot_text
    assert "publish-compiler-plugin:" in snapshot_text
    assert "compiler_base_version_print_command" in snapshot_text
    assert "compiler_snapshot_publish_command" in snapshot_text
