from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import jinja2
import pytest
from git import Repo

if TYPE_CHECKING:
    from dev.config import Config, DataProject, PremakeProject, PurescriptProject, PythonApplication, PythonProject
    from dev.tasks.setup import RepoSetupContext


def _load_repo_config(repo_root: Path) -> Config:
    from dev.config import load_config

    candidate_roots = [repo_root, repo_root / "test"]
    for candidate in candidate_roots:
        if (candidate / "root.clj").is_file() and (candidate / "root.private.clj").is_file():
            cwd = os.getcwd()
            os.chdir(candidate)
            try:
                return load_config()
            finally:
                os.chdir(cwd)
    pytest.skip("No root.clj/root.private.clj fixture available for setup context tests")


def _make_python_project(
    path: Path, github_repo: str | None = None, application: PythonApplication | None = None
) -> PythonProject:
    from dev.config import OwnershipType, PythonProject

    return PythonProject(
        path=path,
        name="pkg",
        version=None,
        description=None,
        authors=[],
        license=None,
        github_repo=github_repo,
        requires_python=None,
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        application=application,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=False,
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
    )


def _make_purescript_project(path: Path, github_repo: str | None = None) -> PurescriptProject:
    from dev.config import OwnershipType, PurescriptProject

    return PurescriptProject(
        path=path,
        name="pkg",
        description=None,
        authors=[],
        quarantine=False,
        publish=False,
        license="MIT",
        github_repo=github_repo,
        ownership=OwnershipType.WABBIT,
        version=None,
        resolved_dependencies=[],
    )


def _make_premake_project(path: Path, github_repo: str | None = None) -> PremakeProject:
    from dev.config import OwnershipType, PremakeProject

    return PremakeProject(
        path=path,
        name="pkg",
        description=None,
        authors=[],
        quarantine=False,
        publish=False,
        license="AGPL",
        github_repo=github_repo,
        ownership=OwnershipType.WABBIT,
        version=None,
        resolved_dependencies=[],
        test_license="LicenseRef-Wabbit-Public-Test-License",
    )


def _make_data_project(path: Path, github_repo: str | None = None) -> DataProject:
    from dev.config import DataProject, OwnershipType

    return DataProject(
        path=path,
        name="pkg",
        description=None,
        authors=[],
        quarantine=False,
        publish=False,
        license="AGPL",
        github_repo=github_repo,
        ownership=OwnershipType.WABBIT,
        version=None,
        resolved_dependencies=[],
        test_license="LicenseRef-Wabbit-Public-Test-License",
    )


def _make_setup_context(pyproject_template: str, codespell_words: str = "wabbit\n") -> RepoSetupContext:
    import dev.tasks.setup as setup_module

    repo_root = Path(__file__).resolve().parents[1]
    config = _load_repo_config(repo_root)
    config.default_git_user_email = "test@example.com"
    config.default_git_user_name = "Test User"

    return setup_module.RepoSetupContext(
        config=config,
        known_repo_names=[],
        known_github_repos={},
        is_github_api_available=True,
        repo_template=Path("."),
        licenses={},
        coc=jinja2.Template(""),
        gitignore_template=jinja2.Template("# base\n"),
        cla=jinja2.Template(""),
        cla_explanations=jinja2.Template(""),
        contributor_privacy_policy=jinja2.Template(""),
        settings_template=jinja2.Template(""),
        settings_local_template=jinja2.Template(""),
        subproject_settings_template=jinja2.Template(""),
        build_template=jinja2.Template(""),
        subproject_build_template=jinja2.Template(""),
        subproject_build_kmp_template=jinja2.Template(""),
        gradle_gitignore_template=jinja2.Template(""),
        gradle_properties_template=jinja2.Template(""),
        python_gitignore_template=jinja2.Template("# python\n"),
        purescript_gitignore_template=jinja2.Template(""),
        python_pyproject_template=jinja2.Template(pyproject_template),
        python_pyrightconfig_template=jinja2.Template(
            '{\n  "include": {{ include_json }},\n  "exclude": {{ exclude_json }},\n  "pythonVersion": "{{ python_version }}"\n}\n'
        ),
        python_mkdocs_template=jinja2.Template("site_name: {{ site_name }}\n"),
        python_docs_index_template=jinja2.Template("# {{ project_name }}\n"),
        python_docs_installation_template=jinja2.Template("# Install {{ package_name }}\n"),
        python_docs_development_template=jinja2.Template("# Dev {{ project_name }}\n"),
        python_contributing_template=jinja2.Template("# Contributing {{ project_name }}\n"),
        python_docs_quality_workflow_template=jinja2.Template("name: Docs Quality\n"),
        python_docs_deploy_workflow_template=jinja2.Template("name: Docs Deploy\n"),
        gradle_release_publish_workflow_template=jinja2.Template("name: Release Publish\n"),
        gradle_snapshot_publish_workflow_template=jinja2.Template("name: Snapshot Publish\n"),
        gradle_compiler_plugin_release_publish_workflow_template=jinja2.Template(
            "name: Compiler Release Publish\n"
        ),
        gradle_compiler_plugin_snapshot_publish_workflow_template=jinja2.Template(
            "name: Compiler Snapshot Publish\n"
        ),
        gradle_docs_quality_workflow_template=jinja2.Template("name: Gradle Docs Quality\n"),
        gradle_docs_deploy_workflow_template=jinja2.Template("name: Gradle Docs Deploy\n"),
        python_codespell_ignore_words_template=jinja2.Template(codespell_words),
        python_build_executable_template=jinja2.Template(
            '#!/usr/bin/env python3\nAPP_NAME = "{{ app_name }}"\nENTRYPOINT = "{{ entrypoint_path }}"\n'
        ),
        mode=setup_module.RepoSetupMode.LOCAL,
    )


def _noop_write_callback(_ctx: object, _project: object) -> None:
    return None


def test_setup_project_creates_directory_before_project_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "missing" / "pkg")
    called = False

    def fake_setup_python_project(ctx: object, python_project: PythonProject, interactive: bool = True) -> None:
        nonlocal called
        called = True
        assert python_project.path.exists()
        assert python_project.path.is_dir()

    monkeypatch.setattr(setup_module, "setup_python_project", fake_setup_python_project)

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.mode = setup_module.RepoSetupMode.LOCAL

    setup_module.setup_project(ctx, project, interactive=False)
    assert called


def test_setup_project_skips_remote_check_when_github_api_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / ".gitignore").write_text("# test\n", encoding="utf-8")
    repo = Repo.init(project.path)
    repo.close()

    warning_messages: list[str] = []
    error_messages: list[str] = []

    def fake_setup_python_project(ctx: object, python_project: PythonProject, interactive: bool = True) -> None:
        del ctx, python_project, interactive

    def capture_warning(message: str) -> None:
        warning_messages.append(message)

    def capture_error(message: str) -> None:
        error_messages.append(message)

    monkeypatch.setattr(setup_module, "setup_python_project", fake_setup_python_project)
    monkeypatch.setattr(setup_module, "warning", capture_warning)
    monkeypatch.setattr(setup_module, "error", capture_error)

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.is_github_api_available = False
    ctx.mode = setup_module.RepoSetupMode.LOCAL

    setup_module.setup_project(ctx, project, interactive=False)

    assert "GitHub API unavailable; skipping remote existence check." in warning_messages
    assert f"Remote repository {project.github_repo} does not exist" not in error_messages


