import dataclasses
import os
import re
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from inspect import signature
from pathlib import Path
from typing import Literal, Protocol, TypeGuard, Union, cast

from mu.exec import Quoted
from mu.parser import parse
from mu.typed import DecodeError, decode
from mu.types import AtomExpr, Document, StringExpr

import dev.config_typed as config_typed
from dev.base import Module
from dev.checks.base import CoarseFileScope, CoarseProjectType
from dev.licenses import canonicalize_license_key
from dev.maven import MavenCoordinate, is_valid_maven_coordinate

################################################################################
# Ownership Type
################################################################################


class OwnershipType(Enum):
    WABBIT = "wabbit"
    IMPORTED = "imported"


################################################################################
# Version
################################################################################


@dataclass
class Version:
    raw: Quoted[StringExpr] | None
    major: int
    minor: int
    patch: int
    is_dev: bool

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}" + ("+dev-SNAPSHOT" if self.is_dev else "")

    def next_major(self) -> "Version":
        return Version(None, self.major + 1, 0, 0, False)

    def next_minor(self) -> "Version":
        return Version(None, self.major, self.minor + 1, 0, False)

    def next_patch(self) -> "Version":
        return Version(None, self.major, self.minor, self.patch + 1, False)

    @classmethod
    def parse_or_null(cls, version: Quoted[StringExpr] | str) -> Union["Version", None]:
        value = version.value.value if isinstance(version, Quoted) else version
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(\+dev-SNAPSHOT)?", value.strip())
        if not match:
            return None

        major, minor, patch, is_dev = match.groups()
        raw_version = version if isinstance(version, Quoted) else None
        return cls(raw_version, int(major), int(minor), int(patch), bool(is_dev))

    @classmethod
    def parse(cls, version: Quoted[StringExpr] | str) -> "Version":
        result = cls.parse_or_null(version)
        assert result is not None, f"Invalid version: {version.value.value if isinstance(version, Quoted) else version}"
        return result

    def __lt__(self, other: "Version") -> bool:
        self_dev_val = 1 if self.is_dev else 0
        other_dev_val = 1 if other.is_dev else 0
        return (self.major, self.minor, self.patch, self_dev_val) < (
            other.major,
            other.minor,
            other.patch,
            other_dev_val,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch, self.is_dev) == (
            other.major,
            other.minor,
            other.patch,
            other.is_dev,
        )

    def __gt__(self, other: "Version") -> bool:
        return other < self

    def __ge__(self, other: "Version") -> bool:
        return not self < other

    def __le__(self, other: "Version") -> bool:
        return not other < self


###############################################################################################
# Features
###############################################################################################


class Feature:
    __feature_name__: str

    def implied(self) -> list["Feature"]:
        return []


def _has_only_str_keys(value: dict[object, object]) -> TypeGuard[dict[str, object]]:
    return all(isinstance(key, str) for key in value)


def _dataclass_field_names(feature: Feature) -> list[str] | None:
    maybe_fields = getattr(feature, "__dataclass_fields__", None)
    if not isinstance(maybe_fields, dict):
        return None
    field_map = cast(dict[object, object], maybe_fields)
    if not _has_only_str_keys(field_map):
        return None
    return list(field_map.keys())


@dataclass
class Kotlin(Feature):
    __feature_name__ = "kotlin"


@dataclass
class Scala(Feature):
    __feature_name__ = "scala"


@dataclass
class Jvm(Feature):
    __feature_name__ = "jvm"
    jarName: str | None = None


@dataclass
class ShadowJar(Feature):
    __feature_name__ = "shadow-jar"
    jarName: str | None = None

    def implied(self) -> list[Feature]:
        return [Jvm()]


@dataclass
class JvmKotlinLibrary(Feature):
    __feature_name__ = "jvm-kotlin-library"

    def implied(self) -> list[Feature]:
        return [Kotlin(), Jvm()]


@dataclass
class KotlinGradlePluginLibrary(Feature):
    __feature_name__ = "kotlin-gradle-plugin-library"

    def implied(self) -> list[Feature]:
        return [Kotlin(), Jvm()]


@dataclass
class JvmScalaLibrary(Feature):
    __feature_name__ = "jvm-scala-library"

    def implied(self) -> list[Feature]:
        return [Scala(), Jvm()]


def _normalize_jar_names(
    *, jar: str | None, shaded: str | None, unshaded: str | None
) -> tuple[str | None, str | None, str | None]:
    provided = sum(value is not None for value in (jar, shaded, unshaded))
    if provided > 1:
        raise ValueError("Provide only one of jarName/shadedJarName/unshadedJarName")

    def _validate_jar_name(value: str | None, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"Expected string for {field_name}, got {type(value)}")
        if not value.endswith(".jar"):
            raise ValueError(f"Expected .jar file, got {value}")
        return value

    if jar is not None:
        jar = _validate_jar_name(jar, "jarName")
        base, _ = os.path.splitext(jar)
        return jar, jar, f"{base}-unshaded.jar"

    if shaded is not None:
        shaded = _validate_jar_name(shaded, "shadedJarName")
        base, _ = os.path.splitext(shaded)
        return shaded, shaded, f"{base}-unshaded.jar"

    if unshaded is not None:
        unshaded = _validate_jar_name(unshaded, "unshadedJarName")
        base, _ = os.path.splitext(unshaded)
        return unshaded, f"{base}-shaded.jar", unshaded

    return None, None, None


@dataclass
class JvmKotlinApplication(Feature):
    __feature_name__ = "jvm-kotlin-application"
    main: str
    jarName: str | None = None
    shadedJarName: str | None = None
    unshadedJarName: str | None = None

    def __post_init__(self) -> None:
        self.jarName, self.shadedJarName, self.unshadedJarName = _normalize_jar_names(
            jar=self.jarName,
            shaded=self.shadedJarName,
            unshaded=self.unshadedJarName,
        )

    def implied(self) -> list[Feature]:
        return [
            Kotlin(),
            Jvm(jarName=self.unshadedJarName),
            ShadowJar(jarName=self.shadedJarName),
        ]


@dataclass
class PaperPlugin(Feature):
    __feature_name__ = "paper-plugin"
    main: str
    name: str
    apiVersion: str
    depend: list[str] | None = None

    def implied(self) -> list[Feature]:
        return [
            Kotlin(),
            Jvm(jarName=f"{self.name}-unshaded.jar"),
            ShadowJar(jarName=f"{self.name}.jar"),
        ]


@dataclass
class JvmKotlinAgent(Feature):
    __feature_name__ = "jvm-kotlin-agent"
    main: str
    jarName: str | None = None
    shadedJarName: str | None = None
    unshadedJarName: str | None = None

    def __post_init__(self) -> None:
        self.jarName, self.shadedJarName, self.unshadedJarName = _normalize_jar_names(
            jar=self.jarName,
            shaded=self.shadedJarName,
            unshaded=self.unshadedJarName,
        )

    def implied(self) -> list[Feature]:
        return [
            Kotlin(),
            Jvm(jarName=self.unshadedJarName),
            ShadowJar(jarName=self.shadedJarName),
        ]


@dataclass
class IntellijPlugin(Feature):
    __feature_name__ = "intellij-plugin"
    pluginName: str
    pluginId: str | None = None
    ideaVersion: str | None = None
    sinceBuild: str | None = None
    untilBuild: str | None = None
    vendorName: str | None = None
    vendorEmail: str | None = None
    vendorUrl: str | None = None
    pluginDescription: str | None = None
    pluginChangeNotes: str | None = None
    depends: list[str] | None = None
    bundledPlugins: list[str] | None = None
    publishChannel: str | None = None
    marketplaceTokenEnv: str | None = None

    def implied(self) -> list[Feature]:
        return [Kotlin(), Jvm()]


@dataclass
class IntellijPlatformLibrary(Feature):
    __feature_name__ = "intellij-platform-library"
    ideaVersion: str | None = None
    bundledPlugins: list[str] | None = None
    modulePlugin: bool = True

    def implied(self) -> list[Feature]:
        return [Kotlin(), Jvm()]


@dataclass
class KotlinSerialization(Feature):
    __feature_name__ = "kotlin-serialization"

    def implied(self) -> list[Feature]:
        return [Kotlin()]


@dataclass
class KotlinComposePlugin(Feature):
    __feature_name__ = "kotlin-compose-plugin"

    def implied(self) -> list[Feature]:
        return [Kotlin()]


@dataclass(frozen=True)
class GradlePluginApplication:
    name: str
    compilerOptions: dict[str, str] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("gradle-plugin.name must not be empty")
        for key, value in self.compilerOptions.items():
            if not key.strip():
                raise ValueError("gradle-plugin.compilerOptions keys must not be empty")
            if not value.strip():
                raise ValueError(f"gradle-plugin.compilerOptions[{key!r}] must not be empty")


@dataclass
class GradlePlugins(Feature):
    __feature_name__ = "gradle-plugin"
    entries: list[GradlePluginApplication]

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("gradle-plugin.entries must not be empty")
        seen: set[str] = set()
        for entry in self.entries:
            if entry.name in seen:
                raise ValueError(f"Duplicate gradle-plugin entry: {entry.name}")
            seen.add(entry.name)


@dataclass
class KotlinCompilerPluginCompatibilitySource:
    kotlinVersionPrefix: str
    path: str

    def __post_init__(self) -> None:
        if not self.kotlinVersionPrefix.strip():
            raise ValueError("kotlin-compiler-plugin.compatibilitySources keys must not be empty")
        if not self.path.strip():
            raise ValueError(
                f"kotlin-compiler-plugin.compatibilitySources[{self.kotlinVersionPrefix!r}] must not be empty"
            )


@dataclass
class KotlinCompilerPlugin(Feature):
    __feature_name__ = "kotlin-compiler-plugin"
    compatibilitySources: list[KotlinCompilerPluginCompatibilitySource] = dataclasses.field(default_factory=list)
    publishVersionWithKotlin: bool = True

    def implied(self) -> list[Feature]:
        return [Kotlin(), Jvm()]


@dataclass
class KotlinCompilerGradlePlugin(Feature):
    __feature_name__ = "kotlin-compiler-gradle-plugin"
    compilerPluginProject: str
    versionPackage: str | None = None
    versionClassName: str | None = None
    versionConstantName: str | None = None

    def implied(self) -> list[Feature]:
        return [Kotlin(), Jvm()]


@dataclass
class KmpAndroidLibrary(Feature):
    __feature_name__ = "kmp-android-library"
    namespace: str
    compileSdk: int
    minSdk: int
    manifestPath: str = "src/androidMain/AndroidManifest.xml"


@dataclass
class KmpCompose(Feature):
    __feature_name__ = "kmp-compose"
    publicResClass: bool = True
    resClassPackage: str | None = None


@dataclass
class KmpJvmRunEntry:
    taskName: str
    mainClass: str
    description: str
    jvmArgs: list[str] = dataclasses.field(default_factory=list)


@dataclass
class KmpJvmRuns(Feature):
    __feature_name__ = "kmp-jvm-runs"
    entries: list[KmpJvmRunEntry]

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("kmp-jvm-runs.entries must not be empty")
        seen: set[str] = set()
        for entry in self.entries:
            if entry.taskName in seen:
                raise ValueError(f"Duplicate kmp-jvm-runs taskName: {entry.taskName}")
            seen.add(entry.taskName)


@dataclass
class PythonDeptry(Feature):
    __feature_name__ = "python-deptry"
    package_map: dict[str, str] = dataclasses.field(default_factory=dict)
    per_rule_ignores: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    auto_package_map: bool = False


@dataclass
class PythonImportLinter(Feature):
    __feature_name__ = "python-importlinter"
    root_packages: list[str] = dataclasses.field(default_factory=list)
    layers: list[str] = dataclasses.field(default_factory=list)


def _merge_feature(existing: Feature, incoming: Feature) -> Feature:
    if type(existing) is not type(incoming):
        raise TypeError(f"Cannot merge features with different types: {type(existing)} vs {type(incoming)}")

    if isinstance(existing, GradlePlugins):
        assert isinstance(incoming, GradlePlugins)
        merged_entries = list(existing.entries)
        existing_indices = {entry.name: index for index, entry in enumerate(existing.entries)}
        for entry in incoming.entries:
            existing_index = existing_indices.get(entry.name)
            if existing_index is not None:
                existing_entry = merged_entries[existing_index]
                merged_entries[existing_index] = GradlePluginApplication(
                    name=existing_entry.name,
                    compilerOptions={
                        **existing_entry.compilerOptions,
                        **entry.compilerOptions,
                    },
                )
                continue
            existing_indices[entry.name] = len(merged_entries)
            merged_entries.append(entry)
        return GradlePlugins(entries=merged_entries)

    dataclass_field_names = _dataclass_field_names(existing)
    if dataclass_field_names is None:
        if existing != incoming:
            raise ValueError(
                f"Implied feature {type(existing).__feature_name__} conflicts: " f"{existing} != {incoming}"
            )
        return existing

    merged_kwargs: dict[str, object] = {}
    for field_name in dataclass_field_names:
        existing_value = getattr(existing, field_name)
        incoming_value = getattr(incoming, field_name)
        if existing_value is None and incoming_value is not None:
            merged_kwargs[field_name] = incoming_value
        elif incoming_value is None or existing_value == incoming_value:
            merged_kwargs[field_name] = existing_value
        else:
            raise ValueError(
                f"Implied feature {type(existing).__feature_name__} conflicts on "
                f"{field_name}: {existing_value} != {incoming_value}"
            )
    return type(existing)(**merged_kwargs)


