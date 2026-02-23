import dataclasses
import os
import re
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Union

from mu.exec import Quoted
from mu.parser import sexpr
from mu.typed import MuDecodeError, decode_expr
from mu.types import SAtom, SDoc, SStr

import dev.config_typed as config_typed
from dev.base import Module
from dev.checks.base import CoarseFileScope, CoarseProjectType
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
    raw: Quoted[SStr] | None
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
    def parse_or_null(cls, version: Quoted[SStr] | str) -> Union["Version", None]:
        value = version.value.value if isinstance(version, Quoted) else version
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(\+dev-SNAPSHOT)?", value.strip())
        if not match:
            return None

        major, minor, patch, is_dev = match.groups()
        return cls(version, int(major), int(minor), int(patch), bool(is_dev))

    @classmethod
    def parse(cls, version: Quoted[SStr] | str) -> "Version":
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

    def implied(self) -> list["Feature"]:
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

    def __post_init__(self):
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

    def __post_init__(self):
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

    def implied(self) -> list[Feature]:
        return [Kotlin(), Jvm()]


@dataclass
class KotlinSerialization(Feature):
    __feature_name__ = "kotlin-serialization"

    def implied(self) -> list[Feature]:
        return [Kotlin()]


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

    if dataclasses.is_dataclass(existing):
        merged_kwargs: dict[str, Any] = {}
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
        raise ValueError(f"Implied feature {type(existing).__feature_name__} conflicts: " f"{existing} != {incoming}")
    return existing


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
            case DependencyTarget.Maven(_maven_repo, artifact):
                return artifact

    @property
    def is_subproject(self) -> bool:
        return isinstance(self.target, ProjectDependencyTarget)

    def __post_init__(self):
        assert (
            isinstance(self.scope, str) or self.scope is None
        ), f"Expected GradleDependencyScope or None, got {type(self.scope)}"
        assert isinstance(self.target, DependencyTarget), f"Expected DependencyTarget, got {type(self.target)}"

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

            case DependencyTarget.Maven(_maven_repo, artifact):
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
    authors: list[str]
    quarantine: bool
    publish: bool
    github_repo: str | None
    ownership: OwnershipType
    resolved_dependencies: list[Dependency]

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
    authors: list[str]
    license: str | None
    github_repo: str | None
    requires_python: str | None
    dependencies: list[str]
    dev_dependencies: list[str]
    scripts: list[str]
    raw_features: list[Feature]
    resolved_features: dict[str, Feature]
    line_length: int | None
    target_version: str | None
    source_sets: list[PythonSourceSet]
    test_paths: list[str]
    ruff_per_file_ignores: dict[str, list[str]]
    deptry_package_map: dict[str, str]
    deptry_per_rule_ignores: dict[str, list[str]]
    deptry_auto_map: bool
    importlinter_root_packages: list[str]
    importlinter_layers: list[str]
    importlinter_contracts: list[dict[str, Any]]
    coverage_source: list[str]
    coverage_omit: list[str]
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

    resolved_dependencies: list[Dependency] = dataclasses.field(default_factory=list)
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

    @property
    def artifact_name(self) -> str:
        if not self.group_name:
            raise ValueError(f"GradleProject {self.name} missing group_name")
        if not self.version:
            raise ValueError(f"GradleProject {self.name} missing version")
        return f"{self.group_name}:{self.name}:{self.version}"

    @property
    def coarse_project_type(self) -> CoarseProjectType | None:
        return None

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
            raise ValueError(f"{field_name} must be an int or numeric string (e.g. 17, '21', '1.8')")
    else:
        raise ValueError(f"{field_name} must be an int or numeric string, got {type(value)}")

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

    repositories: OrderedDict[str, MavenRepositoryDefinition] = dataclasses.field(default_factory=OrderedDict)
    plugins: OrderedDict[str, KotlinPluginDefinition] = dataclasses.field(default_factory=OrderedDict)
    libraries: OrderedDict[str, MavenLibraryDefinition] = dataclasses.field(default_factory=OrderedDict)
    library_groups: OrderedDict[str, list[str | Dependency | list[Dependency]]] = dataclasses.field(
        default_factory=OrderedDict
    )
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


