from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import urlparse

import jinja2
from git import Repo
from git.exc import BadName, GitCommandError, InvalidGitRepositoryError, NoSuchPathError
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion
from packaging.version import Version as PythonVersion

import dev.io
from dev.config import Config, PythonProject
from dev.generated_files import is_setup_managed_file, prepend_generated_comment, stamp_managed_text
from dev.licenses import canonicalize_license_key, python_spdx_for_license
from dev.messages import warning
from dev.tasks.setup_common import (
    clean_text,
    render_template,
    write_banner,
    write_requirements_file,
    write_wabbit_legal_files,
)

_GITHUB_URL_SCHEME = "https"
_GITHUB_URL_HOST = "github.com"
_YAML_TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*:")


class PythonSetupContext(Protocol):
    config: Config
    repo_template: Path
    licenses: dict[str, str]
    coc: jinja2.Template
    cla: jinja2.Template
    cla_explanations: jinja2.Template
    contributor_privacy_policy: jinja2.Template
    gitignore_template: jinja2.Template
    python_gitignore_template: jinja2.Template
    python_pyproject_template: jinja2.Template
    python_pyrightconfig_template: jinja2.Template
    python_mkdocs_template: jinja2.Template
    python_docs_index_template: jinja2.Template
    python_docs_installation_template: jinja2.Template
    python_docs_development_template: jinja2.Template
    python_contributing_template: jinja2.Template
    python_docs_quality_workflow_template: jinja2.Template
    python_docs_deploy_workflow_template: jinja2.Template
    python_codespell_ignore_words_template: jinja2.Template
    python_build_executable_template: jinja2.Template


def _github_repo_url(repo_full_name: str) -> str:
    return _GITHUB_URL_SCHEME + "://" + _GITHUB_URL_HOST + "/" + repo_full_name.strip("/")


def _github_repo_name_from_url(repository_url: str) -> str | None:
    parsed = urlparse(repository_url)
    if parsed.scheme.lower() != _GITHUB_URL_SCHEME:
        return None
    if parsed.netloc.lower() != _GITHUB_URL_HOST:
        return None
    repo_name = parsed.path.strip("/")
    if not repo_name:
        return None
    return repo_name


def _discover_python_packages(project_path: Path) -> list[str]:
    ignore_dirs = {
        ".git",
        ".idea",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "venv",
    }
    ignore_paths = dev.io.read_ignore_file(project_path / ".gitignore")
    packages: list[str] = []
    for child in project_path.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in ignore_dirs or ignore_paths(child):
            continue
        if (child / "__init__.py").exists():
            packages.append(child.name)
    return sorted(packages)


def _discover_test_paths(project_path: Path) -> list[str]:
    ignore_dirs = {
        ".git",
        ".idea",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "venv",
    }
    ignore_paths = dev.io.read_ignore_file(project_path / ".gitignore")
    test_paths: list[str] = []
    for root, dirs, _ in os.walk(project_path):
        root_path = Path(root)
        dirs[:] = [
            d
            for d in dirs
            if d not in ignore_dirs
            and not d.startswith(".")
            and not d.startswith("tmp.")
            and not d.startswith("tmp-setup-")
            and not ignore_paths(root_path / d)
        ]
        for name in dirs:
            if name in {"tests", "test"}:
                test_dir = root_path / name
                rel_path = test_dir.relative_to(project_path).as_posix()
                if rel_path not in test_paths:
                    test_paths.append(rel_path)
    return sorted(test_paths)


def _discover_top_level_python_files(project_path: Path) -> list[str]:
    ignore_paths = dev.io.read_ignore_file(project_path / ".gitignore")
    files: list[str] = []
    for child in project_path.iterdir():
        if child.is_file() and child.suffix == ".py" and not ignore_paths(child):
            files.append(child.name)
    return sorted(files)


