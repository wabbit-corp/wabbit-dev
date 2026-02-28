import sys
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2
import pytest
from git import Repo

if TYPE_CHECKING:
    from dev.config import PythonApplication, PythonProject
    from dev.tasks.setup import RepoSetupContext


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


def _make_setup_context(pyproject_template: str, codespell_words: str = "wabbit\n") -> RepoSetupContext:
    import dev.tasks.setup as setup_module
    from dev.config import load_config

    config = load_config()
    config.default_git_user_email = "test@example.com"
    config.default_git_user_name = "Test User"

    return setup_module.RepoSetupContext(
        config=config,
        known_repo_names=[],
        known_github_repos={},
        is_github_api_available=True,
        repo_template=Path("."),
        licenses={},
        coc="",
        gitignore_template=jinja2.Template("# base\n"),
        cla=jinja2.Template(""),
        cla_explanations=jinja2.Template(""),
        contributor_privacy_policy=jinja2.Template(""),
        settings_template=jinja2.Template(""),
        subproject_settings_template=jinja2.Template(""),
        build_template=jinja2.Template(""),
        subproject_build_template=jinja2.Template(""),
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
    from dev.config import PythonProject

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
    from dev.config import PythonProject

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
    requirements_dev = (project.path / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "pytest>=8.0.0,<9.0.0" in requirements_dev
    assert "mypy>=1.10.0,<2.0.0" in requirements_dev
    assert "ruff>=0.8.0,<1.0.0" in requirements_dev
    assert "black>=24.0.0,<26.0.0" in requirements_dev
    assert "coverage>=7.0.0,<8.0.0" in requirements_dev
    assert "build>=1.2.0,<2.0.0" in requirements_dev
    assert "twine>=5.0.0,<6.0.0" in requirements_dev
    assert "pyinstaller>=6.9.0,<7.0.0" not in requirements_dev


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


def test_setup_python_project_preserves_existing_docs_and_workflows(
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

    for path, content in existing_files.items():
        assert path.read_text(encoding="utf-8") == content


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
