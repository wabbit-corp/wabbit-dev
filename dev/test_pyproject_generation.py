import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import tomllib

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


def _read_requirements(path: Path) -> list[str]:
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _normalize_list(value: list[str]) -> list[str]:
    return sorted(value)


def _normalize_map(value: dict[str, list[str]]) -> dict[str, list[str]]:
    return {key: sorted(items) for key, items in value.items()}


def _normalize_contracts(value: list[dict]) -> list[dict]:
    return sorted(value, key=lambda item: item.get("id", ""))


def _requirement_name(requirement: str) -> str:
    for idx, ch in enumerate(requirement):
        if ch in "<>!=~":
            return requirement[:idx].strip()
    return requirement.strip()


def test_setup_generates_pyproject_from_config(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    from dev.tasks.setup import RepoSetupMode, setup, _derive_deptry_package_map

    test_root = repo_root / "test" / "root.clj"
    test_private = repo_root / "test" / "root.private.clj"
    temp_root = tmp_path

    shutil.copy(test_root, temp_root / "root.clj")
    shutil.copy(test_private, temp_root / "root.private.clj")

    _copy_tree(workspace_root / "data-repo-template", temp_root / "data-repo-template")

    projects = [repo_root] + sorted(workspace_root.glob("python-*"))
    for src in projects:
        dest = temp_root / src.name
        _copy_tree(src, dest)
        for filename in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
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

    for src in projects:
        assert (temp_root / src.name / "pyproject.toml").exists()

    generated_app = _load_toml(temp_root / "app-wabbit-dev" / "pyproject.toml")
    existing_app = _load_toml(repo_root / "pyproject.toml")

    assert generated_app["tool"]["poetry"]["name"] == existing_app["tool"]["poetry"]["name"]
    assert generated_app["tool"]["poetry"]["version"] == existing_app["tool"]["poetry"]["version"]
    assert generated_app["tool"]["poetry"]["license"] == existing_app["tool"]["poetry"]["license"]

    gen_deps = dict(generated_app["tool"]["poetry"]["dependencies"])
    gen_deps.pop("python", None)
    existing_deps = dict(existing_app["tool"]["poetry"]["dependencies"])
    existing_deps.pop("python", None)
    assert gen_deps == existing_deps

    gen_dev_deps = generated_app["tool"]["poetry"]["group"]["dev"]["dependencies"]
    existing_dev_deps = existing_app["tool"]["poetry"]["group"]["dev"]["dependencies"]
    assert gen_dev_deps == existing_dev_deps

    assert _read_requirements(temp_root / "app-wabbit-dev" / "requirements.txt") == _read_requirements(
        repo_root / "requirements.txt"
    )
    assert _read_requirements(
        temp_root / "app-wabbit-dev" / "requirements-dev.txt"
    ) == _read_requirements(repo_root / "requirements-dev.txt")

    generated_jeeves = _load_toml(temp_root / "python-jeeves" / "pyproject.toml")

    expected_layers = ["interface", "service", "data"]
    expected_test_paths = ["tests", "codi/api/tests"]
    expected_main_sources = ["codi", "servant", "typed_json"]

    assert generated_jeeves["tool"]["black"]["line-length"] == 120
    assert generated_jeeves["tool"]["black"]["target-version"] == ["py310"]
    assert generated_jeeves["tool"]["ruff"]["line-length"] == 120
    assert generated_jeeves["tool"]["ruff"]["target-version"] == "py310"
    assert generated_jeeves["tool"]["ruff"]["lint"]["select"] == ["F", "E", "W", "I", "B", "UP"]
    assert generated_jeeves["tool"]["ruff"]["lint"]["ignore"] == ["E501"]

    expected_ruff_ignores = {
        f"{path}/**/*.py": ["B"] for path in expected_test_paths
    }
    assert _normalize_map(
        generated_jeeves["tool"]["ruff"]["lint"]["per-file-ignores"]
    ) == _normalize_map(expected_ruff_ignores)
    assert generated_jeeves["tool"]["pytest"]["ini_options"] == {
        "testpaths": expected_test_paths
    }

    dep_names = [
        dep
        for dep in generated_jeeves["tool"]["poetry"]["dependencies"].keys()
        if dep != "python"
    ]
    auto_deptry_map = _derive_deptry_package_map(
        temp_root / "python-jeeves", dep_names
    )
    explicit_deptry_map = {
        "djangorestframework": "rest_framework",
        "imbalanced-learn": "imblearn",
        "scikit-learn": "sklearn",
    }
    expected_deptry_map = {**auto_deptry_map, **explicit_deptry_map}
    assert generated_jeeves["tool"]["deptry"]["package_module_name_map"] == expected_deptry_map
    assert generated_jeeves["tool"]["deptry"]["per_rule_ignores"] == {
        "DEP002": ["hypothesis"]
    }

    assert generated_jeeves["tool"]["importlinter"]["root_packages"] == expected_main_sources
    assert _normalize_contracts(
        generated_jeeves["tool"]["importlinter"]["contracts"]
    ) == _normalize_contracts(
        [
            {
                "id": "layering",
                "name": "Layered architecture",
                "type": "layers",
                "layers": expected_layers,
            }
        ]
    )

    gen_coverage = generated_jeeves["tool"]["coverage"]
    assert gen_coverage["report"]["fail_under"] == 80
    assert gen_coverage["report"]["precision"] == 0
    assert gen_coverage["report"]["show_missing"] is True
    assert gen_coverage["report"]["skip_empty"] is True
    assert gen_coverage["run"]["branch"] is True
    assert gen_coverage["xml"]["output"] == "coverage.xml"
    assert _normalize_list(gen_coverage["run"]["source"]) == _normalize_list(
        expected_main_sources
    )
    expected_omit = sorted(
        {
            "tests/*",
            ".venv/*",
            "**/__pycache__/*",
            "codi/api/tests/*",
        }
    )
    assert _normalize_list(gen_coverage["run"]["omit"]) == _normalize_list(expected_omit)

    gen_jeeves_deps = [
        dep for dep in generated_jeeves["tool"]["poetry"]["dependencies"].keys() if dep != "python"
    ]
    existing_jeeves = _load_toml(workspace_root / "python-jeeves" / "pyproject.toml")
    existing_jeeves_dep_names = [
        _requirement_name(dep) for dep in existing_jeeves["project"]["dependencies"]
    ]
    assert _normalize_list(gen_jeeves_deps) == _normalize_list(
        existing_jeeves_dep_names
    )
