from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dev.config import (
    CANONICAL_KMP_SOURCE_SET_REQUIREMENTS,
    GRADLE_SOURCE_SET_NAME_RE,
    GRADLE_TARGET_KIND_TO_PLATFORM,
    GradleProject,
    _source_set_is_allowed_for_platforms,
)
from dev.ignore_files import IgnoreMatcher
from dev.repo_metadata import RepoMetadataPlan, expected_repo_metadata_paths

_PYTHON_PACKAGE_IGNORE_DIRS = {
    ".git",
    ".idea",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "venv",
}
_SOURCE_FILE_SUFFIXES = {".kt", ".kts", ".java", ".scala"}
_MARKDOWN_SUFFIXES = {".md", ".markdown"}
_MKDOCS_DOCS_DIR_RE = re.compile(r"^docs_dir:\s*(?P<path>\S+)\s*$", re.MULTILINE)
_MKDOCS_NAV_PATH_RE = re.compile(r":\s*(?P<path>[A-Za-z0-9_./-]+\.(?:md|markdown))\s*$", re.MULTILINE)
_KMP_NATIVE_NAME_RE = re.compile(r"^(?P<stem>[A-Za-z][A-Za-z0-9]*)Native(?P<suffix>Main|Test|UnitTest)?$")
_EXPLICIT_NATIVE_BOUNDARY_TOKENS = frozenset(
    {
        "apple",
        "darwin",
        "ios",
        "linux",
        "macos",
        "mingw",
        "ort",
        "posix",
        "unix",
        "windows",
    }
)
MONITORED_REPO_METADATA_FILENAMES = frozenset(
    {
        ".editorconfig",
        "CODEOWNERS",
        "SECURITY.md",
        "pull_request_template.md",
        "bug_report.yml",
        "feature_request.yml",
    }
)


@dataclass(frozen=True)
class MkdocsLayout:
    config_path: Path
    docs_dir: Path
    nav_paths: tuple[Path, ...]


@dataclass(frozen=True)
class AmbiguousKmpNativeName:
    base_name: str
    variants: tuple[str, ...]
    target_kinds: tuple[str, ...]
    location: Path


def _ignore_matcher(root: Path) -> IgnoreMatcher:
    return IgnoreMatcher(root.resolve())


def _has_source_files(root: Path) -> bool:
    if not root.is_dir():
        return False
    for file_path in root.rglob("*"):
        if file_path.is_file() and file_path.suffix in _SOURCE_FILE_SUFFIXES:
            return True
    return False


def kmp_allowed_source_set_names(project: GradleProject) -> set[str]:
    result = {
        source_set_name
        for source_set_name in CANONICAL_KMP_SOURCE_SET_REQUIREMENTS
        if _source_set_is_allowed_for_platforms(source_set_name, project.platforms)
    }
    has_native_targets = False
    has_apple_targets = False
    has_ios_targets = False
    for target in project.targets:
        if target.kind == "macosArm64":
            has_native_targets = True
            has_apple_targets = True
            target_name = target.name or "macosArm64"
            result.update({f"{target_name}Main", f"{target_name}Test"})
        elif target.kind == "macosX64":
            has_native_targets = True
            has_apple_targets = True
            target_name = target.name or "macosX64"
            result.update({f"{target_name}Main", f"{target_name}Test"})
        elif target.kind in {"linuxX64", "mingwX64"}:
            has_native_targets = True
            target_name = target.name or target.kind
            result.update({f"{target_name}Main", f"{target_name}Test"})
        elif target.kind in {"iosArm64", "iosSimulatorArm64"}:
            has_native_targets = True
            has_apple_targets = True
            has_ios_targets = True
    if has_native_targets:
        result.update({"nativeMain", "nativeTest"})
    if has_apple_targets:
        result.update({"appleMain", "appleTest"})
    if has_ios_targets:
        result.update({"iosMain", "iosTest"})
    return result


def kmp_known_source_set_names(project: GradleProject) -> set[str]:
    return kmp_allowed_source_set_names(project) | set(project.source_sets)


def _kmp_direct_source_set_names_for_target_kind(
    target_kind: str,
    *,
    target_name: str | None = None,
) -> tuple[str, str]:
    if target_kind in {"android-application", "android-kmp-library"}:
        return ("androidMain", "androidUnitTest")

    base_name = target_name or GRADLE_TARGET_KIND_TO_PLATFORM[target_kind]
    return (f"{base_name}Main", f"{base_name}Test")


