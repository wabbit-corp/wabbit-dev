from __future__ import annotations

import os
import shutil
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import jinja2
import pytest

from dev.config import load_config
from dev.json_utils import as_dict

if TYPE_CHECKING:
    from dev.config import Config, PythonApplication, PythonProject
    from dev.tasks.setup import RepoSetupContext


def _copy_tree(src: Path, dest: Path) -> None:
    ignore = shutil.ignore_patterns(
        ".git",
        ".venv",
        "build",
        "dist",
        "__pycache__",
        ".pytest_cache",
        ".dev.cache.db",
        ".idea",
        ".vscode",
        ".DS_Store",
        "tmp-setup-*",
        "*.bak",
    )
    shutil.copytree(src, dest, ignore=ignore)


def _load_toml(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _load_repo_config(repo_root: Path) -> Config:
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


def _make_python_project_for_render(path: Path, *, application: PythonApplication | None = None) -> PythonProject:
    from dev.config import OwnershipType, PythonProject

    return PythonProject(
        path=path,
        name="demo",
        version=None,
        description="Demo",
        authors=["Dev"],
        license="AGPL",
        github_repo="wabbit-corp/demo",
        requires_python=">=3.10",
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        application=application,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=True,
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
    )


def _make_render_context(pyproject_template: str | None = None) -> RepoSetupContext:
    import dev.tasks.setup as setup_module

    repo_root = Path(__file__).resolve().parents[1]
    config = _load_repo_config(repo_root)
    config.default_git_user_email = "test@example.com"
    config.default_git_user_name = "Test User"

    template_text = pyproject_template or (
        '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n'
        '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
        "{% if has_dev_dependencies %}[tool.poetry.group.dev.dependencies]\n{{ dev_dependencies_block }}\n{% endif %}\n"
        "{% if has_scripts %}[tool.poetry.scripts]\n{{ scripts_block }}\n{% endif %}\n"
        "{% if has_deptry_rule_ignores %}[tool.deptry]\nper_rule_ignores = {{ deptry_per_rule_ignores_inline }}\n{% endif %}\n"
    )

    return setup_module.RepoSetupContext(
        config=config,
        known_repo_names=[],
        known_github_repos={},
        is_github_api_available=False,
        repo_template=Path("."),
        licenses={},
        coc=jinja2.Template(""),
        gitignore_template=jinja2.Template(""),
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
        python_gitignore_template=jinja2.Template(""),
        purescript_gitignore_template=jinja2.Template(""),
        python_pyproject_template=jinja2.Template(template_text),
        python_pyrightconfig_template=jinja2.Template("{}"),
        python_mkdocs_template=jinja2.Template(""),
        python_docs_index_template=jinja2.Template(""),
        python_docs_installation_template=jinja2.Template(""),
        python_docs_development_template=jinja2.Template(""),
        python_contributing_template=jinja2.Template(""),
        python_docs_quality_workflow_template=jinja2.Template(""),
        python_docs_deploy_workflow_template=jinja2.Template(""),
        python_codespell_ignore_words_template=jinja2.Template(""),
        python_build_executable_template=jinja2.Template(""),
        mode=setup_module.RepoSetupMode.LOCAL,
    )


def test_render_python_pyproject_excludes_pyinstaller_for_non_app(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.tasks.setup import render_python_pyproject

    project_path = tmp_path / "demo"
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (project_path / "demo").mkdir(parents=True, exist_ok=True)
    (project_path / "demo" / "__init__.py").write_text("", encoding="utf-8")

    project = _make_python_project_for_render(project_path)
    rendered = render_python_pyproject(_make_render_context(), project)

    assert "pyinstaller" not in rendered
    assert "[tool.poetry.scripts]" not in rendered


def test_render_python_pyproject_includes_pyinstaller_for_python_application(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.config import PythonApplication
    from dev.tasks.setup import render_python_pyproject

    project_path = tmp_path / "demo"
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (project_path / "demo").mkdir(parents=True, exist_ok=True)
    (project_path / "demo" / "__init__.py").write_text("", encoding="utf-8")

    project = _make_python_project_for_render(
        project_path,
        application=PythonApplication(
            script="demo-cli",
            entry="demo.cli:main",
            path="demo/cli.py",
            aliases=["demo"],
        ),
    )
    rendered = render_python_pyproject(_make_render_context(), project)

    assert "pyinstaller" in rendered
    assert 'demo-cli = "demo.cli:main"' in rendered
    assert 'demo = "demo.cli:main"' in rendered


def test_render_python_pyproject_preserves_existing_metadata_when_config_omits_it(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.tasks.setup import render_python_pyproject

    project_path = tmp_path / "demo"
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (project_path / "demo").mkdir(parents=True, exist_ok=True)
    (project_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.poetry]",
                'name = "demo"',
                'version = "0.1.0"',
                'description = "Existing description"',
                'authors = ["Someone <someone@example.com>"]',
                'license = "AGPL-3.0-or-later"',
                'keywords = ["mu", "parser"]',
                'classifiers = ["Topic :: Software Development :: Libraries :: Python Modules"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    project = _make_python_project_for_render(project_path)
    project.description = None
    project.authors = []
    project.keywords = []
    project.classifiers = []

    context = _make_render_context(
        '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n'
        'description = "{{ description }}"\n'
        "{% if authors_toml %}authors = {{ authors_toml }}\n{% endif %}"
        '{% if license %}license = "{{ license }}"\n{% endif %}'
        "{% if keywords_toml %}keywords = {{ keywords_toml }}\n{% endif %}"
        "classifiers = {{ classifiers_toml }}\n"
        '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
    )

    rendered = render_python_pyproject(context, project)

    assert 'description = "Existing description"' in rendered
    assert 'authors = ["Someone <someone@example.com>"]' in rendered
    assert 'license = "AGPL-3.0-or-later"' in rendered
    assert 'keywords = ["mu", "parser"]' in rendered
    assert 'classifiers = ["Topic :: Software Development :: Libraries :: Python Modules"]' in rendered


def test_render_python_pyproject_ignores_gitignored_packages(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.tasks.setup import render_python_pyproject

    project_path = tmp_path / "demo"
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (project_path / ".gitignore").write_text("/scratch/\n", encoding="utf-8")
    (project_path / "demo").mkdir(parents=True, exist_ok=True)
    (project_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project_path / "scratch").mkdir(parents=True, exist_ok=True)
    (project_path / "scratch" / "__init__.py").write_text("", encoding="utf-8")

    project = _make_python_project_for_render(project_path)
    rendered = render_python_pyproject(
        _make_render_context(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n'
            "{% if packages_toml %}packages = {{ packages_toml }}\n{% endif %}\n"
            "[tool.coverage.run]\nsource = {{ coverage_source_toml }}\n"
        ),
        project,
    )

    assert '{ include = "demo" }' in rendered
    assert "scratch" not in rendered


def test_default_deptry_map_includes_common_python_package_aliases(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.tasks.setup_python import _default_deptry_map

    deptry_map = _default_deptry_map(
        tmp_path,
        [
            "discord-ext-voice-recv>=0.5.2a179,<0.6.0",
            "djangorestframework>=3.16.1,<4.0.0",
            "imbalanced-learn>=0.14.1,<1.0.0",
            "levenshtein>=0.27.3,<1.0.0",
            "pynacl>=1.6.2,<2.0.0",
            "scikit-learn>=1.8.0,<2.0.0",
        ],
    )

    assert deptry_map == {
        "discord-ext-voice-recv": "discord.ext.voice_recv",
        "djangorestframework": "rest_framework",
        "imbalanced-learn": "imblearn",
        "levenshtein": "Levenshtein",
        "pynacl": "nacl",
        "scikit-learn": "sklearn",
    }


def test_default_deptry_map_prefers_curated_aliases_over_auto_discovery(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.tasks.setup_python import _default_deptry_map

    package_path = tmp_path / "demo"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "__init__.py").write_text("", encoding="utf-8")
    (package_path / "imports.py").write_text(
        "\n".join(
            [
                "import django",
                "import discord",
                "",
            ]
        ),
        encoding="utf-8",
    )

    deptry_map = _default_deptry_map(
        tmp_path,
        [
            "discord-ext-voice-recv>=0.5.2a179,<0.6.0",
            "discord.py>=2.6.4,<3.0.0",
            "djangorestframework>=3.16.1,<4.0.0",
        ],
    )

    assert deptry_map["discord-ext-voice-recv"] == "discord.ext.voice_recv"
    assert deptry_map["discord.py"] == "discord"
    assert deptry_map["djangorestframework"] == "rest_framework"


@pytest.mark.parametrize(
    ("project_license", "expected_spdx"),
    [
        ("MIT", "MIT"),
        ("BSD", "BSD-3-Clause"),
        ("GPLv3", "GPL-3.0-only"),
        ("mit", "MIT"),
        ("gpl-3.0", "GPL-3.0-only"),
    ],
)
def test_render_python_pyproject_maps_supported_license_to_spdx(
    tmp_path: Path,
    project_license: str,
    expected_spdx: str,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.tasks.setup import render_python_pyproject

    project_path = tmp_path / "demo"
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (project_path / "demo").mkdir(parents=True, exist_ok=True)
    (project_path / "demo" / "__init__.py").write_text("", encoding="utf-8")

    project = _make_python_project_for_render(project_path)
    project.license = project_license

    context = _make_render_context(
        '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n'
        '{% if license %}license = "{{ license }}"\n{% endif %}\n'
        '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
    )

    rendered = render_python_pyproject(context, project)

    assert f'license = "{expected_spdx}"' in rendered


def test_setup_generates_python_docs_and_quality_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))

    from dev.tasks.setup import RepoSetupMode, setup

    test_root = repo_root / "test" / "root.clj"
    test_private = repo_root / "test" / "root.private.clj"
    if not test_root.is_file() or not test_private.is_file():
        pytest.skip("No repo-local root.clj/root.private.clj fixture available for setup generation test")

    temp_root = tmp_path
    shutil.copy(test_root, temp_root / "root.clj")
    shutil.copy(test_private, temp_root / "root.private.clj")
    _copy_tree(workspace_root / "data-repo-template", temp_root / "data-repo-template")

    projects = [repo_root] + sorted(workspace_root.glob("python-*"))
    for src in projects:
        dest = temp_root / src.name
        _copy_tree(src, dest)
        for filename in (
            "pyproject.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "mkdocs.yml",
            "CONTRIBUTING.md",
            ".codespell-ignore-words.txt",
        ):
            target = dest / filename
            if target.exists():
                target.unlink()

    class DummyRepo:
        def __init__(self, full_name: str) -> None:
            self.full_name = full_name
            self.name = full_name.split("/")[-1]
            self.private = False
            self.clone_url = f"https://example.invalid/{full_name}.git"
            self.owner = SimpleNamespace(login=full_name.split("/")[0])

    class DummyUser:
        def get_repos(self) -> list[DummyRepo]:
            return [DummyRepo("wabbit-corp/wabbit-dev")]

    class DummyGithub:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def get_user(self) -> DummyUser:
            return DummyUser()

    def fake_create_banner(**_: object) -> None:
        return None

    monkeypatch.setattr("github.Github", DummyGithub)
    monkeypatch.setattr("dev.tasks.setup.create_banner", fake_create_banner)

    cwd = os.getcwd()
    os.chdir(temp_root)
    try:
        setup(RepoSetupMode.LOCAL, interactive=False)
    finally:
        os.chdir(cwd)

    generated_project = temp_root / "app-wabbit-dev"
    generated_pyproject = _load_toml(generated_project / "pyproject.toml")
    tool = as_dict(generated_pyproject.get("tool"))
    assert tool is not None
    poetry = as_dict(tool.get("poetry"))
    assert poetry is not None
    group = as_dict(poetry.get("group"))
    assert group is not None
    docs_group = as_dict(group.get("docs"))
    assert docs_group is not None
    docs_dependencies = as_dict(docs_group.get("dependencies"))
    assert docs_dependencies is not None
    dev_group = as_dict(group.get("dev"))
    assert dev_group is not None
    dev_dependencies = as_dict(dev_group.get("dependencies"))
    assert dev_dependencies is not None

    assert poetry["repository"] == "https://github.com/wabbit-corp/wabbit-dev"
    assert poetry["homepage"] == "https://github.com/wabbit-corp/wabbit-dev"
    assert docs_dependencies.get("mkdocs") == ">=1.6,<2.0"
    assert docs_dependencies.get("mkdocs-material") == ">=9.6,<9.7"
    assert docs_dependencies.get("codespell") == ">=2.3,<3.0"
    assert "pytest" in dev_dependencies
    assert "mypy" in dev_dependencies
    assert "ruff" in dev_dependencies
    assert "black" in dev_dependencies

    assert "mypy" in tool
    assert "ruff" in tool
    assert "black" in tool
    assert "pytest" in tool

    assert (generated_project / "mkdocs.yml").is_file()
    assert (generated_project / "docs" / "index.md").is_file()
    assert (generated_project / "docs" / "installation.md").is_file()
    assert (generated_project / "docs" / "development.md").is_file()
    assert (generated_project / "CONTRIBUTING.md").is_file()
    assert (generated_project / ".codespell-ignore-words.txt").is_file()
    assert (generated_project / ".github" / "workflows" / "docs-quality.yml").is_file()
    assert (generated_project / ".github" / "workflows" / "docs-deploy.yml").is_file()
