from __future__ import annotations

import os
from pathlib import Path

from dev.checks.base import Issue, IssueType, ProjectCheck, RepoCheck, Severity
from dev.config import (
    CANONICAL_KMP_SOURCE_SET_REQUIREMENTS,
    GradleProject,
    Project,
    PythonProject,
    _source_set_is_allowed_for_platforms,
    load_config,
)
from dev.ignore_files import IgnoreMatcher
from dev.licenses import license_display_name, license_spdx_url
from dev.project_layout import build_project_layout
from dev.project_metadata import (
    MONITORED_REPO_METADATA_FILENAMES,
    ambiguous_kmp_native_names,
    discover_markdown_files,
    discover_python_package_roots,
    existing_android_manifest_paths,
    existing_custom_kmp_source_roots,
    existing_gradle_resource_roots,
    expected_gradle_manifest_paths,
    expected_gradle_resource_roots,
    expected_repo_metadata_paths_for_plan,
    kmp_concrete_platforms_for_source_set,
    kmp_declared_source_root_paths,
    kmp_direct_source_set_platforms,
    kmp_known_source_set_names,
    kmp_source_set_child_map,
    kmp_source_set_directories,
    kmp_source_set_has_sources,
    kmp_source_set_parent_map,
    kmp_source_set_root_paths,
    kmp_structural_source_set_names,
    load_mkdocs_layout,
    parse_pyproject_poetry_paths,
)
from dev.repo_metadata import build_repo_metadata_plan, repo_projects_for_root

