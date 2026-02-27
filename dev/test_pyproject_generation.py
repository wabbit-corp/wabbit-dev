import os
import shutil
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import jinja2
import pytest


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


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _make_python_project_for_render(path: Path, *, application: object | None = None):
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


def _make_render_context() -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            python_defaults=SimpleNamespace(requires_python=None, line_length=None, coverage_fail_under=None)
        ),
        python_pyproject_template=jinja2.Template(
            '[tool.poetry]\nname = "{{ name }}"\nversion = "{{ version }}"\n'
            '[tool.poetry.dependencies]\npython = "{{ python_version }}"\n'
            "{% if has_dev_dependencies %}[tool.poetry.group.dev.dependencies]\n{{ dev_dependencies_block }}\n{% endif %}\n"
            "{% if has_scripts %}[tool.poetry.scripts]\n{{ scripts_block }}\n{% endif %}\n"
            "{% if has_deptry_rule_ignores %}[tool.deptry]\nper_rule_ignores = {{ deptry_per_rule_ignores_inline }}\n{% endif %}\n"
        ),
    )


def test_render_python_pyproject_excludes_pyinstaller_for_non_app(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

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
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

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


def test_setup_generates_python_docs_and_quality_defaults(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

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
        def get_repos(self):
            return [DummyRepo("wabbit-corp/wabbit-dev")]

    class DummyGithub:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_user(self):
            return DummyUser()

    monkeypatch.setattr("github.Github", DummyGithub)
    monkeypatch.setattr("dev.tasks.setup.get_coc_file", lambda: "CODE_OF_CONDUCT\n")
    monkeypatch.setattr("dev.tasks.setup.create_banner", lambda **_: None)

    cwd = os.getcwd()
    os.chdir(temp_root)
    try:
        setup(RepoSetupMode.LOCAL, interactive=False)
    finally:
        os.chdir(cwd)

    generated_project = temp_root / "app-wabbit-dev"
    generated_pyproject = _load_toml(generated_project / "pyproject.toml")
    tool = generated_pyproject["tool"]
    poetry = tool["poetry"]

    assert poetry["repository"] == "https://github.com/wabbit-corp/wabbit-dev"
    assert poetry["homepage"] == "https://github.com/wabbit-corp/wabbit-dev"
    assert poetry["group"]["docs"]["dependencies"]["mkdocs"] == ">=1.6,<2.0"
    assert poetry["group"]["docs"]["dependencies"]["mkdocs-material"] == ">=9.6,<9.7"
    assert poetry["group"]["docs"]["dependencies"]["codespell"] == ">=2.3,<3.0"
    assert "pytest" in poetry["group"]["dev"]["dependencies"]
    assert "mypy" in poetry["group"]["dev"]["dependencies"]
    assert "ruff" in poetry["group"]["dev"]["dependencies"]
    assert "black" in poetry["group"]["dev"]["dependencies"]

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