def resolve_features(features: list[Feature]) -> dict[str, Feature]:
    resolved_features: dict[str, Feature] = {}
    queue: list[Feature] = []
    for feature in features:
        feature_name = type(feature).__feature_name__
        existing = resolved_features.get(feature_name)
        if existing is None:
            resolved_features[feature_name] = feature
            queue.append(feature)
            continue

        merged = _merge_feature(existing, feature)
        if merged != existing:
            resolved_features[feature_name] = merged
            queue.append(merged)

    while queue:
        feature = queue.pop()
        for implied in feature.implied():
            implied_name = type(implied).__feature_name__
            existing = resolved_features.get(implied_name)
            if existing is None:
                resolved_features[implied_name] = implied
                queue.append(implied)
            else:
                merged = _merge_feature(existing, implied)
                if merged != existing:
                    resolved_features[implied_name] = merged
                    queue.append(merged)
    return resolved_features


################################################################################
# Dependencies for Gradle-like resolution
################################################################################


@dataclass
class KotlinPluginDefinition:
    plugin_id: str | None = None
    version: str | None = None
    repo: str | None = None
    project: str | None = None
    compiler_plugin: str | None = None
    compiler_plugin_id: str | None = None

    def __post_init__(self) -> None:
        if (self.plugin_id is None) == (self.project is None):
            raise ValueError("KotlinPluginDefinition must define exactly one of plugin_id or project")


def _normalize_project_reference(reference: str, *, field_name: str) -> str:
    if not reference.startswith(":"):
        raise ValueError(f"{field_name} must use :project-name syntax")
    project_name = reference[1:].strip()
    if not project_name:
        raise ValueError(f"{field_name} must not be empty")
    return project_name


def resolve_kotlin_plugin_project(config: "Config", definition: KotlinPluginDefinition) -> "GradleProject | None":
    if definition.project is None:
        return None
    project = config.defined_projects.get(definition.project)
    if project is None:
        raise ValueError(f"Kotlin plugin references unknown local project {definition.project}")
    if not isinstance(project, GradleProject):
        raise ValueError(f"Kotlin plugin local project {definition.project} is not a Gradle project")
    return project


def resolve_kotlin_plugin_id(config: "Config", definition: KotlinPluginDefinition) -> str:
    if definition.plugin_id is not None:
        return definition.plugin_id
    project = resolve_kotlin_plugin_project(config, definition)
    assert project is not None
    if project.gradle_plugin_id is None:
        raise ValueError(f"Gradle project {project.name} is used as a local plugin but has no gradlePluginId")
    return project.gradle_plugin_id


def resolve_kotlin_plugin_version(config: "Config", definition: KotlinPluginDefinition) -> str:
    if definition.version is not None:
        return definition.version
    project = resolve_kotlin_plugin_project(config, definition)
    assert project is not None
    if project.version is None:
        raise ValueError(f"Gradle project {project.name} is used as a local plugin but has no version")
    return str(project.version)


def resolve_kotlin_compiler_plugin_id(config: "Config", definition: KotlinPluginDefinition) -> str:
    if definition.compiler_plugin_id is not None:
        return definition.compiler_plugin_id
    return resolve_kotlin_plugin_id(config, definition)


def resolve_kotlin_plugin_compiler_plugin_project(
    config: "Config",
    definition: KotlinPluginDefinition,
) -> "GradleProject | None":
    if definition.compiler_plugin is None:
        return None
    project_name = (
        definition.compiler_plugin[1:] if definition.compiler_plugin.startswith(":") else definition.compiler_plugin
    )
    project = config.defined_projects.get(project_name)
    if project is None:
        return None
    if not isinstance(project, GradleProject):
        raise ValueError(f"Kotlin compiler plugin reference {definition.compiler_plugin} is not a Gradle project")
    return project


@dataclass
class MavenRepositoryDefinition:
    name: str
    url: str


@dataclass
class MavenLibraryDefinition:
    name: str
    maven_urn: MavenCoordinate
    repo: str | None = None


@dataclass(frozen=True)
class CodeOwner:
    name: str
    email: str


@dataclass(frozen=True)
class RepoDefinition:
    repo_id: str
    path: Path
    github_repo: str | None
    gradle_root_project_name: str | None
    jvm_policy: str | None
    project_version: str | None = None
    default_kotlin_version: str | None = None
    supported_kotlin_versions: list[str] = dataclasses.field(default_factory=list)
    dotnet_sdk_version: str | None = None
    default_target_framework: str | None = None
    solution_name: str | None = None
    use_central_package_management: bool = False
    docs_project_id: str | None = None
    project_ids: list[str] = dataclasses.field(default_factory=list)


@dataclass(frozen=True)
class GradleTargetSpec:
    kind: str
    name: str | None = None
    namespace: str | None = None
    application_id: str | None = None
    compile_sdk: int | None = None
    min_sdk: int | None = None
    target_sdk: int | None = None
    manifest_path: str | None = None
    browser: bool | None = None
    browser_test: str | None = None
    executable: bool | None = None


@dataclass(frozen=True)
class GradleSourceSet:
    name: str
    depends_on: list[str] = dataclasses.field(default_factory=list)
    dependencies: list["Dependency"] = dataclasses.field(default_factory=list)
    kotlin_src_dirs: list[str] = dataclasses.field(default_factory=list)


# In general a dependency looks like:
#   scope@artifact
#   scope can be omitted, in which case it defaults to 'implementation'


class GradleDependencyScope(Enum):
    TEST = "test"
    API = "api"
    IMPLEMENTATION = "implementation"
    COMPILE_ONLY = "compileOnly"
    KAPT = "kapt"
    RUNTIME_ONLY = "runtimeOnly"
    TEST_IMPLEMENTATION = "testImplementation"
    TEST_COMPILE_ONLY = "testCompileOnly"
    TEST_RUNTIME_ONLY = "testRuntimeOnly"


@dataclass
class Dependency:
    scope: str | None
    target: "DependencyTarget"

    @property
    def name(self) -> str:
        target = self.target
        if isinstance(target, JarFileDependencyTarget):
            return target.path.name
        if isinstance(target, ProjectDependencyTarget):
            return target.project
        if isinstance(target, MavenDependencyTarget):
            if target.artifact is None:
                raise ValueError("Maven dependency is missing artifact")
            return target.artifact
        if isinstance(target, NpmDependencyTarget):
            return target.package
        if isinstance(target, NugetDependencyTarget):
            return target.package
        raise ValueError(f"Unsupported dependency target type: {type(target).__name__}")

    @property
    def is_subproject(self) -> bool:
        return isinstance(self.target, ProjectDependencyTarget)

    def __post_init__(self) -> None:
        assert (
            isinstance(self.scope, str) or self.scope is None
        ), f"Expected GradleDependencyScope or None, got {type(self.scope)}"
        assert isinstance(self.target, DependencyTarget), f"Expected DependencyTarget, got {type(self.target)}"

    def __str__(self) -> str:
        return self.as_string()

    def as_string(self) -> str:
        modifier = self.scope
        if modifier is None:
            modifier = "implementation"

        target = self.target
        if isinstance(target, JarFileDependencyTarget):
            dirname = target.path.parent.as_posix() or "."
            basename = target.path.name

            escaped_dirname = dirname.replace("\\", "\\\\").replace('"', '\\"')
            escaped_basename = basename.replace("\\", "\\\\").replace('"', '\\"')

            return (
                f'{modifier}(fileTree(mapOf("dir" to "{escaped_dirname}", '
                f'"include" to listOf("{escaped_basename}"))))'
            )

        if isinstance(target, ProjectDependencyTarget):
            return f'{modifier}(project(":{target.project}"))'

        if isinstance(target, MavenDependencyTarget):
            # FIXME: repo is not used
            artifact = target.artifact or ""
            return f'{modifier}("{artifact}")'

        if isinstance(target, NpmDependencyTarget):
            return f'{modifier}(npm("{target.package}", "{target.version}"))'

        if isinstance(target, NugetDependencyTarget):
            return f"{target.package}@{target.version}"

        raise ValueError(f"Unsupported dependency target type: {type(target).__name__}")


class DependencyTarget:
    JarFile: type["JarFileDependencyTarget"] = None  # type: ignore
    Project: type["ProjectDependencyTarget"] = None  # type: ignore
    Maven: type["MavenDependencyTarget"] = None  # type: ignore
    Npm: type["NpmDependencyTarget"] = None  # type: ignore
    Nuget: type["NugetDependencyTarget"] = None  # type: ignore


@dataclass
class JarFileDependencyTarget(DependencyTarget):
    path: Path


DependencyTarget.JarFile = JarFileDependencyTarget


@dataclass
class ProjectDependencyTarget(DependencyTarget):
    project: str


DependencyTarget.Project = ProjectDependencyTarget


@dataclass
class MavenDependencyTarget(DependencyTarget):
    maven_repo: str | None = None
    artifact: str | None = None


DependencyTarget.Maven = MavenDependencyTarget


@dataclass
class NpmDependencyTarget(DependencyTarget):
    package: str
    version: str


DependencyTarget.Npm = NpmDependencyTarget


@dataclass
class NugetDependencyTarget(DependencyTarget):
    package: str
    version: str


DependencyTarget.Nuget = NugetDependencyTarget

################################################################################
# Project base + Gradle/Python subtypes
################################################################################


class Project(ABC):
    path: Path
    project_id: str | None
    repo_id: str | None
    repo_root: Path | None
    name: str
    description: str | None
    authors: list[str]
    license: str | None
    test_license: str | None
    copyright_holder: str | None
    copyright_year_start: int | None
    quarantine: bool
    publish: bool
    github_repo: str | None
    ownership: OwnershipType
    managed_by_setup: bool
    resolved_dependencies: list[Dependency]
    publish_target: str | None
    publish_snapshots: bool
    docs_enabled: bool
    docs_system: str | None

    @property
    def effective_repo_root(self) -> Path:
        repo_root = self.repo_root
        if repo_root is not None:
            return repo_root
        return self.path

    @property
    def is_repo_managed(self) -> bool:
        return self.effective_repo_root != self.path

    @abstractmethod
    def get_coarse_file_scope(self, path: Path) -> CoarseFileScope | None:
        raise NotImplementedError(f"get_file_scope not implemented for {type(self)}")

    @property
    @abstractmethod
    def coarse_project_type(self) -> CoarseProjectType | None:
        raise NotImplementedError(f"coarse_project_type not implemented for {type(self)}")


@dataclass
class PythonDependency:
    """
    Simple container for Python dependency info: name, version spec, optional extras,
    a scope (main/dev/test), etc.
    """

    package: str
    version_spec: str | None = None
    scope: str = "main"  # or dev/test/extras?

    def __str__(self) -> str:
        if self.version_spec:
            return f"{self.package}{self.version_spec}"
        return self.package


@dataclass
class PythonApplication:
    script: str
    entry: str
    path: str
    aliases: list[str] = dataclasses.field(default_factory=list)


@dataclass
class PythonProject(Project):
    path: Path
    name: str
    version: Version | None
    description: str | None
    authors: list[str]
    license: str | None
    github_repo: str | None
    requires_python: str | None
    dependencies: list[str]
    dev_dependencies: list[str]
    scripts: list[str]
    application: PythonApplication | None
    homepage: str | None
    repository: str | None
    keywords: list[str]
    classifiers: list[str]
    quarantine: bool
    publish: bool
    ownership: OwnershipType

    # # Python dependencies in a raw user form vs. resolved objects
    # raw_dependencies: List[str]
    # resolved_python_dependencies: List[PythonDependency]

    resolved_dependencies: list[Dependency] = dataclasses.field(default_factory=list)
    project_id: str | None = None
    repo_id: str | None = None
    repo_root: Path | None = None
    managed_by_setup: bool = True
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    publish_target: str | None = None
    publish_snapshots: bool = False
    docs_enabled: bool = True
    docs_system: str | None = "mkdocs"
    test_license: str | None = None
    # (We keep a list of `Dependency` too if you want to unify anything across projects,
    #  but typically a pure Python project won't rely on Gradle dependencies.)

    def get_coarse_file_scope(self, path: Path) -> CoarseFileScope | None:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(f"Path {path} is not contained in project path {self.path}")
        return None

    @property
    def coarse_project_type(self) -> CoarseProjectType | None:
        return None


@dataclass
class PurescriptProject(Project):
    path: Path
    name: str
    description: str | None
    authors: list[str]
    quarantine: bool
    publish: bool
    license: str | None
    github_repo: str | None
    ownership: OwnershipType
    version: Version | None
    resolved_dependencies: list[Dependency]
    project_id: str | None = None
    repo_id: str | None = None
    repo_root: Path | None = None
    managed_by_setup: bool = True
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    publish_target: str | None = None
    publish_snapshots: bool = False
    docs_enabled: bool = False
    docs_system: str | None = None
    test_license: str | None = None

    def get_coarse_file_scope(self, path: Path) -> CoarseFileScope | None:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(f"Path {path} is not contained in project path {self.path}")
        return None

    @property
    def coarse_project_type(self) -> CoarseProjectType | None:
        return None


@dataclass
class PremakeProject(Project):
    path: Path
    name: str
    description: str | None
    authors: list[str]
    quarantine: bool
    publish: bool
    license: str | None
    github_repo: str | None
    ownership: OwnershipType
    version: Version | None
    resolved_dependencies: list[Dependency]
    project_id: str | None = None
    repo_id: str | None = None
    repo_root: Path | None = None
    managed_by_setup: bool = True
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    publish_target: str | None = None
    publish_snapshots: bool = False
    docs_enabled: bool = False
    docs_system: str | None = None
    test_license: str | None = None

    def get_coarse_file_scope(self, path: Path) -> CoarseFileScope | None:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(f"Path {path} is not contained in project path {self.path}")
        return None

    @property
    def coarse_project_type(self) -> CoarseProjectType | None:
        return None