E_KMP_CUSTOM_SOURCE_ROOT_UNDECLARED = IssueType(
    "E_KMP_CUSTOM_SOURCE_ROOT_UNDECLARED",
    "KMP custom source root is not declared in root.clj sourceSets.kotlinSrcDirs: {relative_path}.",
)
E_KMP_DECLARED_SOURCE_ROOT_MISSING = IssueType(
    "E_KMP_DECLARED_SOURCE_ROOT_MISSING",
    "KMP declared source root does not exist on disk: {relative_path}.",
)
E_KMP_DECLARED_SOURCE_ROOT_EMPTY = IssueType(
    "E_KMP_DECLARED_SOURCE_ROOT_EMPTY",
    "KMP declared source root exists but contains no Kotlin/Java sources: {relative_path}.",
    severity=Severity.WARNING,
)
E_KMP_SOURCE_SET_DIRECTORY_UNDECLARED = IssueType(
    "E_KMP_SOURCE_SET_DIRECTORY_UNDECLARED",
    "KMP source set directory exists on disk but is not declared in root.clj: {source_set}.",
)
E_KMP_PLATFORM_SOURCE_SET_WITHOUT_TARGET = IssueType(
    "E_KMP_PLATFORM_SOURCE_SET_WITHOUT_TARGET",
    "KMP source set directory requires an unsupported target for this project: {source_set}.",
)
E_KMP_AMBIGUOUS_NATIVE_NAME = IssueType(
    "E_KMP_AMBIGUOUS_NATIVE_NAME",
    "Ambiguous KMP native name '{name}'; 'Native' does not say which machine or portability boundary it refers to"
    " (found: {variants}{target_suffix}).",
    severity=Severity.WARNING,
)
E_KMP_REDUNDANT_TARGET_ALIAS = IssueType(
    "E_KMP_REDUNDANT_TARGET_ALIAS",
    "KMP target alias '{alias}' for {platform} appears redundant; no alias-specific source sets or source roots use it.",
    severity=Severity.WARNING,
)
E_KMP_SINGLE_TARGET_ABSTRACTION = IssueType(
    "E_KMP_SINGLE_TARGET_ABSTRACTION",
    "Custom KMP source set '{source_set}' only serves one concrete platform ({platform}); consider using the platform source set directly.",
    severity=Severity.WARNING,
)
E_KMP_PASS_THROUGH_SOURCE_SET = IssueType(
    "E_KMP_PASS_THROUGH_SOURCE_SET",
    "Custom KMP source set '{source_set}' has no sources or direct dependencies and only forwards the graph{detail}.",
    severity=Severity.WARNING,
)
E_KMP_FILE_SUFFIX_BOUNDARY = IssueType(
    "E_KMP_FILE_SUFFIX_BOUNDARY",
    "File boundary suffix '.{suffix}' in {file_name} does not match {source_set}: {reason}.",
    severity=Severity.WARNING,
)
E_KMP_ALIAS_MEANING_MISMATCH = IssueType(
    "E_KMP_ALIAS_MEANING_MISMATCH",
    "KMP name '{name}' implies {implied}, but the actual platform scope is {actual_scope}.",
    severity=Severity.WARNING,
)
E_GRADLE_MANIFEST_PATH_MISSING = IssueType(
    "E_GRADLE_MANIFEST_PATH_MISSING",
    "Configured Gradle manifest path does not exist on disk: {relative_path}.",
)
E_GRADLE_UNDECLARED_MANIFEST_PATH = IssueType(
    "E_GRADLE_UNDECLARED_MANIFEST_PATH",
    "Android manifest exists on disk but is not declared by the current Gradle targets: {relative_path}.",
)
E_GRADLE_UNDECLARED_RESOURCE_ROOT = IssueType(
    "E_GRADLE_UNDECLARED_RESOURCE_ROOT",
    "Gradle resource root exists on disk but is not part of the current source-set layout: {relative_path}.",
)
E_GRADLE_PUBLICATION_LICENSE_FILE_MISSING = IssueType(
    "E_GRADLE_PUBLICATION_LICENSE_FILE_MISSING",
    "Publishable Gradle project is missing repo-root LICENSE.md.",
)
E_GRADLE_PUBLICATION_METADATA_DRIFT = IssueType(
    "E_GRADLE_PUBLICATION_METADATA_DRIFT",
    "Gradle build file is missing expected publication metadata value: {expected}.",
)
E_PYTHON_PACKAGE_ROOT_UNDECLARED = IssueType(
    "E_PYTHON_PACKAGE_ROOT_UNDECLARED",
    "Python package root exists on disk but is not declared in pyproject.toml packages: {package}.",
)
E_PYTHON_DECLARED_PACKAGE_ROOT_MISSING = IssueType(
    "E_PYTHON_DECLARED_PACKAGE_ROOT_MISSING",
    "Python package root declared in pyproject.toml is missing on disk: {package}.",
)
E_PYTHON_DECLARED_INCLUDE_PATH_MISSING = IssueType(
    "E_PYTHON_DECLARED_INCLUDE_PATH_MISSING",
    "Python include path declared in pyproject.toml is missing on disk: {path}.",
)
E_DOCS_ROOT_MISSING = IssueType(
    "E_DOCS_ROOT_MISSING",
    "Documentation root configured by mkdocs.yml does not exist: {relative_path}.",
)
E_DOCS_NAV_PATH_MISSING = IssueType(
    "E_DOCS_NAV_PATH_MISSING",
    "MkDocs nav entry points to a missing documentation file: {relative_path}.",
)
E_DOCS_FILE_NOT_IN_NAV = IssueType(
    "E_DOCS_FILE_NOT_IN_NAV",
    "Documentation file exists on disk but is not reachable from MkDocs nav: {relative_path}.",
    severity=Severity.WARNING,
)
E_MISPLACED_REPO_METADATA_FILE = IssueType(
    "E_MISPLACED_REPO_METADATA_FILE",
    "Repository metadata file is in the wrong location: {relative_path}.",
)
E_TEST_LICENSE_COPY_MISSING = IssueType(
    "E_TEST_LICENSE_COPY_MISSING",
    "Configured test-license coverage is missing a local LICENSE.md in {relative_path}.",
)
E_STALE_TEST_LICENSE_COPY = IssueType(
    "E_STALE_TEST_LICENSE_COPY",
    "Test directory contains LICENSE.md but the project has no test_license configured: {relative_path}.",
)


def _relative_to_project(project: Project, path: Path) -> str:
    return path.resolve().relative_to(project.path.resolve()).as_posix()


def _repo_relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _has_source_files(root: Path) -> bool:
    for file_path in root.rglob("*"):
        if file_path.is_file() and file_path.suffix in {".kt", ".kts", ".java", ".scala"}:
            return True
    return False