def test_setup_python_project_generates_docs_and_workflows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module
    from dev.generated_files import verify_managed_file_integrity

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        ),
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    assert (project.path / "pyproject.toml").is_file()
    assert (project.path / "pyrightconfig.json").is_file()
    assert (project.path / "mkdocs.yml").is_file()
    assert (project.path / "docs" / "index.md").is_file()
    assert (project.path / "docs" / "installation.md").is_file()
    assert (project.path / "docs" / "development.md").is_file()
    assert (project.path / "CONTRIBUTING.md").is_file()
    assert (project.path / ".codespell-ignore-words.txt").is_file()
    assert (project.path / ".github" / "workflows" / "docs-quality.yml").is_file()
    assert (project.path / ".github" / "workflows" / "docs-deploy.yml").is_file()
    pyproject_text = (project.path / "pyproject.toml").read_text(encoding="utf-8")
    assert pyproject_text.startswith("# Generated by app-wabbit-dev setup. Do not edit by hand.\n")
    assert "managed-integrity-v1:" in pyproject_text
    assert "pyproject.extra.toml" in pyproject_text
    assert verify_managed_file_integrity(project.path / "pyproject.toml").is_valid
    mkdocs_text = (project.path / "mkdocs.yml").read_text(encoding="utf-8")
    assert mkdocs_text.startswith("# Generated by app-wabbit-dev setup. Do not edit by hand.\n")
    assert "managed-integrity-v1:" in mkdocs_text
    assert "mkdocs.extra.yml" in mkdocs_text
    assert verify_managed_file_integrity(project.path / "mkdocs.yml").is_valid
    requirements_dev = (project.path / "requirements-dev.txt").read_text(encoding="utf-8")
    assert requirements_dev.startswith("# Generated by app-wabbit-dev setup. Do not edit by hand.\n")
    assert "managed-integrity-v1:" in requirements_dev
    assert verify_managed_file_integrity(project.path / "requirements-dev.txt").is_valid
    assert "pytest>=8.0.0,<9.0.0" in requirements_dev
    assert "mypy>=1.10.0,<2.0.0" in requirements_dev
    assert "ruff>=0.8.0,<1.0.0" in requirements_dev
    assert "black>=24.0.0,<26.0.0" in requirements_dev
    assert "coverage>=7.0.0,<8.0.0" in requirements_dev
    assert "build>=1.2.0,<2.0.0" in requirements_dev
    assert "twine>=5.0.0,<6.0.0" in requirements_dev
    assert "pyinstaller>=6.9.0,<7.0.0" not in requirements_dev


def test_setup_python_project_keeps_optional_docs_quality_hooks_when_sources_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")
    (project.path / "scripts").mkdir(parents=True, exist_ok=True)
    (project.path / "tests").mkdir(parents=True, exist_ok=True)
    (project.path / "scripts" / "check_changelog_guard.py").write_text("print('ok')\n", encoding="utf-8")
    (project.path / "scripts" / "generate_api_docs.py").write_text("print('ok')\n", encoding="utf-8")
    (project.path / "scripts" / "check_docs_links.py").write_text("print('ok')\n", encoding="utf-8")
    (project.path / "tests" / "test_docs_snippets.py").write_text("def test_docs():\n    pass\n", encoding="utf-8")

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        ),
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    workflow_text = (project.path / ".github" / "workflows" / "docs-quality.yml").read_text(encoding="utf-8")
    assert "python scripts/check_changelog_guard.py" in workflow_text
    assert "python scripts/generate_api_docs.py --check" in workflow_text
    assert "python scripts/check_docs_links.py" in workflow_text
    assert "python -m pytest -q tests/test_docs_snippets.py" in workflow_text


def test_setup_purescript_project_generates_legal_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_purescript_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)

    wrote_legal_files = False
    wrote_banner = False

    def fake_write_wabbit_legal_files(_ctx: object, purescript_project: PurescriptProject) -> None:
        nonlocal wrote_legal_files
        wrote_legal_files = True
        assert purescript_project is project

    def fake_write_banner(_ctx: object, purescript_project: PurescriptProject) -> None:
        nonlocal wrote_banner
        wrote_banner = True
        assert purescript_project is project

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", fake_write_wabbit_legal_files)
    monkeypatch.setattr(setup_module, "_write_banner", fake_write_banner)

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')

    setup_module.setup_purescript_project(ctx, project, interactive=False)

    assert (project.path / ".gitignore").is_file()
    assert wrote_legal_files
    assert wrote_banner


@pytest.mark.parametrize(
    ("project_factory", "project_type_name"),
    [
        (_make_premake_project, "PremakeProject"),
        (_make_data_project, "DataProject"),
    ],
)
def test_setup_project_generates_legal_files_for_data_like_projects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_factory: object,
    project_type_name: str,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = project_factory(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)

    written_projects: list[object] = []

    def fake_write_wabbit_legal_files(_ctx: object, current_project: object) -> None:
        written_projects.append(current_project)

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", fake_write_wabbit_legal_files)

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.mode = setup_module.RepoSetupMode.LOCAL
    ctx.is_github_api_available = False

    setup_module.setup_project(ctx, project, interactive=False, commit_changes=False, allow_push=False)

    assert written_projects == [project], project_type_name


def test_setup_python_project_generates_app_build_script_for_python_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module
    from dev.config import PythonApplication

    project = _make_python_project(
        tmp_path / "pkg",
        github_repo="org/pkg",
        application=PythonApplication(
            script="pkg-cli",
            entry="pkg.cli:main",
            path="src/pkg/cli.py",
            aliases=["pkg"],
        ),
    )
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
            "{% if has_scripts %}[tool.poetry.scripts]\n{{ scripts_block }}\n{% endif %}"
        ),
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    build_script = project.path / "scripts" / "build_executable.py"
    assert build_script.is_file()
    content = build_script.read_text(encoding="utf-8")
    assert 'APP_NAME = "pkg-cli"' in content
    assert 'ENTRYPOINT = "src/pkg/cli.py"' in content
    requirements_dev = (project.path / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "pyinstaller>=6.9.0,<7.0.0" in requirements_dev


def test_setup_python_project_preserves_existing_gitignore_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")
    (project.path / ".gitignore").write_text("# custom\n/custom-data/\n", encoding="utf-8")

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        ),
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    gitignore_content = (project.path / ".gitignore").read_text(encoding="utf-8")
    assert "# custom" in gitignore_content
    assert "/custom-data/" in gitignore_content
    assert "# base" in gitignore_content
    assert "# python" in gitignore_content


def test_setup_python_project_recovers_tracked_gitignore_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")
    (project.path / ".gitignore").write_text("# tracked\n/.private.yml\n/custom-data/\n", encoding="utf-8")

    repo = Repo.init(project.path)
    repo.index.add([".gitignore", "README.md"])
    repo.index.commit("Initial commit")
    repo.close()

    (project.path / ".gitignore").write_text("# stale generated copy\n# python\n", encoding="utf-8")

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        ),
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    gitignore_content = (project.path / ".gitignore").read_text(encoding="utf-8")
    assert "# tracked" in gitignore_content
    assert "/.private.yml" in gitignore_content
    assert "/custom-data/" in gitignore_content
    assert "# base" in gitignore_content
    assert "# python" in gitignore_content


def test_setup_python_project_preserves_existing_docs_and_refreshes_workflows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")

    existing_files = {
        project.path / "pyrightconfig.json": "preexisting pyright config\n",
        project.path / "mkdocs.yml": "preexisting mkdocs\n",
        project.path / "docs" / "index.md": "preexisting index\n",
        project.path / "docs" / "installation.md": "preexisting installation\n",
        project.path / "docs" / "development.md": "preexisting development\n",
        project.path / "CONTRIBUTING.md": "preexisting contributing\n",
        project.path / ".github" / "workflows" / "docs-quality.yml": "preexisting quality workflow\n",
        project.path / ".github" / "workflows" / "docs-deploy.yml": "preexisting deploy workflow\n",
    }
    for path, content in existing_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        )
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    preserved_paths = {
        project.path / "pyrightconfig.json",
        project.path / "mkdocs.yml",
        project.path / "docs" / "index.md",
        project.path / "docs" / "installation.md",
        project.path / "docs" / "development.md",
        project.path / "CONTRIBUTING.md",
    }
    for path, content in existing_files.items():
        if path in preserved_paths:
            assert path.read_text(encoding="utf-8") == content

    assert (project.path / ".github" / "workflows" / "docs-quality.yml").read_text(encoding="utf-8") == (
        "name: Docs Quality\n"
    )
    assert (project.path / ".github" / "workflows" / "docs-deploy.yml").read_text(encoding="utf-8") == (
        "name: Docs Deploy\n"
    )


