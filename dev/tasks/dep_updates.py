from __future__ import annotations

from dataclasses import dataclass

from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion
from packaging.version import Version as PythonVersion

from dev.config import Config, MavenRepositoryDefinition, PythonProject, load_config
from dev.maven import MavenVersion, fetch_metadata
from dev.pypi import fetch_project_metadata

MAVEN_CENTRAL = MavenRepositoryDefinition(
    name="Maven Central",
    url="https://repo1.maven.org/maven2/",  # check:ignore E_HARDCODED_URL value=https://repo1.maven.org/maven2/
)


@dataclass(frozen=True)
class PythonDependencyUpdateCandidate:
    project_name: str
    scope: str
    dependency_name: str
    pinned_version: str
    latest_version: str


def _check_maven_library_updates(config: Config) -> None:
    for _, library in config.libraries.items():
        if library.repo is None:
            repo = MAVEN_CENTRAL
        else:
            repo = config.repositories[library.repo]

        group_id = library.maven_urn.group_id
        artifact_id = library.maven_urn.artifact_id
        current_version = library.maven_urn.version
        try:
            current_version_obj = MavenVersion.parse(current_version)
        except ValueError:
            continue

        try:
            metadata = fetch_metadata(repo.url, group_id, artifact_id)
        except Exception:
            continue

        newer_versions: list[str] = []
        for version in metadata.versions:
            try:
                available_version = MavenVersion.parse(version)
                if available_version > current_version_obj:
                    newer_versions.append(version)
            except ValueError:
                pass

        if newer_versions:
            print(f"{library.name}: {current_version} < {newer_versions}")


def _iter_python_project_dependencies(project: PythonProject) -> list[tuple[str, str]]:
    dependencies: list[tuple[str, str]] = []
    dependencies.extend(("main", dep) for dep in project.dependencies)
    dependencies.extend(("dev", dep) for dep in project.dev_dependencies)
    return dependencies


def _extract_exact_pinned_python_version(requirement: Requirement) -> PythonVersion | None:
    exact_versions = {
        spec.version
        for spec in requirement.specifier
        if spec.operator in {"==", "==="} and "*" not in spec.version
    }
    if len(exact_versions) != 1:
        return None

    try:
        return PythonVersion(next(iter(exact_versions)))
    except InvalidVersion:
        return None


def _latest_pypi_version_for_requirement(
    requirement: Requirement,
    current_version: PythonVersion,
) -> PythonVersion | None:
    try:
        metadata = fetch_project_metadata(requirement.name)
    except Exception:
        return None

    versions: list[PythonVersion] = []
    for release in metadata.releases:
        try:
            parsed = PythonVersion(release)
        except InvalidVersion:
            continue
        if not current_version.is_prerelease and parsed.is_prerelease:
            continue
        versions.append(parsed)

    if not versions:
        raw_latest = metadata.latest_version
        if raw_latest is None:
            return None
        try:
            latest = PythonVersion(raw_latest)
        except InvalidVersion:
            return None
        if not current_version.is_prerelease and latest.is_prerelease:
            return None
        return latest if latest > current_version else None

    latest = max(versions)
    return latest if latest > current_version else None


def _collect_python_dependency_updates(config: Config) -> list[PythonDependencyUpdateCandidate]:
    updates: list[PythonDependencyUpdateCandidate] = []

    for project in config.defined_projects.values():
        if not isinstance(project, PythonProject):
            continue

        for scope, requirement_text in _iter_python_project_dependencies(project):
            try:
                requirement = Requirement(requirement_text)
            except InvalidRequirement:
                continue

            if requirement.url is not None:
                continue

            pinned_version = _extract_exact_pinned_python_version(requirement)
            if pinned_version is None:
                continue

            latest_version = _latest_pypi_version_for_requirement(requirement, pinned_version)
            if latest_version is None:
                continue

            updates.append(
                PythonDependencyUpdateCandidate(
                    project_name=project.name,
                    scope=scope,
                    dependency_name=requirement.name,
                    pinned_version=str(pinned_version),
                    latest_version=str(latest_version),
                )
            )

    return sorted(
        updates,
        key=lambda item: (
            item.project_name,
            0 if item.scope == "main" else 1,
            item.dependency_name,
        ),
    )


def check_for_updates() -> None:
    config = load_config()
    _check_maven_library_updates(config)
    for update in _collect_python_dependency_updates(config):
        scope_suffix = "" if update.scope == "main" else f" [{update.scope}]"
        print(
            f"{update.project_name}{scope_suffix}: {update.dependency_name} "
            f"{update.pinned_version} < {update.latest_version}"
        )


__all__ = [
    "PythonDependencyUpdateCandidate",
    "check_for_updates",
]