def _project_is_publishable_gradle(project: GradleProject) -> bool:
    return project.publish and not project.quarantine and project.publish_target is not None


def _expected_publication_strings(project: GradleProject, config: object) -> list[str]:
    if project.github_repo is None:
        return []
    default_company_name = getattr(config, "default_company_legal_name", None)
    default_company_email = getattr(config, "default_company_email", None)
    github_repo_url = f"https://github.com/{project.github_repo}"
    scm_connection = f"scm:git:git://github.com/{project.github_repo}.git"
    scm_developer_connection = f"scm:git:ssh://git@github.com/{project.github_repo}.git"
    license_name = license_display_name(project.license) or "Open Source"
    license_url = license_spdx_url(project.license) or github_repo_url
    values = [
        license_name,
        license_url,
        github_repo_url,
        scm_connection,
        scm_developer_connection,
    ]
    if default_company_name:
        values.append(default_company_name)
    if default_company_email:
        values.append(default_company_email)
    if project.description:
        values.append(project.description)
    return values


_KMP_APPLE_PLATFORMS = frozenset({"iosArm64", "iosSimulatorArm64", "macosArm64", "macosX64"})
_KMP_IOS_PLATFORMS = frozenset({"iosArm64", "iosSimulatorArm64"})
_KMP_MACOS_PLATFORMS = frozenset({"macosArm64", "macosX64"})
_KMP_POSIX_PLATFORMS = frozenset({"iosArm64", "iosSimulatorArm64", "macosArm64", "macosX64", "linuxX64"})
_KMP_DESKTOP_PLATFORMS = frozenset({"jvm", "macosArm64", "macosX64", "linuxX64", "mingwX64"})
_KMP_MOBILE_PLATFORMS = frozenset({"android", "iosArm64", "iosSimulatorArm64"})
_KMP_WEB_PLATFORMS = frozenset({"js", "wasmJs"})


