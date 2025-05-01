from typing import Any, Dict, List, Optional, Union
import dataclasses
from dataclasses import dataclass
from enum import Enum
from collections import OrderedDict

import re

import os
from pathlib import Path

from dev.maven import MavenCoordinate, is_valid_maven_coordinate

from mu.types import SAtom, SStr, SDoc
from mu.parser import sexpr
from mu.exec import ExecutionContext, Quoted, eval_sexpr

################################################################################
# Ownership Type
################################################################################

class OwnershipType(Enum):
    WABBIT = 'wabbit'
    IMPORTED = 'imported'

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
    
    def next_major(self) -> 'Version':
        return Version(None, self.major + 1, 0, 0, False)
    
    def next_minor(self) -> 'Version':
        return Version(None, self.major, self.minor + 1, 0, False)
    
    def next_patch(self) -> 'Version':
        return Version(None, self.major, self.minor, self.patch + 1, False)

    @classmethod
    def parse_or_null(cls, version: Quoted[SStr] | str) -> Union['Version', None]:
        value = version.value.value if isinstance(version, Quoted) else version
        match = re.match(r'(\d+)\.(\d+)\.(\d+)(\+dev-SNAPSHOT)?', value)
        if not match:
            return None

        major, minor, patch, is_dev = match.groups()
        return cls(version, int(major), int(minor), int(patch), bool(is_dev))

    @classmethod
    def parse(cls, version: Quoted[SStr] | str) -> 'Version':
        result = cls.parse_or_null(version)
        assert result is not None, f"Invalid version: {version.value.value if isinstance(version, Quoted) else version}"
        return result

    def __lt__(self, other: 'Version') -> bool:
        self_dev_val = 1 if self.is_dev else 0
        other_dev_val = 1 if other.is_dev else 0
        return (self.major, self.minor, self.patch, self_dev_val) < (other.major, other.minor, other.patch, other_dev_val)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch, self.is_dev) == (other.major, other.minor, other.patch, other.is_dev)
    
    def __gt__(self, other: 'Version') -> bool:
        return other < self
    def __ge__(self, other: 'Version') -> bool:
        return not self < other
    def __le__(self, other: 'Version') -> bool:
        return not other < self

###############################################################################################
# Features
###############################################################################################

class Feature:
    __feature_name__: str
    def implied(self) -> List['Feature']:
        return []

@dataclass
class Kotlin(Feature):
    __feature_name__ = 'kotlin'

@dataclass
class Scala(Feature):
    __feature_name__ = 'scala'

@dataclass
class Jvm(Feature):
    __feature_name__ = 'jvm'
    jarName: Optional[str] = None

@dataclass
class ShadowJar(Feature):
    __feature_name__ = 'shadow-jar'
    jarName: Optional[str] = None
    def implied(self) -> List[Feature]:
        return [Jvm()]

@dataclass
class JvmKotlinLibrary(Feature):
    __feature_name__ = 'jvm-kotlin-library'
    def implied(self) -> List[Feature]:
        return [Kotlin(), Jvm()]

@dataclass
class JvmScalaLibrary(Feature):
    __feature_name__ = 'jvm-scala-library'
    def implied(self) -> List[Feature]:
        return [Scala(), Jvm()]

@dataclass
class JvmKotlinApplication(Feature):
    __feature_name__ = 'jvm-kotlin-application'
    main: str
    jarName: Optional[str] = None
    shadedJarName: Optional[str] = None
    unshadedJarName: Optional[str] = None

    def __post_init__(self):
        if self.jarName:
            assert isinstance(self.jarName, str), f"Expected string, got {type(self.jarName)}"
            assert self.jarName.endswith('.jar'), f"Expected .jar file, got {self.jarName}"
            base, _ = os.path.splitext(self.jarName)
            self.shadedJarName = self.jarName
            self.unshadedJarName = f"{base}-unshaded.jar"
        elif self.shadedJarName:
            assert isinstance(self.shadedJarName, str), f"Expected string, got {type(self.shadedJarName)}"
            assert self.shadedJarName.endswith('.jar'), f"Expected .jar file, got {self.shadedJarName}"
            base, _ = os.path.splitext(self.shadedJarName)
            self.jarName = self.shadedJarName
            self.unshadedJarName = f"{base}-unshaded.jar"
        elif self.unshadedJarName:
            assert isinstance(self.unshadedJarName, str), f"Expected string, got {type(self.unshadedJarName)}"
            assert self.unshadedJarName.endswith('.jar'), f"Expected .jar file, got {self.unshadedJarName}"
            base, _ = os.path.splitext(self.unshadedJarName)
            self.jarName = self.unshadedJarName
            self.shadedJarName = f"{base}-shaded.jar"

    def implied(self) -> List[Feature]:
        return [
            Kotlin(),
            Jvm(jarName=self.unshadedJarName),
            ShadowJar(jarName=self.shadedJarName)
        ]