def test_setup_python_project_appends_pyproject_extra_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module
    from dev.generated_files import verify_managed_file_integrity

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")
    (project.path / "pyproject.extra.toml").write_text(
        '[tool.pyright]\nvenvPath = ".venvs"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        )
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    pyproject_text = (project.path / "pyproject.toml").read_text(encoding="utf-8")
    assert "Additional unmanaged sections from pyproject.extra.toml" in pyproject_text
    assert 'venvPath = ".venvs"' in pyproject_text
    assert verify_managed_file_integrity(project.path / "pyproject.toml").is_valid
    parsed = tomllib.loads(pyproject_text)
    assert parsed["tool"]["pyright"]["venvPath"] == ".venvs"


def test_setup_python_project_rejects_conflicting_pyproject_extra_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")
    (project.path / "pyproject.extra.toml").write_text(
        '[tool.poetry]\nname = "override"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        )
    )

    with pytest.raises(ValueError, match="pyproject.extra.toml must append only valid, non-conflicting TOML sections"):
        setup_module.setup_python_project(ctx, project, interactive=False)


def test_setup_python_project_appends_mkdocs_extra_yml_to_generated_mkdocs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module
    from dev.generated_files import verify_managed_file_integrity

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")
    (project.path / "mkdocs.extra.yml").write_text(
        "plugins:\n  - search\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        )
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    mkdocs_text = (project.path / "mkdocs.yml").read_text(encoding="utf-8")
    assert "Additional unmanaged top-level keys from mkdocs.extra.yml" in mkdocs_text
    assert "plugins:" in mkdocs_text
    assert "  - search" in mkdocs_text
    assert verify_managed_file_integrity(project.path / "mkdocs.yml").is_valid


def test_setup_python_project_rejects_conflicting_mkdocs_extra_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")
    (project.path / "mkdocs.extra.yml").write_text(
        "site_name: override\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        )
    )

    with pytest.raises(ValueError, match="mkdocs.extra.yml redefines generated MkDocs top-level keys: site_name"):
        setup_module.setup_python_project(ctx, project, interactive=False)


def test_setup_python_project_merges_codespell_words_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")
    (project.path / ".codespell-ignore-words.txt").write_text("langmu\nwabbit\n", encoding="utf-8")

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        ),
        codespell_words="wabbit\nnewword\n",
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    content = (project.path / ".codespell-ignore-words.txt").read_text(encoding="utf-8").splitlines()
    assert content == ["langmu", "wabbit", "newword"]


def test_setup_python_project_removes_docs_workflows_when_docs_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.docs_enabled = False
    project.docs_system = None
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")
    (project.path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (project.path / ".github" / "workflows" / "docs-quality.yml").write_text("old\n", encoding="utf-8")
    (project.path / ".github" / "workflows" / "docs-deploy.yml").write_text("old\n", encoding="utf-8")

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", _noop_write_callback)
    monkeypatch.setattr(setup_module, "_write_banner", _noop_write_callback)

    ctx = _make_setup_context(
        pyproject_template=(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        )
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    assert not (project.path / ".github" / "workflows" / "docs-quality.yml").exists()
    assert not (project.path / ".github" / "workflows" / "docs-deploy.yml").exists()


def test_targeted_prod_setup_omits_cross_repo_gradle_projects_from_root_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, GradleProject, KotlinPluginDefinition, OwnershipType, RepoDefinition, Version

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        repo_root_path: Path,
        gradle_project_name: str,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=path.name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license="AGPL",
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.WABBIT,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features={},
            platforms=["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0] if "/" in project_id else None,
            repo_root=repo_root_path,
            managed_by_setup=False,
            gradle_root=repo_root_path,
            module_dir=Path(path.name),
            gradle_project_name=gradle_project_name,
        )

    jeeves_root = tmp_path / "jeeves"
    external_root = tmp_path / "kotlin-dotenv-parser"
    api_project = make_gradle_project(
        jeeves_root / "api",
        project_id="jeeves/api",
        repo_root_path=jeeves_root,
        gradle_project_name="jeeves-api",
    )
    server_project = make_gradle_project(
        jeeves_root / "server",
        project_id="jeeves/server",
        repo_root_path=jeeves_root,
        gradle_project_name="jeeves-server",
    )
    external_project = make_gradle_project(
        external_root,
        project_id="kotlin-dotenv-parser",
        repo_root_path=external_root,
        gradle_project_name="kotlin-dotenv-parser",
    )

    config = Config(raw=Document([]))
    config.defined_projects.update(
        {
            "jeeves/api": api_project,
            "kotlin-dotenv-parser": external_project,
            "jeeves/server": server_project,
        }
    )
    config.defined_repos["jeeves"] = RepoDefinition(
        repo_id="jeeves",
        path=jeeves_root,
        github_repo="org/jeeves",
        gradle_root_project_name="jeeves",
        jvm_policy=None,
        project_ids=["jeeves/api", "jeeves/server"],
    )
    config.plugins["kotlin-jvm"] = KotlinPluginDefinition(plugin_id="org.jetbrains.kotlin.jvm", version="2.2.20")

    root_write_calls: list[tuple[Path, list[str], bool]] = []

    def fake_load_config() -> Config:
        return config

    def fake_toposort_projects(_projects: object, target_project: object = None) -> list[str]:
        assert target_project == ["jeeves/server"]
        return ["jeeves/api", "kotlin-dotenv-parser", "jeeves/server"]

    def fake_create_repo_setup_context(_config: Config, mode: object) -> object:
        return SimpleNamespace(config=config, mode=mode)

    monkeypatch.setattr(setup_module, "load_config", fake_load_config)
    monkeypatch.setattr(setup_module, "toposort_projects", fake_toposort_projects)
    monkeypatch.setattr(setup_module, "create_repo_setup_context", fake_create_repo_setup_context)
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        setup_module,
        "_write_gradle_root_files",
        lambda _ctx, *, root_path, seed_projects, include_external_dependencies, **_kwargs: root_write_calls.append(
            (root_path, [project.project_id for project in seed_projects], include_external_dependencies)
        ),
    )
    monkeypatch.setattr(setup_module, "_write_repo_root_wabbit_legal_documents", lambda *_args, **_kwargs: None)

    setup_module.setup(setup_module.RepoSetupMode.PROD, interactive=False, project="jeeves/server")

    assert root_write_calls == [
        (jeeves_root, ["jeeves/api", "jeeves/server"], False),
    ]


def test_setup_prod_removes_stale_gradle_local_overlay_from_selected_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, GradleProject, KotlinPluginDefinition, OwnershipType, RepoDefinition, Version

    repo_root = tmp_path / "kotlin-web-common"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "settings.local.gradle.kts").write_text("// stale local overlay\n", encoding="utf-8")

    project = GradleProject(
        path=repo_root,
        group_name="one.wabbit",
        name="kotlin-web-common",
        version=Version.parse("1.1.0"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo="wabbit-corp/kotlin-web-common",
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        platforms=["jvm"],
        source_set_dependencies={},
        project_id="kotlin-web-common",
        repo_id="kotlin-web-common",
        repo_root=repo_root,
        gradle_root=repo_root,
        module_dir=Path("."),
        gradle_project_name="kotlin-web-common",
    )

    config = Config(raw=Document([]))
    config.defined_projects["kotlin-web-common"] = project
    config.defined_repos["kotlin-web-common"] = RepoDefinition(
        repo_id="kotlin-web-common",
        path=repo_root,
        github_repo="wabbit-corp/kotlin-web-common",
        gradle_root_project_name="kotlin-web-common",
        jvm_policy=None,
        project_ids=["kotlin-web-common"],
    )
    config.plugins["kotlin-jvm"] = KotlinPluginDefinition(plugin_id="org.jetbrains.kotlin.jvm", version="2.3.10")

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(setup_module, "toposort_projects", lambda _projects, target_project=None: ["kotlin-web-common"])
    monkeypatch.setattr(setup_module, "create_repo_setup_context", lambda _config, mode: SimpleNamespace(config=config, mode=mode))
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "_write_gradle_root_files", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "_write_repo_root_wabbit_legal_documents", lambda *_args, **_kwargs: None)

    setup_module.setup(setup_module.RepoSetupMode.PROD, interactive=False, project="kotlin-web-common")

    assert not (repo_root / "settings.local.gradle.kts").exists()


def test_setup_treats_empty_projects_list_as_all_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, GradleProject, KotlinPluginDefinition, OwnershipType, Version

    demo_root = tmp_path / "demo"
    demo_project = GradleProject(
        path=demo_root,
        group_name="one.wabbit",
        name="demo",
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo="org/demo",
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        platforms=["jvm"],
        source_set_dependencies={},
        project_id="demo",
        repo_id=None,
        repo_root=demo_root,
        gradle_root=demo_root,
        module_dir=Path("."),
        gradle_project_name="demo",
    )

    config = Config(raw=Document([]))
    config.default_maven_project_group = "one.wabbit"
    config.defined_projects["demo"] = demo_project
    config.plugins["kotlin-jvm"] = KotlinPluginDefinition(plugin_id="org.jetbrains.kotlin.jvm", version="2.2.20")

    root_write_calls: list[tuple[Path, list[str], bool, bool]] = []
    setup_calls: list[str] = []

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(
        setup_module,
        "toposort_projects",
        lambda *_args, **_kwargs: pytest.fail("toposort_projects should not be called when projects=[] means all projects"),
    )
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, mode: SimpleNamespace(config=config, mode=mode),
    )
    monkeypatch.setattr(
        setup_module,
        "_write_gradle_root_files",
        lambda _ctx, *, root_path, seed_projects, include_external_dependencies, write_dependency_substitutions, **_kwargs: root_write_calls.append(
            (
                root_path,
                [project.project_id for project in seed_projects],
                include_external_dependencies,
                write_dependency_substitutions,
            )
        ),
    )
    monkeypatch.setattr(
        setup_module,
        "setup_project",
        lambda _ctx, project, **_kwargs: setup_calls.append(project.project_id),
    )
    monkeypatch.setattr(setup_module, "_write_gradle_local_overlay", lambda *_args, **_kwargs: None)

    setup_module.setup(setup_module.RepoSetupMode.LOCAL, interactive=False, projects=[])

    assert root_write_calls == [
        (Path("."), ["demo"], True, True),
    ]
    assert setup_calls == ["demo"]