def _strip_source_set_suffix(name: str) -> str:
    for suffix in ("UnitTest", "Main", "Test"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _sorted_platforms(platforms: set[str] | frozenset[str]) -> tuple[str, ...]:
    return tuple(sorted(platforms))


def _render_platform_scope(platforms: set[str] | frozenset[str]) -> str:
    ordered = _sorted_platforms(platforms)
    return ", ".join(ordered) if ordered else "none"


def _semantic_platform_scope(name: str) -> tuple[str, frozenset[str]] | None:
    normalized = _strip_source_set_suffix(name).casefold()
    detected: list[tuple[str, frozenset[str]]] = []

    def add(label: str, platforms: frozenset[str]) -> None:
        if any(existing_platforms == platforms for _, existing_platforms in detected):
            return
        detected.append((label, platforms))

    has_ios_simulator = "iossimulatorarm64" in normalized or "iossimulator" in normalized
    has_ios_arm64 = "iosarm64" in normalized
    has_macos_arm64 = "macosarm64" in normalized
    has_macos_x64 = "macosx64" in normalized
    has_linux_x64 = "linuxx64" in normalized
    has_mingw_x64 = "mingwx64" in normalized

    if has_ios_simulator:
        add("iosSimulatorArm64", frozenset({"iosSimulatorArm64"}))
    if has_ios_arm64:
        add("iosArm64", frozenset({"iosArm64"}))
    if has_macos_arm64:
        add("macosArm64", frozenset({"macosArm64"}))
    if has_macos_x64:
        add("macosX64", frozenset({"macosX64"}))
    if has_linux_x64:
        add("linuxX64", frozenset({"linuxX64"}))
    if has_mingw_x64:
        add("mingwX64", frozenset({"mingwX64"}))

    if "ios" in normalized and not (has_ios_simulator or has_ios_arm64):
        add("iOS", _KMP_IOS_PLATFORMS)
    if ("macos" in normalized or "darwin" in normalized) and not (has_macos_arm64 or has_macos_x64):
        add("macOS", _KMP_MACOS_PLATFORMS)
    if ("linux" in normalized) and not has_linux_x64:
        add("Linux", frozenset({"linuxX64"}))
    if ("mingw" in normalized or "windows" in normalized) and not has_mingw_x64:
        add("Windows", frozenset({"mingwX64"}))
    if "android" in normalized:
        add("Android", frozenset({"android"}))
    if "jvm" in normalized:
        add("JVM", frozenset({"jvm"}))
    if "apple" in normalized:
        add("Apple", _KMP_APPLE_PLATFORMS)
    if "posix" in normalized or "unix" in normalized:
        add("POSIX", _KMP_POSIX_PLATFORMS)
    if "desktop" in normalized:
        add("desktop", _KMP_DESKTOP_PLATFORMS)
    if "mobile" in normalized:
        add("mobile", _KMP_MOBILE_PLATFORMS)
    if "browser" in normalized or "web" in normalized:
        add("web", _KMP_WEB_PLATFORMS)
    if "wasm" in normalized:
        add("Wasm", frozenset({"wasmJs"}))
    if "js" in normalized:
        add("JS", frozenset({"js"}))

    if not detected:
        return None
    if len(detected) == 1:
        return detected[0]

    labels = " + ".join(label for label, _ in detected)
    platforms: set[str] = set()
    for _, detected_platforms in detected:
        platforms.update(detected_platforms)
    return (labels, frozenset(platforms))


def _source_set_names_using_target_alias(project: GradleProject, alias: str) -> tuple[str, ...]:
    prefixes = (f"{alias}Main", f"{alias}Test", f"{alias}UnitTest")
    names: set[str] = set()
    for source_set_name in set(project.source_sets) | set(kmp_source_set_directories(project)):
        if any(source_set_name == prefix for prefix in prefixes):
            names.add(source_set_name)
    return tuple(sorted(names))


def _is_custom_kmp_source_set(project: GradleProject, source_set_name: str) -> bool:
    return source_set_name not in kmp_structural_source_set_names(project)


def _source_set_source_files(project: GradleProject, source_set_name: str) -> tuple[Path, ...]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root in kmp_source_set_root_paths(project, source_set_name):
        if not root.exists():
            continue
        if root.is_file():
            if root.suffix == ".kt" and root not in seen:
                seen.add(root)
                files.append(root)
            continue
        for file_path in root.rglob("*.kt"):
            if file_path not in seen:
                seen.add(file_path)
                files.append(file_path)
    return tuple(sorted(files))


class KmpSourceLayoutDriftCheck(ProjectCheck):
    """
    Ensure KMP source roots and source-set directories on disk line up with
    declared sourceSets, declared kotlinSrcDirs, and enabled targets.
    """

    order = 225

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject) or not project.is_kmp:
            return []

        issues: list[Issue] = []
        known_source_set_names = kmp_known_source_set_names(project)
        declared_source_roots = {
            root_path
            for source_roots in kmp_declared_source_root_paths(project).values()
            for root_path in source_roots
        }

        for source_root in existing_custom_kmp_source_roots(project):
            if source_root not in declared_source_roots:
                issues.append(
                    E_KMP_CUSTOM_SOURCE_ROOT_UNDECLARED.make(relative_path=_relative_to_project(project, source_root)).at(
                        source_root
                    )
                )

        for source_roots in kmp_declared_source_root_paths(project).values():
            for source_root in source_roots:
                if not source_root.exists():
                    issues.append(
                        E_KMP_DECLARED_SOURCE_ROOT_MISSING.make(relative_path=_relative_to_project(project, source_root)).at(
                            source_root
                        )
                    )
                    continue
                if not _has_source_files(source_root):
                    issues.append(
                        E_KMP_DECLARED_SOURCE_ROOT_EMPTY.make(relative_path=_relative_to_project(project, source_root)).at(
                            source_root
                        )
                    )

        for source_set_name, source_set_dir in kmp_source_set_directories(project).items():
            if source_set_name in known_source_set_names:
                if (
                    source_set_name in CANONICAL_KMP_SOURCE_SET_REQUIREMENTS
                    and not _source_set_is_allowed_for_platforms(source_set_name, project.platforms)
                ):
                    issues.append(
                        E_KMP_PLATFORM_SOURCE_SET_WITHOUT_TARGET.make(source_set=source_set_name).at(source_set_dir)
                    )
                continue
            if source_set_name in CANONICAL_KMP_SOURCE_SET_REQUIREMENTS:
                if not _source_set_is_allowed_for_platforms(source_set_name, project.platforms):
                    issues.append(
                        E_KMP_PLATFORM_SOURCE_SET_WITHOUT_TARGET.make(source_set=source_set_name).at(source_set_dir)
                    )
                continue
            if source_set_name not in project.source_sets:
                issues.append(E_KMP_SOURCE_SET_DIRECTORY_UNDECLARED.make(source_set=source_set_name).at(source_set_dir))

        return issues