def _iter_python_files(project_path: Path) -> list[Path]:
    ignore_dirs = {
        ".git",
        ".idea",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "venv",
    }
    ignore_paths = dev.io.read_ignore_file(project_path / ".gitignore")
    files: list[Path] = []
    for root, dirs, filenames in os.walk(project_path):
        root_path = Path(root)
        dirs[:] = [
            d
            for d in dirs
            if d not in ignore_dirs
            and not d.startswith(".")
            and not d.startswith("tmp.")
            and not d.startswith("tmp-setup-")
            and not ignore_paths(root_path / d)
        ]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            file_path = root_path / name
            if ignore_paths(file_path):
                continue
            files.append(file_path)
    return files


def _discover_import_modules(project_path: Path) -> list[str]:
    modules: set[str] = set()
    for file_path in _iter_python_files(project_path):
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                if node.module:
                    modules.add(node.module.split(".", 1)[0])
    return sorted(modules)


def _normalize_import_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return normalized.strip("_")


def _derive_deptry_package_map(project_path: Path, dependencies: list[str]) -> dict[str, str]:
    imports = _discover_import_modules(project_path)
    if not imports:
        return {}
    import_norm = {_normalize_import_name(name): name for name in imports}
    import_norm_keys = sorted(import_norm.keys(), key=len, reverse=True)
    mapping: dict[str, str] = {}

    for dep in dependencies:
        try:
            dep_name = Requirement(dep).name
        except InvalidRequirement:
            warning(f"Invalid dependency requirement {dep!r}; skipping deptry auto-map")
            continue
        if dep_name in imports:
            continue
        dep_norm = _normalize_import_name(dep_name)
        if dep_norm in import_norm:
            module = import_norm[dep_norm]
            if module != dep_name:
                mapping[dep_name] = module
            continue

        for prefix in ("python_", "py"):
            if dep_norm.startswith(prefix):
                candidate = dep_norm[len(prefix) :]
                if candidate in import_norm:
                    mapping[dep_name] = import_norm[candidate]
                    break
        if dep_name in mapping:
            continue

        for norm_module in import_norm_keys:
            if dep_norm.startswith(norm_module) or dep_norm.endswith(norm_module):
                mapping[dep_name] = import_norm[norm_module]
                break

    return mapping


def _toml_list(items: list[str]) -> str:
    quoted = [f'"{item}"' for item in items]
    return f"[{', '.join(quoted)}]"