def test_setup_writes_repo_root_legal_docs_for_repo_managed_gradle_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from mu.types import Document

    import dev.tasks.setup as setup_module
    import dev.tasks.setup_common as setup_common_module
    from dev.config import Config, GradleProject, KotlinPluginDefinition, OwnershipType, RepoDefinition, Version

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        repo_root_path: Path,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=path.name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license="AGPL",
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.WABBIT,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features={},
            platforms=["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0],
            repo_root=repo_root_path,
            managed_by_setup=False,
            gradle_root=repo_root_path,
            module_dir=Path(path.name),
            gradle_project_name=path.name,
        )

    jeeves_root = tmp_path / "jeeves"
    api_project = make_gradle_project(
        jeeves_root / "api",
        project_id="jeeves/api",
        repo_root_path=jeeves_root,
    )
    impl_project = make_gradle_project(
        jeeves_root / "impl",
        project_id="jeeves/impl",
        repo_root_path=jeeves_root,
    )
    impl_project.license = "MIT"

    config = Config(raw=Document([]))
    config.defined_projects.update({"jeeves/api": api_project, "jeeves/impl": impl_project})
    config.defined_repos.update(
        {
            "jeeves": RepoDefinition(
                repo_id="jeeves",
                path=jeeves_root,
                github_repo="org/jeeves",
                gradle_root_project_name="one.wabbit",
                jvm_policy=None,
                project_ids=["jeeves/api", "jeeves/impl"],
            )
        }
    )
    config.plugins["kotlin-jvm"] = KotlinPluginDefinition(plugin_id="org.jetbrains.kotlin.jvm", version="2.2.20")

    written_paths: list[Path] = []
    written_license_paths: list[Path] = []

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(setup_module, "toposort_projects", lambda _projects, target_project=None: ["jeeves/api"])
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, mode: SimpleNamespace(config=config, mode=mode),
    )
    monkeypatch.setattr(setup_module, "_write_gradle_root_files", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_common_module, "write_wabbit_legal_documents", lambda _ctx, project: written_paths.append(project.path))
    monkeypatch.setattr(setup_common_module, "write_wabbit_legal_files", lambda _ctx, project: written_license_paths.append(project.path))
    monkeypatch.setattr(setup_module, "_write_gradle_local_overlay", lambda *_args, **_kwargs: None)

    setup_module.setup(setup_module.RepoSetupMode.LOCAL, interactive=False, project="jeeves/api")

    assert written_paths == [jeeves_root]
    assert written_license_paths == []


def test_setup_writes_repo_root_license_when_repo_managed_gradle_project_licenses_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    import dev.tasks.setup_common as setup_common_module
    from dev.config import Config, GradleProject, KotlinPluginDefinition, OwnershipType, RepoDefinition, Version

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        repo_root_path: Path,
        license_name: str,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=path.name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license=license_name,
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.WABBIT,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features={},
            platforms=["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0],
            repo_root=repo_root_path,
            managed_by_setup=False,
            gradle_root=repo_root_path,
            module_dir=Path(path.name),
            gradle_project_name=path.name,
        )

    repo_root = tmp_path / "repo"
    api_project = make_gradle_project(
        repo_root / "api",
        project_id="repo/api",
        repo_root_path=repo_root,
        license_name="AGPL",
    )
    impl_project = make_gradle_project(
        repo_root / "impl",
        project_id="repo/impl",
        repo_root_path=repo_root,
        license_name="AGPL",
    )

    config = Config(raw=Document([]))
    config.defined_projects.update({"repo/api": api_project, "repo/impl": impl_project})
    config.defined_repos["repo"] = RepoDefinition(
        repo_id="repo",
        path=repo_root,
        github_repo="org/repo",
        gradle_root_project_name="one.wabbit",
        jvm_policy=None,
        project_ids=["repo/api", "repo/impl"],
    )
    config.plugins["kotlin-jvm"] = KotlinPluginDefinition(plugin_id="org.jetbrains.kotlin.jvm", version="2.2.20")

    written_license_paths: list[Path] = []
    written_document_paths: list[Path] = []

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(setup_module, "toposort_projects", lambda _projects, target_project=None: ["repo/api"])
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, mode: SimpleNamespace(config=config, mode=mode),
    )
    monkeypatch.setattr(setup_module, "_write_gradle_root_files", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        setup_common_module,
        "write_wabbit_legal_files",
        lambda _ctx, project: written_license_paths.append(project.path),
    )
    monkeypatch.setattr(
        setup_common_module,
        "write_wabbit_legal_documents",
        lambda _ctx, project: written_document_paths.append(project.path),
    )
    monkeypatch.setattr(setup_module, "_write_gradle_local_overlay", lambda *_args, **_kwargs: None)

    setup_module.setup(setup_module.RepoSetupMode.LOCAL, interactive=False, project="repo/api")

    assert written_license_paths == [repo_root]
    assert written_document_paths == []