class KmpSourceSetNamingStyleCheck(ProjectCheck):
    """
    Warn on custom KMP native aliases/source-set names that hide the concrete
    platform or portability boundary behind a generic '*Native*' label.
    """

    order = 226

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject) or not project.is_kmp:
            return []

        issues: list[Issue] = []
        for finding in ambiguous_kmp_native_names(project):
            target_suffix = ""
            if finding.target_kinds:
                rendered_target_kinds = ", ".join(finding.target_kinds)
                target_suffix = f"; target kind(s): {rendered_target_kinds}"
            issues.append(
                E_KMP_AMBIGUOUS_NATIVE_NAME.make(
                    name=finding.base_name,
                    variants=", ".join(finding.variants),
                    target_suffix=target_suffix,
                ).at(finding.location)
            )
        return issues


class KmpRedundantTargetAliasCheck(ProjectCheck):
    """
    Warn on custom target aliases that never become alias-specific source sets
    or source roots.
    """

    order = 227

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject) or not project.is_kmp:
            return []

        issues: list[Issue] = []
        source_set_dirs = kmp_source_set_directories(project)
        for target in project.targets:
            if target.name is None:
                continue
            alias_source_sets = _source_set_names_using_target_alias(project, target.name)
            alias_source_dirs = [
                source_set_name
                for source_set_name in alias_source_sets
                if source_set_name in source_set_dirs or source_set_name in project.source_sets
            ]
            if alias_source_dirs:
                continue
            issues.append(
                E_KMP_REDUNDANT_TARGET_ALIAS.make(
                    alias=target.name,
                    platform=target.kind,
                ).at(project.path)
            )
        return issues


class KmpAliasMeaningMismatchCheck(ProjectCheck):
    """
    Warn when a custom alias/source-set name implies a platform scope that
    contradicts or greatly overstates the actual concrete platforms involved.
    """

    order = 228

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject) or not project.is_kmp:
            return []

        issues: list[Issue] = []

        for target in project.targets:
            if target.name is None:
                continue
            semantic_scope = _semantic_platform_scope(target.name)
            if semantic_scope is None:
                continue
            implied_label, implied_platforms = semantic_scope
            actual_platform = "android" if target.kind.startswith("android-") else target.kind
            actual_platforms = frozenset({actual_platform})
            if not actual_platforms <= implied_platforms or (
                len(actual_platforms) == 1 and actual_platforms != implied_platforms
            ):
                issues.append(
                    E_KMP_ALIAS_MEANING_MISMATCH.make(
                        name=target.name,
                        implied=implied_label,
                        actual_scope=_render_platform_scope(actual_platforms),
                    ).at(project.path)
                )

        for source_set_name in sorted(project.source_sets):
            if not _is_custom_kmp_source_set(project, source_set_name):
                continue
            semantic_scope = _semantic_platform_scope(source_set_name)
            if semantic_scope is None:
                continue
            actual_platforms = kmp_concrete_platforms_for_source_set(project, source_set_name)
            if not actual_platforms:
                continue
            implied_label, implied_platforms = semantic_scope
            if not actual_platforms <= implied_platforms or (
                len(actual_platforms) == 1 and actual_platforms != implied_platforms
            ):
                issues.append(
                    E_KMP_ALIAS_MEANING_MISMATCH.make(
                        name=source_set_name,
                        implied=implied_label,
                        actual_scope=_render_platform_scope(actual_platforms),
                    ).at(project.path / "src" / source_set_name)
                )

        return issues