@dataclass
class DataProject(Project):
    path: Path
    name: str
    description: str | None
    authors: list[str]
    quarantine: bool
    publish: bool
    license: str | None
    github_repo: str | None
    ownership: OwnershipType
    version: Version | None
    resolved_dependencies: list[Dependency]
    project_id: str | None = None
    repo_id: str | None = None
    repo_root: Path | None = None
    managed_by_setup: bool = True
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    publish_target: str | None = None
    publish_snapshots: bool = False
    docs_enabled: bool = False
    docs_system: str | None = None
    test_license: str | None = None
    preserve_legal_files: bool = False

    def get_coarse_file_scope(self, path: Path) -> CoarseFileScope | None:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(f"Path {path} is not contained in project path {self.path}")
        return None

    @property
    def coarse_project_type(self) -> CoarseProjectType | None:
        return CoarseProjectType.DATA


@dataclass
class GradleProject(Project):
    path: Path
    group_name: str
    name: str
    version: Version | None
    description: str | None
    authors: list[str]
    license: str | None
    quarantine: bool
    publish: bool
    github_repo: str | None
    ownership: OwnershipType

    raw_dependencies: list[str | Dependency | list[Dependency]]
    raw_features: list[Feature]

    resolved_dependencies: list[Dependency]
    resolved_maven_repositories: list[MavenRepositoryDefinition]
    resolved_features: dict[str, Feature]
    platforms: list[str] = dataclasses.field(default_factory=lambda: ["jvm"])
    source_set_dependencies: dict[str, list[Dependency]] = dataclasses.field(default_factory=dict)
    project_id: str | None = None
    repo_id: str | None = None
    repo_root: Path | None = None
    managed_by_setup: bool = True
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    gradle_root: Path | None = None
    module_dir: Path | None = None
    gradle_project_name: str | None = None
    artifact_id: str | None = None
    gradle_plugin_id: str | None = None
    build_model: str | None = None
    targets: list["GradleTargetSpec"] = dataclasses.field(default_factory=list)
    source_sets: dict[str, "GradleSourceSet"] = dataclasses.field(default_factory=dict)
    build_inline_file: str | None = None
    kotlin_free_compiler_args: list[str] = dataclasses.field(default_factory=list)
    dokka_suppress_source_sets: list[str] = dataclasses.field(default_factory=list)
    jvm_policy: str | None = None
    jvm_task_policies: dict[str, str] = dataclasses.field(default_factory=dict)
    publish_target: str | None = None
    publish_snapshots: bool = False
    docs_enabled: bool = False
    docs_system: str | None = None
    version_from_repo: bool = False
    test_license: str | None = None

    @property
    def artifact_name(self) -> str:
        if not self.group_name:
            raise ValueError(f"GradleProject {self.name} missing group_name")
        if not self.version:
            raise ValueError(f"GradleProject {self.name} missing version")
        return f"{self.group_name}:{self.effective_artifact_id}:{self.version}"

    @property
    def effective_gradle_root(self) -> Path:
        gradle_root = self.gradle_root
        if gradle_root is not None:
            return gradle_root
        return self.path

    @property
    def effective_gradle_project_name(self) -> str:
        gradle_project_name = self.gradle_project_name
        if gradle_project_name is not None:
            return gradle_project_name
        return self.name

    @property
    def effective_artifact_id(self) -> str:
        artifact_id = self.artifact_id
        if artifact_id is not None:
            return artifact_id
        return self.effective_gradle_project_name

    @property
    def coarse_project_type(self) -> CoarseProjectType | None:
        return None

    @property
    def is_kmp(self) -> bool:
        if self.build_model is not None:
            return self.build_model == "kmp"
        return _is_kmp_mode(self.platforms)

    def get_coarse_file_scope(self, path: Path) -> CoarseFileScope | None:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(f"Path {path} is not contained in project path {self.path}")

        rel_path = path.relative_to(self.path)

        if rel_path.as_posix().startswith("src/main/"):
            return CoarseFileScope.MAIN
        if rel_path.as_posix().startswith("src/test/"):
            return CoarseFileScope.TEST
        if rel_path.as_posix().startswith("build/"):
            return CoarseFileScope.BUILD_TEMP
        if rel_path.as_posix().startswith("kotlin-js-store/"):
            return CoarseFileScope.BUILD_TEMP
        return None


DotnetLanguage = Literal["fsharp", "csharp"]
DotnetProjectKind = Literal["library", "exe", "tool", "test"]


@dataclass
class DotnetProject(Project):
    path: Path
    name: str
    version: Version | None
    description: str | None
    authors: list[str]
    license: str | None
    quarantine: bool
    publish: bool
    github_repo: str | None
    ownership: OwnershipType
    resolved_dependencies: list[Dependency]
    language: DotnetLanguage
    project_kind: DotnetProjectKind
    sdk: str
    output_type: str | None = None
    target_framework: str | None = None
    target_frameworks: list[str] = dataclasses.field(default_factory=list)
    assembly_name: str | None = None
    root_namespace: str | None = None
    package_id: str | None = None
    package_tags: list[str] = dataclasses.field(default_factory=list)
    generate_documentation_file: bool = True
    nullable: bool | None = None
    implicit_usings: bool | None = None
    lang_version: str | None = None
    source_roots: list[str] = dataclasses.field(default_factory=list)
    packable: bool = True
    project_id: str | None = None
    repo_id: str | None = None
    repo_root: Path | None = None
    managed_by_setup: bool = True
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    publish_target: str | None = None
    publish_snapshots: bool = False
    docs_enabled: bool = False
    docs_system: str | None = None
    test_license: str | None = None

    @property
    def effective_target_frameworks(self) -> list[str]:
        if self.target_frameworks:
            return list(self.target_frameworks)
        if self.target_framework is not None:
            return [self.target_framework]
        return []

    @property
    def effective_assembly_name(self) -> str:
        if self.assembly_name is not None:
            return self.assembly_name
        return self.name

    @property
    def effective_root_namespace(self) -> str:
        if self.root_namespace is not None:
            return self.root_namespace
        return self.effective_assembly_name

    @property
    def effective_package_id(self) -> str:
        if self.package_id is not None:
            return self.package_id
        return self.effective_assembly_name

    @property
    def effective_output_type(self) -> str | None:
        if self.output_type is not None:
            return self.output_type
        if self.project_kind in ("exe", "tool", "test"):
            return "Exe"
        return None

    @property
    def effective_project_extension(self) -> str:
        if self.language == "fsharp":
            return "fsproj"
        return "csproj"

    @property
    def source_dir_name(self) -> str:
        if self.project_kind == "test":
            return "tests"
        return "src"

    @property
    def project_dir_name(self) -> str:
        return self.effective_assembly_name

    @property
    def project_file_path(self) -> Path:
        return (
            self.path
            / self.source_dir_name
            / self.project_dir_name
            / f"{self.project_dir_name}.{self.effective_project_extension}"
        )

    @property
    def coarse_project_type(self) -> CoarseProjectType | None:
        return None

    def get_coarse_file_scope(self, path: Path) -> CoarseFileScope | None:
        if not path.is_relative_to(self.path):
            raise ValueError(f"Path {path} is not contained in project path {self.path}")

        rel_path = path.relative_to(self.path)
        rel_posix = rel_path.as_posix()
        if rel_posix.startswith("src/"):
            return CoarseFileScope.MAIN
        if rel_posix.startswith("tests/"):
            return CoarseFileScope.TEST
        if rel_posix.startswith(("bin/", "obj/", "artifacts/", ".packages/")):
            return CoarseFileScope.BUILD_TEMP
        return None


##################################################################################################
# Config
##################################################################################################

CONFIG_FILE = "root.clj"
CONFIG_PRIVATE_FILE = "root.private.clj"


def find_workspace_root(start: Path | None = None) -> Path | None:
    current = Path.cwd() if start is None else start
    if current.is_file():
        current = current.parent
    current = current.resolve()

    for candidate in (current, *current.parents):
        if (candidate / CONFIG_FILE).is_file():
            return candidate
    return None


@dataclass
class PythonDefaults:
    requires_python: str | None = None
    line_length: int | str | None = None
    coverage_fail_under: int | str | None = None


def _coerce_jvm_version(value: int | str, field_name: str = "jvm_version") -> int:
    if isinstance(value, int):
        version = value
    else:
        normalized = value.strip()
        if normalized == "1.8":
            version = 8
        elif re.fullmatch(r"\d+", normalized):
            version = int(normalized)
        else:
            raise ValueError(f"{field_name} must be an int or numeric string (e.g. 17, '21', '1.8')")

    if version < 8:
        raise ValueError(f"{field_name} must be >= 8")
    return version


_INTELLIJ_IDEA_VERSION_RE = re.compile(r"^(?P<year>\d{4})\.(?P<release>\d+)(?:\.\d+)?(?:\.\d+)?$")
_INTELLIJ_BUILD_RE = re.compile(r"^(?P<branch>\d{3})(?:\.\*)?$")


def _parse_intellij_idea_version(value: str, field_name: str) -> tuple[int, int]:
    normalized = value.strip()
    match = _INTELLIJ_IDEA_VERSION_RE.fullmatch(normalized)
    if match is None:
        raise ValueError(f"{field_name} must look like YYYY.R (for example 2023.2)")

    year = int(match.group("year"))
    release = int(match.group("release"))
    if release < 1 or release > 3:
        raise ValueError(f"{field_name} has unsupported release segment {release}; expected 1, 2, or 3")
    return year, release


def _parse_intellij_build_branch(value: str, field_name: str) -> int:
    normalized = value.strip()
    match = _INTELLIJ_BUILD_RE.fullmatch(normalized)
    if match is None:
        raise ValueError(f"{field_name} must look like NNN or NNN.* (for example 232 or 253.*)")

    branch = int(match.group("branch"))
    release = branch % 10
    if release < 1 or release > 3:
        year = 2000 + branch // 10
        raise ValueError(f"{field_name} branch {branch} implies IDE version {year}.{release}, which does not exist")
    return branch


def _validate_intellij_feature(feature: IntellijPlugin, *, project_name: str) -> None:
    if feature.ideaVersion is not None:
        _parse_intellij_idea_version(feature.ideaVersion, f"{project_name}.intellij-plugin.ideaVersion")

    since_branch: int | None = None
    if feature.sinceBuild is not None:
        since_branch = _parse_intellij_build_branch(feature.sinceBuild, f"{project_name}.intellij-plugin.sinceBuild")

    until_branch: int | None = None
    if feature.untilBuild is not None:
        until_branch = _parse_intellij_build_branch(feature.untilBuild, f"{project_name}.intellij-plugin.untilBuild")

    if since_branch is not None and until_branch is not None and since_branch > until_branch:
        raise ValueError(
            f"{project_name}.intellij-plugin.sinceBuild ({feature.sinceBuild}) "
            f"must be <= untilBuild ({feature.untilBuild})"
        )


def _validate_intellij_platform_library_feature(
    feature: IntellijPlatformLibrary,
    *,
    project_name: str,
) -> None:
    if feature.ideaVersion is not None:
        _parse_intellij_idea_version(
            feature.ideaVersion,
            f"{project_name}.intellij-platform-library.ideaVersion",
        )


SUPPORTED_GRADLE_BUILD_MODELS: tuple[str, ...] = (
    "jvm",
    "kmp",
)

SUPPORTED_PUBLISH_TARGETS: tuple[str, ...] = (
    "maven-central",
    "jetbrains-marketplace",
    "pypi",
    "jitpack",
    "nuget",
)

SUPPORTED_DOC_SYSTEMS: tuple[str, ...] = (
    "dokka",
    "mkdocs",
)

SUPPORTED_KMP_PLATFORMS: tuple[str, ...] = (
    "jvm",
    "android",
    "js",
    "wasmJs",
    "iosArm64",
    "iosSimulatorArm64",
    "macosX64",
    "macosArm64",
    "linuxX64",
    "mingwX64",
)

SUPPORTED_GRADLE_TARGET_KINDS: tuple[str, ...] = (
    "jvm",
    "android-application",
    "android-kmp-library",
    "js",
    "wasmJs",
    "iosArm64",
    "iosSimulatorArm64",
    "macosX64",
    "macosArm64",
    "linuxX64",
    "mingwX64",
)

GRADLE_TARGET_KIND_TO_PLATFORM: dict[str, str] = {
    "jvm": "jvm",
    "android-application": "android",
    "android-kmp-library": "android",
    "js": "js",
    "wasmJs": "wasmJs",
    "iosArm64": "iosArm64",
    "iosSimulatorArm64": "iosSimulatorArm64",
    "macosX64": "macosX64",
    "macosArm64": "macosArm64",
    "linuxX64": "linuxX64",
    "mingwX64": "mingwX64",
}

APPLE_KMP_PLATFORMS: frozenset[str] = frozenset({"iosArm64", "iosSimulatorArm64", "macosX64", "macosArm64"})
NATIVE_KMP_PLATFORMS: frozenset[str] = frozenset(
    {"iosArm64", "iosSimulatorArm64", "macosX64", "macosArm64", "linuxX64", "mingwX64"}
)

CANONICAL_KMP_SOURCE_SET_REQUIREMENTS: dict[str, str] = {
    "commonMain": "common",
    "commonTest": "common",
    "jvmMain": "jvm",
    "jvmTest": "jvm",
    "androidMain": "android",
    "androidUnitTest": "android",
    "jsMain": "js",
    "jsTest": "js",
    "wasmJsMain": "wasmJs",
    "wasmJsTest": "wasmJs",
    "nativeMain": "native",
    "nativeTest": "native",
    "appleMain": "apple",
    "appleTest": "apple",
    "iosArm64Main": "iosArm64",
    "iosArm64Test": "iosArm64",
    "iosSimulatorArm64Main": "iosSimulatorArm64",
    "iosSimulatorArm64Test": "iosSimulatorArm64",
    "macosX64Main": "macosX64",
    "macosX64Test": "macosX64",
    "macosArm64Main": "macosArm64",
    "macosArm64Test": "macosArm64",
    "clientNativeMain": "macosArm64",
    "clientNativeTest": "macosArm64",
    "linuxX64Main": "linuxX64",
    "linuxX64Test": "linuxX64",
    "mingwX64Main": "mingwX64",
    "mingwX64Test": "mingwX64",
}