def test_setup_repo_root_license_keeps_shared_test_license_when_some_repo_projects_do_not_set_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    import dev.tasks.setup_common as setup_common_module
    from dev.config import Config, GradleProject, KotlinPluginDefinition, OwnershipType, RepoDefinition, Version

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        repo_root_path: Path,
        test_license: str | None,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=path.name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license="AGPL",
            test_license=test_license,
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.WABBIT,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features={},
            platforms=["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0],
            repo_root=repo_root_path,
            managed_by_setup=False,
            gradle_root=repo_root_path,
            module_dir=Path(path.name),
            gradle_project_name=path.name,
        )

    repo_root = tmp_path / "repo"
    api_project = make_gradle_project(
        repo_root / "api",
        project_id="repo/api",
        repo_root_path=repo_root,
        test_license="LicenseRef-Wabbit-Public-Test-License",
    )
    quarantined_project = make_gradle_project(
        repo_root / "quarantined",
        project_id="repo/quarantined",
        repo_root_path=repo_root,
        test_license=None,
    )
    quarantined_project.quarantine = True

    config = Config(raw=Document([]))
    config.defined_projects.update({"repo/api": api_project, "repo/quarantined": quarantined_project})
    config.defined_repos["repo"] = RepoDefinition(
        repo_id="repo",
        path=repo_root,
        github_repo="org/repo",
        gradle_root_project_name="one.wabbit",
        jvm_policy=None,
        project_ids=["repo/api", "repo/quarantined"],
    )
    config.plugins["kotlin-jvm"] = KotlinPluginDefinition(plugin_id="org.jetbrains.kotlin.jvm", version="2.2.20")

    written_projects: list[GradleProject] = []

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(setup_module, "toposort_projects", lambda _projects, target_project=None: ["repo/api"])
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, mode: SimpleNamespace(config=config, mode=mode),
    )
    monkeypatch.setattr(setup_module, "_write_gradle_root_files", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        setup_common_module,
        "write_wabbit_legal_files",
        lambda _ctx, project: written_projects.append(project),
    )
    monkeypatch.setattr(
        setup_common_module,
        "write_wabbit_legal_documents",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(setup_module, "_write_gradle_local_overlay", lambda *_args, **_kwargs: None)

    setup_module.setup(setup_module.RepoSetupMode.LOCAL, interactive=False, project="repo/api")

    assert len(written_projects) == 1
    assert written_projects[0].path == repo_root
    assert written_projects[0].test_license == "LicenseRef-Wabbit-Public-Test-License"


def test_setup_does_not_commit_or_push_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, OwnershipType, PythonProject

    project_path = tmp_path / "demo"
    project = PythonProject(
        path=project_path,
        name="demo",
        version=None,
        description=None,
        authors=[],
        license=None,
        github_repo=None,
        requires_python=None,
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        application=None,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=False,
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
    )

    config = Config(raw=Document([]))
    config.defined_projects["demo"] = project

    setup_calls: list[tuple[str, bool, bool, bool]] = []

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(setup_module, "toposort_projects", lambda _projects, target_project=None: ["demo"])
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, mode: SimpleNamespace(config=config, mode=mode),
    )
    monkeypatch.setattr(setup_module, "_write_gradle_root_files", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "_write_gradle_local_overlay", lambda *_args, **_kwargs: None)

    def fake_setup_project(
        _ctx: object,
        setup_project_item: object,
        *,
        interactive: bool,
        commit_changes: bool,
        allow_push: bool,
    ) -> None:
        assert setup_project_item is project
        setup_calls.append((project.name, interactive, commit_changes, allow_push))

    monkeypatch.setattr(setup_module, "setup_project", fake_setup_project)

    setup_module.setup(setup_module.RepoSetupMode.PROD, interactive=False, project="demo")

    assert setup_calls == [("demo", False, False, False)]


def test_targeted_local_setup_does_not_write_workspace_root_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, GradleProject, KotlinPluginDefinition, OwnershipType, Version

    project = GradleProject(
        path=tmp_path / "demo",
        group_name="one.wabbit",
        name="demo",
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo="org/demo",
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        platforms=["jvm"],
        source_set_dependencies={},
        project_id="demo",
        repo_id=None,
        repo_root=tmp_path / "demo",
        managed_by_setup=True,
        gradle_root=tmp_path / "demo",
        module_dir=Path("."),
        gradle_project_name="demo",
    )

    config = Config(raw=Document([]))
    config.defined_projects["demo"] = project
    config.plugins["kotlin-jvm"] = KotlinPluginDefinition(plugin_id="org.jetbrains.kotlin.jvm", version="2.2.20")

    root_writes: list[Path] = []

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(setup_module, "toposort_projects", lambda _projects, target_project=None: ["demo"])
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, mode: SimpleNamespace(config=config, mode=mode),
    )
    monkeypatch.setattr(
        setup_module,
        "_write_gradle_root_files",
        lambda _ctx, *, root_path, **_kwargs: root_writes.append(root_path),
    )
    monkeypatch.setattr(setup_module, "_write_gradle_local_overlay", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)

    setup_module.setup(setup_module.RepoSetupMode.LOCAL, interactive=False, project="demo")

    assert Path(".") not in root_writes


def test_write_gradle_local_overlay_groups_external_builds_and_uses_correct_project_paths(tmp_path: Path) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, Dependency, GradleProject, OwnershipType, ProjectDependencyTarget, Version

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        repo_root_path: Path,
        gradle_root_path: Path,
        gradle_project_name: str,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=gradle_project_name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license="AGPL",
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.IMPORTED,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features={},
            platforms=["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0] if "/" in project_id else None,
            repo_root=repo_root_path,
            gradle_root=gradle_root_path,
            module_dir=Path(path.name),
            gradle_project_name=gradle_project_name,
        )

    repo_root = tmp_path / "jeeves"
    repo_root.mkdir(parents=True, exist_ok=True)
    local_project = make_gradle_project(
        repo_root / "server",
        project_id="jeeves/server",
        repo_root_path=repo_root,
        gradle_root_path=repo_root,
        gradle_project_name="jeeves-server",
    )

    standalone_root = tmp_path / "kotlin-dotenv-parser"
    standalone_project = make_gradle_project(
        standalone_root,
        project_id="kotlin-dotenv-parser",
        repo_root_path=standalone_root,
        gradle_root_path=standalone_root,
        gradle_project_name="kotlin-dotenv-parser",
    )

    shared_root = tmp_path / "shared"
    shared_api = make_gradle_project(
        shared_root / "api",
        project_id="shared/api",
        repo_root_path=shared_root,
        gradle_root_path=shared_root,
        gradle_project_name="shared-api",
    )
    shared_cli = make_gradle_project(
        shared_root / "cli",
        project_id="shared/cli",
        repo_root_path=shared_root,
        gradle_root_path=shared_root,
        gradle_project_name="shared-cli",
    )

    local_project.resolved_dependencies = [
        Dependency(scope=None, target=ProjectDependencyTarget(project="kotlin-dotenv-parser")),
        Dependency(scope=None, target=ProjectDependencyTarget(project="shared/api")),
        Dependency(scope=None, target=ProjectDependencyTarget(project="shared/cli")),
    ]

    config = Config(raw=Document([]))
    config.defined_projects.update(
        {
            "jeeves/server": local_project,
            "kotlin-dotenv-parser": standalone_project,
            "shared/api": shared_api,
            "shared/cli": shared_cli,
        }
    )

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.config = config
    ctx.settings_local_template = jinja2.Template(
        "{% for plugin_build_path in plugin_included_builds %}"
        "{{ plugin_build_path }}:[plugin]\n"
        "{% endfor %}"
        "{% for included_build in included_builds %}"
        "{{ included_build.build_path }}:"
        "{% for substitution in included_build.substitutions %}"
        "[{{ substitution.module_coordinate }}=>{{ substitution.project_path }}]"
        "{% endfor %}\n"
        "{% endfor %}"
    )

    setup_module._write_gradle_local_overlay(
        ctx,
        root_path=repo_root,
        seed_projects=[local_project],
    )

    overlay_text = (repo_root / "settings.local.gradle.kts").read_text(encoding="utf-8")
    assert "../kotlin-dotenv-parser:[one.wabbit:kotlin-dotenv-parser=>:]" in overlay_text
    assert "../shared:[one.wabbit:shared-api=>:shared-api][one.wabbit:shared-cli=>:shared-cli]" in overlay_text