def kmp_direct_source_set_names_by_platform(project: GradleProject) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}

    if project.targets:
        for target in project.targets:
            platform = GRADLE_TARGET_KIND_TO_PLATFORM[target.kind]
            result[platform] = _kmp_direct_source_set_names_for_target_kind(target.kind, target_name=target.name)
        return result

    for platform in project.platforms:
        target_kind = "android-kmp-library" if platform == "android" else platform
        result[platform] = _kmp_direct_source_set_names_for_target_kind(target_kind)
    return result


def kmp_direct_source_set_platforms(project: GradleProject) -> dict[str, str]:
    result: dict[str, str] = {}
    for platform, source_set_names in kmp_direct_source_set_names_by_platform(project).items():
        main_name, test_name = source_set_names
        result[main_name] = platform
        result[test_name] = platform
    return result


def kmp_source_set_parent_map(project: GradleProject) -> dict[str, tuple[str, ...]]:
    parent_map: dict[str, tuple[str, ...]] = {}
    for _platform, source_set_names in kmp_direct_source_set_names_by_platform(project).items():
        main_name, test_name = source_set_names
        parent_map.setdefault(main_name, ("commonMain",))
        parent_map.setdefault(test_name, ("commonTest",))

    for source_set_name, source_set in project.source_sets.items():
        if source_set.depends_on:
            parent_map[source_set_name] = tuple(source_set.depends_on)
        else:
            parent_map.setdefault(source_set_name, ())

    return parent_map


def kmp_source_set_child_map(project: GradleProject) -> dict[str, tuple[str, ...]]:
    child_map: dict[str, list[str]] = {}
    for source_set_name, parents in kmp_source_set_parent_map(project).items():
        for parent in parents:
            child_map.setdefault(parent, []).append(source_set_name)
    return {name: tuple(sorted(children)) for name, children in child_map.items()}


def kmp_concrete_platforms_for_source_set(project: GradleProject, source_set_name: str) -> frozenset[str]:
    direct_platforms = kmp_direct_source_set_platforms(project)
    child_map = kmp_source_set_child_map(project)
    cache: dict[str, frozenset[str]] = {}

    def visit(current_source_set_name: str, visiting: set[str]) -> frozenset[str]:
        if current_source_set_name in cache:
            return cache[current_source_set_name]
        if current_source_set_name in visiting:
            return frozenset()

        visiting.add(current_source_set_name)
        platforms: set[str] = set()
        direct_platform = direct_platforms.get(current_source_set_name)
        if direct_platform is not None:
            platforms.add(direct_platform)
        for child_source_set_name in child_map.get(current_source_set_name, ()):
            platforms.update(visit(child_source_set_name, visiting))
        visiting.remove(current_source_set_name)
        result = frozenset(platforms)
        cache[current_source_set_name] = result
        return result

    return visit(source_set_name, set())


def kmp_structural_source_set_names(project: GradleProject) -> set[str]:
    canonical_names = {
        source_set_name
        for source_set_name in CANONICAL_KMP_SOURCE_SET_REQUIREMENTS
        if _source_set_is_allowed_for_platforms(source_set_name, project.platforms)
    }
    return canonical_names | set(kmp_direct_source_set_platforms(project))


def kmp_source_set_root_paths(project: GradleProject, source_set_name: str) -> tuple[Path, ...]:
    roots: list[Path] = []
    default_root = (project.path / "src" / source_set_name).resolve()
    if default_root.exists():
        roots.append(default_root)

    source_set = project.source_sets.get(source_set_name)
    if source_set is not None:
        for configured_dir in source_set.kotlin_src_dirs:
            configured_root = (project.path / configured_dir).resolve()
            if configured_root not in roots:
                roots.append(configured_root)

    return tuple(roots)


def kmp_source_set_has_sources(project: GradleProject, source_set_name: str) -> bool:
    return any(_has_source_files(root) for root in kmp_source_set_root_paths(project, source_set_name))


def _ambiguous_native_base_name(name: str) -> str | None:
    match = _KMP_NATIVE_NAME_RE.fullmatch(name)
    if match is None:
        return None
    stem = match.group("stem")
    if any(token in stem.casefold() for token in _EXPLICIT_NATIVE_BOUNDARY_TOKENS):
        return None
    return f"{stem}Native"