GRADLE_SOURCE_SET_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:Main|Test|UnitTest)$")


def _normalize_gradle_build_model(
    project_name: str,
    build_model: str | None,
    *,
    platforms: list[str] | None,
    targets: list[config_typed.GradleTargetCommand] | None,
    source_sets: dict[str, config_typed.GradleSourceSetCommand] | None,
    source_set_dependencies: dict[str, list[config_typed.DependencyInput]] | None,
) -> str:
    if build_model is not None:
        if build_model not in SUPPORTED_GRADLE_BUILD_MODELS:
            supported = ", ".join(SUPPORTED_GRADLE_BUILD_MODELS)
            raise ValueError(f"{project_name}.buildModel must be one of: {supported}")
        return build_model

    if targets:
        if any(GRADLE_TARGET_KIND_TO_PLATFORM[target.kind] != "jvm" for target in targets):
            return "kmp"
        return "jvm"

    if platforms is not None:
        if any(platform != "jvm" for platform in platforms):
            return "kmp"
        return "jvm"

    if source_sets is not None or source_set_dependencies is not None:
        return "kmp"

    return "jvm"


def _normalize_publish_target(
    project_name: str,
    publish_target: str | None,
    *,
    default_target: str | None,
) -> str | None:
    if publish_target is None:
        return default_target
    if publish_target not in SUPPORTED_PUBLISH_TARGETS:
        supported = ", ".join(SUPPORTED_PUBLISH_TARGETS)
        raise ValueError(f"{project_name}.publishTarget must be one of: {supported}")
    return publish_target


def _normalize_docs_system(
    project_name: str,
    docs_system: str | None,
    *,
    default_docs_system: str | None,
) -> str | None:
    if docs_system is None:
        return default_docs_system
    if docs_system not in SUPPORTED_DOC_SYSTEMS:
        supported = ", ".join(SUPPORTED_DOC_SYSTEMS)
        raise ValueError(f"{project_name}.docsSystem must be one of: {supported}")
    return docs_system


def _normalize_gradle_targets(
    project_name: str,
    targets: list[config_typed.GradleTargetCommand] | None,
) -> list[GradleTargetSpec]:
    if targets is None:
        return []

    normalized_targets: list[GradleTargetSpec] = []
    seen_target_names: set[str] = set()
    seen_platforms: set[str] = set()

    for target_index, target in enumerate(targets):
        kind = target.kind.strip()
        if kind not in SUPPORTED_GRADLE_TARGET_KINDS:
            supported = ", ".join(SUPPORTED_GRADLE_TARGET_KINDS)
            raise ValueError(f"{project_name}.targets[{target_index}].kind must be one of: {supported}")

        platform = GRADLE_TARGET_KIND_TO_PLATFORM[kind]
        if platform in seen_platforms:
            raise ValueError(f"{project_name}.targets declares duplicate platform {platform}")
        seen_platforms.add(platform)

        name = target.name.strip() if target.name is not None else None
        namespace = target.namespace.strip() if target.namespace is not None else None
        application_id = target.applicationId.strip() if target.applicationId is not None else None
        compile_sdk = target.compileSdk
        min_sdk = target.minSdk
        target_sdk = target.targetSdk
        manifest_path = target.manifestPath.strip() if target.manifestPath is not None else None
        browser = target.browser
        browser_test = target.browserTest.strip() if target.browserTest is not None else None
        executable = target.executable

        if name == "":
            raise ValueError(f"{project_name}.targets[{target_index}].name must not be empty")
        if namespace == "":
            raise ValueError(f"{project_name}.targets[{target_index}].namespace must not be empty")
        if application_id == "":
            raise ValueError(f"{project_name}.targets[{target_index}].applicationId must not be empty")
        if manifest_path == "":
            raise ValueError(f"{project_name}.targets[{target_index}].manifestPath must not be empty")
        if browser_test == "":
            raise ValueError(f"{project_name}.targets[{target_index}].browserTest must not be empty")

        if name is not None:
            if name in seen_target_names:
                raise ValueError(f"{project_name}.targets declares duplicate target name {name}")
            seen_target_names.add(name)

        if kind == "android-application":
            if namespace is None or application_id is None or compile_sdk is None or min_sdk is None:
                raise ValueError(
                    f"{project_name}.targets[{target_index}] android-application requires "
                    f"namespace/applicationId/compileSdk/minSdk"
                )
            if manifest_path is None:
                manifest_path = "src/androidMain/AndroidManifest.xml"

        if kind == "android-kmp-library":
            if namespace is None or compile_sdk is None or min_sdk is None:
                raise ValueError(
                    f"{project_name}.targets[{target_index}] android-kmp-library requires "
                    f"namespace/compileSdk/minSdk"
                )
            if manifest_path is None:
                manifest_path = "src/androidMain/AndroidManifest.xml"

        if browser_test is not None:
            if browser is False:
                raise ValueError(f"{project_name}.targets[{target_index}] browserTest requires browser=true")
            browser = True

        if browser_test is not None and browser_test != "chromeHeadless":
            raise ValueError(
                f"{project_name}.targets[{target_index}].browserTest must be chromeHeadless when specified"
            )

        if executable and kind != "wasmJs":
            raise ValueError(f"{project_name}.targets[{target_index}] executable is only valid for wasmJs")

        normalized_targets.append(
            GradleTargetSpec(
                kind=kind,
                name=name,
                namespace=namespace,
                application_id=application_id,
                compile_sdk=compile_sdk,
                min_sdk=min_sdk,
                target_sdk=target_sdk,
                manifest_path=manifest_path,
                browser=browser,
                browser_test=browser_test,
                executable=executable,
            )
        )

    return normalized_targets


