from __future__ import annotations

import os
from pathlib import Path


def _write_workspace(tmp_path: Path, root_clj: str) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "root.clj").write_text(root_clj, encoding="utf-8")
    (tmp_path / "root.private.clj").write_text('(github-token "dummy")\n', encoding="utf-8")


def _load_config_from_workspace(workspace_root: Path):
    from dev.config import load_config

    cwd = Path.cwd()
    os.chdir(workspace_root)
    try:
        return load_config()
    finally:
        os.chdir(cwd)


def _load_subset_config(subset_path: Path):
    subset_workspace = subset_path.parent / "subset-workspace"
    subset_workspace.mkdir(parents=True, exist_ok=True)
    (subset_workspace / "root.clj").write_text(subset_path.read_text(encoding="utf-8"), encoding="utf-8")
    (subset_workspace / "root.private.clj").write_text('(github-token "dummy")\n', encoding="utf-8")
    return _load_config_from_workspace(subset_workspace)


def test_config_cut_includes_transitive_project_dependencies_and_library_defs(tmp_path: Path) -> None:
    from dev.tasks.config_cut import config_cut

    workspace_root = tmp_path / "workspace"
    _write_workspace(
        workspace_root,
        "\n".join(
            [
                '(define ktor-version "3.3.0")',
                '(define-maven-library "ktor-client-core" "io.ktor:ktor-client-core:${ktor-version}")',
                '(default-maven-project-group "one.wabbit")',
                '('
                'gradle "base" '
                ':version "0.1.0" '
                ':features [(jvm-kotlin-library)] '
                ':dependencies ["ktor-client-core"])',
                '('
                'gradle "app" '
                ':version "0.1.0" '
                ':features [(jvm-kotlin-library)] '
                ':dependencies [":base"])',
                '('
                'gradle "unused" '
                ':version "0.1.0" '
                ':features [(jvm-kotlin-library)])',
                "",
            ]
        ),
    )

    cwd = Path.cwd()
    os.chdir(workspace_root)
    try:
        subset_path = workspace_root / "subset.clj"
        selected = config_cut(str(subset_path), ["app"])
    finally:
        os.chdir(cwd)

    assert selected == ["app", "base"]
    subset_text = subset_path.read_text(encoding="utf-8")
    assert '(define ktor-version "3.3.0")' in subset_text
    assert 'define-maven-library "ktor-client-core"' in subset_text
    assert 'gradle "base"' in subset_text
    assert 'gradle "app"' in subset_text
    assert 'gradle "unused"' not in subset_text

    subset_config = _load_subset_config(subset_path)
    assert set(subset_config.defined_projects) == {"app", "base"}


def test_config_cut_trims_repo_projects_and_drops_missing_docs_project(tmp_path: Path) -> None:
    from dev.tasks.config_cut import config_cut

    workspace_root = tmp_path / "workspace"
    _write_workspace(
        workspace_root,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(repo "demo"',
                '    :repo "wabbit-corp/demo"',
                '    :docsProject "docs"',
                "    :projects [",
                '        (gradle "lib" :version "0.1.0" :features [(jvm-kotlin-library)])',
                '        (gradle "docs" :version "0.1.0" :features [(jvm-kotlin-library)])',
                "    ])",
                "",
            ]
        ),
    )

    cwd = Path.cwd()
    os.chdir(workspace_root)
    try:
        subset_path = workspace_root / "demo-subset.clj"
        selected = config_cut(str(subset_path), ["demo/lib"])
    finally:
        os.chdir(cwd)

    assert selected == ["demo/lib"]
    subset_text = subset_path.read_text(encoding="utf-8")
    assert 'repo "demo"' in subset_text
    assert 'gradle "lib"' in subset_text
    assert 'gradle "docs"' not in subset_text
    assert ':docsProject "docs"' not in subset_text

    subset_config = _load_subset_config(subset_path)
    assert set(subset_config.defined_projects) == {"demo/lib"}
    assert subset_config.defined_repos["demo"].docs_project_id is None


def test_config_cut_includes_local_plugin_project_dependencies(tmp_path: Path) -> None:
    from dev.tasks.config_cut import config_cut

    workspace_root = tmp_path / "workspace"
    _write_workspace(
        workspace_root,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(define-kotlin-plugin "demo-plugin" ":plugin")',
                '('
                'gradle "plugin" '
                ':version "0.1.0" '
                ':gradlePluginId "one.wabbit.demo-plugin" '
                ':features [(kotlin-gradle-plugin-library)])',
                '('
                'gradle "app" '
                ':version "0.1.0" '
                ':features [(jvm-kotlin-library) (gradle-plugin "demo-plugin")])',
                "",
            ]
        ),
    )

    cwd = Path.cwd()
    os.chdir(workspace_root)
    try:
        subset_path = workspace_root / "plugin-subset.clj"
        selected = config_cut(str(subset_path), ["app"])
    finally:
        os.chdir(cwd)

    assert selected == ["app", "plugin"]
    subset_text = subset_path.read_text(encoding="utf-8")
    assert 'define-kotlin-plugin "demo-plugin" ":plugin"' in subset_text
    assert 'gradle "plugin"' in subset_text
    assert 'gradle "app"' in subset_text

    subset_config = _load_subset_config(subset_path)
    assert set(subset_config.defined_projects) == {"app", "plugin"}