def ambiguous_kmp_native_names(project: GradleProject) -> tuple[AmbiguousKmpNativeName, ...]:
    buckets: dict[str, dict[str, object]] = {}

    def remember(base_name: str, variant: str, location: Path, *, target_kind: str | None = None) -> None:
        bucket = buckets.setdefault(
            base_name,
            {
                "variants": set(),
                "target_kinds": set(),
                "location": location.resolve(),
            },
        )
        variants = bucket["variants"]
        assert isinstance(variants, set)
        variants.add(variant)

        if target_kind is not None:
            target_kinds = bucket["target_kinds"]
            assert isinstance(target_kinds, set)
            target_kinds.add(target_kind)

        bucket_location = bucket["location"]
        assert isinstance(bucket_location, Path)
        if bucket_location == project.path.resolve() and location.resolve() != project.path.resolve():
            bucket["location"] = location.resolve()

    for target in project.targets:
        if target.name is None:
            continue
        base_name = _ambiguous_native_base_name(target.name)
        if base_name is None:
            continue
        remember(base_name, target.name, project.path, target_kind=target.kind)

    for source_set_name, source_set_dir in kmp_source_set_directories(project).items():
        base_name = _ambiguous_native_base_name(source_set_name)
        if base_name is None:
            continue
        remember(base_name, source_set_name, source_set_dir)

    for source_set_name in project.source_sets:
        base_name = _ambiguous_native_base_name(source_set_name)
        if base_name is None:
            continue
        remember(base_name, source_set_name, project.path / "src" / source_set_name)

    results: list[AmbiguousKmpNativeName] = []
    for base_name in sorted(buckets):
        bucket = buckets[base_name]
        variants = bucket["variants"]
        target_kinds = bucket["target_kinds"]
        location = bucket["location"]
        assert isinstance(variants, set)
        assert isinstance(target_kinds, set)
        assert isinstance(location, Path)
        results.append(
            AmbiguousKmpNativeName(
                base_name=base_name,
                variants=tuple(sorted(str(variant) for variant in variants)),
                target_kinds=tuple(sorted(str(target_kind) for target_kind in target_kinds)),
                location=location,
            )
        )
    return tuple(results)


def kmp_declared_source_root_paths(project: GradleProject) -> dict[str, tuple[Path, ...]]:
    result: dict[str, tuple[Path, ...]] = {}
    for source_set_name, source_set in project.source_sets.items():
        result[source_set_name] = tuple((project.path / path).resolve() for path in source_set.kotlin_src_dirs)
    return result


def kmp_source_set_directories(project: GradleProject) -> dict[str, Path]:
    src_root = project.path / "src"
    if not src_root.is_dir():
        return {}
    result: dict[str, Path] = {}
    for child in sorted(src_root.iterdir(), key=lambda path: path.name):
        if child.is_dir() and GRADLE_SOURCE_SET_NAME_RE.fullmatch(child.name):
            result[child.name] = child
    return result