def _platforms_from_targets(targets: list[GradleTargetSpec]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for target in targets:
        platform = GRADLE_TARGET_KIND_TO_PLATFORM[target.kind]
        if platform in seen:
            continue
        seen.add(platform)
        normalized.append(platform)
    return normalized


def _legacy_targets_from_platforms(
    platforms: list[str],
    resolved_features: dict[str, Feature],
) -> list[GradleTargetSpec]:
    targets: list[GradleTargetSpec] = []
    for platform in platforms:
        if platform == "android":
            android_feature = resolved_features.get("kmp-android-library")
            if isinstance(android_feature, KmpAndroidLibrary):
                targets.append(
                    GradleTargetSpec(
                        kind="android-kmp-library",
                        namespace=android_feature.namespace,
                        compile_sdk=android_feature.compileSdk,
                        min_sdk=android_feature.minSdk,
                        manifest_path=android_feature.manifestPath,
                    )
                )
            else:
                targets.append(GradleTargetSpec(kind="android-application"))
            continue
        if platform == "macosArm64":
            targets.append(GradleTargetSpec(kind="macosArm64"))
            continue
        if platform == "macosX64":
            targets.append(GradleTargetSpec(kind="macosX64"))
            continue
        targets.append(GradleTargetSpec(kind=platform))
    return targets


def _android_library_target_from_features(
    resolved_features: dict[str, Feature],
) -> GradleTargetSpec | None:
    android_feature = resolved_features.get("kmp-android-library")
    if not isinstance(android_feature, KmpAndroidLibrary):
        return None

    return GradleTargetSpec(
        kind="android-kmp-library",
        namespace=android_feature.namespace,
        compile_sdk=android_feature.compileSdk,
        min_sdk=android_feature.minSdk,
        manifest_path=android_feature.manifestPath,
    )


def _is_valid_gradle_source_set_name(source_set_name: str) -> bool:
    return (
        source_set_name in CANONICAL_KMP_SOURCE_SET_REQUIREMENTS
        or GRADLE_SOURCE_SET_NAME_RE.fullmatch(source_set_name) is not None
    )


def _normalize_gradle_platforms(project_name: str, platforms: list[str] | None) -> list[str]:
    if platforms is None:
        return ["jvm"]
    if not platforms:
        raise ValueError(f"{project_name}.platforms must not be empty")

    normalized: list[str] = []
    seen: set[str] = set()
    for platform in platforms:
        if platform not in SUPPORTED_KMP_PLATFORMS:
            supported = ", ".join(SUPPORTED_KMP_PLATFORMS)
            raise ValueError(
                f"{project_name}.platforms contains unsupported platform {platform!r}; supported: {supported}"
            )
        if platform in seen:
            continue
        seen.add(platform)
        normalized.append(platform)
    return normalized


def _is_kmp_mode(platforms: list[str]) -> bool:
    return any(platform != "jvm" for platform in platforms)


def _source_set_is_allowed_for_platforms(source_set: str, platforms: list[str]) -> bool:
    requirement = CANONICAL_KMP_SOURCE_SET_REQUIREMENTS[source_set]
    if requirement == "common":
        return True
    if requirement == "native":
        return any(platform in NATIVE_KMP_PLATFORMS for platform in platforms)
    if requirement == "apple":
        return any(platform in APPLE_KMP_PLATFORMS for platform in platforms)
    return requirement in platforms


def source_set_is_allowed_for_platforms(source_set: str, platforms: list[str]) -> bool:
    return _source_set_is_allowed_for_platforms(source_set, platforms)


@dataclass(frozen=True)
class BackupTarget:
    name: str
    kind: Literal["restic-sftp"]
    host: str
    user: str
    path: str
    ssh_key: str | None = None
    password_file: str | None = None
    password_command: str | None = None
    compression: str = "auto"


@dataclass(frozen=True)
class BackupPolicy:
    target_names: tuple[str, ...]
    service_enabled: bool = True
    service_dirty_age_minutes: int = 60
    service_min_interval_minutes: int = 360
    include_git: bool = True
    exclude: tuple[str, ...] = ()
    exclude_if_present: tuple[str, ...] = ()
    exclude_caches: bool = True
    include_repos: tuple[str, ...] = ("*",)
    exclude_repos: tuple[str, ...] = ()


@dataclass
class Config:
    raw: Document
    workspace_root: Path | None = None

    openai_key: str | None = None
    github_token: str | None = None
    github_ssh_key: str | None = None
    anthropic_key: str | None = None
    jetbrains_marketplace_token: str | None = None
    pypi_token: str | None = None
    nuget_api_key: str | None = None
    maven_username: str | None = None
    maven_password: str | None = None
    maven_gpg_private_key: str | None = None
    maven_gpg_passphrase: str | None = None
    maven_gpg_key_id: str | None = None
    jitpack_cookie: str | None = None

    backup_targets: OrderedDict[str, BackupTarget] = dataclasses.field(default_factory=OrderedDict)
    backup_policy: BackupPolicy | None = None

    default_maven_project_group: str | None = None
    default_company_email: str | None = None
    default_company_legal_name: str | None = None
    default_company_short_name: str | None = None
    default_code_owners: list[CodeOwner] = dataclasses.field(default_factory=list)
    default_git_user_email: str | None = None
    default_git_user_name: str | None = None

    repositories: OrderedDict[str, MavenRepositoryDefinition] = dataclasses.field(default_factory=OrderedDict)
    plugins: OrderedDict[str, KotlinPluginDefinition] = dataclasses.field(default_factory=OrderedDict)
    default_gradle_plugin_applications: list[GradlePluginApplication] = dataclasses.field(default_factory=list)
    libraries: OrderedDict[str, MavenLibraryDefinition] = dataclasses.field(default_factory=OrderedDict)
    library_groups: OrderedDict[str, list[str | Dependency | list[Dependency]]] = dataclasses.field(
        default_factory=OrderedDict
    )
    defined_repos: OrderedDict[str, RepoDefinition] = dataclasses.field(default_factory=OrderedDict)
    defined_projects: OrderedDict[str, Project] = dataclasses.field(default_factory=OrderedDict)

    disabled_checks: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    ignored_findings: list[tuple[str, str, str]] = dataclasses.field(default_factory=list)

    modules: dict[str, Module] = dataclasses.field(default_factory=dict)
    python_defaults: PythonDefaults = dataclasses.field(default_factory=PythonDefaults)
    jvm_version: int = 21

    @property
    def java_version(self) -> int:
        return self.jvm_version

    @property
    def kotlin_jvm_target(self) -> str:
        if self.jvm_version == 8:
            return "JVM_1_8"
        return f"JVM_{self.jvm_version}"


def get_gradle_plugin_applications(project: GradleProject) -> list[GradlePluginApplication]:
    feature = project.resolved_features.get("gradle-plugin")
    if not isinstance(feature, GradlePlugins):
        return []
    return list(feature.entries)


def _with_default_gradle_plugins(
    features: list[Feature],
    default_applications: Sequence[GradlePluginApplication],
) -> list[Feature]:
    if not default_applications:
        return features
    return [GradlePlugins(entries=list(default_applications)), *features]


def project_repo_root(project: Project | object) -> Path:
    if isinstance(project, Project):
        return project.effective_repo_root
    repo_root = getattr(project, "repo_root", None)
    if isinstance(repo_root, Path):
        return repo_root
    path = getattr(project, "path", None)
    if isinstance(path, Path):
        return path
    raise TypeError(f"Unsupported project object without path/repo_root: {project!r}")


def load_config(start: Path | None = None) -> Config:
    parse_params = signature(parse).parameters

    class ParseWithKeywordOptions(Protocol):
        def __call__(self, text: str, **kwargs: object) -> Document: ...

    def parse_document(text: str) -> Document:
        if "no_spans" in parse_params:
            parser_with_kwargs = cast(ParseWithKeywordOptions, parse)
            return parser_with_kwargs(text, no_spans=False)
        return parse(text)

    workspace_root = find_workspace_root(start)
    if workspace_root is None:
        start_path = Path.cwd() if start is None else start
        raise FileNotFoundError(f"Could not find {CONFIG_FILE} in {start_path} or any parent directory")

    workspace_root = workspace_root.resolve()
    root_path = workspace_root / CONFIG_FILE
    root_private_path = workspace_root / CONFIG_PRIVATE_FILE

    with open(root_path, encoding="utf-8") as f:
        root = parse_document(f.read())
    with open(root_private_path, encoding="utf-8") as f:
        root_private = parse_document(f.read())

    config = Config(raw=root, workspace_root=workspace_root)

    modules = Module.load_modules()
    config.modules = modules

    module_command_handlers: dict[type[object], Callable[[object], None]] = {}
    module_command_types: list[type[object]] = []
    for module in modules.values():
        for registration in module.register_typed_config_commands():
            if registration.command_type in module_command_handlers:
                raise ValueError(f"Duplicate typed config command registration for " f"{registration.command_type}")
            module_command_handlers[registration.command_type] = registration.apply
            module_command_types.append(registration.command_type)

    top_level_target = config_typed.make_top_level_target(module_command_types)
    defines: dict[str, object] = {}

    def register_project(project_id: str, project: Project) -> None:
        if project_id in config.defined_projects:
            raise ValueError(f"Project {project_id} already exists")
        config.defined_projects[project_id] = project

    def _extract_expr_span(expr: object) -> object | None:
        if isinstance(expr, (AtomExpr, StringExpr)):
            span = expr.span
            if span is None:
                return None
            token: object | None = getattr(span, "token", None)
            return token if token is not None else span

        for attr in ("open_bracket", "span"):
            value = getattr(expr, attr, None)
            if value is None:
                continue
            nested_token: object | None = getattr(value, "token", None)
            return nested_token if nested_token is not None else value

        values = getattr(expr, "values", None)
        if isinstance(values, list):
            for item in cast(list[object], values):
                nested = _extract_expr_span(item)
                if nested is not None:
                    return nested

        for attr in ("key", "value"):
            value = getattr(expr, attr, None)
            if value is None:
                continue
            nested = _extract_expr_span(value)
            if nested is not None:
                return nested
        return expr

    def _coerce_ownership(value: str | None) -> OwnershipType:
        if value is None:
            return OwnershipType.WABBIT
        return OwnershipType(value)

    def _resolve_maven_version(value: config_typed.Value[str]) -> str:
        if isinstance(value, config_typed.Const):
            return value.value
        if value.name not in defines:
            raise ValueError(f"Undefined variable referenced in maven version: {value.name}")
        resolved = defines[value.name]
        if not isinstance(resolved, str):
            raise ValueError(f"Maven version variable {value.name} must resolve to string, got {type(resolved)}")
        return resolved

    def _render_maven_coordinate(expr: config_typed.MavenCoordinateExpr) -> str:
        version_value = _resolve_maven_version(expr.version)
        rendered = f"{expr.group_id}:{expr.artifact_id}:{version_value}"
        if expr.suffix:
            rendered = f"{rendered}:{expr.suffix}"
        return rendered

    def _feature_from_command(command: config_typed.FeatureCommand) -> Feature:
        if isinstance(command, config_typed.JvmKotlinLibraryCommand):
            return JvmKotlinLibrary()
        if isinstance(command, config_typed.KotlinGradlePluginLibraryCommand):
            return KotlinGradlePluginLibrary()
        if isinstance(command, config_typed.JvmScalaLibraryCommand):
            return JvmScalaLibrary()
        if isinstance(command, config_typed.JvmKotlinApplicationCommand):
            return JvmKotlinApplication(command.main, command.jar)
        if isinstance(command, config_typed.ShadowJarCommand):
            return ShadowJar(jarName=command.jar)
        if isinstance(command, config_typed.PaperPluginCommand):
            return PaperPlugin(
                main=command.main,
                name=command.name,
                apiVersion=command.apiVersion,
                depend=list(command.depend or []) or None,
            )
        if isinstance(command, config_typed.JvmKotlinAgentCommand):
            return JvmKotlinAgent(command.main, command.jar)
        if isinstance(command, config_typed.IntellijPluginCommand):
            return IntellijPlugin(
                pluginName=command.pluginName,
                pluginId=command.pluginId,
                ideaVersion=command.ideaVersion,
                sinceBuild=command.sinceBuild,
                untilBuild=command.untilBuild,
                vendorName=command.vendorName,
                vendorEmail=command.vendorEmail,
                vendorUrl=command.vendorUrl,
                pluginDescription=command.pluginDescription,
                pluginChangeNotes=command.pluginChangeNotes,
                depends=command.depends,
                bundledPlugins=command.bundledPlugins,
                publishChannel=command.publishChannel,
                marketplaceTokenEnv=command.marketplaceTokenEnv,
            )
        if isinstance(command, config_typed.IntellijPlatformLibraryCommand):
            return IntellijPlatformLibrary(
                ideaVersion=command.ideaVersion,
                bundledPlugins=command.bundledPlugins,
            )
        if isinstance(command, config_typed.KotlinSerializationCommand):
            return KotlinSerialization()
        if isinstance(command, config_typed.KotlinComposePluginCommand):
            return KotlinComposePlugin()
        if isinstance(command, config_typed.GradlePluginCommand):
            return GradlePlugins(
                entries=[
                    GradlePluginApplication(
                        name=command.name,
                        compilerOptions=dict(command.compilerOptions or {}),
                    )
                ]
            )
        if isinstance(command, config_typed.KotlinCompilerPluginCommand):
            compatibility_sources = [
                KotlinCompilerPluginCompatibilitySource(kotlinVersionPrefix=prefix, path=path)
                for prefix, path in (command.compatibilitySources or {}).items()
            ]
            return KotlinCompilerPlugin(
                compatibilitySources=compatibility_sources,
                publishVersionWithKotlin=command.publishVersionWithKotlin,
            )
        if isinstance(command, config_typed.KotlinCompilerGradlePluginCommand):
            return KotlinCompilerGradlePlugin(
                compilerPluginProject=_normalize_project_reference(
                    command.compilerPluginProject,
                    field_name="kotlin-compiler-gradle-plugin.compilerPluginProject",
                ),
                versionPackage=command.versionPackage,
                versionClassName=command.versionClassName,
                versionConstantName=command.versionConstantName,
            )
        if isinstance(command, config_typed.KmpAndroidLibraryCommand):
            return KmpAndroidLibrary(
                namespace=command.namespace,
                compileSdk=command.compileSdk,
                minSdk=command.minSdk,
                manifestPath=command.manifestPath,
            )
        if isinstance(command, config_typed.KmpComposeCommand):
            return KmpCompose(
                publicResClass=command.publicResClass,
                resClassPackage=command.resClassPackage,
            )
        if isinstance(command, config_typed.KmpJvmRunsCommand):
            run_entries: list[KmpJvmRunEntry] = []
            for _index, entry in enumerate(command.entries):
                task_name = entry.taskName
                main_class = entry.mainClass
                description = entry.description
                jvm_args = list(entry.jvmArgs or [])
                run_entries.append(
                    KmpJvmRunEntry(
                        taskName=task_name,
                        mainClass=main_class,
                        description=description,
                        jvmArgs=jvm_args,
                    )
                )
            return KmpJvmRuns(entries=run_entries)
        if isinstance(command, config_typed.PythonDeptryCommand):
            return PythonDeptry(
                package_map=command.package_map or {},
                per_rule_ignores=command.per_rule_ignores or {},
                auto_package_map=command.auto_package_map,
            )
        return PythonImportLinter(
            root_packages=command.root_packages or [],
            layers=command.layers or [],
        )

    def _validate_modifier(modifier: str | None) -> str | None:
        if modifier is None:
            return None
        if modifier not in [
            "test",
            "implementation",
            "api",
            "compileOnly",
            "kapt",
            "runtimeOnly",
            "testImplementation",
            "testCompileOnly",
            "testRuntimeOnly",
        ]:
            raise ValueError(f"Unknown modifier: {modifier}")
        return modifier

    def parse_gradle_dependency(
        dep: str | Dependency | config_typed.DepCall | list[Dependency],
        modifier: str | None = None,
        current_repo_id: str | None = None,
    ) -> list[Dependency]:
        if isinstance(dep, config_typed.DepCall):
            effective_modifier = dep.modifier if dep.modifier is not None else modifier
            return parse_gradle_dependency(dep.name, effective_modifier, current_repo_id=current_repo_id)

        if isinstance(dep, Dependency):
            return [dep]

        if isinstance(dep, list):
            return list(dep)

        modifier = _validate_modifier(modifier)

        if dep.startswith(".") or dep.startswith("/"):
            path = Path(dep)
            return [Dependency(scope=modifier, target=JarFileDependencyTarget(path=path))]

        if dep.startswith(":"):
            project_name = dep[1:]
            resolved_project_name = project_name
            if resolved_project_name not in config.defined_projects and current_repo_id is not None:
                local_project_name = f"{current_repo_id}/{project_name}"
                if local_project_name in config.defined_projects:
                    resolved_project_name = local_project_name
            if resolved_project_name not in config.defined_projects:
                raise ValueError(f"Project {project_name} is not defined")
            return [
                Dependency(
                    scope=modifier,
                    target=ProjectDependencyTarget(project=resolved_project_name),
                )
            ]

        if dep.startswith("npm:"):
            npm_spec = dep.removeprefix("npm:")
            if ":" not in npm_spec:
                raise ValueError(f"NPM dependency must be npm:<package>:<version>, got {dep!r}")
            package, version = npm_spec.rsplit(":", 1)
            if not package or not version:
                raise ValueError(f"NPM dependency must be npm:<package>:<version>, got {dep!r}")
            return [Dependency(scope=modifier, target=NpmDependencyTarget(package=package, version=version))]

        if dep in config.library_groups:
            group_result: list[Dependency] = []
            for lib in config.library_groups[dep]:
                if isinstance(lib, str):
                    group_result.extend(parse_gradle_dependency(lib, modifier, current_repo_id=current_repo_id))
                elif isinstance(lib, list):
                    group_result.extend(parse_gradle_dependency(lib, modifier, current_repo_id=current_repo_id))
                else:
                    group_result.extend(parse_gradle_dependency(lib, modifier, current_repo_id=current_repo_id))
            return group_result

        if dep in config.libraries:
            maven_urn = config.libraries[dep].maven_urn.__str__()
            maven_repo = config.libraries[dep].repo
            return [
                Dependency(
                    scope=modifier,
                    target=MavenDependencyTarget(
                        artifact=maven_urn,
                        maven_repo=maven_repo,
                    ),
                )
            ]

        if is_valid_maven_coordinate(dep):
            return [Dependency(scope=modifier, target=MavenDependencyTarget(artifact=dep))]

        raise ValueError(f"Unknown library or library group: {dep}")

    def parse_dotnet_dependency(
        dep: str,
        *,
        current_repo_id: str | None,
    ) -> Dependency:
        if dep.startswith(":"):
            project_name = dep[1:]
            resolved_project_name = project_name
            if resolved_project_name not in config.defined_projects and current_repo_id is not None:
                local_project_name = f"{current_repo_id}/{project_name}"
                if local_project_name in config.defined_projects:
                    resolved_project_name = local_project_name
            if resolved_project_name not in config.defined_projects:
                raise ValueError(f"Project {project_name} is not defined")
            return Dependency(
                scope=None,
                target=ProjectDependencyTarget(project=resolved_project_name),
            )

        package_name, separator, version = dep.rpartition("@")
        if not separator or not package_name.strip() or not version.strip():
            raise ValueError(
                f".NET dependency {dep!r} must use :project-id or Package.Id@Version syntax"
            )
        return Dependency(
            scope=None,
            target=NugetDependencyTarget(package=package_name.strip(), version=version.strip()),
        )

    def _normalize_dotnet_project_kind(project_name: str, project_kind: str | None) -> DotnetProjectKind:
        if project_kind is None:
            return "library"
        if project_kind not in ("library", "exe", "tool", "test"):
            raise ValueError(
                f"{project_name}.projectKind has unsupported value {project_kind!r}; "
                "expected one of: library, exe, tool, test"
            )
        return project_kind

    def _normalize_dotnet_target_frameworks(
        project_name: str,
        *,
        target_framework: str | None,
        target_frameworks: list[str] | None,
        default_target_framework: str | None,
    ) -> tuple[str | None, list[str]]:
        if target_framework is not None and target_frameworks is not None:
            raise ValueError(
                f"{project_name} cannot define both targetFramework and targetFrameworks"
            )
        if target_frameworks is not None:
            normalized_frameworks = [framework.strip() for framework in target_frameworks if framework.strip()]
            if not normalized_frameworks:
                raise ValueError(f"{project_name}.targetFrameworks must not be empty")
            return None, normalized_frameworks
        if target_framework is not None:
            normalized_framework = target_framework.strip()
            if not normalized_framework:
                raise ValueError(f"{project_name}.targetFramework must not be empty")
            return normalized_framework, []
        if default_target_framework is not None:
            normalized_default_framework = default_target_framework.strip()
            if normalized_default_framework:
                return normalized_default_framework, []
        raise ValueError(f"{project_name} must define targetFramework/targetFrameworks or inherit a repo default")

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
                if dependency_project.is_kmp:
                    if "jvm" not in dependency_project.platforms:
                        return False
                continue
            if not dependency_project.is_kmp or requirement not in dependency_project.platforms:
                return False
        return True

    def _source_set_base_required_platforms(project: GradleProject, source_set_name: str) -> set[str]:
        requirement = CANONICAL_KMP_SOURCE_SET_REQUIREMENTS.get(source_set_name)
        if requirement is None:
            return set()
        if requirement == "apple":
            if any(platform in APPLE_KMP_PLATFORMS for platform in project.platforms):
                return {"apple"}
            return set()
        return {requirement}

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
        return {}

    def _source_set_required_platforms(project: GradleProject, source_set_name: str) -> set[str]:
        reverse_graph: dict[str, list[str]] = {}
        for platform in project.platforms:
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
            requirements = _source_set_base_required_platforms(project, current_source_set_name)
            if requirements == {"common"}:
                visiting.remove(current_source_set_name)
                cache[current_source_set_name] = requirements
                return requirements
            for child_source_set_name in reverse_graph.get(current_source_set_name, []):
                requirements.update(visit(child_source_set_name, visiting))
            if current_source_set_name not in CANONICAL_KMP_SOURCE_SET_REQUIREMENTS and requirements:
                if requirements == {"jvm"}:
                    pass
                elif requirements == {"android"}:
                    pass
                elif requirements <= {"apple", "iosArm64", "iosSimulatorArm64", "macosArm64"}:
                    requirements = {"apple"}
                else:
                    requirements = {"common"}
            visiting.remove(current_source_set_name)
            cache[current_source_set_name] = requirements
            return requirements

        return visit(source_set_name, set())

    def _validate_kmp_project_dependencies(project: GradleProject) -> None:
        has_kmp_specific_features = any(
            key in project.resolved_features
            for key in (
                "kmp-compose",
                "kmp-jvm-runs",
            )
        )
        if "kmp-android-library" in project.resolved_features and not project.targets:
            has_kmp_specific_features = True

        if not project.is_kmp:
            if has_kmp_specific_features:
                raise ValueError(
                    f"{project.name} defines KMP-specific features but is JVM-only; "
                    f"declare non-JVM :platforms or remove KMP features"
                )
            return

        android_feature = project.resolved_features.get("kmp-android-library")
        has_android_library_target = any(target.kind == "android-kmp-library" for target in project.targets)
        if isinstance(android_feature, KmpAndroidLibrary):
            if has_android_library_target:
                android_target = next(target for target in project.targets if target.kind == "android-kmp-library")
                if (
                    android_target.namespace != android_feature.namespace
                    or android_target.compile_sdk != android_feature.compileSdk
                    or android_target.min_sdk != android_feature.minSdk
                    or android_target.manifest_path != android_feature.manifestPath
                ):
                    raise ValueError(
                        f"{project.name} defines android-kmp-library target settings that do not match "
                        "kmp-android-library; keep only the target or make the values identical"
                    )
            elif "android" not in project.platforms:
                raise ValueError(f"{project.name} enables kmp-android-library but does not declare an android target")

        jvm_runs_feature = project.resolved_features.get("kmp-jvm-runs")
        if jvm_runs_feature is not None and "jvm" not in project.platforms:
            raise ValueError(f"{project.name} enables kmp-jvm-runs but does not declare jvm in :platforms")

        for source_set_name, dependencies in project.source_set_dependencies.items():
            required_platforms = _source_set_required_platforms(project, source_set_name)
            for dependency in dependencies:
                target = dependency.target
                if not isinstance(target, ProjectDependencyTarget):
                    continue
                dependency_project = config.defined_projects[target.project]
                if not _project_supports_required_platforms(dependency_project, required_platforms):
                    requirement_text = ", ".join(sorted(required_platforms)) or "unknown"
                    if "common" in required_platforms:
                        requirement_text = "common"
                    elif "apple" in required_platforms:
                        requirement_text = "apple"
                    raise ValueError(
                        f"{project.name}.{source_set_name} cannot depend on {dependency_project.name}: "
                        f"source set requires {requirement_text} compatibility"
                    )

    def verify_project(project: Project) -> None:
        project.license = canonicalize_license_key(project.license)
        project.test_license = canonicalize_license_key(project.test_license)
        if project.copyright_holder is not None:
            project.copyright_holder = project.copyright_holder.strip() or None
        if project.copyright_year_start is not None and project.copyright_year_start <= 0:
            raise ValueError(f"{project.name} has invalid copyright_year_start={project.copyright_year_start}")

        match project:
            case GradleProject():
                intellij_feature = project.resolved_features.get("intellij-plugin")
                if isinstance(intellij_feature, IntellijPlugin):
                    _validate_intellij_feature(intellij_feature, project_name=project.name)
                intellij_platform_library_feature = project.resolved_features.get("intellij-platform-library")
                if isinstance(intellij_platform_library_feature, IntellijPlatformLibrary):
                    _validate_intellij_platform_library_feature(
                        intellij_platform_library_feature,
                        project_name=project.name,
                    )
                _validate_kmp_project_dependencies(project)
                if project.docs_enabled and project.docs_system not in (None, "dokka"):
                    raise ValueError(f"{project.name} is a Gradle project and must use docsSystem 'dokka'")
            case PythonProject():
                if project.docs_enabled and project.docs_system not in (None, "mkdocs"):
                    raise ValueError(f"{project.name} is a Python project and must use docsSystem 'mkdocs'")
            case DotnetProject():
                if not project.effective_target_frameworks:
                    raise ValueError(f"{project.name} must define at least one target framework")
                if project.publish_target not in (None, "nuget"):
                    raise ValueError(f"{project.name} is a .NET project and must use publishTarget 'nuget'")
                if project.publish_snapshots:
                    raise ValueError(f"{project.name} cannot enable publishSnapshots for NuGet publishing")
                if project.docs_enabled and project.docs_system not in (None, "mkdocs"):
                    raise ValueError(f"{project.name} is a .NET project and must use docsSystem 'mkdocs'")
                for dependency in project.resolved_dependencies:
                    target = dependency.target
                    if not isinstance(target, ProjectDependencyTarget):
                        continue
                    dependency_project = config.defined_projects[target.project]
                    if not isinstance(dependency_project, DotnetProject):
                        raise ValueError(
                            f".NET project {project.name} cannot depend on non-.NET project {dependency_project.name}"
                        )
            case _:
                if project.docs_enabled:
                    raise ValueError(
                        f"{project.name} enables docs, but {type(project).__name__} does not support docs generation"
                    )

        def is_publishable(input_project: Project) -> bool:
            return input_project.publish and input_project.github_repo is not None and (not input_project.quarantine)

        for dep in project.resolved_dependencies:
            if not isinstance(dep.target, ProjectDependencyTarget):
                continue
            dep_project = config.defined_projects[dep.target.project]
            if project.effective_repo_root == dep_project.effective_repo_root:
                continue
            if is_publishable(project):
                assert is_publishable(dep_project), (
                    f"Project {project.name} depends on {dep_project.name}. "
                    f"Project {dep_project.name} is not publishable, but {project.name} is publishable. "
                    f"{project.name}.github_repo = {project.github_repo}, "
                    f"{dep_project.name}.github_repo = {dep_project.github_repo}, "
                    f"{project.name}.quarantine = {project.quarantine}, "
                    f"{dep_project.name}.quarantine = {dep_project.quarantine}"
                    f"{project.name}.publish = {project.publish}, "
                    f"{dep_project.name}.publish = {dep_project.publish}"
                )

    def _project_id_for(dir_name: str, repo_id: str | None) -> str:
        if repo_id is None:
            return dir_name
        return f"{repo_id}/{dir_name}"

    def _project_path_for(dir_name: str, repo_root_path: Path | None) -> Path:
        if repo_root_path is None:
            return workspace_root / dir_name
        return repo_root_path / dir_name

    def _project_name_for(dir_name: str, configured_name: str | None, repo_id: str | None) -> str:
        if configured_name is not None:
            return configured_name
        if repo_id is None:
            return dir_name
        return Path(dir_name).name

    def _project_github_repo_for(project_repo: str | None, default_repo: str | None) -> str | None:
        if project_repo is not None:
            return project_repo
        return default_repo

    def _gradle_project_name_for(
        command: config_typed.GradleProjectCommand,
        *,
        project_id: str,
        repo_id: str | None,
    ) -> str:
        if command.gradleProjectName is not None:
            return command.gradleProjectName
        if repo_id is None:
            return command.dir_name
        return project_id.replace("/", "-")

    def _gradle_artifact_id_for(
        command: config_typed.GradleProjectCommand,
        *,
        display_name: str,
        gradle_project_name: str,
        repo_id: str | None,
    ) -> str:
        if command.artifactId is not None:
            return command.artifactId
        if repo_id is None:
            return display_name
        return gradle_project_name

    def _parse_source_set_dependency_items(
        project_name: str,
        source_set_name: str,
        items: list[config_typed.DependencyInput],
        *,
        current_repo_id: str | None,
    ) -> list[Dependency]:
        parsed_dependencies: list[Dependency] = []
        for item in items:
            if isinstance(item, str):
                parsed_dependencies.extend(parse_gradle_dependency(item, current_repo_id=current_repo_id))
                continue
            if isinstance(item, config_typed.DepCall):
                parsed_dependencies.extend(parse_gradle_dependency(item, current_repo_id=current_repo_id))
                continue
            raise TypeError(f"Unknown source set dependency value in {project_name}.{source_set_name}: {item}")
        return parsed_dependencies

    def _apply_project_command(
        command: object,
        *,
        repo_id: str | None,
        repo_root_path: Path | None,
        default_github_repo: str | None,
        repo_jvm_policy: str | None,
        repo_dotnet_sdk_version: str | None,
        repo_default_target_framework: str | None,
        managed_by_setup: bool,
    ) -> str | None:
        if isinstance(command, config_typed.PythonProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            path = _project_path_for(command.dir_name, repo_root_path)
            name = _project_name_for(command.dir_name, command.name, repo_id)
            project_id = _project_id_for(command.dir_name, repo_id)
            defaults = config.python_defaults
            requires_python = command.requires_python or defaults.requires_python
            legacy_scripts = command.scripts or []

            if command.features and legacy_scripts:
                raise ValueError(
                    f"Python project {name} cannot set both :features (python-application) and legacy :scripts"
                )

            application: PythonApplication | None = None
            for feature in command.features or []:
                if application is not None:
                    raise ValueError(f"Python project {name} defines multiple python-application features")

                script = feature.script.strip()
                entry = feature.entry.strip()
                script_path = feature.path.strip()
                aliases = [alias.strip() for alias in (feature.aliases or []) if alias.strip()]

                if not script:
                    raise ValueError(f"Python project {name} has empty python-application.script")
                if "=" in script:
                    raise ValueError(
                        f"Python project {name} python-application.script must be a command name, not script=entry"
                    )
                if not entry or ":" not in entry:
                    raise ValueError(
                        f"Python project {name} python-application.entry must use module:function form, got {entry!r}"
                    )
                if not script_path:
                    raise ValueError(f"Python project {name} has empty python-application.path")

                all_script_names = [script, *aliases]
                if len(set(all_script_names)) != len(all_script_names):
                    raise ValueError(f"Python project {name} python-application has duplicate script names")

                application = PythonApplication(
                    script=script,
                    entry=entry,
                    path=script_path,
                    aliases=aliases,
                )

            publish_target = _normalize_publish_target(
                name,
                command.publishTarget,
                default_target="pypi" if command.publish else None,
            )
            publish_snapshots = command.publishSnapshots if command.publishSnapshots is not None else False
            if publish_snapshots and publish_target != "maven-central":
                raise ValueError(f"Python project {name} cannot enable publishSnapshots for target {publish_target!r}")
            docs_enabled = command.docs if command.docs is not None else True
            docs_system = _normalize_docs_system(
                name,
                command.docsSystem,
                default_docs_system="mkdocs" if docs_enabled else None,
            )

            python_project = PythonProject(
                path=path,
                name=name,
                quarantine=command.quarantine,
                publish=command.publish,
                description=command.description,
                authors=command.authors or [],
                license=command.license,
                github_repo=_project_github_repo_for(command.repo, default_github_repo),
                ownership=ownership,
                requires_python=requires_python,
                dependencies=command.dependencies or [],
                dev_dependencies=command.dev_dependencies or [],
                scripts=legacy_scripts,
                application=application,
                homepage=command.homepage,
                repository=command.repository,
                keywords=command.keywords or [],
                classifiers=command.classifiers or [],
                version=Version.parse(command.version) if command.version else None,
                resolved_dependencies=[],
                project_id=project_id,
                repo_id=repo_id,
                repo_root=repo_root_path,
                managed_by_setup=managed_by_setup,
                copyright_holder=command.copyright_holder,
                copyright_year_start=command.copyright_year_start,
                publish_target=publish_target,
                publish_snapshots=publish_snapshots,
                docs_enabled=docs_enabled,
                docs_system=docs_system,
                test_license=command.testLicense,
            )
            verify_project(python_project)
            register_project(project_id, python_project)
            return project_id

        if isinstance(command, config_typed.PurescriptProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            name = _project_name_for(command.dir_name, command.name, repo_id)
            project_id = _project_id_for(command.dir_name, repo_id)
            purescript_project = PurescriptProject(
                path=_project_path_for(command.dir_name, repo_root_path),
                name=name,
                description=command.description,
                authors=command.authors or [],
                quarantine=command.quarantine,
                license=command.license,
                publish=command.publish,
                github_repo=_project_github_repo_for(command.repo, default_github_repo),
                ownership=ownership,
                version=Version.parse(command.version) if command.version else None,
                resolved_dependencies=[],
                project_id=project_id,
                repo_id=repo_id,
                repo_root=repo_root_path,
                managed_by_setup=managed_by_setup,
                copyright_holder=command.copyright_holder,
                copyright_year_start=command.copyright_year_start,
                test_license=command.testLicense,
            )
            verify_project(purescript_project)
            register_project(project_id, purescript_project)
            return project_id

        if isinstance(command, config_typed.DataProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            name = _project_name_for(command.dir_name, command.name, repo_id)
            project_id = _project_id_for(command.dir_name, repo_id)
            data_project = DataProject(
                path=_project_path_for(command.dir_name, repo_root_path),
                name=name,
                description=command.description,
                authors=command.authors or [],
                quarantine=command.quarantine,
                publish=command.publish,
                license=command.license,
                github_repo=_project_github_repo_for(command.repo, default_github_repo),
                ownership=ownership,
                version=Version.parse(command.version) if command.version else None,
                resolved_dependencies=[],
                project_id=project_id,
                repo_id=repo_id,
                repo_root=repo_root_path,
                managed_by_setup=managed_by_setup,
                copyright_holder=command.copyright_holder,
                copyright_year_start=command.copyright_year_start,
                test_license=command.testLicense,
                preserve_legal_files=command.preserveLegalFiles if command.preserveLegalFiles is not None else False,
            )
            verify_project(data_project)
            register_project(project_id, data_project)
            return project_id

        if isinstance(command, config_typed.PremakeProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            name = _project_name_for(command.dir_name, command.name, repo_id)
            project_id = _project_id_for(command.dir_name, repo_id)
            premake_project = PremakeProject(
                path=_project_path_for(command.dir_name, repo_root_path),
                name=name,
                description=command.description,
                authors=command.authors or [],
                github_repo=_project_github_repo_for(command.repo, default_github_repo),
                license=command.license,
                quarantine=command.quarantine,
                publish=command.publish,
                ownership=ownership,
                version=Version.parse(command.version) if command.version else None,
                resolved_dependencies=[],
                project_id=project_id,
                repo_id=repo_id,
                repo_root=repo_root_path,
                managed_by_setup=managed_by_setup,
                copyright_holder=command.copyright_holder,
                copyright_year_start=command.copyright_year_start,
                test_license=command.testLicense,
            )
            verify_project(premake_project)
            register_project(project_id, premake_project)
            return project_id

        if isinstance(command, config_typed.GradleProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            project_id = _project_id_for(command.dir_name, repo_id)
            path = _project_path_for(command.dir_name, repo_root_path)
            display_name = _project_name_for(command.dir_name, command.name, repo_id)
            raw_features = [_feature_from_command(item) for item in (command.features or [])]
            resolved_features = resolve_features(
                _with_default_gradle_plugins(raw_features, config.default_gradle_plugin_applications)
            )

            build_model = _normalize_gradle_build_model(
                display_name,
                command.buildModel,
                platforms=command.platforms,
                targets=command.targets,
                source_sets=command.sourceSets,
                source_set_dependencies=command.sourceSetDependencies,
            )

            normalized_targets = _normalize_gradle_targets(display_name, command.targets)
            if normalized_targets:
                platforms = _platforms_from_targets(normalized_targets)
            elif command.platforms is not None:
                platforms = _normalize_gradle_platforms(display_name, command.platforms)
                normalized_targets = _legacy_targets_from_platforms(platforms, resolved_features)
            elif build_model == "kmp":
                platforms = ["jvm"]
                normalized_targets = [GradleTargetSpec(kind="jvm")]
            else:
                platforms = ["jvm"]

            if build_model == "jvm" and any(platform != "jvm" for platform in platforms):
                raise ValueError(f"Gradle project {display_name} declares non-JVM targets but buildModel is jvm")

            raw_dependencies: list[str | Dependency | list[Dependency]] = []
            resolved_dependencies: list[Dependency] = []
            source_set_dependencies: dict[str, list[Dependency]] = {}
            source_sets: dict[str, GradleSourceSet] = {}

            if build_model == "kmp":
                if command.dependencies is not None:
                    raise ValueError(
                        f"Gradle project {display_name} in KMP mode must use :sourceSetDependencies instead of "
                        f":dependencies (or the newer :sourceSets form)"
                    )
                if command.sourceSets is not None and command.sourceSetDependencies is not None:
                    raise ValueError(
                        f"Gradle project {display_name} cannot define both :sourceSets and :sourceSetDependencies"
                    )

                if command.sourceSets is not None:
                    for source_set_name, source_set_command in command.sourceSets.items():
                        if not _is_valid_gradle_source_set_name(source_set_name):
                            raise ValueError(
                                f"Gradle project {display_name} has invalid source set {source_set_name!r}"
                            )
                        if (
                            source_set_name in CANONICAL_KMP_SOURCE_SET_REQUIREMENTS
                            and not _source_set_is_allowed_for_platforms(source_set_name, platforms)
                        ):
                            raise ValueError(
                                f"Gradle project {display_name} declares {source_set_name} but current targets do not support it"
                            )
                        parsed_dependencies = _parse_source_set_dependency_items(
                            display_name,
                            source_set_name,
                            source_set_command.dependencies or [],
                            current_repo_id=repo_id,
                        )
                        source_sets[source_set_name] = GradleSourceSet(
                            name=source_set_name,
                            depends_on=list(source_set_command.dependsOn or []),
                            dependencies=parsed_dependencies,
                            kotlin_src_dirs=list(source_set_command.kotlinSrcDirs or []),
                        )
                        source_set_dependencies[source_set_name] = parsed_dependencies
                        resolved_dependencies.extend(parsed_dependencies)
                elif command.sourceSetDependencies is not None:
                    assert command.sourceSetDependencies is not None
                    for source_set_name, source_set_items in command.sourceSetDependencies.items():
                        if source_set_name not in CANONICAL_KMP_SOURCE_SET_REQUIREMENTS:
                            supported_keys = ", ".join(CANONICAL_KMP_SOURCE_SET_REQUIREMENTS.keys())
                            raise ValueError(
                                f"Gradle project {display_name} has unsupported source set key {source_set_name!r}; "
                                f"supported keys: {supported_keys}"
                            )
                        if not _source_set_is_allowed_for_platforms(source_set_name, platforms):
                            raise ValueError(
                                f"Gradle project {display_name} declares {source_set_name} but :platforms={platforms} "
                                f"does not support it"
                            )
                        parsed_dependencies = _parse_source_set_dependency_items(
                            display_name,
                            source_set_name,
                            source_set_items,
                            current_repo_id=repo_id,
                        )
                        source_sets[source_set_name] = GradleSourceSet(
                            name=source_set_name,
                            depends_on=[],
                            dependencies=parsed_dependencies,
                            kotlin_src_dirs=[],
                        )
                        source_set_dependencies[source_set_name] = parsed_dependencies
                        resolved_dependencies.extend(parsed_dependencies)

                if not normalized_targets and build_model == "kmp":
                    feature_target = _android_library_target_from_features(resolved_features)
                    if feature_target is not None:
                        normalized_targets = [GradleTargetSpec(kind="jvm"), feature_target]
                        platforms = _platforms_from_targets(normalized_targets)

                for source_set_name, source_set in source_sets.items():
                    for parent_source_set in source_set.depends_on:
                        if (
                            parent_source_set not in source_sets
                            and parent_source_set not in CANONICAL_KMP_SOURCE_SET_REQUIREMENTS
                        ):
                            raise ValueError(
                                f"Gradle project {display_name}.{source_set_name} dependsOn unknown source set "
                                f"{parent_source_set}"
                            )
            else:
                if command.sourceSets is not None or command.sourceSetDependencies is not None:
                    raise ValueError(
                        f"Gradle project {display_name} is JVM-only and must use :dependencies instead of KMP source sets"
                    )
                for item in command.dependencies or []:
                    if isinstance(item, str):
                        raw_dependencies.append(item)
                        resolved_dependencies.extend(parse_gradle_dependency(item, current_repo_id=repo_id))
                    elif isinstance(item, config_typed.DepCall):
                        resolved = parse_gradle_dependency(item, current_repo_id=repo_id)
                        raw_dependencies.append(resolved)
                        resolved_dependencies.extend(resolved)
                    else:
                        raise TypeError(f"Unknown gradle dependency value: {item}")

            maven_repositories: list[MavenRepositoryDefinition] = []
            for dep in resolved_dependencies:
                if isinstance(dep.target, MavenDependencyTarget) and dep.target.maven_repo:
                    maven_repo = config.repositories[dep.target.maven_repo]
                    if maven_repo not in maven_repositories:
                        maven_repositories.append(maven_repo)

            default_group_name = config.default_maven_project_group
            if default_group_name is None:
                raise ValueError("default-maven-project-group must be configured for gradle projects")

            gradle_project_name = _gradle_project_name_for(command, project_id=project_id, repo_id=repo_id)
            artifact_id = _gradle_artifact_id_for(
                command,
                display_name=display_name,
                gradle_project_name=gradle_project_name,
                repo_id=repo_id,
            )
            build_inline_file = command.buildInlineFile.strip() if command.buildInlineFile is not None else None
            if build_inline_file == "":
                raise ValueError(f"Gradle project {display_name}.buildInlineFile must not be empty")
            if build_inline_file is not None and Path(build_inline_file).is_absolute():
                raise ValueError(f"Gradle project {display_name}.buildInlineFile must be a relative path")

            default_publish_target: str | None
            if not command.publish:
                default_publish_target = None
            elif "intellij-plugin" in resolved_features:
                default_publish_target = "jetbrains-marketplace"
            else:
                default_publish_target = "maven-central"
            publish_target = _normalize_publish_target(
                display_name,
                command.publishTarget,
                default_target=default_publish_target,
            )
            publish_snapshots = (
                command.publishSnapshots
                if command.publishSnapshots is not None
                else (publish_target == "maven-central")
            )
            if publish_snapshots and publish_target != "maven-central":
                raise ValueError(
                    f"Gradle project {display_name} cannot enable publishSnapshots for target {publish_target!r}"
                )
            github_repo = _project_github_repo_for(command.repo, default_github_repo)
            docs_enabled_default = github_repo is not None and not command.quarantine
            docs_enabled = command.docs if command.docs is not None else docs_enabled_default
            docs_system = _normalize_docs_system(
                display_name,
                command.docsSystem,
                default_docs_system="dokka" if docs_enabled else None,
            )

            gradle_project = GradleProject(
                path=path,
                group_name=default_group_name,
                name=display_name,
                version=Version.parse(command.version) if command.version else None,
                description=command.description,
                authors=command.authors or [],
                quarantine=command.quarantine,
                license=command.license,
                publish=command.publish,
                github_repo=github_repo,
                raw_dependencies=raw_dependencies,
                raw_features=raw_features,
                resolved_maven_repositories=maven_repositories,
                resolved_features=resolved_features,
                resolved_dependencies=resolved_dependencies,
                ownership=ownership,
                platforms=platforms,
                source_set_dependencies=source_set_dependencies,
                project_id=project_id,
                repo_id=repo_id,
                repo_root=repo_root_path,
                managed_by_setup=managed_by_setup,
                copyright_holder=command.copyright_holder,
                copyright_year_start=command.copyright_year_start,
                gradle_root=repo_root_path,
                module_dir=Path(command.dir_name),
                gradle_project_name=gradle_project_name,
                artifact_id=artifact_id,
                gradle_plugin_id=command.gradlePluginId,
                build_model=build_model,
                targets=normalized_targets,
                source_sets=source_sets,
                build_inline_file=build_inline_file,
                kotlin_free_compiler_args=list(command.kotlinFreeCompilerArgs or []),
                dokka_suppress_source_sets=list(command.dokkaSuppressSourceSets or []),
                jvm_policy=command.jvmPolicy or repo_jvm_policy,
                jvm_task_policies=dict(command.jvmTaskPolicies or {}),
                publish_target=publish_target,
                publish_snapshots=publish_snapshots,
                docs_enabled=docs_enabled,
                docs_system=docs_system,
                version_from_repo=command.versionFromRepo,
                test_license=command.testLicense,
            )
            verify_project(gradle_project)
            register_project(project_id, gradle_project)
            return project_id

        if isinstance(command, (config_typed.FsharpProjectCommand, config_typed.CsharpProjectCommand)):
            ownership = _coerce_ownership(command.ownership)
            path = _project_path_for(command.dir_name, repo_root_path)
            display_name = _project_name_for(command.dir_name, command.name, repo_id)
            project_id = _project_id_for(command.dir_name, repo_id)
            language: DotnetLanguage
            if isinstance(command, config_typed.FsharpProjectCommand):
                language = "fsharp"
            else:
                language = "csharp"

            project_kind = _normalize_dotnet_project_kind(display_name, command.projectKind)
            target_framework, target_frameworks = _normalize_dotnet_target_frameworks(
                display_name,
                target_framework=command.targetFramework,
                target_frameworks=command.targetFrameworks,
                default_target_framework=repo_default_target_framework,
            )
            publish_target = _normalize_publish_target(
                display_name,
                command.publishTarget,
                default_target="nuget" if command.publish else None,
            )
            publish_snapshots = command.publishSnapshots if command.publishSnapshots is not None else False
            if publish_snapshots:
                raise ValueError(f"{display_name} cannot enable publishSnapshots for NuGet publishing")
            github_repo = _project_github_repo_for(command.repo, default_github_repo)
            docs_enabled_default = github_repo is not None and not command.quarantine
            docs_enabled = command.docs if command.docs is not None else docs_enabled_default
            docs_system = _normalize_docs_system(
                display_name,
                command.docsSystem,
                default_docs_system="mkdocs" if docs_enabled else None,
            )
            resolved_dependencies = [
                parse_dotnet_dependency(item, current_repo_id=repo_id)
                for item in (command.dependencies or [])
            ]

            dotnet_project = DotnetProject(
                path=path,
                name=display_name,
                version=Version.parse(command.version) if command.version else None,
                description=command.description,
                authors=command.authors or [],
                license=command.license,
                quarantine=command.quarantine,
                publish=command.publish,
                github_repo=github_repo,
                ownership=ownership,
                resolved_dependencies=resolved_dependencies,
                language=language,
                project_kind=project_kind,
                sdk=command.sdk or "Microsoft.NET.Sdk",
                output_type=command.outputType,
                target_framework=target_framework,
                target_frameworks=target_frameworks,
                assembly_name=command.assemblyName,
                root_namespace=command.rootNamespace,
                package_id=command.packageId,
                package_tags=list(command.packageTags or []),
                generate_documentation_file=(
                    command.generateDocumentationFile if command.generateDocumentationFile is not None else True
                ),
                nullable=command.nullable,
                implicit_usings=command.implicitUsings,
                lang_version=command.langVersion,
                project_id=project_id,
                repo_id=repo_id,
                repo_root=repo_root_path,
                managed_by_setup=managed_by_setup,
                copyright_holder=command.copyright_holder,
                copyright_year_start=command.copyright_year_start,
                publish_target=publish_target,
                publish_snapshots=publish_snapshots,
                docs_enabled=docs_enabled,
                docs_system=docs_system,
                test_license=command.testLicense,
                packable=project_kind != "test",
            )
            verify_project(dotnet_project)
            register_project(project_id, dotnet_project)
            return project_id

        return None

    def _apply_builtin_command(command: config_typed.BuiltinTopLevelCommand) -> None:
        if isinstance(command, config_typed.ChecksDisableCommand):
            config.disabled_checks.append((command.error_name, command.pathspec))
            return

        if isinstance(command, config_typed.ChecksIgnoreFindingCommand):
            config.ignored_findings.append((command.error_name, command.pathspec, command.value))
            return

        if isinstance(command, config_typed.DefineCommand):
            defines[command.name] = command.value
            return

        if isinstance(command, config_typed.OpenaiKeyCommand):
            config.openai_key = command.key
            return

        if isinstance(command, config_typed.GithubTokenCommand):
            config.github_token = command.token
            return

        if isinstance(command, config_typed.GithubSshKeyCommand):
            config.github_ssh_key = command.key
            return

        if isinstance(command, config_typed.JitpackCookieCommand):
            config.jitpack_cookie = command.cookie
            return

        if isinstance(command, config_typed.DefineBackupTargetCommand):
            if command.name in config.backup_targets:
                raise ValueError(f"Backup target {command.name} already exists")
            if command.kind != "restic-sftp":
                raise ValueError(f"Unsupported backup target kind: {command.kind}")
            compression = command.compression or "auto"
            if compression not in {"auto", "off", "max"}:
                raise ValueError(f"Unsupported backup compression mode: {compression}")
            config.backup_targets[command.name] = BackupTarget(
                name=command.name,
                kind="restic-sftp",
                host=command.host,
                user=command.user,
                path=command.path,
                ssh_key=command.sshKey,
                password_file=command.passwordFile,
                password_command=command.passwordCommand,
                compression=compression,
            )
            return

        if isinstance(command, config_typed.BackupPolicyCommand):
            if not command.targets:
                raise ValueError("backup-policy.targets must not be empty")
            dirty_age_minutes = command.serviceDirtyAgeMinutes if command.serviceDirtyAgeMinutes is not None else 60
            min_interval_minutes = command.serviceMinIntervalMinutes if command.serviceMinIntervalMinutes is not None else 360
            if dirty_age_minutes < 0:
                raise ValueError("backup-policy.serviceDirtyAgeMinutes must be >= 0")
            if min_interval_minutes < 0:
                raise ValueError("backup-policy.serviceMinIntervalMinutes must be >= 0")
            config.backup_policy = BackupPolicy(
                target_names=tuple(command.targets),
                service_enabled=command.service if command.service is not None else True,
                service_dirty_age_minutes=dirty_age_minutes,
                service_min_interval_minutes=min_interval_minutes,
                include_git=command.includeGit if command.includeGit is not None else True,
                exclude=tuple(command.exclude or []),
                exclude_if_present=tuple(command.excludeIfPresent or []),
                exclude_caches=command.excludeCaches if command.excludeCaches is not None else True,
                include_repos=tuple(command.includeRepos or ["*"]),
                exclude_repos=tuple(command.excludeRepos or []),
            )
            return

        if isinstance(command, config_typed.AnthropicKeyCommand):
            config.anthropic_key = command.key
            return

        if isinstance(command, config_typed.JetbrainsMarketplaceTokenCommand):
            config.jetbrains_marketplace_token = command.token
            return

        if isinstance(command, config_typed.PypiTokenCommand):
            config.pypi_token = command.token
            return

        if isinstance(command, config_typed.NugetApiKeyCommand):
            config.nuget_api_key = command.token
            return

        if isinstance(command, config_typed.MavenUsernameCommand):
            config.maven_username = command.username
            return

        if isinstance(command, config_typed.MavenPasswordCommand):
            config.maven_password = command.password
            return

        if isinstance(command, config_typed.MavenGpgPrivateKeyCommand):
            config.maven_gpg_private_key = command.key
            return

        if isinstance(command, config_typed.MavenGpgPassphraseCommand):
            config.maven_gpg_passphrase = command.passphrase
            return

        if isinstance(command, config_typed.MavenGpgKeyIdCommand):
            config.maven_gpg_key_id = command.key_id
            return

        if isinstance(command, config_typed.DefaultMavenProjectGroupCommand):
            config.default_maven_project_group = command.group
            return

        if isinstance(command, config_typed.DefaultCompanyEmailCommand):
            config.default_company_email = command.email
            return

        if isinstance(command, config_typed.DefaultCompanyLegalNameCommand):
            config.default_company_legal_name = command.name
            return

        if isinstance(command, config_typed.DefaultCompanyShortNameCommand):
            config.default_company_short_name = command.name
            return

        if isinstance(command, config_typed.CodeOwnerCommand):
            config.default_code_owners.append(
                CodeOwner(
                    name=command.name,
                    email=command.email,
                )
            )
            return

        if isinstance(command, config_typed.GitUserCommand):
            config.default_git_user_name = command.name
            config.default_git_user_email = command.email
            return

        if isinstance(command, config_typed.GitCensorCommand):
            return

        if isinstance(command, config_typed.JvmVersionCommand):
            config.jvm_version = _coerce_jvm_version(command.version, "jvm-version")
            return

        if isinstance(command, config_typed.JvmDefaultsCommand):
            if command.version is not None:
                config.jvm_version = _coerce_jvm_version(command.version, "jvm-defaults.version")
            return

        if isinstance(command, config_typed.PythonDefaultsCommand):
            defaults = config.python_defaults
            if command.requires_python is not None:
                defaults.requires_python = command.requires_python
            if command.line_length is not None:
                defaults.line_length = command.line_length
            if command.coverage_fail_under is not None:
                defaults.coverage_fail_under = command.coverage_fail_under
            return

        if isinstance(command, config_typed.DefineMavenRepoCommand):
            config.repositories[command.name] = MavenRepositoryDefinition(command.name, command.url)
            return

        if isinstance(command, config_typed.DefineKotlinPluginCommand):
            if command.name in config.plugins:
                raise ValueError(f"Plugin {command.name} already exists")
            if command.value.startswith(":"):
                config.plugins[command.name] = KotlinPluginDefinition(
                    project=_normalize_project_reference(command.value, field_name=f"plugin {command.name}"),
                    repo=command.repo,
                    compiler_plugin=command.compilerPlugin,
                    compiler_plugin_id=command.compilerPluginId,
                )
                return
            if ":" not in command.value:
                raise ValueError(f"Invalid plugin definition: {command.value}")
            plugin_id, version = command.value.rsplit(":", 1)
            config.plugins[command.name] = KotlinPluginDefinition(
                plugin_id=plugin_id,
                version=version,
                repo=command.repo,
                compiler_plugin=command.compilerPlugin,
                compiler_plugin_id=command.compilerPluginId,
            )
            return

        if isinstance(command, config_typed.AddDefaultGradlePluginCommand):
            application = GradlePluginApplication(
                name=command.name,
                compilerOptions=dict(command.compilerOptions or {}),
            )
            if application not in config.default_gradle_plugin_applications:
                config.default_gradle_plugin_applications.append(application)
            return

        if isinstance(command, config_typed.DefineMavenLibraryCommand):
            if command.name in config.libraries:
                raise ValueError(f"Library {command.name} already exists")
            maven_urn = _render_maven_coordinate(command.maven_urn)
            if not is_valid_maven_coordinate(maven_urn):
                raise ValueError(f"Invalid Maven coordinate: {maven_urn}")
            coord = MavenCoordinate.parse(maven_urn)
            config.libraries[command.name] = MavenLibraryDefinition(
                command.name,
                coord,
                command.repo,
            )
            return

        if isinstance(command, config_typed.DefineMavenLibraryGroupCommand):
            if command.name in config.library_groups:
                raise ValueError(f"Library group {command.name} already exists")

            normalized_children: list[str | Dependency | list[Dependency]] = []
            for child in command.children:
                if isinstance(child, str):
                    if (
                        child in config.libraries
                        or child in config.library_groups
                        or is_valid_maven_coordinate(child)
                        or child.startswith((".", "/", ":"))
                    ):
                        normalized_children.append(child)
                        continue
                    raise ValueError(f"Unknown library/group in group {command.name}: {child}")

                if isinstance(child, config_typed.DepCall):
                    normalized_children.append(parse_gradle_dependency(child))
                    continue

                raise TypeError(f"Invalid group child in {command.name}: {child} ({type(child)})")

            config.library_groups[command.name] = normalized_children
            return

        project_command_id = _apply_project_command(
            command,
            repo_id=None,
            repo_root_path=None,
            default_github_repo=None,
            repo_jvm_policy=None,
            repo_dotnet_sdk_version=None,
            repo_default_target_framework=None,
            managed_by_setup=True,
        )
        if project_command_id is not None:
            return

        if isinstance(command, config_typed.RepoCommand):
            repo_id = command.dir_name
            if repo_id in config.defined_repos:
                raise ValueError(f"Repo {repo_id} already exists")
            repo_root_path = workspace_root / command.dir_name
            nested_project_ids: list[str] = []
            for nested_project in command.projects or []:
                nested_project_id = _apply_project_command(
                    nested_project,
                    repo_id=repo_id,
                    repo_root_path=repo_root_path,
                    default_github_repo=command.repo,
                    repo_jvm_policy=command.jvmPolicy,
                    repo_dotnet_sdk_version=command.dotnetSdkVersion,
                    repo_default_target_framework=command.defaultTargetFramework,
                    managed_by_setup=False,
                )
                if nested_project_id is None:
                    raise ValueError(f"Unsupported nested project type in repo {repo_id}: {type(nested_project)}")
                nested_project_ids.append(nested_project_id)

            docs_project_id: str | None = None
            if command.docsProject is not None:
                docs_project_id = _project_id_for(command.docsProject, repo_id)
                if docs_project_id not in nested_project_ids:
                    raise ValueError(
                        f"Repo {repo_id}.docsProject refers to unknown nested project {command.docsProject}"
                    )

            config.defined_repos[repo_id] = RepoDefinition(
                repo_id=repo_id,
                path=repo_root_path,
                github_repo=command.repo,
                gradle_root_project_name=command.gradleRootProjectName,
                jvm_policy=command.jvmPolicy,
                project_version=command.projectVersion,
                default_kotlin_version=command.defaultKotlinVersion,
                supported_kotlin_versions=list(command.supportedKotlinVersions or []),
                dotnet_sdk_version=command.dotnetSdkVersion,
                default_target_framework=command.defaultTargetFramework,
                solution_name=command.solutionName,
                use_central_package_management=bool(command.useCentralPackageManagement),
                docs_project_id=docs_project_id,
                project_ids=nested_project_ids,
            )
            return

        raise ValueError(f"Unknown builtin command: {type(command)}")

    def _is_builtin_command(command: object) -> TypeGuard[config_typed.BuiltinTopLevelCommand]:
        return isinstance(command, config_typed.BUILTIN_TOPLEVEL_COMMAND_TYPES)

    def _apply_command(command: object) -> None:
        command_handler = module_command_handlers.get(type(command))
        if command_handler is not None:
            command_handler(command)
            return
        if _is_builtin_command(command):
            _apply_builtin_command(command)
            return
        raise ValueError(f"Unknown command type: {type(command)}")

    def _decode_and_apply(doc: Document, source_name: str) -> None:
        for index, expr in enumerate(doc.exprs):
            path = f"{source_name}[{index}]"
            command = decode(expr, top_level_target, path=path)
            try:
                _apply_command(command)
            except TypeError:
                raise
            except DecodeError:
                raise
            except Exception as cause:
                raise DecodeError(
                    path=path,
                    expected=f"valid config command ({type(command).__name__})",
                    got=type(expr).__name__,
                    span=_extract_expr_span(expr),
                    cause=cause,
                ) from cause

    _decode_and_apply(root, "root")
    _decode_and_apply(root_private, "root.private")

    if config.backup_policy is not None:
        missing_targets = [
            target_name for target_name in config.backup_policy.target_names if target_name not in config.backup_targets
        ]
        if missing_targets:
            raise ValueError(f"backup-policy references undefined backup target(s): {', '.join(missing_targets)}")

    for project in config.defined_projects.values():
        if not isinstance(project, GradleProject):
            continue
        for application in get_gradle_plugin_applications(project):
            definition = config.plugins.get(application.name)
            if definition is None:
                raise ValueError(f"Gradle project {project.name} references unknown gradle-plugin {application.name}")
            plugin_id = resolve_kotlin_plugin_id(config, definition)
            if ":" in plugin_id:
                raise ValueError(
                    f"Gradle project {project.name} uses gradle-plugin {application.name}, "
                    f"but its definition must use plugin-id:version syntax"
                )
            if definition.repo is not None and definition.repo not in config.repositories:
                raise ValueError(
                    f"Gradle project {project.name} uses gradle-plugin {application.name}, "
                    f"but repo {definition.repo} is not defined"
                )

    return config
