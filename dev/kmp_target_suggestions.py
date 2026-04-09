from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dev.config import (
    APPLE_KMP_PLATFORMS,
    NATIVE_KMP_PLATFORMS,
    SUPPORTED_KMP_PLATFORMS,
    Config,
    GradleProject,
    Project,
    ProjectDependencyTarget,
)

_IOS_KMP_PLATFORMS: frozenset[str] = frozenset({"iosArm64", "iosSimulatorArm64"})

_DIRECT_SOURCE_SETS_BY_PLATFORM: dict[str, tuple[str, str]] = {
    "jvm": ("jvmMain", "jvmTest"),
    "android": ("androidMain", "androidUnitTest"),
    "js": ("jsMain", "jsTest"),
    "wasmJs": ("wasmJsMain", "wasmJsTest"),
    "iosArm64": ("iosArm64Main", "iosArm64Test"),
    "iosSimulatorArm64": ("iosSimulatorArm64Main", "iosSimulatorArm64Test"),
    "macosX64": ("macosX64Main", "macosX64Test"),
    "macosArm64": ("macosArm64Main", "macosArm64Test"),
    "linuxX64": ("linuxX64Main", "linuxX64Test"),
    "mingwX64": ("mingwX64Main", "mingwX64Test"),
}


@dataclass(frozen=True)
class KmpTargetExpansionSuggestion:
    platform: str
    supporting_dependencies: tuple[str, ...]
    newly_activated_source_sets: tuple[str, ...]


def _default_source_set_parents_for_platform(platform: str) -> dict[str, list[str]]:
    if platform == "jvm":
        return {
            "jvmMain": ["commonMain"],
            "jvmTest": ["commonTest"],
        }
    if platform == "android":
        return {
            "androidMain": ["commonMain"],
            "androidUnitTest": ["commonTest"],
        }
    if platform == "js":
        return {
            "jsMain": ["commonMain"],
            "jsTest": ["commonTest"],
        }
    if platform == "wasmJs":
        return {
            "wasmJsMain": ["commonMain"],
            "wasmJsTest": ["commonTest"],
        }
    if platform == "iosArm64":
        return {
            "iosArm64Main": ["commonMain"],
            "iosArm64Test": ["commonTest"],
        }
    if platform == "iosSimulatorArm64":
        return {
            "iosSimulatorArm64Main": ["commonMain"],
            "iosSimulatorArm64Test": ["commonTest"],
        }
    if platform == "macosArm64":
        return {
            "macosArm64Main": ["commonMain"],
            "macosArm64Test": ["commonTest"],
        }
    if platform == "macosX64":
        return {
            "macosX64Main": ["commonMain"],
            "macosX64Test": ["commonTest"],
        }
    if platform == "linuxX64":
        return {
            "linuxX64Main": ["commonMain"],
            "linuxX64Test": ["commonTest"],
        }
    if platform == "mingwX64":
        return {
            "mingwX64Main": ["commonMain"],
            "mingwX64Test": ["commonTest"],
        }
    return {}


def _source_set_base_required_platforms(source_set_name: str, platforms: list[str]) -> set[str]:
    if source_set_name in {"commonMain", "commonTest"}:
        return {"common"}
    if source_set_name in {"jvmMain", "jvmTest"}:
        return {"jvm"} if "jvm" in platforms else set()
    if source_set_name in {"androidMain", "androidUnitTest"}:
        return {"android"} if "android" in platforms else set()
    if source_set_name in {"jsMain", "jsTest"}:
        return {"js"} if "js" in platforms else set()
    if source_set_name in {"wasmJsMain", "wasmJsTest"}:
        return {"wasmJs"} if "wasmJs" in platforms else set()
    if source_set_name in {"nativeMain", "nativeTest"}:
        return {"common"} if any(platform in NATIVE_KMP_PLATFORMS for platform in platforms) else set()
    if source_set_name in {"appleMain", "appleTest"}:
        return {"apple"} if any(platform in APPLE_KMP_PLATFORMS for platform in platforms) else set()
    if source_set_name in {"iosMain", "iosTest"}:
        return {"apple"} if any(platform in _IOS_KMP_PLATFORMS for platform in platforms) else set()
    if source_set_name in {"iosArm64Main", "iosArm64Test"}:
        return {"iosArm64"} if "iosArm64" in platforms else set()
    if source_set_name in {"iosSimulatorArm64Main", "iosSimulatorArm64Test"}:
        return {"iosSimulatorArm64"} if "iosSimulatorArm64" in platforms else set()
    if source_set_name in {"macosX64Main", "macosX64Test"}:
        return {"macosX64"} if "macosX64" in platforms else set()
    if source_set_name in {"macosArm64Main", "macosArm64Test", "clientNativeMain", "clientNativeTest"}:
        return {"macosArm64"} if "macosArm64" in platforms else set()
    if source_set_name in {"linuxX64Main", "linuxX64Test"}:
        return {"linuxX64"} if "linuxX64" in platforms else set()
    if source_set_name in {"mingwX64Main", "mingwX64Test"}:
        return {"mingwX64"} if "mingwX64" in platforms else set()
    return set()


