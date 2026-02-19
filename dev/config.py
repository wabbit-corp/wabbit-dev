from typing import Any, Dict, List, Optional, Tuple, Union
from abc import ABC, abstractmethod
import dataclasses
from dataclasses import dataclass
from enum import Enum
from collections import OrderedDict

import re

import os
from pathlib import Path

from dev.maven import MavenCoordinate, is_valid_maven_coordinate
from dev.checks.base import CoarseFileScope, CoarseProjectType

from mu.types import SAtom, SStr, SDoc
from mu.parser import sexpr
from mu.exec import ExecutionContext, Quoted, eval_sexpr
from dev.base import Module

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
    raw: Quoted[SStr] | None
    major: int
    minor: int
    patch: int
    is_dev: bool

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}" + (
            "+dev-SNAPSHOT" if self.is_dev else ""
        )

    def next_major(self) -> "Version":
        return Version(None, self.major + 1, 0, 0, False)

    def next_minor(self) -> "Version":
        return Version(None, self.major, self.minor + 1, 0, False)

    def next_patch(self) -> "Version":
        return Version(None, self.major, self.minor, self.patch + 1, False)

    @classmethod
    def parse_or_null(cls, version: Quoted[SStr] | str) -> Union["Version", None]:
        value = version.value.value if isinstance(version, Quoted) else version
        match = re.match(r"(\d+)\.(\d+)\.(\d+)(\+dev-SNAPSHOT)?", value)
        if not match:
            return None

        major, minor, patch, is_dev = match.groups()
        return cls(version, int(major), int(minor), int(patch), bool(is_dev))

    @classmethod
    def parse(cls, version: Quoted[SStr] | str) -> "Version":
        result = cls.parse_or_null(version)
        assert (
            result is not None
        ), f"Invalid version: {version.value.value if isinstance(version, Quoted) else version}"
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

    def __eq__(self, other: Any) -> bool:
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

    def implied(self) -> List["Feature"]:
        return []


@dataclass
class Kotlin(Feature):
    __feature_name__ = "kotlin"


@dataclass
class Scala(Feature):
    __feature_name__ = "scala"


@dataclass
class Jvm(Feature):
    __feature_name__ = "jvm"
    jarName: Optional[str] = None


@dataclass
class ShadowJar(Feature):
    __feature_name__ = "shadow-jar"
    jarName: Optional[str] = None

    def implied(self) -> List[Feature]:
        return [Jvm()]


@dataclass
class JvmKotlinLibrary(Feature):
    __feature_name__ = "jvm-kotlin-library"

    def implied(self) -> List[Feature]:
        return [Kotlin(), Jvm()]


@dataclass
class JvmScalaLibrary(Feature):
    __feature_name__ = "jvm-scala-library"

    def implied(self) -> List[Feature]:
        return [Scala(), Jvm()]


def _normalize_jar_names(
    *, jar: str | None, shaded: str | None, unshaded: str | None
) -> tuple[str | None, str | None, str | None]:
    provided = sum(value is not None for value in (jar, shaded, unshaded))
    if provided > 1:
        raise ValueError(
            "Provide only one of jarName/shadedJarName/unshadedJarName"
        )

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
    jarName: Optional[str] = None
    shadedJarName: Optional[str] = None
    unshadedJarName: Optional[str] = None

    def __post_init__(self):
        self.jarName, self.shadedJarName, self.unshadedJarName = _normalize_jar_names(
            jar=self.jarName,
            shaded=self.shadedJarName,
            unshaded=self.unshadedJarName,
        )

    def implied(self) -> List[Feature]:
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

    def implied(self) -> List[Feature]:
        return [
            Kotlin(),
            Jvm(jarName=f"{self.name}-unshaded.jar"),
            ShadowJar(jarName=f"{self.name}.jar"),
        ]


@dataclass
class JvmKotlinAgent(Feature):
    __feature_name__ = "jvm-kotlin-agent"
    main: str
    jarName: Optional[str] = None
    shadedJarName: Optional[str] = None
    unshadedJarName: Optional[str] = None

    def __post_init__(self):
        self.jarName, self.shadedJarName, self.unshadedJarName = _normalize_jar_names(
            jar=self.jarName,
            shaded=self.shadedJarName,
            unshaded=self.unshadedJarName,
        )

    def implied(self) -> List[Feature]:
        return [
            Kotlin(),
            Jvm(jarName=self.unshadedJarName),
            ShadowJar(jarName=self.shadedJarName),
        ]

@dataclass
class IntellijPlugin(Feature):
    __feature_name__ = "intellij-plugin"
    pluginName: str

    def implied(self) -> List[Feature]:
        return [Kotlin(), Jvm()]


@dataclass
class KotlinSerialization(Feature):
    __feature_name__ = "kotlin-serialization"

    def implied(self) -> List[Feature]:
        return [Kotlin()]


@dataclass
class PythonDeptry(Feature):
    __feature_name__ = "python-deptry"
    package_map: Dict[str, str] = dataclasses.field(default_factory=dict)
    per_rule_ignores: Dict[str, List[str]] = dataclasses.field(default_factory=dict)
    auto_package_map: bool = False


@dataclass
class PythonImportLinter(Feature):
    __feature_name__ = "python-importlinter"
    root_packages: List[str] = dataclasses.field(default_factory=list)
    layers: List[str] = dataclasses.field(default_factory=list)