def test_write_gradle_local_overlay_includes_kmp_source_set_project_dependencies(tmp_path: Path) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, Dependency, GradleProject, OwnershipType, ProjectDependencyTarget, Version

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        repo_root_path: Path,
        gradle_root_path: Path,
        gradle_project_name: str,
        platforms: list[str] | None = None,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=gradle_project_name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license="AGPL",
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.IMPORTED,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features={},
            platforms=platforms or ["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0] if "/" in project_id else None,
            repo_root=repo_root_path,
            gradle_root=gradle_root_path,
            module_dir=Path(path.name),
            gradle_project_name=gradle_project_name,
        )

    consumer_root = tmp_path / "kotlin-web-crossref"
    consumer_root.mkdir(parents=True, exist_ok=True)
    consumer_project = make_gradle_project(
        consumer_root,
        project_id="kotlin-web-crossref",
        repo_root_path=consumer_root,
        gradle_root_path=consumer_root,
        gradle_project_name="kotlin-web-crossref",
        platforms=["jvm", "iosArm64"],
    )
    data_root = tmp_path / "kotlin-data"
    data_project = make_gradle_project(
        data_root,
        project_id="kotlin-data",
        repo_root_path=data_root,
        gradle_root_path=data_root,
        gradle_project_name="kotlin-data",
    )
    common_root = tmp_path / "kotlin-web-common"
    common_project = make_gradle_project(
        common_root,
        project_id="kotlin-web-common",
        repo_root_path=common_root,
        gradle_root_path=common_root,
        gradle_project_name="kotlin-web-common",
        platforms=["jvm", "iosArm64"],
    )
    consumer_project.source_set_dependencies = {
        "commonMain": [
            Dependency(scope=None, target=ProjectDependencyTarget(project="kotlin-data")),
            Dependency(scope=None, target=ProjectDependencyTarget(project="kotlin-web-common")),
        ]
    }

    config = Config(raw=Document([]))
    config.defined_projects.update(
        {
            "kotlin-web-crossref": consumer_project,
            "kotlin-data": data_project,
            "kotlin-web-common": common_project,
        }
    )

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.config = config
    ctx.settings_local_template = jinja2.Template(
        "{% for plugin_build_path in plugin_included_builds %}"
        "{{ plugin_build_path }}:[plugin]\n"
        "{% endfor %}"
        "{% for included_build in included_builds %}"
        "{{ included_build.build_path }}:"
        "{% for substitution in included_build.substitutions %}"
        "[{{ substitution.module_coordinate }}=>{{ substitution.project_path }}]"
        "{% endfor %}\n"
        "{% endfor %}"
    )

    setup_module._write_gradle_local_overlay(
        ctx,
        root_path=consumer_root,
        seed_projects=[consumer_project],
    )

    overlay_text = (consumer_root / "settings.local.gradle.kts").read_text(encoding="utf-8")
    assert "../kotlin-data:[one.wabbit:kotlin-data=>:]" in overlay_text
    assert "../kotlin-web-common:[one.wabbit:kotlin-web-common=>:]" in overlay_text


def test_write_gradle_local_overlay_includes_local_plugin_projects_for_reachable_projects(tmp_path: Path) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import (
        Config,
        Dependency,
        Feature,
        GradlePluginApplication,
        GradlePlugins,
        GradleProject,
        KotlinPluginDefinition,
        OwnershipType,
        ProjectDependencyTarget,
        Version,
    )

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        repo_root_path: Path,
        gradle_root_path: Path,
        gradle_project_name: str,
        resolved_features: dict[str, Feature] | None = None,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=gradle_project_name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license="AGPL",
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.IMPORTED,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features=resolved_features or {},
            platforms=["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0] if "/" in project_id else None,
            repo_root=repo_root_path,
            gradle_root=gradle_root_path,
            module_dir=Path(path.name),
            gradle_project_name=gradle_project_name,
        )

    consumer_root = tmp_path / "consumer"
    consumer_project = make_gradle_project(
        consumer_root,
        project_id="consumer",
        repo_root_path=consumer_root,
        gradle_root_path=consumer_root,
        gradle_project_name="consumer",
    )
    dependency_root = tmp_path / "kotlin-hashing-simple"
    dependency_project = make_gradle_project(
        dependency_root,
        project_id="kotlin-hashing-simple",
        repo_root_path=dependency_root,
        gradle_root_path=dependency_root,
        gradle_project_name="kotlin-hashing-simple",
        resolved_features={
            "gradle-plugin": GradlePlugins(entries=[GradlePluginApplication(name="acyclic-gradle")]),
        },
    )
    consumer_project.resolved_dependencies = [
        Dependency(scope=None, target=ProjectDependencyTarget(project="kotlin-hashing-simple"))
    ]
    gradle_plugin_root = tmp_path / "kotlin-acyclic-gradle-plugin"
    gradle_plugin_project = make_gradle_project(
        gradle_plugin_root,
        project_id="kotlin-acyclic-gradle-plugin",
        repo_root_path=gradle_plugin_root,
        gradle_root_path=gradle_plugin_root,
        gradle_project_name="kotlin-acyclic-gradle-plugin",
    )
    gradle_plugin_project.gradle_plugin_id = "one.wabbit.acyclic"
    compiler_plugin_root = tmp_path / "kotlin-acyclic-plugin"
    compiler_plugin_project = make_gradle_project(
        compiler_plugin_root,
        project_id="kotlin-acyclic-plugin",
        repo_root_path=compiler_plugin_root,
        gradle_root_path=compiler_plugin_root,
        gradle_project_name="kotlin-acyclic-plugin",
    )

    config = Config(raw=Document([]))
    config.defined_projects.update(
        {
            "consumer": consumer_project,
            "kotlin-hashing-simple": dependency_project,
            "kotlin-acyclic-gradle-plugin": gradle_plugin_project,
            "kotlin-acyclic-plugin": compiler_plugin_project,
        }
    )
    config.plugins["acyclic-gradle"] = KotlinPluginDefinition(
        project="kotlin-acyclic-gradle-plugin",
        compiler_plugin="kotlin-acyclic-plugin",
    )

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.config = config
    ctx.settings_local_template = jinja2.Template(
        "{% for plugin_build_path in plugin_included_builds %}"
        "{{ plugin_build_path }}:[plugin]\n"
        "{% endfor %}"
        "{% for included_build in included_builds %}"
        "{{ included_build.build_path }}:"
        "{% for substitution in included_build.substitutions %}"
        "[{{ substitution.module_coordinate }}=>{{ substitution.project_path }}]"
        "{% endfor %}"
        "\n"
        "{% endfor %}"
    )
    setup_module._write_gradle_local_overlay(
        ctx,
        root_path=consumer_root,
        seed_projects=[consumer_project],
    )

    overlay_text = (consumer_root / "settings.local.gradle.kts").read_text(encoding="utf-8")
    assert "../kotlin-hashing-simple:[one.wabbit:kotlin-hashing-simple=>:]" in overlay_text
    assert "../kotlin-acyclic-gradle-plugin:[plugin]" in overlay_text
    assert "../kotlin-acyclic-plugin:[one.wabbit:kotlin-acyclic-plugin=>:]" in overlay_text


