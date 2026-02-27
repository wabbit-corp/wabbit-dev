import sys
from pathlib import Path
from types import SimpleNamespace

import jinja2


def _make_python_project(path: Path, github_repo: str | None = None, application: object | None = None):
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


def test_setup_project_creates_directory_before_project_setup(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

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

    ctx = SimpleNamespace(
        known_repo_names=[],
        mode=setup_module.RepoSetupMode.LOCAL,
        config=SimpleNamespace(
            default_git_user_email="test@example.com",
            default_git_user_name="Test User",
        ),
    )

    setup_module.setup_project(ctx, project, interactive=False)
    assert called


def test_setup_project_skips_remote_check_when_github_api_unavailable(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    import dev.tasks.setup as setup_module
    from dev.config import PythonProject

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / ".gitignore").write_text("# test\n", encoding="utf-8")
    repo = setup_module.Repo.init(project.path)
    repo.close()

    warning_messages: list[str] = []
    error_messages: list[str] = []

    def fake_setup_python_project(ctx: object, python_project: PythonProject, interactive: bool = True) -> None:
        del ctx, python_project, interactive

    monkeypatch.setattr(setup_module, "setup_python_project", fake_setup_python_project)
    monkeypatch.setattr(setup_module, "warning", lambda message: warning_messages.append(message))
    monkeypatch.setattr(setup_module, "error", lambda message: error_messages.append(message))

    ctx = SimpleNamespace(
        known_repo_names=[],
        is_github_api_available=False,
        mode=setup_module.RepoSetupMode.LOCAL,
        config=SimpleNamespace(
            default_git_user_email="test@example.com",
            default_git_user_name="Test User",
        ),
    )

    setup_module.setup_project(ctx, project, interactive=False)

    assert "GitHub API unavailable; skipping remote existence check." in warning_messages
    assert f"Remote repository {project.github_repo} does not exist" not in error_messages


def test_setup_python_project_generates_docs_and_workflows(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    import dev.tasks.setup as setup_module

    project = _make_python_project(tmp_path / "pkg", github_repo="org/pkg")
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "README.md").write_text("# pkg\n", encoding="utf-8")

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", lambda _ctx, _project: None)
    monkeypatch.setattr(setup_module, "_write_banner", lambda _ctx, _project: None)

    ctx = SimpleNamespace(
        config=SimpleNamespace(
            python_defaults=SimpleNamespace(requires_python=None, line_length=None, coverage_fail_under=None)
        ),
        gitignore_template=jinja2.Template("# base\n"),
        python_gitignore_template=jinja2.Template("# python\n"),
        python_pyproject_template=jinja2.Template(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        ),
        python_mkdocs_template=jinja2.Template("site_name: {{ site_name }}\n"),
        python_docs_index_template=jinja2.Template("# {{ project_name }}\n"),
        python_docs_installation_template=jinja2.Template("# Install {{ package_name }}\n"),
        python_docs_development_template=jinja2.Template("# Dev {{ project_name }}\n"),
        python_contributing_template=jinja2.Template("# Contributing {{ project_name }}\n"),
        python_docs_quality_workflow_template=jinja2.Template("name: Docs Quality\n"),
        python_docs_deploy_workflow_template=jinja2.Template("name: Docs Deploy\n"),
        python_codespell_ignore_words_template=jinja2.Template("wabbit\n"),
        python_build_executable_template=jinja2.Template(
            '#!/usr/bin/env python3\nAPP_NAME = "{{ app_name }}"\nENTRYPOINT = "{{ entrypoint_path }}"\n'
        ),
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    assert (project.path / "pyproject.toml").is_file()
    assert (project.path / "mkdocs.yml").is_file()
    assert (project.path / "docs" / "index.md").is_file()
    assert (project.path / "docs" / "installation.md").is_file()
    assert (project.path / "docs" / "development.md").is_file()
    assert (project.path / "CONTRIBUTING.md").is_file()
    assert (project.path / ".codespell-ignore-words.txt").is_file()
    assert (project.path / ".github" / "workflows" / "docs-quality.yml").is_file()
    assert (project.path / ".github" / "workflows" / "docs-deploy.yml").is_file()


def test_setup_python_project_generates_app_build_script_for_python_application(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

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

    monkeypatch.setattr(setup_module, "_write_wabbit_legal_files", lambda _ctx, _project: None)
    monkeypatch.setattr(setup_module, "_write_banner", lambda _ctx, _project: None)

    ctx = SimpleNamespace(
        config=SimpleNamespace(
            python_defaults=SimpleNamespace(requires_python=None, line_length=None, coverage_fail_under=None)
        ),
        gitignore_template=jinja2.Template("# base\n"),
        python_gitignore_template=jinja2.Template("# python\n"),
        python_pyproject_template=jinja2.Template(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
            "{% if has_scripts %}[tool.poetry.scripts]\n{{ scripts_block }}\n{% endif %}"
        ),
        python_mkdocs_template=jinja2.Template("site_name: {{ site_name }}\n"),
        python_docs_index_template=jinja2.Template("# {{ project_name }}\n"),
        python_docs_installation_template=jinja2.Template("# Install {{ package_name }}\n"),
        python_docs_development_template=jinja2.Template("# Dev {{ project_name }}\n"),
        python_contributing_template=jinja2.Template("# Contributing {{ project_name }}\n"),
        python_docs_quality_workflow_template=jinja2.Template("name: Docs Quality\n"),
        python_docs_deploy_workflow_template=jinja2.Template("name: Docs Deploy\n"),
        python_codespell_ignore_words_template=jinja2.Template("wabbit\n"),
        python_build_executable_template=jinja2.Template(
            '#!/usr/bin/env python3\nAPP_NAME = "{{ app_name }}"\nENTRYPOINT = "{{ entrypoint_path }}"\n'
        ),
    )

    setup_module.setup_python_project(ctx, project, interactive=False)

    build_script = project.path / "scripts" / "build_executable.py"
    assert build_script.is_file()
    content = build_script.read_text(encoding="utf-8")
    assert 'APP_NAME = "pkg-cli"' in content
    assert 'ENTRYPOINT = "src/pkg/cli.py"' in content
