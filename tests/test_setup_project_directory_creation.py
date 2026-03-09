from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import jinja2
import pytest
from git import Repo

if TYPE_CHECKING:
    from dev.config import Config, PurescriptProject, PythonApplication, PythonProject
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


def test_targeted_prod_setup_omits_cross_repo_gradle_projects_from_root_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, GradleProject, OwnershipType, Version

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
    config.defined_projects = {
        "jeeves/api": api_project,
        "kotlin-dotenv-parser": external_project,
        "jeeves/server": server_project,
    }
    config.plugins["kotlin-jvm"] = SimpleNamespace(version="2.2.20")

    written_files: dict[str, str] = {}

    def fake_load_config() -> Config:
        return config

    def fake_toposort_projects(_projects: object, target_project: str | None = None) -> list[str]:
        assert target_project == "jeeves/server"
        return ["jeeves/api", "kotlin-dotenv-parser", "jeeves/server"]

    def fake_create_repo_setup_context(_config: Config, mode: object) -> object:
        return SimpleNamespace(
            config=config,
            mode=mode,
            build_template=jinja2.Template("ROOT_BUILD {{ kotlin_version }}"),
            settings_template=jinja2.Template(
                "{% for included_project in included_projects %}"
                "{{ included_project.gradle_project_name }}={{ included_project.project_dir }}\n"
                "{% endfor %}"
            ),
        )

    def fake_write_text_file(path: Path, content: str) -> None:
        written_files[path.as_posix()] = content

    monkeypatch.setattr(setup_module, "load_config", fake_load_config)
    monkeypatch.setattr(setup_module, "toposort_projects", fake_toposort_projects)
    monkeypatch.setattr(setup_module, "create_repo_setup_context", fake_create_repo_setup_context)
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module.dev.io, "write_text_file", fake_write_text_file)

    setup_module.setup(setup_module.RepoSetupMode.PROD, interactive=False, project="jeeves/server")

    settings_text = written_files["settings.gradle.kts"]
    assert "jeeves-api=" in settings_text
    assert "jeeves-server=" in settings_text
    assert "kotlin-dotenv-parser=" not in settings_text


def test_setup_writes_repo_root_legal_docs_for_repo_managed_gradle_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from mu.types import Document

    import dev.tasks.setup as setup_module
    from dev.config import Config, GradleProject, OwnershipType, RepoDefinition, Version

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

    config = Config(raw=Document([]))
    config.defined_projects = {"jeeves/api": api_project}
    config.defined_repos = {
        "jeeves": RepoDefinition(
            repo_id="jeeves",
            path=jeeves_root,
            github_repo="org/jeeves",
            gradle_root_project_name="one.wabbit",
            jvm_policy=None,
            project_ids=["jeeves/api"],
        )
    }
    config.plugins["kotlin-jvm"] = SimpleNamespace(version="2.2.20")

    written_paths: list[Path] = []

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(setup_module, "toposort_projects", lambda _projects, target_project=None: ["jeeves/api"])
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, mode: SimpleNamespace(config=config, mode=mode),
    )
    monkeypatch.setattr(setup_module, "_write_gradle_root_files", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        setup_module.setup_common,
        "write_wabbit_legal_documents",
        lambda _ctx, project: written_paths.append(project.path),
    )

    setup_module.setup(setup_module.RepoSetupMode.LOCAL, interactive=False, project="jeeves/api")

    assert written_paths == [jeeves_root]