class KmpSingleTargetAbstractionCheck(ProjectCheck):
    """
    Warn when a custom source set only serves a single concrete platform.
    """

    order = 229

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject) or not project.is_kmp:
            return []

        issues: list[Issue] = []
        for source_set_name in sorted(project.source_sets):
            if not _is_custom_kmp_source_set(project, source_set_name):
                continue
            concrete_platforms = kmp_concrete_platforms_for_source_set(project, source_set_name)
            if len(concrete_platforms) != 1:
                continue
            issues.append(
                E_KMP_SINGLE_TARGET_ABSTRACTION.make(
                    source_set=source_set_name,
                    platform=_render_platform_scope(concrete_platforms),
                ).at(project.path / "src" / source_set_name)
            )
        return issues


class KmpPassThroughSourceSetCheck(ProjectCheck):
    """
    Warn when a custom source set is effectively just an empty relay node.
    """

    order = 231

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject) or not project.is_kmp:
            return []

        issues: list[Issue] = []
        parent_map = kmp_source_set_parent_map(project)
        child_map = kmp_source_set_child_map(project)
        for source_set_name, source_set in sorted(project.source_sets.items()):
            if not _is_custom_kmp_source_set(project, source_set_name):
                continue
            if source_set.dependencies:
                continue
            if kmp_source_set_has_sources(project, source_set_name):
                continue

            parents = parent_map.get(source_set_name, ())
            children = child_map.get(source_set_name, ())
            concrete_platforms = kmp_concrete_platforms_for_source_set(project, source_set_name)
            if len(children) > 1 and len(concrete_platforms) > 1:
                continue

            detail_parts: list[str] = []
            if parents:
                detail_parts.append(f"{len(parents)} parent")
            if children:
                detail_parts.append(f"{len(children)} child")
            if concrete_platforms:
                detail_parts.append(f"scope={_render_platform_scope(concrete_platforms)}")
            detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
            issues.append(
                E_KMP_PASS_THROUGH_SOURCE_SET.make(
                    source_set=source_set_name,
                    detail=detail,
                ).at(project.path / "src" / source_set_name)
            )

        return issues


class KmpFileSuffixBoundaryCheck(ProjectCheck):
    """
    Warn when Kotlin file suffixes encode a platform boundary that conflicts
    with the containing source set.
    """

    order = 232

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject) or not project.is_kmp:
            return []

        issues: list[Issue] = []
        direct_source_set_platforms = kmp_direct_source_set_platforms(project)
        source_set_names = sorted(set(kmp_source_set_directories(project)) | set(project.source_sets))
        for source_set_name in source_set_names:
            actual_platforms = frozenset(
                {direct_source_set_platforms[source_set_name]}
                if source_set_name in direct_source_set_platforms
                else kmp_concrete_platforms_for_source_set(project, source_set_name)
            )
            if not actual_platforms:
                continue

            for file_path in _source_set_source_files(project, source_set_name):
                stem_parts = file_path.stem.split(".")
                if len(stem_parts) < 2:
                    continue
                suffix = stem_parts[-1]
                semantic_scope = _semantic_platform_scope(suffix)
                reason: str | None = None
                if semantic_scope is None:
                    if "native" in suffix.casefold() and len(actual_platforms) == 1:
                        reason = f"generic native suffix is too broad for {_render_platform_scope(actual_platforms)}"
                else:
                    implied_label, implied_platforms = semantic_scope
                    if suffix.casefold() == "js" and actual_platforms == frozenset({"wasmJs"}):
                        continue
                    if not actual_platforms <= implied_platforms:
                        reason = f"it implies {implied_label}, but this source set serves {_render_platform_scope(actual_platforms)}"
                if reason is None:
                    continue
                issues.append(
                    E_KMP_FILE_SUFFIX_BOUNDARY.make(
                        suffix=suffix,
                        file_name=file_path.name,
                        source_set=source_set_name,
                        reason=reason,
                    ).at(file_path)
                )

        return issues