def test_write_gradle_local_overlay_merges_plugin_and_compiler_included_builds_for_same_repo_root(tmp_path: Path) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import (
        Config,
        Feature,
        GradlePluginApplication,
        GradlePlugins,
        GradleProject,
        KotlinPluginDefinition,
        OwnershipType,
        Version,
    )

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        repo_root_path: Path,
        gradle_root_path: Path,
        gradle_project_name: str,
        artifact_id: str | None = None,
        resolved_features: dict[str, Feature] | None = None,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=artifact_id or gradle_project_name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license="AGPL",
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.IMPORTED,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features=resolved_features or {},
            platforms=["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0] if "/" in project_id else None,
            repo_root=repo_root_path,
            gradle_root=gradle_root_path,
            module_dir=Path(path.name),
            gradle_project_name=gradle_project_name,
        )

    consumer_root = tmp_path / "consumer"
    consumer_project = make_gradle_project(
        consumer_root,
        project_id="consumer",
        repo_root_path=consumer_root,
        gradle_root_path=consumer_root,
        gradle_project_name="consumer",
        resolved_features={
            "gradle-plugin": GradlePlugins(entries=[GradlePluginApplication(name="acyclic-gradle")]),
        },
    )

    acyclic_root = tmp_path / "kotlin-acyclic"
    gradle_plugin_project = make_gradle_project(
        acyclic_root / "gradle-plugin",
        project_id="kotlin-acyclic/gradle-plugin",
        repo_root_path=acyclic_root,
        gradle_root_path=acyclic_root,
        gradle_project_name="gradle-plugin",
        artifact_id="kotlin-acyclic-gradle-plugin",
    )
    gradle_plugin_project.gradle_plugin_id = "one.wabbit.acyclic"

    compiler_plugin_project = make_gradle_project(
        acyclic_root / "compiler-plugin",
        project_id="kotlin-acyclic/compiler-plugin",
        repo_root_path=acyclic_root,
        gradle_root_path=acyclic_root,
        gradle_project_name="compiler-plugin",
        artifact_id="kotlin-acyclic-plugin",
    )

    config = Config(raw=Document([]))
    config.defined_projects.update(
        {
            "consumer": consumer_project,
            "kotlin-acyclic/gradle-plugin": gradle_plugin_project,
            "kotlin-acyclic/compiler-plugin": compiler_plugin_project,
        }
    )
    config.plugins["acyclic-gradle"] = KotlinPluginDefinition(
        project="kotlin-acyclic/gradle-plugin",
        compiler_plugin="kotlin-acyclic/compiler-plugin",
    )

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.config = config
    ctx.settings_local_template = jinja2.Template(
        "{% for plugin_build_path in plugin_included_builds %}"
        "{{ plugin_build_path }}:[plugin]\n"
        "{% endfor %}"
        "{% for included_build in included_builds %}"
        "{{ included_build.build_path }}:"
        "{% for substitution in included_build.substitutions %}"
        "[{{ substitution.module_coordinate }}=>{{ substitution.project_path }}]"
        "{% endfor %}"
        "\n"
        "{% endfor %}"
    )

    setup_module._write_gradle_local_overlay(
        ctx,
        root_path=consumer_root,
        seed_projects=[consumer_project],
    )

    overlay_text = (consumer_root / "settings.local.gradle.kts").read_text(encoding="utf-8")
    assert "../kotlin-acyclic:[plugin]" in overlay_text
    assert "../kotlin-acyclic:[one.wabbit:kotlin-acyclic-plugin=>:compiler-plugin]" in overlay_text


def test_write_gradle_root_files_writes_workspace_dependency_substitutions_in_local_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, Dependency, GradleProject, OwnershipType, ProjectDependencyTarget, Version

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        repo_root_path: Path,
        gradle_project_name: str,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=gradle_project_name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license="AGPL",
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.IMPORTED,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features={},
            platforms=["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0] if "/" in project_id else None,
            repo_root=repo_root_path,
            gradle_root=repo_root_path,
            module_dir=Path(path.name),
            gradle_project_name=gradle_project_name,
        )

    repo_root = tmp_path / "jeeves"
    local_project = make_gradle_project(
        repo_root / "server",
        project_id="jeeves/server",
        repo_root_path=repo_root,
        gradle_project_name="jeeves-server",
    )
    dependency_root = tmp_path / "kotlin-dotenv-parser"
    dependency_project = make_gradle_project(
        dependency_root,
        project_id="kotlin-dotenv-parser",
        repo_root_path=dependency_root,
        gradle_project_name="kotlin-dotenv-parser",
    )
    local_project.resolved_dependencies = [
        Dependency(scope=None, target=ProjectDependencyTarget(project="kotlin-dotenv-parser"))
    ]

    config = Config(raw=Document([]))
    config.defined_projects.update(
        {
            "jeeves/server": local_project,
            "kotlin-dotenv-parser": dependency_project,
        }
    )

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.config = config
    ctx.build_template = jinja2.Template(
        "{% for substitution in dependency_substitutions %}"
        "{{ substitution.module_coordinate }}=>{{ substitution.gradle_project_name }}\n"
        "{% endfor %}"
    )
    ctx.settings_template = jinja2.Template(
        "{% for included_project in included_projects %}"
        "{{ included_project.gradle_project_name }}={{ included_project.project_dir }}\n"
        "{% endfor %}"
    )

    import dev.tasks.setup_kotlin as setup_kotlin_module

    monkeypatch.setattr(setup_kotlin_module, "settings_plugin_versions", lambda _ctx: {})

    workspace_root = tmp_path / "workspace"
    setup_module._write_gradle_root_files(
        ctx,
        root_path=workspace_root,
        root_project_name="workspace",
        seed_projects=[local_project],
        write_wrapper=False,
        write_build=True,
        include_external_dependencies=True,
        write_dependency_substitutions=True,
    )

    build_text = (workspace_root / "build.gradle.kts").read_text(encoding="utf-8")
    settings_text = (workspace_root / "settings.gradle.kts").read_text(encoding="utf-8")
    assert "one.wabbit:kotlin-dotenv-parser=>kotlin-dotenv-parser" in build_text
    assert "jeeves-server=../jeeves/server" in settings_text
    assert "kotlin-dotenv-parser=../kotlin-dotenv-parser" in settings_text


def test_write_gradle_root_files_resolves_local_gradle_plugin_projects_in_settings(tmp_path: Path) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import (
        Config,
        GradlePluginApplication,
        GradlePlugins,
        GradleProject,
        KotlinPluginDefinition,
        OwnershipType,
        Version,
    )

    project = GradleProject(
        path=tmp_path / "workspace" / "demo",
        group_name="one.wabbit",
        name="demo",
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo="org/repo",
        ownership=OwnershipType.IMPORTED,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={
            "gradle-plugin": GradlePlugins(entries=[GradlePluginApplication(name="acyclic-gradle")]),
        },
        platforms=["jvm"],
        source_set_dependencies={},
        project_id="demo",
        repo_root=tmp_path / "workspace",
        gradle_root=tmp_path / "workspace",
        gradle_project_name="demo",
    )
    plugin_project = GradleProject(
        path=tmp_path / "kotlin-acyclic-gradle-plugin",
        group_name="one.wabbit",
        name="kotlin-acyclic-gradle-plugin",
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo="org/repo",
        ownership=OwnershipType.IMPORTED,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        platforms=["jvm"],
        source_set_dependencies={},
        project_id="kotlin-acyclic-gradle-plugin",
        repo_root=tmp_path / "kotlin-acyclic-gradle-plugin",
        gradle_root=tmp_path / "kotlin-acyclic-gradle-plugin",
        gradle_project_name="kotlin-acyclic-gradle-plugin",
        gradle_plugin_id="one.wabbit.acyclic",
    )

    config = Config(raw=Document([]))
    config.defined_projects["demo"] = project
    config.defined_projects["kotlin-acyclic-gradle-plugin"] = plugin_project
    config.plugins["acyclic-gradle"] = KotlinPluginDefinition(project="kotlin-acyclic-gradle-plugin")

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.config = config
    ctx.build_template = jinja2.Template("")
    ctx.settings_template = jinja2.Template(
        "{% for plugin in extra_gradle_plugins %}[{{ plugin.plugin_id }}={{ plugin.version }}]{% endfor %}"
    )
    ctx.repo_template = tmp_path
    ctx.gradle_properties_template = jinja2.Template("")

    workspace_root = tmp_path / "workspace"
    setup_module._write_gradle_root_files(
        ctx,
        root_path=workspace_root,
        root_project_name="workspace",
        seed_projects=[project],
        write_wrapper=False,
        write_build=True,
        include_external_dependencies=False,
        write_dependency_substitutions=False,
    )

    settings_text = (workspace_root / "settings.gradle.kts").read_text(encoding="utf-8")
    assert "[one.wabbit.acyclic=0.0.1]" in settings_text