@dataclass
class PaperPlugin(Feature):
    __feature_name__ = 'paper-plugin'
    main: str
    name: str
    apiVersion: str
    def implied(self) -> List[Feature]:
        return [
            Kotlin(),
            Jvm(jarName=f"{self.name}-unshaded.jar"),
            ShadowJar(jarName=f"{self.name}.jar")
        ]

@dataclass
class JvmKotlinAgent(Feature):
    __feature_name__ = 'jvm-kotlin-agent'
    main: str
    jarName: Optional[str] = None
    shadedJarName: Optional[str] = None
    unshadedJarName: Optional[str] = None

    def __post_init__(self):
        if self.jarName:
            assert isinstance(self.jarName, str), f"Expected string, got {type(self.jarName)}"
            assert self.jarName.endswith('.jar'), f"Expected .jar file, got {self.jarName}"
            base, _ = os.path.splitext(self.jarName)
            self.shadedJarName = self.jarName
            self.unshadedJarName = f"{base}-unshaded.jar"
        elif self.shadedJarName:
            assert isinstance(self.shadedJarName, str), f"Expected string, got {type(self.shadedJarName)}"
            assert self.shadedJarName.endswith('.jar'), f"Expected .jar file, got {self.shadedJarName}"
            base, _ = os.path.splitext(self.shadedJarName)
            self.jarName = self.shadedJarName
            self.unshadedJarName = f"{base}-unshaded.jar"
        elif self.unshadedJarName:
            assert isinstance(self.unshadedJarName, str), f"Expected string, got {type(self.unshadedJarName)}"
            assert self.unshadedJarName.endswith('.jar'), f"Expected .jar file, got {self.unshadedJarName}"
            base, _ = os.path.splitext(self.unshadedJarName)
            self.jarName = self.unshadedJarName
            self.shadedJarName = f"{base}-shaded.jar"

    def implied(self) -> List[Feature]:
        return [
            Kotlin(),
            Jvm(jarName=self.unshadedJarName),
            ShadowJar(jarName=self.shadedJarName)
        ]

@dataclass
class KotlinSerialization(Feature):
    __feature_name__ = 'kotlin-serialization'

    def implied(self) -> List[Feature]:
        return [Kotlin()]
    

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
    TEST = 'test'
    API = 'api'
    IMPLEMENTATION = 'implementation'
    COMPILE_ONLY = 'compileOnly'
    RUNTIME_ONLY = 'runtimeOnly'
    TEST_IMPLEMENTATION = 'testImplementation'
    TEST_COMPILE_ONLY = 'testCompileOnly'
    TEST_RUNTIME_ONLY = 'testRuntimeOnly'

@dataclass
class Dependency:
    scope: str | None
    target: 'DependencyTarget'

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
        assert isinstance(self.scope, str) or self.scope is None, f"Expected GradleDependencyScope or None, got {type(self.scope)}"
        assert isinstance(self.target, DependencyTarget), f"Expected DependencyTarget, got {type(self.target)}"

    def __str__(self):
        return self.as_string()

    def as_string(self):
        modifier = self.scope
        if modifier is None:
            modifier = 'implementation'

        match self.target:
            case DependencyTarget.JarFile(path):
                dirname, basename = os.path.split(path)
                return f'{modifier}(fileTree(mapOf("dir" to "{dirname}", "include" to listOf("{basename}"))))'
            
            case DependencyTarget.Project(project):
                return f'{modifier}(project(":{project}"))'
            
            case DependencyTarget.Maven(maven_repo, artifact):
                # FIXME: repo is not used
                return f'{modifier}("{artifact}")'
            