def _source_set_required_platforms(project: GradleProject, source_set_name: str, platforms: list[str]) -> set[str]:
    reverse_graph: dict[str, list[str]] = {}
    for platform in platforms:
        for child_source_set, parent_source_sets in _default_source_set_parents_for_platform(platform).items():
            for parent_source_set in parent_source_sets:
                reverse_graph.setdefault(parent_source_set, []).append(child_source_set)
    for child_source_set, source_set in project.source_sets.items():
        for parent_source_set in source_set.depends_on:
            reverse_graph.setdefault(parent_source_set, []).append(child_source_set)

    cache: dict[str, set[str]] = {}

    def visit(current_source_set_name: str, visiting: set[str]) -> set[str]:
        if current_source_set_name in cache:
            return cache[current_source_set_name]
        if current_source_set_name in visiting:
            raise ValueError(f"{project.name} has cyclic sourceSet dependsOn involving {current_source_set_name}")

        visiting.add(current_source_set_name)
        requirements = _source_set_base_required_platforms(current_source_set_name, platforms)
        if requirements == {"common"}:
            visiting.remove(current_source_set_name)
            cache[current_source_set_name] = requirements
            return requirements

        for child_source_set_name in reverse_graph.get(current_source_set_name, []):
            requirements.update(visit(child_source_set_name, visiting))

        if requirements and current_source_set_name not in {
            "commonMain",
            "commonTest",
            "jvmMain",
            "jvmTest",
            "androidMain",
            "androidUnitTest",
            "jsMain",
            "jsTest",
            "wasmJsMain",
            "wasmJsTest",
            "nativeMain",
            "nativeTest",
            "appleMain",
            "appleTest",
            "iosMain",
            "iosTest",
            "iosArm64Main",
            "iosArm64Test",
            "iosSimulatorArm64Main",
            "iosSimulatorArm64Test",
            "macosX64Main",
            "macosX64Test",
            "macosArm64Main",
            "macosArm64Test",
            "clientNativeMain",
            "clientNativeTest",
            "linuxX64Main",
            "linuxX64Test",
            "mingwX64Main",
            "mingwX64Test",
        }:
            if requirements == {"jvm"} or requirements == {"android"}:
                pass
            elif requirements <= {"apple", "iosArm64", "iosSimulatorArm64", "macosArm64", "macosX64"}:
                requirements = {"apple"}
            else:
                requirements = {"common"}

        visiting.remove(current_source_set_name)
        cache[current_source_set_name] = requirements
        return requirements

    return visit(source_set_name, set())


def _project_supports_required_platforms(
    dependency_project: Project,
    required_platforms: set[str],
) -> bool:
    if not isinstance(dependency_project, GradleProject):
        return False

    if not required_platforms:
        return True

    for requirement in required_platforms:
        if requirement == "common":
            if not dependency_project.is_kmp:
                return False
            continue
        if requirement == "apple":
            if not dependency_project.is_kmp:
                return False
            if not any(platform in APPLE_KMP_PLATFORMS for platform in dependency_project.platforms):
                return False
            continue
        if requirement == "jvm":
            if dependency_project.is_kmp and "jvm" not in dependency_project.platforms:
                return False
            continue
        if not dependency_project.is_kmp or requirement not in dependency_project.platforms:
            return False
    return True