@pytest.mark.parametrize(
    ("existing_build_text", "expected_write_build"),
    [
        (None, True),
        (
            "// Generated by app-wabbit-dev setup. Do not edit by hand.\n"
            "//\n"
            "// This file is generated from workspace configuration in root.clj.\n"
            "// To change it, update root.clj (or the relevant setup inputs) and regenerate\n"
            "// with the dev command, for example:\n"
            "//   dev setup <project-or-repo>\n"
            "// Direct edits to this file will be overwritten the next time setup runs.\n"
            "\n"
            "plugins {}\n",
            True,
        ),
        ("plugins { base }\n", False),
    ],
)
def test_setup_gradle_repo_root_only_overwrites_generated_root_builds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing_build_text: str | None,
    expected_write_build: bool,
) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, GradleProject, OwnershipType, RepoDefinition, Version

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    if existing_build_text is not None:
        (repo_root / "build.gradle.kts").write_text(existing_build_text, encoding="utf-8")

    project = GradleProject(
        path=repo_root / "library",
        group_name="one.wabbit",
        name="library",
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo="org/repo",
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        platforms=["jvm"],
        source_set_dependencies={},
        project_id="repo/library",
        repo_id="repo",
        repo_root=repo_root,
        gradle_root=repo_root,
        gradle_project_name="library",
    )

    config = Config(raw=Document([]))
    config.defined_projects["repo/library"] = project
    config.defined_repos["repo"] = RepoDefinition(
        repo_id="repo",
        path=repo_root,
        github_repo="org/repo",
        gradle_root_project_name="repo",
        jvm_policy=None,
        project_ids=["repo/library"],
    )

    captured_write_build: list[bool] = []

    def fake_write_gradle_root_files(
        ctx: object,
        *,
        root_path: Path,
        root_project_name: str,
        seed_projects: list[GradleProject],
        write_wrapper: bool,
        write_build: bool = True,
        include_external_dependencies: bool = False,
        write_dependency_substitutions: bool = False,
    ) -> None:
        del ctx, root_path, root_project_name, seed_projects, write_wrapper, include_external_dependencies, write_dependency_substitutions
        captured_write_build.append(write_build)

    monkeypatch.setattr(setup_module, "_write_gradle_root_files", fake_write_gradle_root_files)
    monkeypatch.setattr(setup_module, "_write_repo_root_wabbit_legal_documents", lambda ctx, projects: None)
    monkeypatch.setattr(setup_module.setup_kotlin, "_write_gradle_repo_root_workflows", lambda *args, **kwargs: None)

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.config = config

    setup_module.setup_gradle_repo_root(ctx, project)

    assert captured_write_build == [expected_write_build]


def test_write_gradle_root_files_renders_extra_gradle_plugins_in_settings(tmp_path: Path) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import (
        Config,
        GradlePluginApplication,
        GradlePlugins,
        GradleProject,
        KotlinPluginDefinition,
        MavenRepositoryDefinition,
        OwnershipType,
        Version,
    )

    project = GradleProject(
        path=tmp_path / "workspace" / "demo",
        group_name="one.wabbit",
        name="demo",
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo="org/repo",
        ownership=OwnershipType.IMPORTED,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={
            "gradle-plugin": GradlePlugins(entries=[GradlePluginApplication(name="acyclic-gradle")]),
        },
        platforms=["jvm"],
        source_set_dependencies={},
        project_id="demo",
        repo_root=tmp_path / "workspace",
        gradle_root=tmp_path / "workspace",
        gradle_project_name="demo",
    )

    config = Config(raw=Document([]))
    config.defined_projects["demo"] = project
    config.plugins["acyclic-gradle"] = KotlinPluginDefinition(plugin_id="one.wabbit.acyclic", version="0.0.1")
    config.repositories["repo:company"] = MavenRepositoryDefinition(
        name="repo:company",
        url="https://repo.example.com/releases",
    )
    config.plugins["company-plugin"] = KotlinPluginDefinition(
        plugin_id="com.example.company",
        version="1.2.3",
        repo="repo:company",
    )
    project.resolved_features["gradle-plugin"] = GradlePlugins(
        entries=[
            GradlePluginApplication(name="acyclic-gradle"),
            GradlePluginApplication(name="company-plugin"),
        ]
    )

    ctx = _make_setup_context("")
    ctx.config = config
    ctx.build_template = jinja2.Template("")
    ctx.settings_template = jinja2.Template(
        "{% for plugin in extra_gradle_plugins %}[{{ plugin.plugin_id }}={{ plugin.version }}]{% endfor %}"
        "{% for repo in extra_gradle_plugin_repositories %}[repo={{ repo.url }}]{% endfor %}"
    )
    ctx.repo_template = tmp_path
    ctx.gradle_properties_template = jinja2.Template("")

    workspace_root = tmp_path / "workspace"
    setup_module._write_gradle_root_files(
        ctx,
        root_path=workspace_root,
        root_project_name="workspace",
        seed_projects=[project],
        write_wrapper=False,
        write_build=True,
        include_external_dependencies=False,
        write_dependency_substitutions=False,
    )

    settings_text = (workspace_root / "settings.gradle.kts").read_text(encoding="utf-8")
    assert "[one.wabbit.acyclic=0.0.1][com.example.company=1.2.3]" in settings_text
    assert "[repo=https://repo.example.com/releases]" in settings_text


def test_setup_wires_repo_root_gradle_workflow_generation_to_repo_docs_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mu.types import Document

    import dev.tasks.setup as setup_module
    import dev.tasks.setup_kotlin as setup_kotlin_module
    from dev.config import Config, GradleProject, OwnershipType, RepoDefinition, Version

    repo_root = tmp_path / "jeeves"
    api_path = repo_root / "api"
    api_path.mkdir(parents=True, exist_ok=True)

    api_project = GradleProject(
        path=api_path,
        group_name="one.wabbit",
        name="api",
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=True,
        github_repo="wabbit-corp/jeeves",
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        platforms=["jvm"],
        source_set_dependencies={},
        project_id="jeeves/api",
        repo_id="jeeves",
        repo_root=repo_root,
        gradle_root=repo_root,
        gradle_project_name="jeeves-api",
        publish_target="maven-central",
        docs_enabled=True,
        docs_system="dokka",
    )

    config = Config(raw=Document([]))
    config.defined_projects["jeeves/api"] = api_project
    config.defined_repos["jeeves"] = RepoDefinition(
        repo_id="jeeves",
        path=repo_root,
        github_repo="wabbit-corp/jeeves",
        gradle_root_project_name="one.wabbit",
        jvm_policy=None,
        docs_project_id="jeeves/api",
        project_ids=["jeeves/api"],
    )

    ctx = _make_setup_context('[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n')
    ctx.config = config

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(setup_module, "create_repo_setup_context", lambda _config, _mode: ctx)
    monkeypatch.setattr(setup_module, "_write_gradle_root_files", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup_module, "_write_repo_root_wabbit_legal_documents", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup_module, "setup_project", lambda *args, **kwargs: None)

    recorded: dict[str, object] = {}

    def fake_write_gradle_repo_root_workflows(
        _ctx: object,
        *,
        root_path: Path,
        repo_github_repo: str | None,
        projects: object,
        docs_project: object,
        java_version: int,
    ) -> None:
        recorded["root_path"] = root_path
        recorded["repo_github_repo"] = repo_github_repo
        recorded["projects"] = projects
        recorded["docs_project"] = docs_project
        recorded["java_version"] = java_version

    monkeypatch.setattr(setup_kotlin_module, "_write_gradle_repo_root_workflows", fake_write_gradle_repo_root_workflows)

    setup_module.setup(setup_module.RepoSetupMode.PROD, interactive=False, project="jeeves/api")

    assert recorded["root_path"] == repo_root
    assert recorded["repo_github_repo"] == "wabbit-corp/jeeves"
    assert recorded["projects"] == [api_project]
    assert recorded["docs_project"] is api_project
    assert recorded["java_version"] == config.java_version


def test_gradle_release_publish_workflow_template_checks_tag_version_match() -> None:
    template_path = (
        Path(__file__).resolve().parents[2]
        / "data-repo-template"
        / "gradle-files"
        / ".github"
        / "workflows"
        / "release-publish.yml.jinja2"
    )
    template_text = template_path.read_text(encoding="utf-8")

    assert "Match tag to published version" in template_text
    assert "{{ version_print_command }}" in template_text
    assert 'EXPECTED_VERSION="${GITHUB_REF_NAME#v}"' in template_text