class GradleManifestResourceDriftCheck(ProjectCheck):
    """
    Ensure Gradle manifest and resource roots on disk still match the current
    target/source-set layout.
    """

    order = 230

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject):
            return []

        issues: list[Issue] = []
        expected_manifests = expected_gradle_manifest_paths(project)
        for manifest_path in sorted(expected_manifests):
            if not manifest_path.is_file():
                issues.append(
                    E_GRADLE_MANIFEST_PATH_MISSING.make(relative_path=_relative_to_project(project, manifest_path)).at(
                        manifest_path
                    )
                )

        for manifest_path in existing_android_manifest_paths(project):
            if manifest_path not in expected_manifests:
                issues.append(
                    E_GRADLE_UNDECLARED_MANIFEST_PATH.make(relative_path=_relative_to_project(project, manifest_path)).at(
                        manifest_path
                    )
                )

        expected_resource_roots = expected_gradle_resource_roots(project)
        for resource_root in existing_gradle_resource_roots(project):
            if resource_root not in expected_resource_roots:
                issues.append(
                    E_GRADLE_UNDECLARED_RESOURCE_ROOT.make(relative_path=_relative_to_project(project, resource_root)).at(
                        resource_root
                    )
                )

        return issues


class GradlePublicationMetadataDriftCheck(ProjectCheck):
    """
    Ensure publishable Gradle projects still have repo files and generated build
    metadata that support the configured publication metadata.
    """

    order = 235

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject) or not _project_is_publishable_gradle(project):
            return []

        issues: list[Issue] = []
        repo_license_path = project.effective_repo_root / "LICENSE.md"
        if not repo_license_path.is_file():
            issues.append(E_GRADLE_PUBLICATION_LICENSE_FILE_MISSING.at(project.effective_repo_root))

        build_file = project.path / "build.gradle.kts"
        if not build_file.is_file():
            issues.append(E_GRADLE_PUBLICATION_METADATA_DRIFT.make(expected="build.gradle.kts").at(project.path))
            return issues

        build_text = build_file.read_text(encoding="utf-8")
        config = load_config(project.path)
        for expected_value in _expected_publication_strings(project, config):
            if expected_value and expected_value not in build_text:
                issues.append(E_GRADLE_PUBLICATION_METADATA_DRIFT.make(expected=expected_value).at(build_file))
        return issues


class PythonPackageLayoutDriftCheck(ProjectCheck):
    """
    Ensure Python package roots on disk line up with pyproject.toml package and
    include declarations.
    """

    order = 230

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, PythonProject):
            return []

        issues: list[Issue] = []
        declared_packages, declared_includes = parse_pyproject_poetry_paths(project.path)
        discovered_packages = {package_path.name: package_path for package_path in discover_python_package_roots(project.path)}

        for package_name, package_path in discovered_packages.items():
            if package_name not in declared_packages:
                issues.append(E_PYTHON_PACKAGE_ROOT_UNDECLARED.make(package=package_name).at(package_path))

        for package_name, package_path in declared_packages.items():
            if not package_path.exists():
                issues.append(E_PYTHON_DECLARED_PACKAGE_ROOT_MISSING.make(package=package_name).at(project.path))

        for include_path_name, include_path in declared_includes.items():
            if not include_path.exists():
                issues.append(
                    E_PYTHON_DECLARED_INCLUDE_PATH_MISSING.make(path=include_path_name).at(project.path / include_path_name)
                )

        return issues


class DocsLayoutDriftCheck(ProjectCheck):
    """
    Ensure mkdocs documentation roots, nav references, and on-disk docs pages do
    not drift apart.
    """

    order = 232

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if project is None or not project.docs_enabled or project.docs_system != "mkdocs":
            return []

        mkdocs_layout = load_mkdocs_layout(project.path)
        if mkdocs_layout is None:
            return []

        issues: list[Issue] = []
        if not mkdocs_layout.docs_dir.is_dir():
            issues.append(
                E_DOCS_ROOT_MISSING.make(relative_path=_relative_to_project(project, mkdocs_layout.docs_dir)).at(
                    mkdocs_layout.config_path
                )
            )
            return issues

        for nav_path in mkdocs_layout.nav_paths:
            if not nav_path.is_file():
                issues.append(
                    E_DOCS_NAV_PATH_MISSING.make(relative_path=_relative_to_project(project, nav_path)).at(
                        mkdocs_layout.config_path
                    )
                )

        nav_paths = {path.resolve() for path in mkdocs_layout.nav_paths}
        for docs_file in discover_markdown_files(mkdocs_layout.docs_dir):
            if docs_file not in nav_paths:
                issues.append(
                    E_DOCS_FILE_NOT_IN_NAV.make(relative_path=_relative_to_project(project, docs_file)).at(docs_file)
                )
        return issues