def load_config() -> Config:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        root = sexpr(f.read(), no_spans=False)
    with open(CONFIG_PRIVATE_FILE, encoding="utf-8") as f:
        root_private = sexpr(f.read(), no_spans=False)

    config = Config(raw=root)

    modules = Module.load_modules()
    config.modules = modules

    module_command_handlers: dict[type[Any], Any] = {}
    module_command_types: list[type[Any]] = []
    for module in modules.values():
        for registration in module.register_typed_config_commands():
            if registration.command_type in module_command_handlers:
                raise ValueError(f"Duplicate typed config command registration for " f"{registration.command_type}")
            module_command_handlers[registration.command_type] = registration.apply
            module_command_types.append(registration.command_type)

    top_level_target = config_typed.make_top_level_target(module_command_types)
    defines: dict[str, Any] = {}

    def _extract_expr_span(expr: Any) -> Any | None:
        if isinstance(expr, (SAtom, SStr)):
            span = expr.span
            if span is None:
                return None
            token = getattr(span, "token", None)
            return token if token is not None else span

        for attr in ("open_bracket", "span"):
            value = getattr(expr, attr, None)
            if value is None:
                continue
            token = getattr(value, "token", None)
            return token if token is not None else value
        return None

    def _coerce_int(value: int | str | None, field_name: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
            return int(value)
        raise ValueError(f"{field_name} must be an int or numeric string")

    def _parse_python_source_sets(
        raw_sets: list[Any] | None,
    ) -> list[PythonSourceSet]:
        if not raw_sets:
            return []
        parsed: list[PythonSourceSet] = []
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

    def _coerce_ownership(value: str | None) -> OwnershipType:
        if value is None:
            return OwnershipType.WABBIT
        return OwnershipType(value)

    def _resolve_maven_version(value: config_typed.Value[str]) -> str:
        if isinstance(value, config_typed.Const):
            return value.value
        if isinstance(value, config_typed.VarName):
            if value.name not in defines:
                raise ValueError(f"Undefined variable referenced in maven version: {value.name}")
            resolved = defines[value.name]
            if not isinstance(resolved, str):
                raise ValueError(f"Maven version variable {value.name} must resolve to string, got {type(resolved)}")
            return resolved
        raise TypeError(f"Unknown maven version value: {value}")

    def _render_maven_coordinate(expr: config_typed.MavenCoordinateExpr) -> str:
        version_value = _resolve_maven_version(expr.version)
        rendered = f"{expr.group_id}:{expr.artifact_id}:{version_value}"
        if expr.suffix:
            rendered = f"{rendered}:{expr.suffix}"
        return rendered

    def _feature_from_command(command: config_typed.FeatureCommand) -> Feature:
        if isinstance(command, config_typed.JvmKotlinLibraryCommand):
            return JvmKotlinLibrary()
        if isinstance(command, config_typed.JvmScalaLibraryCommand):
            return JvmScalaLibrary()
        if isinstance(command, config_typed.JvmKotlinApplicationCommand):
            return JvmKotlinApplication(command.main, command.jar)
        if isinstance(command, config_typed.PaperPluginCommand):
            return PaperPlugin(command.main, command.name, command.apiVersion)
        if isinstance(command, config_typed.JvmKotlinAgentCommand):
            return JvmKotlinAgent(command.main, command.jar)
        if isinstance(command, config_typed.IntellijPluginCommand):
            return IntellijPlugin(command.pluginName)
        if isinstance(command, config_typed.KotlinSerializationCommand):
            return KotlinSerialization()
        if isinstance(command, config_typed.PythonDeptryCommand):
            return PythonDeptry(
                package_map=command.package_map or {},
                per_rule_ignores=command.per_rule_ignores or {},
                auto_package_map=command.auto_package_map,
            )
        if isinstance(command, config_typed.PythonImportlinterCommand):
            return PythonImportLinter(
                root_packages=command.root_packages or [],
                layers=command.layers or [],
            )
        raise TypeError(f"Unknown feature command: {type(command)}")

    def _validate_modifier(modifier: str | None) -> str | None:
        if modifier is None:
            return None
        if modifier not in [
            "test",
            "implementation",
            "api",
            "compileOnly",
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
    ) -> list[Dependency]:
        if isinstance(dep, config_typed.DepCall):
            effective_modifier = dep.modifier if dep.modifier is not None else modifier
            return parse_gradle_dependency(dep.name, effective_modifier)

        if isinstance(dep, Dependency):
            return [dep]

        if isinstance(dep, list):
            result: list[Dependency] = []
            for item in dep:
                if isinstance(item, Dependency):
                    result.append(item)
                else:
                    raise ValueError(f"Unknown dependency type: {item}")
            return result

        if not isinstance(dep, str):
            raise TypeError(f"Expected string, Dependency, or DepCall, got {type(dep)}")

        modifier = _validate_modifier(modifier)

        if dep.startswith(".") or dep.startswith("/"):
            path = Path(dep)
            return [Dependency(scope=modifier, target=JarFileDependencyTarget(path=path))]

        if dep.startswith(":"):
            project_name = dep[1:]
            if project_name not in config.defined_projects:
                raise ValueError(f"Project {project_name} is not defined")
            return [
                Dependency(
                    scope=modifier,
                    target=ProjectDependencyTarget(project=project_name),
                )
            ]

        if dep in config.library_groups:
            result: list[Dependency] = []
            for lib in config.library_groups[dep]:
                if isinstance(lib, str):
                    result.extend(parse_gradle_dependency(lib, modifier))
                elif isinstance(lib, list):
                    result.extend(parse_gradle_dependency(lib, modifier))
                elif isinstance(lib, Dependency):
                    result.extend(parse_gradle_dependency(lib, modifier))
                else:
                    raise ValueError(f"Unknown library-group child type: {lib}")
            return result

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

    def verify_project(project: Project) -> None:
        def is_publishable(input_project: Project) -> bool:
            return input_project.publish and input_project.github_repo is not None and (not input_project.quarantine)

        for dep in project.resolved_dependencies:
            if not isinstance(dep.target, ProjectDependencyTarget):
                continue
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

        if isinstance(command, config_typed.JitpackCookieCommand):
            config.jitpack_cookie = command.cookie
            return

        if isinstance(command, config_typed.AnthropicKeyCommand):
            config.anthropic_key = command.key
            return

        if isinstance(command, config_typed.DefaultMavenProjectGroupCommand):
            config.default_maven_project_group = command.group
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
            if command.line_length is not None:
                defaults.line_length = command.line_length
            if command.target_version is not None:
                defaults.target_version = command.target_version
            if command.coverage_fail_under is not None:
                defaults.coverage_fail_under = command.coverage_fail_under
            if command.coverage_precision is not None:
                defaults.coverage_precision = command.coverage_precision
            if command.coverage_branch is not None:
                defaults.coverage_branch = command.coverage_branch
            if command.coverage_show_missing is not None:
                defaults.coverage_show_missing = command.coverage_show_missing
            if command.coverage_skip_empty is not None:
                defaults.coverage_skip_empty = command.coverage_skip_empty
            if command.coverage_xml_output is not None:
                defaults.coverage_xml_output = command.coverage_xml_output
            return

        if isinstance(command, config_typed.DefineMavenRepoCommand):
            config.repositories[command.name] = MavenRepositoryDefinition(command.name, command.url)
            return

        if isinstance(command, config_typed.DefineKotlinPluginCommand):
            if command.name in config.plugins:
                raise ValueError(f"Plugin {command.name} already exists")
            if ":" not in command.value:
                raise ValueError(f"Invalid plugin definition: {command.value}")
            artifact_name, version = command.value.rsplit(":", 1)
            config.plugins[command.name] = KotlinPluginDefinition(artifact_name, version, command.repo)
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

        if isinstance(command, config_typed.PythonProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            path = Path(f"./{command.dir_name}")
            name = command.name or command.dir_name
            raw_features = [_feature_from_command(item) for item in (command.features or [])]
            resolved_features = resolve_features(raw_features)

            defaults = config.python_defaults
            line_length = (
                _coerce_int(command.line_length, "line-length")
                if command.line_length is not None
                else _coerce_int(defaults.line_length, "python-defaults.line-length")
            )
            coverage_fail_under = (
                _coerce_int(command.coverage_fail_under, "coverage-fail-under")
                if command.coverage_fail_under is not None
                else _coerce_int(
                    defaults.coverage_fail_under,
                    "python-defaults.coverage-fail-under",
                )
            )
            coverage_precision = (
                _coerce_int(command.coverage_precision, "coverage-precision")
                if command.coverage_precision is not None
                else _coerce_int(
                    defaults.coverage_precision,
                    "python-defaults.coverage-precision",
                )
            )

            deptry_feature = resolved_features.get("python-deptry")
            deptry_package_map = command.deptry_package_map or {}
            deptry_per_rule_ignores = command.deptry_per_rule_ignores or {}
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
            importlinter_root_packages = command.importlinter_root_packages or []
            importlinter_layers: list[str] = []
            if isinstance(importlinter_feature, PythonImportLinter):
                if importlinter_feature.root_packages:
                    importlinter_root_packages = importlinter_feature.root_packages
                importlinter_layers = importlinter_feature.layers or []

            parsed_source_sets = _parse_python_source_sets(command.source_sets)
            project_obj = PythonProject(
                path=path,
                name=name,
                quarantine=command.quarantine,
                publish=command.publish,
                description=command.description,
                authors=command.authors or [],
                license=command.license,
                github_repo=command.repo,
                ownership=ownership,
                requires_python=command.requires_python,
                dependencies=command.dependencies or [],
                dev_dependencies=command.dev_dependencies or [],
                scripts=command.scripts or [],
                raw_features=raw_features,
                resolved_features=resolved_features,
                line_length=line_length,
                target_version=command.target_version or defaults.target_version,
                source_sets=parsed_source_sets,
                test_paths=command.test_paths or [],
                ruff_per_file_ignores=command.ruff_per_file_ignores or {},
                deptry_package_map=deptry_package_map,
                deptry_per_rule_ignores=deptry_per_rule_ignores,
                deptry_auto_map=deptry_auto_map,
                importlinter_root_packages=importlinter_root_packages,
                importlinter_layers=importlinter_layers,
                importlinter_contracts=command.importlinter_contracts or [],
                coverage_source=command.coverage_source or [],
                coverage_omit=command.coverage_omit or [],
                coverage_fail_under=coverage_fail_under,
                coverage_precision=coverage_precision,
                coverage_branch=(
                    command.coverage_branch if command.coverage_branch is not None else defaults.coverage_branch
                ),
                coverage_show_missing=(
                    command.coverage_show_missing
                    if command.coverage_show_missing is not None
                    else defaults.coverage_show_missing
                ),
                coverage_skip_empty=(
                    command.coverage_skip_empty
                    if command.coverage_skip_empty is not None
                    else defaults.coverage_skip_empty
                ),
                coverage_xml_output=(command.coverage_xml_output or defaults.coverage_xml_output),
                version=Version.parse(command.version) if command.version else None,
                resolved_dependencies=[],
            )
            verify_project(project_obj)
            config.defined_projects[name] = project_obj
            return

        if isinstance(command, config_typed.PurescriptProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            name = command.name or command.dir_name
            project_obj = PurescriptProject(
                path=Path(f"./{command.dir_name}"),
                name=name,
                description=command.description,
                authors=command.authors or [],
                quarantine=command.quarantine,
                license=command.license,
                publish=command.publish,
                github_repo=command.repo,
                ownership=ownership,
                version=Version.parse(command.version) if command.version else None,
                resolved_dependencies=[],
            )
            verify_project(project_obj)
            config.defined_projects[name] = project_obj
            return

        if isinstance(command, config_typed.DataProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            name = command.name or command.dir_name
            project_obj = DataProject(
                path=Path(f"./{command.dir_name}"),
                name=name,
                description=command.description,
                authors=command.authors or [],
                quarantine=command.quarantine,
                publish=command.publish,
                license=command.license,
                github_repo=command.repo,
                ownership=ownership,
                version=Version.parse(command.version) if command.version else None,
                resolved_dependencies=[],
            )
            verify_project(project_obj)
            config.defined_projects[name] = project_obj
            return

        if isinstance(command, config_typed.PremakeProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            name = command.name or command.dir_name
            project_obj = PremakeProject(
                path=Path(f"./{command.dir_name}"),
                name=name,
                description=command.description,
                authors=command.authors or [],
                github_repo=command.repo,
                license=command.license,
                quarantine=command.quarantine,
                publish=command.publish,
                ownership=ownership,
                version=Version.parse(command.version) if command.version else None,
                resolved_dependencies=[],
            )
            verify_project(project_obj)
            config.defined_projects[name] = project_obj
            return

        if isinstance(command, config_typed.GradleProjectCommand):
            ownership = _coerce_ownership(command.ownership)
            name = command.name or command.dir_name
            raw_features = [_feature_from_command(item) for item in (command.features or [])]
            resolved_features = resolve_features(raw_features)

            raw_dependencies: list[str | Dependency | list[Dependency]] = []
            resolved_dependencies: list[Dependency] = []
            for item in command.dependencies or []:
                if isinstance(item, str):
                    raw_dependencies.append(item)
                    resolved_dependencies.extend(parse_gradle_dependency(item))
                elif isinstance(item, config_typed.DepCall):
                    resolved = parse_gradle_dependency(item)
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

            project_obj = GradleProject(
                path=Path(f"./{command.dir_name}"),
                group_name=config.default_maven_project_group,
                name=name,
                version=Version.parse(command.version) if command.version else None,
                description=command.description,
                authors=command.authors or [],
                quarantine=command.quarantine,
                license=command.license,
                publish=command.publish,
                github_repo=command.repo,
                raw_dependencies=raw_dependencies,
                raw_features=raw_features,
                resolved_maven_repositories=maven_repositories,
                resolved_features=resolved_features,
                resolved_dependencies=resolved_dependencies,
                ownership=ownership,
            )
            verify_project(project_obj)
            config.defined_projects[name] = project_obj
            return

        raise ValueError(f"Unknown builtin command: {type(command)}")

    def _apply_command(command: Any) -> None:
        command_handler = module_command_handlers.get(type(command))
        if command_handler is not None:
            command_handler(command)
            return
        _apply_builtin_command(command)

    def _decode_and_apply(doc: SDoc, source_name: str) -> None:
        for index, expr in enumerate(doc.exprs):
            path = f"{source_name}[{index}]"
            command = decode_expr(expr, top_level_target, path=path)
            try:
                _apply_command(command)
            except TypeError:
                raise
            except MuDecodeError:
                raise
            except Exception as cause:
                raise MuDecodeError(
                    path=path,
                    expected=f"valid config command ({type(command).__name__})",
                    got=type(expr).__name__,
                    span=_extract_expr_span(expr),
                    cause=cause,
                ) from cause

    _decode_and_apply(root, "root")
    _decode_and_apply(root_private, "root.private")

    return config