def _merge_feature(existing: Feature, incoming: Feature) -> Feature:
    if type(existing) is not type(incoming):
        raise TypeError(
            f"Cannot merge features with different types: {type(existing)} vs {type(incoming)}"
        )

    if dataclasses.is_dataclass(existing):
        merged_kwargs: Dict[str, Any] = {}
        for field in dataclasses.fields(existing):
            existing_value = getattr(existing, field.name)
            incoming_value = getattr(incoming, field.name)
            if existing_value is None and incoming_value is not None:
                merged_kwargs[field.name] = incoming_value
            elif incoming_value is None or existing_value == incoming_value:
                merged_kwargs[field.name] = existing_value
            else:
                raise ValueError(
                    f"Implied feature {type(existing).__feature_name__} conflicts on "
                    f"{field.name}: {existing_value} != {incoming_value}"
                )
        return type(existing)(**merged_kwargs)

    if existing != incoming:
        raise ValueError(
            f"Implied feature {type(existing).__feature_name__} conflicts: "
            f"{existing} != {incoming}"
        )
    return existing


def resolve_features(features: List[Feature]) -> Dict[str, Feature]:
    resolved_features: Dict[str, Feature] = {}
    queue: List[Feature] = []
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
    name: str
    version: str
    repo: str | None = None


@dataclass
class MavenRepositoryDefinition:
    name: str
    url: str


@dataclass
class MavenLibraryDefinition:
    name: str
    maven_urn: MavenCoordinate
    repo: str | None = None


# In general a dependency looks like:
#   scope@artifact
#   scope can be omitted, in which case it defaults to 'implementation'


class GradleDependencyScope(Enum):
    TEST = "test"
    API = "api"
    IMPLEMENTATION = "implementation"
    COMPILE_ONLY = "compileOnly"
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
        match self.target:
            case DependencyTarget.JarFile(path):
                return path.name
            case DependencyTarget.Project(project):
                return project
            case DependencyTarget.Maven(maven_repo, artifact):
                return artifact

    @property
    def is_subproject(self) -> bool:
        return isinstance(self.target, ProjectDependencyTarget)

    def __post_init__(self):
        assert (
            isinstance(self.scope, str) or self.scope is None
        ), f"Expected GradleDependencyScope or None, got {type(self.scope)}"
        assert isinstance(
            self.target, DependencyTarget
        ), f"Expected DependencyTarget, got {type(self.target)}"

    def __str__(self):
        return self.as_string()

    def as_string(self):
        modifier = self.scope
        if modifier is None:
            modifier = "implementation"

        match self.target:
            case DependencyTarget.JarFile(path):
                dirname = path.parent.as_posix() or "."
                basename = path.name

                escaped_dirname = dirname.replace("\\", "\\\\").replace('"', '\\"')
                escaped_basename = basename.replace("\\", "\\\\").replace('"', '\\"')

                return (
                    f'{modifier}(fileTree(mapOf("dir" to "{escaped_dirname}", '
                    f'"include" to listOf("{escaped_basename}"))))'
                )

            case DependencyTarget.Project(project):
                return f'{modifier}(project(":{project}"))'

            case DependencyTarget.Maven(maven_repo, artifact):
                # FIXME: repo is not used
                return f'{modifier}("{artifact}")'


class DependencyTarget:
    JarFile: type["JarFileDependencyTarget"] = None  # type: ignore
    Project: type["ProjectDependencyTarget"] = None  # type: ignore
    Maven: type["MavenDependencyTarget"] = None  # type: ignore


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

################################################################################
# Project base + Gradle/Python subtypes
################################################################################


class Project(ABC):
    path: Path
    name: str
    description: str | None
    authors: List[str]
    quarantine: bool
    publish: bool
    github_repo: str | None
    ownership: OwnershipType
    resolved_dependencies: List[Dependency]

    @abstractmethod
    def get_coarse_file_scope(self, path: Path) -> Optional[CoarseFileScope]:
        raise NotImplementedError(f"get_file_scope not implemented for {type(self)}")

    @property
    @abstractmethod
    def coarse_project_type(self) -> Optional[CoarseProjectType]:
        raise NotImplementedError(
            f"coarse_project_type not implemented for {type(self)}"
        )


@dataclass
class PythonDependency:
    """
    Simple container for Python dependency info: name, version spec, optional extras,
    a scope (main/dev/test), etc.
    """

    package: str
    version_spec: str | None = None
    scope: str = "main"  # or dev/test/extras?

    def __str__(self):
        if self.version_spec:
            return f"{self.package}{self.version_spec}"
        return self.package


@dataclass
class PythonSourceSet:
    path: str
    kind: str

    @property
    def is_test(self) -> bool:
        return self.kind == "test"