class RepoMetadataPlacementDriftCheck(RepoCheck):
    """
    Ensure repo metadata files like CODEOWNERS and SECURITY live only in their
    expected generated locations.
    """

    order = 82

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        del project
        config = load_config(path)
        repo_root = path.resolve()
        repo_projects = repo_projects_for_root(config, repo_root)
        plan = build_repo_metadata_plan(config, repo_root, repo_projects)
        if plan is None:
            return []

        expected_paths = expected_repo_metadata_paths_for_plan(plan)
        ignore_matcher = IgnoreMatcher(repo_root)
        issues: list[Issue] = []
        for current_root, dirnames, filenames in os.walk(repo_root):
            current_path = Path(current_root)
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if not ignore_matcher.matches(current_path / dirname, is_dir=True)
            ]
            for filename in filenames:
                if filename not in MONITORED_REPO_METADATA_FILENAMES:
                    continue
                file_path = current_path / filename
                if ignore_matcher.matches(file_path, is_dir=False):
                    continue
                if file_path.resolve() in expected_paths:
                    continue
                issues.append(
                    E_MISPLACED_REPO_METADATA_FILE.make(relative_path=_repo_relative(repo_root, file_path)).at(file_path)
                )
        return issues


class TestLicenseCoverageCheck(ProjectCheck):
    """
    Ensure test-license coverage is reflected in local test-directory LICENSE.md
    files and that stale copies do not linger when test_license is unset.
    """

    order = 95

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if project is None:
            return []

        layout = build_project_layout(project)
        issues: list[Issue] = []
        if project.test_license is not None:
            for test_root in layout.test_license_roots:
                license_path = test_root / "LICENSE.md"
                if not license_path.is_file():
                    issues.append(
                        E_TEST_LICENSE_COPY_MISSING.make(relative_path=_relative_to_project(project, test_root)).at(
                            test_root
                        )
                    )
            return issues

        for test_root in layout.test_license_roots:
            license_path = test_root / "LICENSE.md"
            if license_path.is_file():
                issues.append(
                    E_STALE_TEST_LICENSE_COPY.make(relative_path=_relative_to_project(project, test_root)).at(
                        license_path
                    )
                )
        return issues


__all__ = [
    "DocsLayoutDriftCheck",
    "E_DOCS_FILE_NOT_IN_NAV",
    "E_DOCS_NAV_PATH_MISSING",
    "E_DOCS_ROOT_MISSING",
    "E_GRADLE_MANIFEST_PATH_MISSING",
    "E_GRADLE_PUBLICATION_LICENSE_FILE_MISSING",
    "E_GRADLE_PUBLICATION_METADATA_DRIFT",
    "E_GRADLE_UNDECLARED_MANIFEST_PATH",
    "E_GRADLE_UNDECLARED_RESOURCE_ROOT",
    "E_KMP_CUSTOM_SOURCE_ROOT_UNDECLARED",
    "E_KMP_DECLARED_SOURCE_ROOT_EMPTY",
    "E_KMP_DECLARED_SOURCE_ROOT_MISSING",
    "E_KMP_PLATFORM_SOURCE_SET_WITHOUT_TARGET",
    "E_KMP_SOURCE_SET_DIRECTORY_UNDECLARED",
    "E_MISPLACED_REPO_METADATA_FILE",
    "E_PYTHON_DECLARED_INCLUDE_PATH_MISSING",
    "E_PYTHON_DECLARED_PACKAGE_ROOT_MISSING",
    "E_PYTHON_PACKAGE_ROOT_UNDECLARED",
    "E_STALE_TEST_LICENSE_COPY",
    "E_TEST_LICENSE_COPY_MISSING",
    "GradleManifestResourceDriftCheck",
    "GradlePublicationMetadataDriftCheck",
    "KmpSourceLayoutDriftCheck",
    "PythonPackageLayoutDriftCheck",
    "RepoMetadataPlacementDriftCheck",
    "TestLicenseCoverageCheck",
]