def test_config_cut_preserves_workspace_defaults_needed_by_setup(tmp_path: Path) -> None:
    from dev.tasks.config_cut import config_cut

    workspace_root = tmp_path / "workspace"
    _write_workspace(
        workspace_root,
        "\n".join(
            [
                '(python "pkg" :version "0.1.0")',
                '(default-company-email "legal@example.com")',
                '(default-company-legal-name "Old Legal Co")',
                '(default-company-legal-name "Example Legal Co")',
                '(default-company-short-name "Example Co")',
                '(code-owner "Owner One" "owner1@example.com")',
                '(code-owner "Owner Two" "owner2@example.com")',
                '(git-user "Example Dev" "dev@example.com")',
                "",
            ]
        ),
    )

    cwd = Path.cwd()
    os.chdir(workspace_root)
    try:
        subset_path = workspace_root / "workspace-defaults-subset.clj"
        selected = config_cut(str(subset_path), ["pkg"])
    finally:
        os.chdir(cwd)

    assert selected == ["pkg"]
    subset_text = subset_path.read_text(encoding="utf-8")
    assert '(default-company-email "legal@example.com")' in subset_text
    assert '(default-company-legal-name "Old Legal Co")' not in subset_text
    assert '(default-company-legal-name "Example Legal Co")' in subset_text
    assert '(default-company-short-name "Example Co")' in subset_text
    assert '(code-owner "Owner One" "owner1@example.com")' in subset_text
    assert '(code-owner "Owner Two" "owner2@example.com")' in subset_text
    assert '(git-user "Example Dev" "dev@example.com")' in subset_text

    subset_config = _load_subset_config(subset_path)
    assert subset_config.default_company_email == "legal@example.com"
    assert subset_config.default_company_legal_name == "Example Legal Co"
    assert subset_config.default_company_short_name == "Example Co"
    assert subset_config.default_git_user_name == "Example Dev"
    assert subset_config.default_git_user_email == "dev@example.com"
    assert len(subset_config.default_code_owners) == 2


def test_config_cut_includes_ambient_gradle_plugin_definitions_needed_by_setup(tmp_path: Path) -> None:
    from dev.tasks.config_cut import config_cut

    workspace_root = tmp_path / "workspace"
    _write_workspace(
        workspace_root,
        "\n".join(
            [
                '(define kotlinx-serialization-version "1.9.0")',
                '(define-kotlin-plugin "kotlin-jvm" "org.jetbrains.kotlin.jvm:2.3.10")',
                '(define-kotlin-plugin "shadow" "com.gradleup.shadow:8.3.0")',
                '(define-maven-library "kotlinx-serialization-core" "org.jetbrains.kotlinx:kotlinx-serialization-core:${kotlinx-serialization-version}")',
                '(default-maven-project-group "one.wabbit")',
                '('
                'gradle "demo" '
                ':version "0.1.0" '
                ':features [(jvm-kotlin-library)])',
                "",
            ]
        ),
    )

    cwd = Path.cwd()
    os.chdir(workspace_root)
    try:
        subset_path = workspace_root / "gradle-plugins-subset.clj"
        selected = config_cut(str(subset_path), ["demo"])
    finally:
        os.chdir(cwd)

    assert selected == ["demo"]
    subset_text = subset_path.read_text(encoding="utf-8")
    assert '(define kotlinx-serialization-version "1.9.0")' in subset_text
    assert '(define-kotlin-plugin "kotlin-jvm" "org.jetbrains.kotlin.jvm:2.3.10")' in subset_text
    assert '(define-kotlin-plugin "shadow" "com.gradleup.shadow:8.3.0")' in subset_text
    assert (
        '(define-maven-library "kotlinx-serialization-core" '
        '"org.jetbrains.kotlinx:kotlinx-serialization-core:${kotlinx-serialization-version}")'
    ) in subset_text

    subset_config = _load_subset_config(subset_path)
    assert subset_config.plugins["kotlin-jvm"].version == "2.3.10"
    assert subset_config.plugins["shadow"].version == "8.3.0"
    assert (
        subset_config.libraries["kotlinx-serialization-core"].maven_urn.__str__()
        == "org.jetbrains.kotlinx:kotlinx-serialization-core:1.9.0"
    )