def _toml_map_lines(map_data: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for key in sorted(map_data.keys()):
        lines.append(f'"{key}" = {_toml_list(map_data[key])}')
    return "\n".join(lines)


def _toml_kv_lines(map_data: dict[str, str]) -> str:
    lines: list[str] = []
    for key in sorted(map_data.keys()):
        lines.append(f'"{key}" = "{map_data[key]}"')
    return "\n".join(lines)


def _toml_inline_table_list_map(map_data: dict[str, list[str]]) -> str:
    if not map_data:
        return "{}"
    parts = [f'"{key}" = {_toml_list(map_data[key])}' for key in map_data.keys()]
    return "{ " + ", ".join(parts) + " }"


def _format_toml_key(key: str) -> str:
    if re.match(r"^[A-Za-z0-9_-]+$", key):
        return key
    return f'"{key}"'


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_poetry_dependency(requirement: str) -> tuple[str, str]:
    try:
        parsed = Requirement(requirement)
    except InvalidRequirement as ex:
        raise ValueError(f"Invalid dependency requirement: {requirement}") from ex

    key = _format_toml_key(parsed.name)
    specifier = str(parsed.specifier) or "*"
    marker = str(parsed.marker) if parsed.marker is not None else None
    extras = sorted(parsed.extras)

    core = requirement.split(";", 1)[0].strip()
    remainder = core
    if core.lower().startswith(parsed.name.lower()):
        remainder = core[len(parsed.name) :].lstrip()
    if remainder.startswith("["):
        extras_end = remainder.find("]")
        if extras_end != -1:
            remainder = remainder[extras_end + 1 :].lstrip()
    if remainder and not remainder.startswith("@"):
        specifier = remainder

    if parsed.url is None and not extras and marker is None:
        return key, _toml_string(specifier)

    table_fields: list[str] = []
    if parsed.url is not None:
        table_fields.append(f"url = {_toml_string(parsed.url)}")
    else:
        table_fields.append(f"version = {_toml_string(specifier)}")

    if extras:
        table_fields.append(f"extras = {_toml_list(extras)}")

    if marker is not None:
        table_fields.append(f"markers = {_toml_string(marker)}")

    value = "{ " + ", ".join(table_fields) + " }"
    return key, value


def _python_target_version(requires_python: str | None) -> str:
    default = PythonVersion("3.10")
    if not requires_python:
        target = default
    else:
        try:
            spec = SpecifierSet(requires_python)
        except InvalidSpecifier:
            warning(f"Invalid requires-python specifier {requires_python!r}; defaulting to py310")
            target = default
        else:
            lower_bounds: list[PythonVersion] = []
            for item in spec:
                if item.operator not in {">=", ">", "==", "===", "~="}:
                    continue
                normalized = item.version
                if normalized.endswith(".*"):
                    normalized = normalized[:-2]
                try:
                    lower_bounds.append(PythonVersion(normalized))
                except InvalidVersion:
                    continue
            target = max(lower_bounds) if lower_bounds else default

    return f"py{target.major}{target.minor}"


def format_poetry_dependency(requirement: str) -> tuple[str, str]:
    return _format_poetry_dependency(requirement)


def python_target_version(requires_python: str | None) -> str:
    return _python_target_version(requires_python)


def _mypy_python_version_from_target(target_version: str) -> str:
    if not target_version.startswith("py") or len(target_version) < 5:
        return "3.10"
    major = target_version[2]
    minor = target_version[3:]
    return f"{major}.{minor}"


def _coerce_int_setting(value: int | str | None, *, default: int, field_name: str) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    warning(f"Invalid {field_name} value {value!r}; defaulting to {default}")
    return default


def _dependency_name(requirement: str) -> str:
    try:
        return Requirement(requirement).name
    except InvalidRequirement:
        return requirement.strip()


def _merge_requirements(base: list[str], extra: list[str]) -> list[str]:
    merged: dict[str, str] = {}
    for dep in base:
        merged[_dependency_name(dep)] = dep
    for dep in extra:
        merged[_dependency_name(dep)] = dep
    return list(merged.values())


def _python_generated_dev_dependencies(project: PythonProject) -> list[str]:
    base_dev_dependencies = [
        "pytest>=8.0.0,<9.0.0",
        "mypy>=1.10.0,<2.0.0",
        "ruff>=0.8.0,<1.0.0",
        "black>=24.0.0,<26.0.0",
        "coverage>=7.0.0,<8.0.0",
        "build>=1.2.0,<2.0.0",
        "twine>=5.0.0,<6.0.0",
    ]
    app_dev_dependencies = ["pyinstaller>=6.9.0,<7.0.0"] if project.application is not None else []
    return _merge_requirements(base_dev_dependencies + app_dev_dependencies, project.dev_dependencies)


def _default_repo_urls(project: PythonProject) -> tuple[str | None, str | None, str | None]:
    repository = project.repository
    if repository is None and project.github_repo is not None:
        repository = _github_repo_url(project.github_repo)
    homepage = project.homepage or repository
    issue_tracker = f"{repository}/issues" if repository else None
    return homepage, repository, issue_tracker


def _default_site_url(project: PythonProject) -> str | None:
    if project.github_repo is None:
        return None
    owner, _, repo_name = project.github_repo.partition("/")
    if not owner or not repo_name:
        return None
    return f"https://{owner}.github.io/{repo_name}/"


def _default_deptry_map(project_path: Path, dependencies: list[str]) -> dict[str, str]:
    common_map = {
        "pygithub": "github",
        "pyyaml": "yaml",
        "pillow": "PIL",
        "beautifulsoup4": "bs4",
        "discord-ext-voice-recv": "discord.ext.voice_recv",
        "djangorestframework": "rest_framework",
        "imbalanced-learn": "imblearn",
        "levenshtein": "Levenshtein",
        "pynacl": "nacl",
        "scikit-learn": "sklearn",
    }
    auto_map = _derive_deptry_package_map(project_path, dependencies)
    # Keep curated aliases authoritative when import auto-discovery would pick a broader module.
    merged = {**auto_map, **common_map}
    present_dependency_names = {_dependency_name(dep) for dep in dependencies}
    return {pkg: module for pkg, module in merged.items() if pkg in present_dependency_names}


def _merge_gitignore_content(generated_content: str, existing_content: str | None) -> str:
    generated_lines = generated_content.rstrip("\n").splitlines()
    if not existing_content:
        return "\n".join(generated_lines).rstrip("\n") + "\n"

    merged_lines = list(generated_lines)
    seen = set(generated_lines)
    extra_lines = [line for line in existing_content.rstrip("\n").splitlines() if line not in seen]
    if extra_lines:
        if merged_lines and merged_lines[-1] != "":
            merged_lines.append("")
        merged_lines.extend(extra_lines)
    return "\n".join(merged_lines).rstrip("\n") + "\n"


def _load_tracked_gitignore(project_path: Path) -> str | None:
    if not (project_path / ".git").exists():
        return None

    try:
        repo = Repo(project_path)
    except (InvalidGitRepositoryError, NoSuchPathError, OSError, ValueError):
        return None

    try:
        if not repo.head.is_valid():
            return None
        tracked_gitignore = repo.git.show("HEAD:.gitignore")
        return tracked_gitignore if isinstance(tracked_gitignore, str) else None
    except (BadName, GitCommandError, OSError, ValueError):
        return None
    finally:
        repo.close()


def _load_existing_poetry_metadata(project_path: Path) -> dict[str, object]:
    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.is_file():
        return {}

    try:
        import tomllib

        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    data_obj = cast(dict[str, object], data)
    tool = data_obj.get("tool")
    if not isinstance(tool, dict):
        return {}
    tool_obj = cast(dict[str, object], tool)
    poetry = tool_obj.get("poetry")
    if not isinstance(poetry, dict):
        return {}
    return cast(dict[str, object], poetry)


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    list_value = cast(list[object], value)
    result: list[str] = []
    for item in list_value:
        if isinstance(item, str):
            result.append(item)
    return result


def _normalize_python_license(project_license: str | None, existing_license: object) -> str | None:
    if project_license is None:
        if isinstance(existing_license, str) and existing_license.strip():
            return existing_license.strip()
        return None

    normalized = canonicalize_license_key(project_license)
    if not normalized:
        if isinstance(existing_license, str) and existing_license.strip():
            return existing_license.strip()
        return None

    if normalized in {"AGPL", "CC0"}:
        if isinstance(existing_license, str) and existing_license.strip():
            return existing_license.strip()

    return python_spdx_for_license(normalized)


def render_python_pyproject(ctx: PythonSetupContext, project: PythonProject) -> str:
    defaults = ctx.config.python_defaults
    requires_python = project.requires_python or defaults.requires_python or ">=3.10"
    if project.requires_python is None and defaults.requires_python is None:
        warning(f"No requires-python set for {project.name}; defaulting to {requires_python}")

    line_length = _coerce_int_setting(
        defaults.line_length,
        default=120,
        field_name="python-defaults.line-length",
    )
    coverage_fail_under = _coerce_int_setting(
        defaults.coverage_fail_under,
        default=80,
        field_name="python-defaults.coverage-fail-under",
    )
    coverage_precision = 0
    coverage_branch = True
    coverage_show_missing = True
    coverage_skip_empty = True
    coverage_xml_output = "coverage.xml"
    target_version = _python_target_version(requires_python)
    mypy_python_version = _mypy_python_version_from_target(target_version)

    docs_dependencies = [
        "mkdocs>=1.6,<2.0",
        "mkdocs-material>=9.6,<9.7",
        "codespell>=2.3,<3.0",
    ]
    app_feature = project.application
    dev_dependencies = _python_generated_dev_dependencies(project)
    dependencies = project.dependencies

    packages = _discover_python_packages(project.path)
    packages_toml = ""
    if packages:
        package_entries = ", ".join([f'{{ include = "{name}" }}' for name in packages])
        packages_toml = f"[{package_entries}]"

    test_paths = _discover_test_paths(project.path)
    if not test_paths:
        test_paths = ["tests"]
    ruff_per_file_ignores = {f"{path}/**/*.py": ["B"] for path in test_paths}

    coverage_source = packages if packages else ["."]
    coverage_omit = sorted(
        {
            ".venv/*",
            "**/__pycache__/*",
            *[f"{path}/*" for path in test_paths],
        }
    )

    deptry_package_map = _default_deptry_map(project.path, dependencies + dev_dependencies)
    if app_feature is not None and "pyinstaller" in {_dependency_name(dep) for dep in dev_dependencies}:
        deptry_package_map["pyinstaller"] = "PyInstaller"

    deptry_per_rule_ignores = {
        "DEP004": [
            "pytest",
            "mypy",
            "ruff",
            "black",
            "coverage",
            "build",
            "twine",
            "codespell",
            "mkdocs",
            "mkdocs-material",
        ]
    }
    if app_feature is not None:
        deptry_per_rule_ignores["DEP004"].extend(["pyinstaller", "PyInstaller"])

    homepage_url, repository_url, issue_tracker_url = _default_repo_urls(project)
    existing_poetry_metadata = _load_existing_poetry_metadata(project.path)
    existing_description = existing_poetry_metadata.get("description")
    existing_authors = _as_string_list(existing_poetry_metadata.get("authors"))
    existing_keywords = _as_string_list(existing_poetry_metadata.get("keywords"))
    existing_classifiers = _as_string_list(existing_poetry_metadata.get("classifiers"))

    description = (
        project.description
        if project.description is not None
        else (existing_description if isinstance(existing_description, str) else "")
    )
    authors = project.authors or existing_authors
    keywords = project.keywords or existing_keywords
    classifiers = (
        project.classifiers
        or existing_classifiers
        or [
            "Development Status :: 3 - Alpha",
            "Intended Audience :: Developers",
            "Programming Language :: Python :: 3",
        ]
    )
    license_value = _normalize_python_license(project.license, existing_poetry_metadata.get("license"))

    dependencies_lines: list[str] = []
    for dep in dependencies:
        key, value = _format_poetry_dependency(dep)
        dependencies_lines.append(f"{key} = {value}")

    dev_dependencies_lines: list[str] = []
    for dep in dev_dependencies:
        key, value = _format_poetry_dependency(dep)
        dev_dependencies_lines.append(f"{key} = {value}")

    docs_dependencies_lines: list[str] = []
    for dep in docs_dependencies:
        key, value = _format_poetry_dependency(dep)
        docs_dependencies_lines.append(f"{key} = {value}")

    script_lines: list[str] = []
    if app_feature is not None:
        script_names = [app_feature.script, *app_feature.aliases]
        script_lines.extend([f'{script_name} = "{app_feature.entry}"' for script_name in script_names])
    else:
        for script in project.scripts:
            if "=" not in script:
                warning(f"Invalid python script entry for {project.name}: {script}")
                continue
            script_name, target = script.split("=", 1)
            script_lines.append(f'{script_name.strip()} = "{target.strip()}"')

    context = {
        "name": project.name,
        "version": str(project.version) if project.version else "0.0.0",
        "description": description,
        "authors_toml": _toml_list(authors) if authors else "",
        "license": license_value,
        "readme": "README.md" if (project.path / "README.md").exists() else "",
        "homepage": homepage_url or "",
        "repository": repository_url or "",
        "issue_tracker": issue_tracker_url or "",
        "keywords_toml": _toml_list(keywords) if keywords else "",
        "classifiers_toml": _toml_list(classifiers),
        "packages_toml": packages_toml,
        "python_version": requires_python,
        "dependencies_block": "\n".join(dependencies_lines),
        "dev_dependencies_block": "\n".join(dev_dependencies_lines),
        "docs_dependencies_block": "\n".join(docs_dependencies_lines),
        "scripts_block": "\n".join(script_lines),
        "has_dev_dependencies": bool(dev_dependencies_lines),
        "has_docs_dependencies": bool(docs_dependencies_lines),
        "has_scripts": bool(script_lines),
        "line_length": line_length,
        "target_version": target_version,
        "mypy_python_version": mypy_python_version,
        "ruff_select_toml": _toml_list(["F", "E", "W", "I", "B", "UP"]),
        "ruff_ignore_toml": _toml_list(["E501"]),
        "ruff_per_file_ignores_block": _toml_map_lines(ruff_per_file_ignores),
        "has_ruff_per_file_ignores": bool(ruff_per_file_ignores),
        "testpaths_toml": _toml_list(test_paths),
        "has_testpaths": bool(test_paths),
        "deptry_package_map_block": _toml_kv_lines(deptry_package_map),
        "deptry_per_rule_ignores_inline": _toml_inline_table_list_map(deptry_per_rule_ignores),
        "has_deptry_package_map": bool(deptry_package_map),
        "has_deptry_rule_ignores": bool(deptry_per_rule_ignores),
        "coverage_source_toml": _toml_list(coverage_source),
        "coverage_omit_toml": _toml_list(coverage_omit),
        "coverage_branch": coverage_branch,
        "coverage_show_missing": coverage_show_missing,
        "coverage_skip_empty": coverage_skip_empty,
        "coverage_fail_under": coverage_fail_under,
        "coverage_precision": coverage_precision,
        "coverage_xml_output": coverage_xml_output,
    }

    return render_template(ctx.python_pyproject_template, **context)


def _render_managed_pyproject_text(ctx: PythonSetupContext, project: PythonProject) -> str:
    base_text = prepend_generated_comment(
        render_python_pyproject(ctx, project),
        comment_prefix="#",
        body_lines=[
            "This file is generated from workspace configuration in root.clj.",
            "To change it, update root.clj and regenerate with the dev command, for example:",
            "  dev setup <project-or-repo>",
            "For unmanaged additional TOML sections, create pyproject.extra.toml beside this file.",
            "Do not redefine tables or keys already generated here.",
            "Direct edits to this file will be overwritten the next time setup runs.",
        ],
    )
    return stamp_managed_text(_append_pyproject_extra_toml(project.path, clean_text(base_text)), comment_prefix="#")


def render_python_pyrightconfig(ctx: PythonSetupContext, project: PythonProject) -> str:
    defaults = ctx.config.python_defaults
    requires_python = project.requires_python or defaults.requires_python or ">=3.10"
    target_version = _python_target_version(requires_python)
    python_version = _mypy_python_version_from_target(target_version)

    include_candidates = [
        *_discover_python_packages(project.path),
        *_discover_test_paths(project.path),
        *_discover_top_level_python_files(project.path),
    ]
    include_paths = list(dict.fromkeys(include_candidates))
    if not include_paths:
        include_paths = ["."]

    exclude_paths = [
        ".venv",
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        "site",
        "tmp",
        "tmp-*",
        "tmp-test",
        "tmp-test-*",
    ]

    return render_template(
        ctx.python_pyrightconfig_template,
        include_json=json.dumps(include_paths),
        exclude_json=json.dumps(exclude_paths),
        python_version=python_version,
    )


def _python_repository_url(project: PythonProject) -> str:
    if project.repository is not None:
        return project.repository
    if project.github_repo is not None:
        return _github_repo_url(project.github_repo)
    return ""


def _python_repository_name(project: PythonProject) -> str:
    if project.github_repo is not None:
        return project.github_repo
    repository_url = _python_repository_url(project)
    repository_name = _github_repo_name_from_url(repository_url)
    if repository_name is not None:
        return repository_name
    return ""


def _append_pyproject_extra_toml(project_path: Path, base_text: str) -> str:
    extra_path = project_path / "pyproject.extra.toml"
    if not extra_path.is_file():
        return base_text

    extra_text = clean_text(extra_path.read_text(encoding="utf-8"))
    if not extra_text.strip():
        return base_text

    combined = clean_text(
        base_text.rstrip("\n")
        + "\n\n"
        + "# Additional unmanaged sections from pyproject.extra.toml\n"
        + "# Do not redefine tables or keys already generated above.\n\n"
        + extra_text
    )

    try:
        import tomllib

        tomllib.loads(combined)
    except Exception as ex:
        raise ValueError(
            f"{extra_path} must append only valid, non-conflicting TOML sections: {ex}"
        ) from ex

    return combined


def _yaml_top_level_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        if not line or line[0].isspace() or line.startswith("-"):
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped in {"---", "..."}:
            continue
        match = _YAML_TOP_LEVEL_KEY_RE.match(line)
        if match is not None:
            keys.add(match.group(1))
    return keys


def _render_managed_mkdocs_text(
    *,
    site_name: str,
    site_description: str,
    site_url: str,
    repo_url: str,
    repo_name: str,
    template: jinja2.Template,
    project_path: Path,
) -> str:
    base_text = prepend_generated_comment(
        render_template(
            template,
            site_name=site_name,
            site_description=site_description,
            site_url=site_url,
            repo_url=repo_url,
            repo_name=repo_name,
        ),
        comment_prefix="#",
        body_lines=[
            "This file is generated from workspace configuration in root.clj.",
            "To change it, update root.clj and regenerate with the dev command, for example:",
            "  dev setup <project-or-repo>",
            "For unmanaged additional MkDocs top-level keys, create mkdocs.extra.yml beside this file.",
            "Do not redefine keys already generated here.",
            "Direct edits to this file will be overwritten the next time setup runs.",
        ],
    )
    return stamp_managed_text(_append_mkdocs_extra_yaml(project_path, clean_text(base_text)), comment_prefix="#")


def _append_mkdocs_extra_yaml(project_path: Path, base_text: str) -> str:
    extra_path = project_path / "mkdocs.extra.yml"
    if not extra_path.is_file():
        return base_text

    extra_text = clean_text(extra_path.read_text(encoding="utf-8"))
    if not extra_text.strip():
        return base_text

    conflicts = sorted(_yaml_top_level_keys(base_text) & _yaml_top_level_keys(extra_text))
    if conflicts:
        conflict_list = ", ".join(conflicts)
        raise ValueError(
            f"{extra_path} redefines generated MkDocs top-level keys: {conflict_list}"
        )

    return clean_text(
        base_text.rstrip("\n")
        + "\n\n"
        + "# Additional unmanaged top-level keys from mkdocs.extra.yml\n\n"
        + extra_text
    )


def _write_python_docs_files(ctx: PythonSetupContext, project: PythonProject) -> None:
    repository_url = _python_repository_url(project)
    repository_name = _python_repository_name(project)
    site_name = project.name
    site_description = project.description or f"Documentation for {project.name}."
    site_url = _default_site_url(project) or ""
    docs_workflow_context = {
        "has_changelog_guard_script": (project.path / "scripts" / "check_changelog_guard.py").is_file(),
        "has_generate_api_docs_script": (project.path / "scripts" / "generate_api_docs.py").is_file(),
        "has_docs_links_script": (project.path / "scripts" / "check_docs_links.py").is_file(),
        "has_docs_snippets_test": (project.path / "tests" / "test_docs_snippets.py").is_file(),
    }

    managed_mkdocs_text = _render_managed_mkdocs_text(
        site_name=site_name,
        site_description=site_description,
        site_url=site_url,
        repo_url=repository_url,
        repo_name=repository_name,
        template=ctx.python_mkdocs_template,
        project_path=project.path,
    )
    mkdocs_path = project.path / "mkdocs.yml"
    if not mkdocs_path.exists() or is_setup_managed_file(mkdocs_path):
        dev.io.write_text_file(mkdocs_path, managed_mkdocs_text)
    elif (project.path / "mkdocs.extra.yml").is_file():
        warning(
            f"{mkdocs_path} is not managed by setup; mkdocs.extra.yml will be ignored until mkdocs.yml is regenerated"
        )
    dev.io.write_text_file_if_missing(
        project.path / "docs" / "index.md",
        clean_text(
            render_template(
                ctx.python_docs_index_template,
                project_name=project.name,
                project_description=project.description or "",
            )
        ),
    )
    dev.io.write_text_file_if_missing(
        project.path / "docs" / "installation.md",
        clean_text(
            render_template(
                ctx.python_docs_installation_template,
                package_name=project.name,
            )
        ),
    )
    dev.io.write_text_file_if_missing(
        project.path / "docs" / "development.md",
        clean_text(
            render_template(
                ctx.python_docs_development_template,
                project_name=project.name,
            )
        ),
    )
    dev.io.write_text_file_if_missing(
        project.path / "CONTRIBUTING.md",
        clean_text(render_template(ctx.python_contributing_template, project_name=project.name)),
    )

    codespell_words = [
        line.strip()
        for line in render_template(ctx.python_codespell_ignore_words_template).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    dev.io.merge_word_list_file(
        project.path / ".codespell-ignore-words.txt",
        codespell_words,
    )

    dev.io.write_text_file(
        project.path / ".github" / "workflows" / "docs-quality.yml",
        clean_text(render_template(ctx.python_docs_quality_workflow_template, **docs_workflow_context)),
    )
    dev.io.write_text_file(
        project.path / ".github" / "workflows" / "docs-deploy.yml",
        clean_text(render_template(ctx.python_docs_deploy_workflow_template)),
    )


def _write_python_application_files(ctx: PythonSetupContext, project: PythonProject) -> None:
    application = project.application
    if application is None:
        return

    dev.io.write_text_file(
        project.path / "scripts" / "build_executable.py",
        clean_text(
            render_template(
                ctx.python_build_executable_template,
                app_name=application.script,
                entrypoint_path=application.path,
            )
        ),
    )


def setup_python_project(ctx: PythonSetupContext, project: PythonProject, interactive: bool = True) -> None:
    existing_gitignore_path = project.path / ".gitignore"
    existing_gitignore = (
        existing_gitignore_path.read_text(encoding="utf-8") if existing_gitignore_path.is_file() else None
    )
    tracked_gitignore = _load_tracked_gitignore(project.path)
    generated_gitignore = clean_text(
        render_template(ctx.gitignore_template) + "\n" + render_template(ctx.python_gitignore_template)
    )
    merged_gitignore = _merge_gitignore_content(generated_gitignore, tracked_gitignore)
    dev.io.write_text_file(
        project.path / ".gitignore",
        _merge_gitignore_content(merged_gitignore, existing_gitignore),
    )

    write_wabbit_legal_files(ctx, project)
    write_banner(ctx, project)

    write_requirements_file(
        project.path / "requirements.txt",
        project.dependencies,
        interactive=interactive,
        project_name=project.name,
    )
    write_requirements_file(
        project.path / "requirements-dev.txt",
        _python_generated_dev_dependencies(project),
        interactive=interactive,
        project_name=project.name,
    )

    pyproject_path = project.path / "pyproject.toml"
    pyproject_text = _render_managed_pyproject_text(ctx, project)
    dev.io.write_text_file(pyproject_path, pyproject_text)

    dev.io.write_text_file_if_missing(
        project.path / "pyrightconfig.json",
        clean_text(render_python_pyrightconfig(ctx, project)),
    )

    if project.docs_enabled and project.docs_system == "mkdocs":
        _write_python_docs_files(ctx, project)
    else:
        dev.io.delete_if_exists(project.path / ".github" / "workflows" / "docs-quality.yml")
        dev.io.delete_if_exists(project.path / ".github" / "workflows" / "docs-deploy.yml")
    _write_python_application_files(ctx, project)


__all__ = [
    "format_poetry_dependency",
    "python_target_version",
    "_format_poetry_dependency",
    "_python_generated_dev_dependencies",
    "_python_target_version",
    "render_python_pyproject",
    "render_python_pyrightconfig",
    "setup_python_project",
    "write_banner",
    "write_wabbit_legal_files",
]