class DependencyTarget:
    JarFile: type['JarFileDependencyTarget'] = None # type: ignore
    Project: type['ProjectDependencyTarget'] = None # type: ignore
    Maven: type['MavenDependencyTarget'] = None # type: ignore

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

class Project:
    path: Path
    name: str
    github_repo: str | None
    ownership: OwnershipType
    resolved_dependencies: List[Dependency]

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
class PythonProject(Project):
    path: Path
    name: str
    version: Version | None
    github_repo: str | None
    ownership: OwnershipType

    # # Python dependencies in a raw user form vs. resolved objects
    # raw_dependencies: List[str]
    # resolved_python_dependencies: List[PythonDependency]

    resolved_dependencies: List[Dependency] = dataclasses.field(default_factory=list)
    # (We keep a list of `Dependency` too if you want to unify anything across projects,
    #  but typically a pure Python project won't rely on Gradle dependencies.)

@dataclass
class PurescriptProject(Project):
    path: Path
    name: str
    github_repo: str | None
    ownership: OwnershipType
    version: Version | None
    resolved_dependencies: List[Dependency]

@dataclass
class PremakeProject(Project):
    path: Path
    name: str
    github_repo: str | None
    ownership: OwnershipType
    version: Version | None
    resolved_dependencies: List[Dependency]

@dataclass
class DataProject(Project):
    path: Path
    name: str
    github_repo: str | None
    ownership: OwnershipType
    version: Version | None
    resolved_dependencies: List[Dependency]

@dataclass
class GradleProject(Project):
    path: Path
    group_name: str
    name: str
    version: Version | None
    github_repo: str | None
    ownership: OwnershipType

    raw_dependencies: List[str | Dependency | List[Dependency]]
    raw_features: List[Feature]

    resolved_dependencies: List[Dependency]
    resolved_maven_repositories: List[MavenRepositoryDefinition]
    resolved_features: Dict[str, Feature]

    @property
    def artifact_name(self) -> str:
        return f"com.github.wabbit-corp:{self.name}:{self.version}"

##################################################################################################
# Config
##################################################################################################

CONFIG_FILE = 'root.clj'
CONFIG_PRIVATE_FILE = 'root.private.clj'

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
    library_groups: OrderedDict[str, List[str]] = dataclasses.field(default_factory=OrderedDict)
    defined_projects: OrderedDict[str, Project] = dataclasses.field(default_factory=OrderedDict)