@dataclass
class PythonProject(Project):
    path: Path
    name: str
    version: Version | None
    description: str | None
    authors: List[str]
    license: str | None
    github_repo: str | None
    requires_python: str | None
    dependencies: List[str]
    dev_dependencies: List[str]
    scripts: List[str]
    raw_features: List[Feature]
    resolved_features: Dict[str, Feature]
    line_length: int | None
    target_version: str | None
    source_sets: List[PythonSourceSet]
    test_paths: List[str]
    ruff_per_file_ignores: Dict[str, List[str]]
    deptry_package_map: Dict[str, str]
    deptry_per_rule_ignores: Dict[str, List[str]]
    deptry_auto_map: bool
    importlinter_root_packages: List[str]
    importlinter_layers: List[str]
    importlinter_contracts: List[Dict[str, Any]]
    coverage_source: List[str]
    coverage_omit: List[str]
    coverage_fail_under: int | None
    coverage_precision: int | None
    coverage_branch: bool | None
    coverage_show_missing: bool | None
    coverage_skip_empty: bool | None
    coverage_xml_output: str | None
    quarantine: bool
    publish: bool
    ownership: OwnershipType

    # # Python dependencies in a raw user form vs. resolved objects
    # raw_dependencies: List[str]
    # resolved_python_dependencies: List[PythonDependency]

    resolved_dependencies: List[Dependency] = dataclasses.field(default_factory=list)
    # (We keep a list of `Dependency` too if you want to unify anything across projects,
    #  but typically a pure Python project won't rely on Gradle dependencies.)

    def get_coarse_file_scope(self, path: Path) -> Optional[CoarseFileScope]:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(
                f"Path {path} is not contained in project path {self.path}"
            )

        rel_path = path.relative_to(self.path)
        return None

    @property
    def coarse_project_type(self) -> Optional[CoarseProjectType]:
        return None


@dataclass
class PurescriptProject(Project):
    path: Path
    name: str
    description: str | None
    authors: List[str]
    quarantine: bool
    publish: bool
    license: str | None
    github_repo: str | None
    ownership: OwnershipType
    version: Version | None
    resolved_dependencies: List[Dependency]

    def get_coarse_file_scope(self, path: Path) -> Optional[CoarseFileScope]:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(
                f"Path {path} is not contained in project path {self.path}"
            )

        rel_path = path.relative_to(self.path)
        return None

    @property
    def coarse_project_type(self) -> Optional[CoarseProjectType]:
        return None


@dataclass
class PremakeProject(Project):
    path: Path
    name: str
    description: str | None
    authors: List[str]
    quarantine: bool
    publish: bool
    license: str | None
    github_repo: str | None
    ownership: OwnershipType
    version: Version | None
    resolved_dependencies: List[Dependency]

    def get_coarse_file_scope(self, path: Path) -> Optional[CoarseFileScope]:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(
                f"Path {path} is not contained in project path {self.path}"
            )

        rel_path = path.relative_to(self.path)
        return None

    @property
    def coarse_project_type(self) -> Optional[CoarseProjectType]:
        return None


@dataclass
class DataProject(Project):
    path: Path
    name: str
    description: str | None
    authors: List[str]
    quarantine: bool
    publish: bool
    license: str | None
    github_repo: str | None
    ownership: OwnershipType
    version: Version | None
    resolved_dependencies: List[Dependency]

    def get_coarse_file_scope(self, path: Path) -> Optional[CoarseFileScope]:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(
                f"Path {path} is not contained in project path {self.path}"
            )

        rel_path = path.relative_to(self.path)
        return None

    @property
    def coarse_project_type(self) -> Optional[CoarseProjectType]:
        return CoarseProjectType.DATA


@dataclass
class GradleProject(Project):
    path: Path
    group_name: str
    name: str
    version: Version | None
    description: str | None
    authors: List[str]
    license: str | None
    quarantine: bool
    publish: bool
    github_repo: str | None
    ownership: OwnershipType

    raw_dependencies: List[str | Dependency | List[Dependency]]
    raw_features: List[Feature]

    resolved_dependencies: List[Dependency]
    resolved_maven_repositories: List[MavenRepositoryDefinition]
    resolved_features: Dict[str, Feature]

    @property
    def artifact_name(self) -> str:
        if not self.group_name:
            raise ValueError(f"GradleProject {self.name} missing group_name")
        if not self.version:
            raise ValueError(f"GradleProject {self.name} missing version")
        return f"{self.group_name}:{self.name}:{self.version}"

    @property
    def coarse_project_type(self) -> Optional[CoarseProjectType]:
        return None

    def get_coarse_file_scope(self, path: Path) -> Optional[CoarseFileScope]:
        # Check that path is contained in the project path
        if not path.is_relative_to(self.path):
            raise ValueError(
                f"Path {path} is not contained in project path {self.path}"
            )

        rel_path = path.relative_to(self.path)

        if rel_path.as_posix().startswith("src/main/"):
            return CoarseFileScope.MAIN
        if rel_path.as_posix().startswith("src/test/"):
            return CoarseFileScope.TEST
        if rel_path.as_posix().startswith("build/"):
            return CoarseFileScope.BUILD_TEMP
        if rel_path.as_posix().startswith("kotlin-js-store/"):
            return CoarseFileScope.BUILD_TEMP


##################################################################################################
# Config
##################################################################################################

CONFIG_FILE = "root.clj"
CONFIG_PRIVATE_FILE = "root.private.clj"


@dataclass
class PythonDefaults:
    line_length: int | str | None = None
    target_version: str | None = None
    coverage_fail_under: int | str | None = None
    coverage_precision: int | str | None = None
    coverage_branch: bool | None = None
    coverage_show_missing: bool | None = None
    coverage_skip_empty: bool | None = None
    coverage_xml_output: str | None = None