def _required_platforms_include_candidate(required_platforms: set[str], candidate_platform: str) -> bool:
    if not required_platforms:
        return False
    if "common" in required_platforms:
        return True
    if "apple" in required_platforms:
        return candidate_platform in APPLE_KMP_PLATFORMS
    return candidate_platform in required_platforms


def _newly_activated_source_sets(candidate_platform: str, current_platforms: list[str]) -> tuple[str, ...]:
    source_sets: list[str] = []

    if candidate_platform in NATIVE_KMP_PLATFORMS and not any(
        platform in NATIVE_KMP_PLATFORMS for platform in current_platforms
    ):
        source_sets.extend(["nativeMain", "nativeTest"])
    if candidate_platform in APPLE_KMP_PLATFORMS and not any(
        platform in APPLE_KMP_PLATFORMS for platform in current_platforms
    ):
        source_sets.extend(["appleMain", "appleTest"])
    if candidate_platform in _IOS_KMP_PLATFORMS and not any(platform in _IOS_KMP_PLATFORMS for platform in current_platforms):
        source_sets.extend(["iosMain", "iosTest"])

    source_sets.extend(_DIRECT_SOURCE_SETS_BY_PLATFORM.get(candidate_platform, ()))
    return tuple(source_sets)


def _kotlin_source_dirs_for(project: GradleProject, source_set_name: str) -> tuple[Path, ...]:
    dirs = [project.path / "src" / source_set_name / "kotlin"]
    source_set = project.source_sets.get(source_set_name)
    if source_set is not None:
        for configured_dir in source_set.kotlin_src_dirs:
            configured_path = Path(configured_dir)
            dirs.append(configured_path if configured_path.is_absolute() else project.path / configured_path)
    return tuple(dirs)


def _source_set_has_kotlin_sources(project: GradleProject, source_set_name: str) -> bool:
    for source_dir in _kotlin_source_dirs_for(project, source_set_name):
        if not source_dir.exists():
            continue
        if any(source_dir.rglob("*.kt")):
            return True
    return False


def find_kmp_target_expansion_suggestions(project: GradleProject, config: Config) -> list[KmpTargetExpansionSuggestion]:
    if not project.is_kmp:
        return []

    suggestions: list[KmpTargetExpansionSuggestion] = []
    current_platforms = list(project.platforms)

    for candidate_platform in SUPPORTED_KMP_PLATFORMS:
        if candidate_platform in current_platforms:
            continue

        hypothetical_platforms = [*current_platforms, candidate_platform]
        supporting_dependencies: set[str] = set()
        candidate_is_compatible = True

        for source_set_name, dependencies in project.source_set_dependencies.items():
            required_platforms = _source_set_required_platforms(project, source_set_name, hypothetical_platforms)
            for dependency in dependencies:
                target = dependency.target
                if not isinstance(target, ProjectDependencyTarget):
                    continue
                dependency_project = config.defined_projects[target.project]
                if not _project_supports_required_platforms(dependency_project, required_platforms):
                    candidate_is_compatible = False
                    break
                if (
                    isinstance(dependency_project, GradleProject)
                    and dependency_project.is_kmp
                    and candidate_platform in dependency_project.platforms
                    and _required_platforms_include_candidate(required_platforms, candidate_platform)
                ):
                    supporting_dependencies.add(target.project)
            if not candidate_is_compatible:
                break

        if not candidate_is_compatible or not supporting_dependencies:
            continue

        newly_activated_source_sets = _newly_activated_source_sets(candidate_platform, current_platforms)
        if any(_source_set_has_kotlin_sources(project, source_set_name) for source_set_name in newly_activated_source_sets):
            continue

        suggestions.append(
            KmpTargetExpansionSuggestion(
                platform=candidate_platform,
                supporting_dependencies=tuple(sorted(supporting_dependencies)),
                newly_activated_source_sets=newly_activated_source_sets,
            )
        )

    return suggestions


__all__ = [
    "KmpTargetExpansionSuggestion",
    "find_kmp_target_expansion_suggestions",
]