def load_config() -> Config:
    with open(CONFIG_FILE, 'rt', encoding='utf-8') as f:
        root = sexpr(f.read())
    with open(CONFIG_PRIVATE_FILE, 'rt', encoding='utf-8') as f:
        root_private = sexpr(f.read())

    config = Config(raw=root)
    ctx = ExecutionContext()

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

    @ctx.register(name="default-git-user-email")
    def default_git_user_email(email: str):
        config.default_git_user_email = email

    @ctx.register(name="default-git-user-name")
    def default_git_user_name(name: str):
        config.default_git_user_name = name

    @ctx.register(name="anthropic-key")
    def anthropic_key(key: str):
        config.anthropic_key = key

    @ctx.register(name="jvm-kotlin-library")
    def jvm_kotlin_library() -> JvmKotlinLibrary:
        return JvmKotlinLibrary()

    @ctx.register(name="jvm-scala-library")
    def jvm_scala_library() -> JvmScalaLibrary:
        return JvmScalaLibrary()

    @ctx.register(name="jvm-kotlin-application")
    def jvm_kotlin_application(main: str, jar: str | None = None) -> JvmKotlinApplication:
        return JvmKotlinApplication(main, jar)

    @ctx.register(name="paper-plugin")
    def paper_plugin(name: str, main: str, apiVersion: str) -> PaperPlugin:
        return PaperPlugin(main, name, apiVersion)

    @ctx.register(name="jvm-kotlin-agent")
    def jvm_kotlin_agent(main: str, jar: str | None = None) -> JvmKotlinAgent:
        return JvmKotlinAgent(main, jar)

    @ctx.register(name="kotlin-serialization")
    def kotlin_serialization() -> KotlinSerialization:
        return KotlinSerialization()

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
        assert isinstance(repo, str) or repo is None, f"Expected string or None, got {type(repo)}"
        assert name not in config.plugins, f"Plugin {name} already exists"
        assert ':' in value, f"Invalid plugin definition: {value}"
        artifact_name, version = value.split(':')
        config.plugins[name] = KotlinPluginDefinition(artifact_name, version, repo)

    @ctx.register(name="define-maven-library")
    def library(name: str, maven_urn: str, repo: str | None = None) -> None:
        assert isinstance(name, str), f"Expected string, got {type(name)}"
        assert isinstance(maven_urn, str), f"Expected string, got {type(maven_urn)}"
        assert is_valid_maven_coordinate(maven_urn), f"Invalid Maven coordinate: {maven_urn}"
        assert name not in config.libraries, f"Library {name} already exists"
        coord = MavenCoordinate.parse(maven_urn)
        config.libraries[name] = MavenLibraryDefinition(name, coord, repo)

    @ctx.register(name='define-maven-library-group')
    def library_group(name: str, children: List[str | Dependency | List[Dependency]]) -> None:
        assert isinstance(name, str), f"Expected string, got {type(name)}"
        assert name not in config.library_groups, f"Library group {name} already exists"
        assert isinstance(children, list), f"Expected list of libraries, got {type(children)}"
        # assert all(isinstance(lib, str) or isinstance(lib, Dependency) for lib in children), f"Expected list of strings, got {children}"
        assert all(lib in children for lib in children), f"Unknown libraries: {children}"
        config.library_groups[name] = children

    def parse_gradle_dependency(dep: str | Dependency, modifier: str | None = None) -> List[Dependency]:
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
            assert modifier in ['test', 'implementation', 'api', 'compileOnly', 'runtimeOnly', 
                                'testImplementation', 'testCompileOnly', 'testRuntimeOnly'], f"Unknown modifier: {modifier}"

        if dep.startswith('.') or dep.startswith('/'):
            path = Path(dep)
            # FIXME: Check if file exists
            # assert path.exists(), f"File {path} does not exist"
            return [Dependency(scope=modifier, target=JarFileDependencyTarget(path=path))]

        if dep.startswith(':'):
            project_name = dep[1:]
            assert project_name in config.defined_projects, f"Project {project_name} is not defined"
            return [Dependency(scope=modifier, target=ProjectDependencyTarget(project=project_name))]

        if dep in config.library_groups:
            result = []
            for lib in config.library_groups[dep]:
                result.extend(parse_gradle_dependency(lib, modifier))
            return result

        if dep in config.libraries:
            maven_urn = config.libraries[dep].maven_urn.__str__()
            maven_repo = config.libraries[dep].repo
            return [Dependency(scope=modifier, target=MavenDependencyTarget(artifact=maven_urn, maven_repo=maven_repo))]

        if is_valid_maven_coordinate(dep):
            return [Dependency(scope=modifier, target=MavenDependencyTarget(artifact=dep))]

        raise ValueError(f"Unknown library or library group: {dep}")

    @ctx.register(name='dep')
    def dep(name: str, modifier: str | None = None) -> List[Dependency]:
        if modifier is not None:
            assert isinstance(modifier, str), f"Expected string, got {type(modifier)}"
            assert modifier in ['test', 'implementation', 'api', 'compileOnly', 'runtimeOnly', 
                                'testImplementation', 'testCompileOnly', 'testRuntimeOnly'], f"Unknown modifier: {modifier}"
        return parse_gradle_dependency(name, modifier)

    ###############################################################################################
    # Projects
    ###############################################################################################

    @ctx.register(name='python')
    def python_project(
        name: str,
        version: Quoted[SStr],
        repo: str | None = None,
        ownership: OwnershipType = OwnershipType.WABBIT,
    ) -> None:
        path = Path(f"./{name}")
        project_obj = PythonProject(
            path=path, name=name, 
            github_repo=repo,
            ownership=ownership,
            version=Version.parse(version) if version else None,
            resolved_dependencies=[])
        config.defined_projects[name] = project_obj

    @ctx.register(name='purescript')
    def purescript_project(
        name: str,
        version: Quoted[SStr],
        repo: str | None = None,
        ownership: OwnershipType = OwnershipType.WABBIT,
    ) -> None:
        path = Path(f"./{name}")
        project_obj = PurescriptProject(
            path=path, name=name, 
            github_repo=repo,
            ownership=ownership,
            version=Version.parse(version) if version else None,
            resolved_dependencies=[])
        config.defined_projects[name] = project_obj

    @ctx.register(name='data')
    def data_project(
        name: str,
        version: Quoted[SStr],
        repo: str | None = None,
        ownership: OwnershipType = OwnershipType.WABBIT,
    ) -> None:
        path = Path(f"./{name}")
        project_obj = DataProject(
            path=path, name=name, 
            github_repo=repo,
            ownership=ownership,
            version=Version.parse(version) if version else None,
            resolved_dependencies=[])
        config.defined_projects[name] = project_obj

    @ctx.register(name='premake')
    def premake_project(
        name: str,
        version: Quoted[SStr],
        repo: str | None = None,
        ownership: OwnershipType = OwnershipType.WABBIT,
    ) -> None:
        path = Path(f"./{name}")
        project_obj = PremakeProject(
            path=path, name=name, 
            github_repo=repo,
            ownership=ownership,
            version=Version.parse(version) if version else None,
            resolved_dependencies=[])
        config.defined_projects[name] = project_obj

    @ctx.register(name='gradle')
    def gradle_project(
        name: str,
        version: Quoted[SStr],
        dependencies: List[str | DependencyTarget | List[DependencyTarget]] | None = None,
        features: List[Feature] | None = None,
        repo: str | None = None,
        ownership: OwnershipType = OwnershipType.WABBIT,
    ) -> None:
        # This makes no sense from typechecking perspective, but it's necessary since we're using eval_sexpr
        if isinstance(ownership, str):
            ownership = OwnershipType(ownership)

        # assert repo is not None, f"Repository is required for Gradle project {name}"

        resolved_features : Dict[str, Feature] = { type(feature).__feature_name__: feature for feature in (features or []) }
        for feature in list(resolved_features.values()):
            for implied in feature.implied():
                implied_name = type(implied).__feature_name__
                if implied_name not in resolved_features:
                    resolved_features[implied_name] = implied
                else:
                    assert resolved_features[implied_name] == implied, f"Implied feature {implied_name} is already defined with a different configuration {resolved_features[implied_name]} != {implied} for {name}"

        raw_dependencies: List[str | DependencyTarget | List[DependencyTarget]] = dependencies or []
        resolved_dependencies: List[DependencyTarget] = []
        for dep in raw_dependencies:
            if isinstance(dep, list):
                resolved_dependencies.extend(dep)
            elif isinstance(dep, str):
                resolved_dependencies.extend(parse_gradle_dependency(dep))
            else:
                assert isinstance(dep, DependencyTarget), f"Expected string or Dependency, got {type(dep)}"
                resolved_dependencies.append(dep)

        maven_repositories: List[MavenRepositoryDefinition] = []
        for dep in resolved_dependencies:
            if isinstance(dep.target, MavenDependencyTarget) and dep.target.maven_repo:
                maven_repo = config.repositories[dep.target.maven_repo]
                if maven_repo not in maven_repositories:
                    maven_repositories.append(maven_repo)

        # Verify that IF there is a github_repo (project is publishable),
        # then ALL projects in the dependency chain are also publishable.
        if repo:
            for dep in resolved_dependencies:
                if isinstance(dep.target, ProjectDependencyTarget):
                    project = config.defined_projects[dep.target.project]
                    assert project.github_repo, f"Project {project.name} is not publishable, but {name} is"

        config.defined_projects[name] = GradleProject(
            path=Path(f"./{name}"),
            group_name=config.default_maven_project_group,
            name=name,
            version=Version.parse(version) if version else None,
            github_repo=repo,
            raw_dependencies=raw_dependencies,
            raw_features=features or [],
            resolved_maven_repositories=maven_repositories,
            resolved_features=resolved_features,
            resolved_dependencies=resolved_dependencies,
            ownership=ownership
        )

    eval_sexpr(ctx, root, ignore_toplevel_exceptions=True)
    eval_sexpr(ctx, root_private, ignore_toplevel_exceptions=True)

    return config