def _coerce_jvm_version(value: int | str, field_name: str = "jvm_version") -> int:
    if isinstance(value, int):
        version = value
    elif isinstance(value, str):
        normalized = value.strip()
        if normalized == "1.8":
            version = 8
        elif re.fullmatch(r"\d+", normalized):
            version = int(normalized)
        else:
            raise ValueError(
                f"{field_name} must be an int or numeric string (e.g. 17, '21', '1.8')"
            )
    else:
        raise ValueError(
            f"{field_name} must be an int or numeric string, got {type(value)}"
        )

    if version < 8:
        raise ValueError(f"{field_name} must be >= 8")
    return version


@dataclass
class Config:
    raw: SDoc

    openai_key: str | None = None
    github_token: str | None = None
    anthropic_key: str | None = None
    jitpack_cookie: str | None = None

    default_maven_project_group: str | None = None
    default_git_user_email: str | None = None
    default_git_user_name: str | None = None

    repositories: OrderedDict[str, MavenRepositoryDefinition] = dataclasses.field(
        default_factory=OrderedDict
    )
    plugins: OrderedDict[str, KotlinPluginDefinition] = dataclasses.field(
        default_factory=OrderedDict
    )
    libraries: OrderedDict[str, MavenLibraryDefinition] = dataclasses.field(
        default_factory=OrderedDict
    )
    library_groups: OrderedDict[str, List[str | Dependency | List[Dependency]]] = dataclasses.field(
        default_factory=OrderedDict
    )
    defined_projects: OrderedDict[str, Project] = dataclasses.field(
        default_factory=OrderedDict
    )

    disabled_checks: List[Tuple[str, str]] = dataclasses.field(default_factory=list)

    modules: Dict[str, Module] = dataclasses.field(default_factory=dict)
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