def existing_custom_kmp_source_roots(project: GradleProject) -> list[Path]:
    src_root = project.path / "src"
    if not src_root.is_dir():
        return []
    known_names = kmp_known_source_set_names(project)
    roots: list[Path] = []
    for child in sorted(src_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir() or child.name in known_names:
            continue
        for language_dir_name in ("kotlin", "java"):
            language_dir = child / language_dir_name
            if _has_source_files(language_dir):
                roots.append(language_dir.resolve())
    return roots


def expected_gradle_manifest_paths(project: GradleProject) -> set[Path]:
    return {
        (project.path / target.manifest_path).resolve()
        for target in project.targets
        if target.manifest_path is not None
    }


def existing_android_manifest_paths(project: GradleProject) -> list[Path]:
    src_root = project.path / "src"
    if not src_root.is_dir():
        return []
    return sorted(path.resolve() for path in src_root.rglob("AndroidManifest.xml") if path.is_file())


def expected_gradle_resource_roots(project: GradleProject) -> set[Path]:
    if project.is_kmp:
        source_set_names = kmp_known_source_set_names(project)
    else:
        source_set_names = {"main", "test"}
    roots: set[Path] = set()
    for source_set_name in source_set_names:
        roots.add((project.path / "src" / source_set_name / "resources").resolve())
        roots.add((project.path / "src" / source_set_name / "res").resolve())
    return roots


def existing_gradle_resource_roots(project: GradleProject) -> list[Path]:
    src_root = project.path / "src"
    if not src_root.is_dir():
        return []
    roots: list[Path] = []
    for child in sorted(src_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        for resource_dir_name in ("resources", "res"):
            resource_dir = child / resource_dir_name
            if resource_dir.is_dir():
                roots.append(resource_dir.resolve())
    return roots


def discover_python_package_roots(project_path: Path) -> list[Path]:
    ignore_paths = _ignore_matcher(project_path)
    packages: list[Path] = []
    for child in sorted(project_path.iterdir(), key=lambda path: path.name.casefold()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in _PYTHON_PACKAGE_IGNORE_DIRS or ignore_paths.matches(child, is_dir=True):
            continue
        if (child / "__init__.py").is_file():
            packages.append(child.resolve())
    return packages


def parse_pyproject_poetry_paths(project_path: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.is_file():
        return {}, {}

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return {}, {}
    poetry = tool.get("poetry")
    if not isinstance(poetry, dict):
        return {}, {}

    package_paths: dict[str, Path] = {}
    packages = poetry.get("packages")
    if isinstance(packages, list):
        for entry in packages:
            if not isinstance(entry, dict):
                continue
            include_value = entry.get("include")
            from_value = entry.get("from")
            if not isinstance(include_value, str):
                continue
            base_path = project_path / from_value if isinstance(from_value, str) else project_path
            package_paths[include_value] = (base_path / include_value).resolve()

    include_paths: dict[str, Path] = {}
    include_entries = poetry.get("include")
    if isinstance(include_entries, list):
        for entry in include_entries:
            if isinstance(entry, str):
                include_paths[entry] = (project_path / entry).resolve()
                continue
            if not isinstance(entry, dict):
                continue
            path_value = entry.get("path")
            if isinstance(path_value, str):
                include_paths[path_value] = (project_path / path_value).resolve()

    return package_paths, include_paths


def _mkdocs_layout_from_yaml(project_path: Path, config_path: Path, text: str) -> MkdocsLayout | None:
    try:
        import yaml
    except ImportError:
        return None

    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        return None

    docs_dir_value = data.get("docs_dir")
    docs_dir = project_path / (docs_dir_value if isinstance(docs_dir_value, str) else "docs")
    nav_paths: list[Path] = []

    def collect(value: Any) -> None:
        if isinstance(value, str) and value.lower().endswith(tuple(_MARKDOWN_SUFFIXES)):
            nav_paths.append((docs_dir / value).resolve())
            return
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                collect(item)

    collect(data.get("nav"))
    return MkdocsLayout(config_path=config_path, docs_dir=docs_dir.resolve(), nav_paths=tuple(nav_paths))


def load_mkdocs_layout(project_path: Path) -> MkdocsLayout | None:
    config_path = project_path / "mkdocs.yml"
    if not config_path.is_file():
        return None
    text = config_path.read_text(encoding="utf-8")

    yaml_layout = _mkdocs_layout_from_yaml(project_path, config_path, text)
    if yaml_layout is not None:
        return yaml_layout

    docs_dir_match = _MKDOCS_DOCS_DIR_RE.search(text)
    docs_dir_name = docs_dir_match.group("path") if docs_dir_match is not None else "docs"
    docs_dir = (project_path / docs_dir_name).resolve()
    nav_paths = tuple((docs_dir / match.group("path")).resolve() for match in _MKDOCS_NAV_PATH_RE.finditer(text))
    return MkdocsLayout(config_path=config_path, docs_dir=docs_dir, nav_paths=nav_paths)


def discover_markdown_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    matcher = _ignore_matcher(root)
    files: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        current_path = Path(current_root)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not dirname.startswith(".") and not matcher.matches(current_path / dirname, is_dir=True)
        ]
        for filename in filenames:
            file_path = current_path / filename
            if file_path.suffix.lower() not in _MARKDOWN_SUFFIXES:
                continue
            if matcher.matches(file_path, is_dir=False):
                continue
            files.append(file_path.resolve())
    return sorted(files)


def expected_repo_metadata_paths_for_plan(plan: RepoMetadataPlan) -> set[Path]:
    return {path.resolve() for path in expected_repo_metadata_paths(plan)}