def load_config() -> Config:
    with open(CONFIG_FILE, "rt", encoding="utf-8") as f:
        root = sexpr(f.read())
    with open(CONFIG_PRIVATE_FILE, "rt", encoding="utf-8") as f:
        root_private = sexpr(f.read())

    config = Config(raw=root)
    ctx = ExecutionContext()

    modules = Module.load_modules()
    for module in modules.values():
        module.register_script_commands(ctx)
    config.modules = modules

    ctx.env["true"] = True
    ctx.env["false"] = False
    ctx.env["null"] = None

    @ctx.register(name="checks/disable")
    def disable_check(error_name: str, pathspec: str):
        config.disabled_checks.append((error_name, pathspec))

    @ctx.register(name="define")
    def define(name: Quoted[SAtom], value: Any):
        assert isinstance(name.value, SAtom), f"Expected atom, got {type(name)}"
        # print(f"Defined {name.value} as {value}")
        ctx.env[name.value.value] = value

    @ctx.register(name="openai-key")
    def openai_key(key: str):
        config.openai_key = key

    @ctx.register(name="github-token")
    def github_token(token: str):
        config.github_token = token

    @ctx.register(name="jitpack-cookie")
    def jitpack_cookie(cookie: str):
        config.jitpack_cookie = cookie

    @ctx.register(name="default-maven-project-group")
    def default_maven_project_group(group: str):
        config.default_maven_project_group = group

    @ctx.register(name="git-user")
    def git_user(name: str, email: str):
        config.default_git_user_name = name
        config.default_git_user_email = email

    @ctx.register(name="git-censor")
    def git_censor(name: str | None = None, email: str | None = None):
        pass

    @ctx.register(name="anthropic-key")
    def anthropic_key(key: str):
        config.anthropic_key = key

    @ctx.register(name="jvm-version")
    def jvm_version(version: int | str):
        config.jvm_version = _coerce_jvm_version(version, "jvm-version")

    @ctx.register(name="jvm-defaults")
    def jvm_defaults(version: int | str | None = None):
        if version is not None:
            config.jvm_version = _coerce_jvm_version(version, "jvm-defaults.version")

    @ctx.register(name="jvm-kotlin-library")
    def jvm_kotlin_library() -> JvmKotlinLibrary:
        return JvmKotlinLibrary()

    @ctx.register(name="jvm-scala-library")
    def jvm_scala_library() -> JvmScalaLibrary:
        return JvmScalaLibrary()

    @ctx.register(name="jvm-kotlin-application")
    def jvm_kotlin_application(
        main: str, jar: str | None = None
    ) -> JvmKotlinApplication:
        return JvmKotlinApplication(main, jar)

    @ctx.register(name="paper-plugin")
    def paper_plugin(name: str, main: str, apiVersion: str) -> PaperPlugin:
        return PaperPlugin(main, name, apiVersion)

    @ctx.register(name="jvm-kotlin-agent")
    def jvm_kotlin_agent(main: str, jar: str | None = None) -> JvmKotlinAgent:
        return JvmKotlinAgent(main, jar)

    @ctx.register(name="intellij-plugin")
    def intellij_plugin(pluginName: str) -> IntellijPlugin:
        return IntellijPlugin(pluginName)

    @ctx.register(name="kotlin-serialization")
    def kotlin_serialization() -> KotlinSerialization:
        return KotlinSerialization()

    def _assert_no_unknown_kwargs(kwargs: Dict[str, Any], context: str) -> None:
        if kwargs:
            raise ValueError(
                f"Unknown {context} keyword arguments: {', '.join(sorted(kwargs.keys()))}"
            )

    def _assert_kebab_case_kwargs(
        raw_kwargs: Dict[str, Any],
        context: str,
        *,
        forbidden_prefixes: List[str] | None = None,
    ) -> None:
        invalid_keys: List[str] = []
        for raw_key in raw_kwargs.keys():
            if not isinstance(raw_key, str):
                raise ValueError(
                    f"Expected keyword argument name as string, got {type(raw_key)}"
                )
            if "_" in raw_key:
                invalid_keys.append(raw_key)
                continue
            if forbidden_prefixes and any(
                raw_key.startswith(prefix) for prefix in forbidden_prefixes
            ):
                invalid_keys.append(raw_key)
        if invalid_keys:
            raise ValueError(
                f"{context} keywords must be kebab-case without legacy prefixes: "
                + ", ".join(sorted(set(invalid_keys)))
            )

    @ctx.register(name="python-deptry")
    def python_deptry(**raw_kwargs: Any) -> PythonDeptry:
        _assert_kebab_case_kwargs(raw_kwargs, "python-deptry")
        kwargs = dict(raw_kwargs)
        package_map = kwargs.pop("package-map", {})
        per_rule_ignores = kwargs.pop("per-rule-ignores", {})
        auto_package_map = kwargs.pop("auto-package-map", False)
        _assert_no_unknown_kwargs(kwargs, "python-deptry")
        if package_map is None:
            package_map = {}
        if per_rule_ignores is None:
            per_rule_ignores = {}
        return PythonDeptry(
            package_map=package_map,
            per_rule_ignores=per_rule_ignores,
            auto_package_map=auto_package_map,
        )

    @ctx.register(name="python-importlinter")
    def python_importlinter(**raw_kwargs: Any) -> PythonImportLinter:
        _assert_kebab_case_kwargs(raw_kwargs, "python-importlinter")
        kwargs = dict(raw_kwargs)
        root_packages = kwargs.pop("root-packages", [])
        layers = kwargs.pop("layers", [])
        _assert_no_unknown_kwargs(kwargs, "python-importlinter")
        if root_packages is None:
            root_packages = []
        if layers is None:
            layers = []
        return PythonImportLinter(
            root_packages=root_packages,
            layers=layers,
        )

    @ctx.register(name="python-defaults")
    def python_defaults(**raw_kwargs: Any) -> None:
        _assert_kebab_case_kwargs(raw_kwargs, "python-defaults")
        kwargs = dict(raw_kwargs)
        line_length = kwargs.pop("line-length", None)
        target_version = kwargs.pop("target-version", None)
        coverage_fail_under = kwargs.pop("coverage-fail-under", None)
        coverage_precision = kwargs.pop("coverage-precision", None)
        coverage_branch = kwargs.pop("coverage-branch", None)
        coverage_show_missing = kwargs.pop("coverage-show-missing", None)
        coverage_skip_empty = kwargs.pop("coverage-skip-empty", None)
        coverage_xml_output = kwargs.pop("coverage-xml-output", None)
        _assert_no_unknown_kwargs(kwargs, "python-defaults")
        defaults = config.python_defaults
        if line_length is not None:
            defaults.line_length = line_length
        if target_version is not None:
            defaults.target_version = target_version
        if coverage_fail_under is not None:
            defaults.coverage_fail_under = coverage_fail_under
        if coverage_precision is not None:
            defaults.coverage_precision = coverage_precision
        if coverage_branch is not None:
            defaults.coverage_branch = coverage_branch
        if coverage_show_missing is not None:
            defaults.coverage_show_missing = coverage_show_missing
        if coverage_skip_empty is not None:
            defaults.coverage_skip_empty = coverage_skip_empty
        if coverage_xml_output is not None:
            defaults.coverage_xml_output = coverage_xml_output

    ###############################################################################################
    # Dependencies
    ###############################################################################################

    @ctx.register(name="define-maven-repo")
    def maven_repository(name: str, url: str):
        config.repositories[name] = MavenRepositoryDefinition(name, url)

    @ctx.register(name="define-kotlin-plugin")
    def plugin_dep(name: str, value: str, repo: str | None = None):
        assert isinstance(name, str), f"Expected string, got {type(name)}"
        assert isinstance(value, str), f"Expected string, got {type(value)}"
        assert (
            isinstance(repo, str) or repo is None
        ), f"Expected string or None, got {type(repo)}"
        assert name not in config.plugins, f"Plugin {name} already exists"
        assert ":" in value, f"Invalid plugin definition: {value}"
        artifact_name, version = value.rsplit(":", 1)
        config.plugins[name] = KotlinPluginDefinition(artifact_name, version, repo)

    @ctx.register(name="define-maven-library")
    def library(name: str, maven_urn: str, repo: str | None = None) -> None:
        assert isinstance(name, str), f"Expected string, got {type(name)}"
        assert isinstance(maven_urn, str), f"Expected string, got {type(maven_urn)}"
        assert is_valid_maven_coordinate(
            maven_urn
        ), f"Invalid Maven coordinate: {maven_urn}"
        assert name not in config.libraries, f"Library {name} already exists"
        coord = MavenCoordinate.parse(maven_urn)
        config.libraries[name] = MavenLibraryDefinition(name, coord, repo)

    @ctx.register(name="define-maven-library-group")
    def library_group(
        name: str, children: List[str | Dependency | List[Dependency]]
    ) -> None:
        if not isinstance(name, str):
            raise TypeError(f"Expected string, got {type(name)}")
        if name in config.library_groups:
            raise ValueError(f"Library group {name} already exists")
        if not isinstance(children, list):
            raise TypeError(f"Expected list of libraries, got {type(children)}")

        for child in children:
            if isinstance(child, str):
                if (
                    child in config.libraries
                    or child in config.library_groups
                    or is_valid_maven_coordinate(child)
                    or child.startswith((".", "/", ":"))
                ):
                    continue
                raise ValueError(f"Unknown library/group in group {name}: {child}")
            if isinstance(child, Dependency):
                continue
            if isinstance(child, list) and all(
                isinstance(item, Dependency) for item in child
            ):
                continue
            raise TypeError(
                f"Invalid group child in {name}: {child} ({type(child)})"
            )

        config.library_groups[name] = children

    def parse_gradle_dependency(
        dep: str | Dependency, modifier: str | None = None
    ) -> List[Dependency]:
        if isinstance(dep, Dependency):
            return [dep]

        if isinstance(dep, list):
            result = []
            for item in dep:
                if isinstance(item, str):
                    result.extend(parse_gradle_dependency(item, modifier))
                elif isinstance(item, Dependency):
                    result.append(item)
                else:
                    raise ValueError(f"Unknown dependency type: {item}")
            return result

        assert isinstance(dep, str), f"Expected string or Dependency, got {type(dep)}"

        if modifier is not None:
            assert modifier in [
                "test",
                "implementation",
                "api",
                "compileOnly",
                "runtimeOnly",
                "testImplementation",
                "testCompileOnly",
                "testRuntimeOnly",
            ], f"Unknown modifier: {modifier}"

        if dep.startswith(".") or dep.startswith("/"):
            path = Path(dep)
            # FIXME: Check if file exists
            # assert path.exists(), f"File {path} does not exist"
            return [
                Dependency(scope=modifier, target=JarFileDependencyTarget(path=path))
            ]

        if dep.startswith(":"):
            project_name = dep[1:]
            assert (
                project_name in config.defined_projects
            ), f"Project {project_name} is not defined"
            return [
                Dependency(
                    scope=modifier, target=ProjectDependencyTarget(project=project_name)
                )
            ]

        if dep in config.library_groups:
            result = []
            for lib in config.library_groups[dep]:
                result.extend(parse_gradle_dependency(lib, modifier))
            return result

        if dep in config.libraries:
            maven_urn = config.libraries[dep].maven_urn.__str__()
            maven_repo = config.libraries[dep].repo
            return [
                Dependency(
                    scope=modifier,
                    target=MavenDependencyTarget(
                        artifact=maven_urn, maven_repo=maven_repo
                    ),
                )
            ]

        if is_valid_maven_coordinate(dep):
            return [
                Dependency(scope=modifier, target=MavenDependencyTarget(artifact=dep))
            ]

        raise ValueError(f"Unknown library or library group: {dep}")

    @ctx.register(name="dep")
    def dep(name: str, modifier: str | None = None) -> List[Dependency]:
        if modifier is not None:
            assert isinstance(modifier, str), f"Expected string, got {type(modifier)}"
            assert modifier in [
                "test",
                "implementation",
                "api",
                "compileOnly",
                "runtimeOnly",
                "testImplementation",
                "testCompileOnly",
                "testRuntimeOnly",
            ], f"Unknown modifier: {modifier}"
        return parse_gradle_dependency(name, modifier)

    ###############################################################################################
    # Projects
    ###############################################################################################

    def _coerce_int(value: int | str | None, field_name: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
            return int(value)
        raise ValueError(f"{field_name} must be an int or numeric string")

    def _parse_python_source_sets(
        raw_sets: List[Any] | None,
    ) -> List[PythonSourceSet]:
        if not raw_sets:
            return []
        parsed: List[PythonSourceSet] = []
        for item in raw_sets:
            if isinstance(item, str):
                parsed.append(PythonSourceSet(path=item, kind="main"))
                continue
            if isinstance(item, dict):
                path = item.get("path") or item.get("dir") or item.get("root")
                if not path:
                    raise ValueError("python source set missing path")
                kind = item.get("kind") or item.get("type")
                if kind is None and "test" in item:
                    kind = "test" if item.get("test") else "main"
                if kind is None:
                    kind = "main"
                kind = str(kind)
                if kind not in {"main", "test"}:
                    raise ValueError(f"Unknown python source set kind: {kind}")
                parsed.append(PythonSourceSet(path=str(path), kind=kind))
                continue
            raise ValueError(f"Invalid python source set entry: {item}")
        return parsed

    def verify_project(project: Project) -> None:
        def is_publishable(project: Project) -> bool:
            return (
                project.publish
                and project.github_repo is not None
                and (not project.quarantine)
            )

        # Verify that IF there is a github_repo (project is publishable),
        # then ALL projects in the dependency chain are also publishable.
        for dep in project.resolved_dependencies:
            if isinstance(dep.target, ProjectDependencyTarget):
                dep_project = config.defined_projects[dep.target.project]
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

    @ctx.register(name="python")
    def python_project(
        dir_name: str,
        version: Quoted[SStr],
        **raw_kwargs: Any,
    ) -> None:
        _assert_kebab_case_kwargs(
            raw_kwargs,
            "python project",
            forbidden_prefixes=["python-"],
        )
        kwargs = dict(raw_kwargs)
        name = kwargs.pop("name", None)
        description = kwargs.pop("description", None)
        authors = kwargs.pop("authors", None)
        license = kwargs.pop("license", "AGPL")
        quarantine = kwargs.pop("quarantine", False)
        publish = kwargs.pop("publish", True)
        requires_python = kwargs.pop("requires-python", None)
        dependencies = kwargs.pop("dependencies", None)
        dev_dependencies = kwargs.pop("dev-dependencies", None)
        scripts = kwargs.pop("scripts", None)
        features = kwargs.pop("features", None)
        source_sets = kwargs.pop("source-sets", None)
        line_length_input = kwargs.pop("line-length", None)
        target_version = kwargs.pop("target-version", None)
        test_paths = kwargs.pop("test-paths", None)
        ruff_per_file_ignores = kwargs.pop("ruff-per-file-ignores", None)
        deptry_package_map_input = kwargs.pop("deptry-package-map", None)
        deptry_per_rule_ignores_input = kwargs.pop("deptry-per-rule-ignores", None)
        importlinter_root_packages_input = kwargs.pop(
            "importlinter-root-packages", None
        )
        importlinter_contracts = kwargs.pop("importlinter-contracts", None)
        coverage_source = kwargs.pop("coverage-source", None)
        coverage_omit = kwargs.pop("coverage-omit", None)
        coverage_fail_under_input = kwargs.pop("coverage-fail-under", None)
        coverage_precision_input = kwargs.pop("coverage-precision", None)
        coverage_branch = kwargs.pop("coverage-branch", None)
        coverage_show_missing = kwargs.pop("coverage-show-missing", None)
        coverage_skip_empty = kwargs.pop("coverage-skip-empty", None)
        coverage_xml_output = kwargs.pop("coverage-xml-output", None)
        repo = kwargs.pop("repo", None)
        ownership = kwargs.pop("ownership", OwnershipType.WABBIT)
        _assert_no_unknown_kwargs(kwargs, "python project")

        if isinstance(ownership, str):
            ownership = OwnershipType(ownership)

        path = Path(f"./{dir_name}")
        name = name or dir_name
        resolved_features = resolve_features(features or [])
        defaults = config.python_defaults
        line_length = (
            _coerce_int(line_length_input, "line-length")
            if line_length_input is not None
            else _coerce_int(defaults.line_length, "python-defaults.line-length")
        )
        coverage_fail_under = (
            _coerce_int(coverage_fail_under_input, "coverage-fail-under")
            if coverage_fail_under_input is not None
            else _coerce_int(
                defaults.coverage_fail_under, "python-defaults.coverage-fail-under"
            )
        )
        coverage_precision = (
            _coerce_int(coverage_precision_input, "coverage-precision")
            if coverage_precision_input is not None
            else _coerce_int(
                defaults.coverage_precision, "python-defaults.coverage-precision"
            )
        )

        deptry_feature = resolved_features.get("python-deptry")
        deptry_package_map = deptry_package_map_input or {}
        deptry_per_rule_ignores = deptry_per_rule_ignores_input or {}
        deptry_auto_map = False
        if isinstance(deptry_feature, PythonDeptry):
            deptry_package_map = {
                **deptry_feature.package_map,
                **deptry_package_map,
            }
            deptry_per_rule_ignores = {
                **deptry_feature.per_rule_ignores,
                **deptry_per_rule_ignores,
            }
            deptry_auto_map = deptry_feature.auto_package_map

        importlinter_feature = resolved_features.get("python-importlinter")
        importlinter_root_packages = importlinter_root_packages_input or []
        importlinter_layers: List[str] = []
        if isinstance(importlinter_feature, PythonImportLinter):
            if importlinter_feature.root_packages:
                importlinter_root_packages = importlinter_feature.root_packages
            importlinter_layers = importlinter_feature.layers or []

        parsed_source_sets = _parse_python_source_sets(source_sets)
        project_obj = PythonProject(
            path=path,
            name=name,
            quarantine=quarantine,
            publish=publish,
            description=description,
            authors=authors or [],
            license=license,
            github_repo=repo,
            ownership=ownership,
            requires_python=requires_python,
            dependencies=dependencies or [],
            dev_dependencies=dev_dependencies or [],
            scripts=scripts or [],
            raw_features=features or [],
            resolved_features=resolved_features,
            line_length=line_length,
            target_version=target_version or defaults.target_version,
            source_sets=parsed_source_sets,
            test_paths=test_paths or [],
            ruff_per_file_ignores=ruff_per_file_ignores or {},
            deptry_package_map=deptry_package_map,
            deptry_per_rule_ignores=deptry_per_rule_ignores,
            deptry_auto_map=deptry_auto_map,
            importlinter_root_packages=importlinter_root_packages,
            importlinter_layers=importlinter_layers,
            importlinter_contracts=importlinter_contracts or [],
            coverage_source=coverage_source or [],
            coverage_omit=coverage_omit or [],
            coverage_fail_under=coverage_fail_under,
            coverage_precision=coverage_precision,
            coverage_branch=(
                coverage_branch
                if coverage_branch is not None
                else defaults.coverage_branch
            ),
            coverage_show_missing=(
                coverage_show_missing
                if coverage_show_missing is not None
                else defaults.coverage_show_missing
            ),
            coverage_skip_empty=(
                coverage_skip_empty
                if coverage_skip_empty is not None
                else defaults.coverage_skip_empty
            ),
            coverage_xml_output=(
                coverage_xml_output or defaults.coverage_xml_output
            ),
            version=Version.parse(version) if version else None,
            resolved_dependencies=[],
        )
        verify_project(project_obj)
        config.defined_projects[name] = project_obj

    @ctx.register(name="purescript")
    def purescript_project(
        dir_name: str,
        version: Quoted[SStr],
        name: Optional[str] = None,
        description: str | None = None,
        authors: List[str] | None = None,
        quarantine: bool = False,
        license: str | None = "AGPL",
        publish: bool = True,
        repo: str | None = None,
        ownership: OwnershipType = OwnershipType.WABBIT,
    ) -> None:
        path = Path(f"./{dir_name}")
        name = name or dir_name
        project_obj = PurescriptProject(
            path=path,
            name=name,
            description=description,
            authors=authors or [],
            quarantine=quarantine,
            license=license,
            publish=publish,
            github_repo=repo,
            ownership=ownership,
            version=Version.parse(version) if version else None,
            resolved_dependencies=[],
        )
        verify_project(project_obj)
        config.defined_projects[name] = project_obj

    @ctx.register(name="data")
    def data_project(
        dir_name: str,
        version: Quoted[SStr],
        name: Optional[str] = None,
        description: str | None = None,
        authors: List[str] | None = None,
        license: str | None = "AGPL",
        quarantine: bool = False,
        publish: bool = True,
        repo: str | None = None,
        ownership: OwnershipType = OwnershipType.WABBIT,
    ) -> None:
        path = Path(f"./{dir_name}")
        name = name or dir_name
        project_obj = DataProject(
            path=path,
            name=name,
            description=description,
            authors=authors or [],
            quarantine=quarantine,
            publish=publish,
            license=license,
            github_repo=repo,
            ownership=ownership,
            version=Version.parse(version) if version else None,
            resolved_dependencies=[],
        )
        verify_project(project_obj)
        config.defined_projects[name] = project_obj

    @ctx.register(name="premake")
    def premake_project(
        dir_name: str,
        version: Quoted[SStr],
        name: Optional[str] = None,
        description: str | None = None,
        authors: List[str] | None = None,
        license: str | None = "AGPL",
        quarantine: bool = False,
        publish: bool = True,
        repo: str | None = None,
        ownership: OwnershipType = OwnershipType.WABBIT,
    ) -> None:
        path = Path(f"./{dir_name}")
        name = name or dir_name
        project_obj = PremakeProject(
            path=path,
            name=name,
            description=description,
            authors=authors or [],
            github_repo=repo,
            license=license,
            quarantine=quarantine,
            publish=publish,
            ownership=ownership,
            version=Version.parse(version) if version else None,
            resolved_dependencies=[],
        )
        verify_project(project_obj)
        config.defined_projects[name] = project_obj

    @ctx.register(name="gradle")
    def gradle_project(
        dir_name: str,
        version: Quoted[SStr],
        name: Optional[str] = None,
        description: str | None = None,
        authors: List[str] | None = None,
        license: str | None = "AGPL",
        quarantine: bool = False,
        publish: bool = True,
        dependencies: (
            List[str | DependencyTarget | List[DependencyTarget]] | None
        ) = None,
        features: List[Feature] | None = None,
        repo: str | None = None,
        ownership: OwnershipType = OwnershipType.WABBIT,
    ) -> None:
        # This makes no sense from typechecking perspective, but it's necessary since we're using eval_sexpr
        if isinstance(ownership, str):
            ownership = OwnershipType(ownership)

        name = name or dir_name

        # assert repo is not None, f"Repository is required for Gradle project {name}"

        resolved_features = resolve_features(features or [])

        raw_dependencies: List[str | DependencyTarget | List[DependencyTarget]] = (
            dependencies or []
        )
        resolved_dependencies: List[DependencyTarget] = []
        for dep in raw_dependencies:
            if isinstance(dep, list):
                resolved_dependencies.extend(dep)
            elif isinstance(dep, str):
                resolved_dependencies.extend(parse_gradle_dependency(dep))
            else:
                assert isinstance(
                    dep, DependencyTarget
                ), f"Expected string or Dependency, got {type(dep)}"
                resolved_dependencies.append(dep)

        maven_repositories: List[MavenRepositoryDefinition] = []
        for dep in resolved_dependencies:
            if isinstance(dep.target, MavenDependencyTarget) and dep.target.maven_repo:
                maven_repo = config.repositories[dep.target.maven_repo]
                if maven_repo not in maven_repositories:
                    maven_repositories.append(maven_repo)

        project_obj = GradleProject(
            path=Path(f"./{dir_name}"),
            group_name=config.default_maven_project_group,
            name=name,
            version=Version.parse(version) if version else None,
            description=description,
            authors=authors or [],
            quarantine=quarantine,
            license=license,
            publish=publish,
            github_repo=repo,
            raw_dependencies=raw_dependencies,
            raw_features=features or [],
            resolved_maven_repositories=maven_repositories,
            resolved_features=resolved_features,
            resolved_dependencies=resolved_dependencies,
            ownership=ownership,
        )

        verify_project(project_obj)

        config.defined_projects[name] = project_obj

    eval_sexpr(ctx, root, ignore_toplevel_exceptions=True)
    eval_sexpr(ctx, root_private, ignore_toplevel_exceptions=True)

    return config
