from __future__ import annotations

import re
import typing
from collections.abc import Sequence
from dataclasses import dataclass
from types import UnionType

from mu.typed import DecodeContext, DecodeError, DecodeWith, tag
from mu.types import AtomExpr, Expr, MappingExpr, SequenceExpr, StringExpr


@dataclass(frozen=True)
class Const[T]:
    value: T


@dataclass(frozen=True)
class VarName:
    name: str


type Value[T] = Const[T] | VarName


@dataclass(frozen=True)
class MavenCoordinateExpr:
    group_id: str
    artifact_id: str
    version: Value[str]
    suffix: str | None = None


_VAR_PATTERN = re.compile(r"^\$\{([^:{}]+)\}$")


def _decode_symbol_atom(expr: Expr, _ctx: DecodeContext) -> str:
    if not isinstance(expr, AtomExpr):
        raise DecodeError(
            path=_ctx.path,
            expected="symbol atom",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )
    value_obj: object = expr.value
    if isinstance(value_obj, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        return value_obj
    raise DecodeError(
        path=_ctx.path,
        expected="symbol atom",
        got=type(value_obj).__name__,
        span=getattr(expr, "span", None),
    )


def _decode_issue_name_or_star(expr: Expr, ctx: DecodeContext) -> str:
    if isinstance(expr, StringExpr):
        value_obj: object = expr.value
    elif isinstance(expr, AtomExpr):
        value_obj = expr.value
    else:
        raise DecodeError(
            path=ctx.path,
            expected="issue id string (E_...) or *",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )
    if not isinstance(value_obj, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise DecodeError(
            path=ctx.path,
            expected="issue id string (E_...) or *",
            got=type(value_obj).__name__,
            span=getattr(expr, "span", None),
        )
    value = value_obj
    if value == "*" or re.fullmatch(r"E_[A-Z0-9_]+", value):
        return value

    raise DecodeError(
        path=ctx.path,
        expected="issue id string (E_...) or *",
        got=value,
        span=getattr(expr, "span", None),
    )


def _decode_maven_coordinate_expr(expr: Expr, ctx: DecodeContext) -> MavenCoordinateExpr:
    if isinstance(expr, StringExpr):
        raw = expr.value
    elif isinstance(expr, AtomExpr):
        raw = expr.value
    else:
        raise DecodeError(
            path=ctx.path,
            expected="maven coordinate string",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )

    parts = raw.split(":")
    if len(parts) < 3:
        raise DecodeError(
            path=ctx.path,
            expected="maven coordinate group:artifact:version[:classifier...]",
            got=raw,
            span=getattr(expr, "span", None),
        )

    group_id, artifact_id = parts[0], parts[1]
    version_text = parts[2]
    suffix = ":".join(parts[3:]) if len(parts) > 3 else None

    if "${" in group_id or "${" in artifact_id or (suffix and "${" in suffix):
        raise DecodeError(
            path=ctx.path,
            expected="variable references only in maven version component",
            got=raw,
            span=getattr(expr, "span", None),
        )

    version_match = _VAR_PATTERN.fullmatch(version_text)
    if version_match:
        version: Value[str] = VarName(version_match.group(1))
    else:
        if "${" in version_text or "$$" in version_text:
            raise DecodeError(
                path=ctx.path,
                expected="maven version constant or ${var-name}",
                got=version_text,
                span=getattr(expr, "span", None),
            )
        version = Const(version_text)

    return MavenCoordinateExpr(
        group_id=group_id,
        artifact_id=artifact_id,
        version=version,
        suffix=suffix,
    )


def _decode_gradle_target_commands(expr: Expr, ctx: DecodeContext) -> list[GradleTargetCommand]:
    if not isinstance(expr, SequenceExpr):
        raise DecodeError(
            path=ctx.path,
            expected="sequence [] of Gradle target maps",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )

    result: list[GradleTargetCommand] = []
    for index, item in enumerate(expr.values):
        if not isinstance(item, MappingExpr):
            raise DecodeError(
                path=f"{ctx.path}[{index}]",
                expected="map {} for Gradle target",
                got=type(item).__name__,
                span=getattr(item, "span", None),
            )

        kind: str | None = None
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
        for field_index, field in enumerate(item.values):
            key = ctx.decode(field.key, str, path=f"{ctx.path}[{index}].keys[{field_index}]")
            value_path = f"{ctx.path}[{index}].values[{field_index}]"
            if key == "kind":
                kind = ctx.decode(field.value, str, path=value_path)
                continue
            if key == "name":
                name = ctx.decode(field.value, str, path=value_path)
                continue
            if key == "namespace":
                namespace = ctx.decode(field.value, str, path=value_path)
                continue
            if key == "applicationId":
                application_id = ctx.decode(field.value, str, path=value_path)
                continue
            if key == "compileSdk":
                compile_sdk = ctx.decode(field.value, int, path=value_path)
                continue
            if key == "minSdk":
                min_sdk = ctx.decode(field.value, int, path=value_path)
                continue
            if key == "targetSdk":
                target_sdk = ctx.decode(field.value, int, path=value_path)
                continue
            if key == "manifestPath":
                manifest_path = ctx.decode(field.value, str, path=value_path)
                continue
            if key == "browser":
                browser = ctx.decode(field.value, bool, path=value_path)
                continue
            if key == "browserTest":
                browser_test = ctx.decode(field.value, str, path=value_path)
                continue
            if key == "executable":
                executable = ctx.decode(field.value, bool, path=value_path)
                continue
            raise DecodeError(
                path=f"{ctx.path}[{index}]",
                expected="Gradle target field",
                got=key,
                span=getattr(field.key, "span", None),
            )

        if kind is None:
            raise DecodeError(
                path=f"{ctx.path}[{index}]",
                expected="Gradle target with kind",
                got="missing kind",
                span=getattr(item, "span", None),
            )
        result.append(
            GradleTargetCommand(
                kind=kind,
                name=name,
                namespace=namespace,
                applicationId=application_id,
                compileSdk=compile_sdk,
                minSdk=min_sdk,
                targetSdk=target_sdk,
                manifestPath=manifest_path,
                browser=browser,
                browserTest=browser_test,
                executable=executable,
            )
        )
    return result


def _decode_kmp_jvm_run_entries(expr: Expr, ctx: DecodeContext) -> list[KmpJvmRunEntryCommand]:
    if not isinstance(expr, SequenceExpr):
        raise DecodeError(
            path=ctx.path,
            expected="sequence [] of kmp-jvm-runs entry maps",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )

    result: list[KmpJvmRunEntryCommand] = []
    for index, item in enumerate(expr.values):
        if not isinstance(item, MappingExpr):
            raise DecodeError(
                path=f"{ctx.path}[{index}]",
                expected="map {} for kmp-jvm-runs entry",
                got=type(item).__name__,
                span=getattr(item, "span", None),
            )

        task_name: str | None = None
        main_class: str | None = None
        description: str | None = None
        jvm_args: list[str] | None = None
        for field_index, field in enumerate(item.values):
            key = ctx.decode(field.key, str, path=f"{ctx.path}[{index}].keys[{field_index}]")
            value_path = f"{ctx.path}[{index}].values[{field_index}]"
            if key == "taskName":
                task_name = ctx.decode(field.value, str, path=value_path)
                continue
            if key == "mainClass":
                main_class = ctx.decode(field.value, str, path=value_path)
                continue
            if key == "description":
                description = ctx.decode(field.value, str, path=value_path)
                continue
            if key == "jvmArgs":
                jvm_args = ctx.decode(field.value, list[str], path=value_path)
                continue
            raise DecodeError(
                path=f"{ctx.path}[{index}]",
                expected="kmp-jvm-runs field",
                got=key,
                span=getattr(field.key, "span", None),
            )

        if task_name is None or main_class is None or description is None:
            raise DecodeError(
                path=f"{ctx.path}[{index}]",
                expected="taskName/mainClass/description strings",
                got="missing required field",
                span=getattr(item, "span", None),
            )
        result.append(
            KmpJvmRunEntryCommand(
                taskName=task_name,
                mainClass=main_class,
                description=description,
                jvmArgs=jvm_args,
            )
        )
    return result


def _decode_gradle_source_sets(expr: Expr, ctx: DecodeContext) -> dict[str, GradleSourceSetCommand]:
    if not isinstance(expr, MappingExpr):
        raise DecodeError(
            path=ctx.path,
            expected="map {} of Gradle source-set definitions",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )

    result: dict[str, GradleSourceSetCommand] = {}
    for index, field in enumerate(expr.values):
        source_set_name = ctx.decode(field.key, str, path=f"{ctx.path}.keys[{index}]")
        if not isinstance(field.value, MappingExpr):
            raise DecodeError(
                path=f"{ctx.path}.values[{index}]",
                expected="map {} for source-set definition",
                got=type(field.value).__name__,
                span=getattr(field.value, "span", None),
            )

        depends_on: list[str] | None = None
        dependencies: list[DependencyInput] | None = None
        kotlin_src_dirs: list[str] | None = None
        for nested_index, nested_field in enumerate(field.value.values):
            nested_key = ctx.decode(
                nested_field.key,
                str,
                path=f"{ctx.path}.values[{index}].keys[{nested_index}]",
            )
            nested_path = f"{ctx.path}.values[{index}].values[{nested_index}]"
            if nested_key == "dependsOn":
                depends_on = ctx.decode(nested_field.value, list[str], path=nested_path)
                continue
            if nested_key == "dependencies":
                dependencies = ctx.decode(nested_field.value, list[DependencyInput], path=nested_path)
                continue
            if nested_key == "kotlinSrcDirs":
                kotlin_src_dirs = ctx.decode(nested_field.value, list[str], path=nested_path)
                continue
            raise DecodeError(
                path=f"{ctx.path}.values[{index}]",
                expected="source-set fields dependsOn/dependencies/kotlinSrcDirs",
                got=nested_key,
                span=getattr(nested_field.key, "span", None),
            )

        result[source_set_name] = GradleSourceSetCommand(
            dependsOn=depends_on,
            dependencies=dependencies,
            kotlinSrcDirs=kotlin_src_dirs,
        )
    return result


def _decode_gradle_source_set_dependencies(expr: Expr, ctx: DecodeContext) -> dict[str, list[DependencyInput]]:
    if not isinstance(expr, MappingExpr):
        raise DecodeError(
            path=ctx.path,
            expected="map {} of Gradle source-set dependency lists",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )

    result: dict[str, list[DependencyInput]] = {}
    for index, field in enumerate(expr.values):
        source_set_name = ctx.decode(field.key, str, path=f"{ctx.path}.keys[{index}]")
        dependencies = ctx.decode(field.value, list[DependencyInput], path=f"{ctx.path}.values[{index}]")
        result[source_set_name] = dependencies
    return result


@tag("checks/disable")
@dataclass(frozen=True)
class ChecksDisableCommand:
    error_name: str
    pathspec: str


@tag("checks/ignore-finding")
@dataclass(frozen=True)
class ChecksIgnoreFindingCommand:
    error_name: typing.Annotated[str, DecodeWith(_decode_issue_name_or_star)]
    pathspec: str
    value: str


@tag("define")
@dataclass(frozen=True)
class DefineCommand:
    name: typing.Annotated[str, DecodeWith(_decode_symbol_atom)]
    value: str | int | float | bool | None


@tag("openai-key")
@dataclass(frozen=True)
class OpenaiKeyCommand:
    key: str


@tag("github-token")
@dataclass(frozen=True)
class GithubTokenCommand:
    token: str


@tag("github-ssh-key")
@dataclass(frozen=True)
class GithubSshKeyCommand:
    key: str


@tag("anthropic-key")
@dataclass(frozen=True)
class AnthropicKeyCommand:
    key: str


@tag("jetbrains-marketplace-token")
@dataclass(frozen=True)
class JetbrainsMarketplaceTokenCommand:
    token: str


@tag("pypi-token")
@dataclass(frozen=True)
class PypiTokenCommand:
    token: str


@tag("nuget-api-key")
@dataclass(frozen=True)
class NugetApiKeyCommand:
    token: str


@tag("maven-username")
@dataclass(frozen=True)
class MavenUsernameCommand:
    username: str


@tag("maven-password")
@dataclass(frozen=True)
class MavenPasswordCommand:
    password: str


@tag("maven-gpg-private-key")
@dataclass(frozen=True)
class MavenGpgPrivateKeyCommand:
    key: str


@tag("maven-gpg-passphrase")
@dataclass(frozen=True)
class MavenGpgPassphraseCommand:
    passphrase: str


@tag("maven-gpg-key-id")
@dataclass(frozen=True)
class MavenGpgKeyIdCommand:
    key_id: str


@tag("jitpack-cookie")
@dataclass(frozen=True)
class JitpackCookieCommand:
    cookie: str


@tag("define-backup-target")
@dataclass(frozen=True)
class DefineBackupTargetCommand:
    name: str
    kind: str
    host: str
    user: str
    path: str
    sshKey: str | None = None
    passwordFile: str | None = None
    passwordCommand: str | None = None
    compression: str | None = None


@tag("backup-policy")
@dataclass(frozen=True)
class BackupPolicyCommand:
    targets: list[str]
    service: bool | None = None
    serviceDirtyAgeMinutes: int | None = None
    serviceMinIntervalMinutes: int | None = None
    includeGit: bool | None = None
    exclude: list[str] | None = None
    excludeIfPresent: list[str] | None = None
    excludeCaches: bool | None = None
    includeRepos: list[str] | None = None
    excludeRepos: list[str] | None = None


@tag("default-maven-project-group")
@dataclass(frozen=True)
class DefaultMavenProjectGroupCommand:
    group: str


@tag("default-company-email")
@dataclass(frozen=True)
class DefaultCompanyEmailCommand:
    email: str


@tag("default-company-legal-name")
@dataclass(frozen=True)
class DefaultCompanyLegalNameCommand:
    name: str


@tag("default-company-short-name")
@dataclass(frozen=True)
class DefaultCompanyShortNameCommand:
    name: str


@tag("code-owner")
@dataclass(frozen=True)
class CodeOwnerCommand:
    name: str
    email: str


@tag("git-user")
@dataclass(frozen=True)
class GitUserCommand:
    name: str
    email: str


@tag("git-censor")
@dataclass(frozen=True)
class GitCensorCommand:
    name: str | None = None
    email: str | None = None


@tag("jvm-version")
@dataclass(frozen=True)
class JvmVersionCommand:
    version: int | str


@tag("jvm-defaults")
@dataclass(frozen=True)
class JvmDefaultsCommand:
    version: int | str | None = None


@tag("python-defaults")
@dataclass(frozen=True)
class PythonDefaultsCommand:
    requires_python: str | None = None
    line_length: int | str | None = None
    coverage_fail_under: int | str | None = None


@tag("jvm-kotlin-library")
@dataclass(frozen=True)
class JvmKotlinLibraryCommand:
    pass


@tag("kotlin-gradle-plugin-library")
@dataclass(frozen=True)
class KotlinGradlePluginLibraryCommand:
    pass


@tag("jvm-scala-library")
@dataclass(frozen=True)
class JvmScalaLibraryCommand:
    pass


@tag("jvm-kotlin-application")
@dataclass(frozen=True)
class JvmKotlinApplicationCommand:
    main: str
    jar: str | None = None


@tag("shadow-jar")
@dataclass(frozen=True)
class ShadowJarCommand:
    jar: str | None = None


@tag("paper-plugin")
@dataclass(frozen=True)
class PaperPluginCommand:
    name: str
    main: str
    apiVersion: str
    depend: list[str] | None = None


@tag("jvm-kotlin-agent")
@dataclass(frozen=True)
class JvmKotlinAgentCommand:
    main: str
    jar: str | None = None


@tag("intellij-plugin")
@dataclass(frozen=True)
class IntellijPluginCommand:
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


@tag("intellij-platform-library")
@dataclass(frozen=True)
class IntellijPlatformLibraryCommand:
    ideaVersion: str | None = None
    bundledPlugins: list[str] | None = None
    modulePlugin: bool = True


@tag("kotlin-serialization")
@dataclass(frozen=True)
class KotlinSerializationCommand:
    pass


@tag("kotlin-compose-plugin")
@dataclass(frozen=True)
class KotlinComposePluginCommand:
    pass


@tag("gradle-plugin")
@dataclass(frozen=True)
class GradlePluginCommand:
    name: str
    compilerOptions: dict[str, str] | None = None


@tag("kotlin-compiler-plugin")
@dataclass(frozen=True)
class KotlinCompilerPluginCommand:
    compatibilitySources: dict[str, str] | None = None
    publishVersionWithKotlin: bool = True


@tag("kotlin-compiler-gradle-plugin")
@dataclass(frozen=True)
class KotlinCompilerGradlePluginCommand:
    compilerPluginProject: str
    versionPackage: str | None = None
    versionClassName: str | None = None
    versionConstantName: str | None = None


@tag("kmp-android-library")
@dataclass(frozen=True)
class KmpAndroidLibraryCommand:
    namespace: str
    compileSdk: int
    minSdk: int
    manifestPath: str = "src/androidMain/AndroidManifest.xml"


@tag("kmp-compose")
@dataclass(frozen=True)
class KmpComposeCommand:
    publicResClass: bool = True
    resClassPackage: str | None = None


@dataclass(frozen=True)
class KmpJvmRunEntryCommand:
    taskName: str
    mainClass: str
    description: str
    jvmArgs: list[str] | None = None


@tag("kmp-jvm-runs")
@dataclass(frozen=True)
class KmpJvmRunsCommand:
    entries: typing.Annotated[list[KmpJvmRunEntryCommand], DecodeWith(_decode_kmp_jvm_run_entries)]


@dataclass(frozen=True)
class GradleSourceSetCommand:
    dependsOn: list[str] | None = None
    dependencies: list[DependencyInput] | None = None
    kotlinSrcDirs: list[str] | None = None


@dataclass(frozen=True)
class GradleTargetCommand:
    kind: str
    name: str | None = None
    namespace: str | None = None
    applicationId: str | None = None
    compileSdk: int | None = None
    minSdk: int | None = None
    targetSdk: int | None = None
    manifestPath: str | None = None
    browser: bool | None = None
    browserTest: str | None = None
    executable: bool | None = None


@tag("python-deptry")
@dataclass(frozen=True)
class PythonDeptryCommand:
    package_map: dict[str, str] | None = None
    per_rule_ignores: dict[str, list[str]] | None = None
    auto_package_map: bool = False


@tag("python-importlinter")
@dataclass(frozen=True)
class PythonImportlinterCommand:
    root_packages: list[str] | None = None
    layers: list[str] | None = None


@tag("python-application")
@dataclass(frozen=True)
class PythonApplicationCommand:
    script: str
    entry: str
    path: str = "main.py"
    aliases: list[str] | None = None


PythonFeatureCommand = PythonApplicationCommand


FeatureCommand = (
    JvmKotlinLibraryCommand
    | KotlinGradlePluginLibraryCommand
    | JvmScalaLibraryCommand
    | JvmKotlinApplicationCommand
    | ShadowJarCommand
    | PaperPluginCommand
    | JvmKotlinAgentCommand
    | IntellijPluginCommand
    | IntellijPlatformLibraryCommand
    | KotlinSerializationCommand
    | KotlinComposePluginCommand
    | GradlePluginCommand
    | KotlinCompilerPluginCommand
    | KotlinCompilerGradlePluginCommand
    | KmpAndroidLibraryCommand
    | KmpComposeCommand
    | KmpJvmRunsCommand
    | PythonDeptryCommand
    | PythonImportlinterCommand
)


@tag("dep")
@dataclass(frozen=True)
class DepCall:
    name: str
    modifier: str | None = None


DependencyInput = bool | None | str | DepCall


@tag("define-maven-repo")
@dataclass(frozen=True)
class DefineMavenRepoCommand:
    name: str
    url: str


@tag("define-kotlin-plugin")
@dataclass(frozen=True)
class DefineKotlinPluginCommand:
    name: str
    value: str
    repo: str | None = None
    compilerPlugin: str | None = None
    compilerPluginId: str | None = None


@tag("add-default-gradle-plugin")
@dataclass(frozen=True)
class AddDefaultGradlePluginCommand:
    name: str
    compilerOptions: dict[str, str] | None = None


@tag("define-maven-library")
@dataclass(frozen=True)
class DefineMavenLibraryCommand:
    name: str
    maven_urn: typing.Annotated[MavenCoordinateExpr, DecodeWith(_decode_maven_coordinate_expr)]
    repo: str | None = None


LibraryGroupChild = bool | None | str | DepCall


@tag("define-maven-library-group")
@dataclass(frozen=True)
class DefineMavenLibraryGroupCommand:
    name: str
    children: list[LibraryGroupChild]


@tag("python")
@dataclass(frozen=True)
class PythonProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    quarantine: bool = False
    publish: bool = True
    requires_python: str | None = None
    dependencies: list[str] | None = None
    dev_dependencies: list[str] | None = None
    scripts: list[str] | None = None
    features: list[PythonFeatureCommand] | None = None
    homepage: str | None = None
    repository: str | None = None
    keywords: list[str] | None = None
    classifiers: list[str] | None = None
    publishTarget: str | None = None
    publishSnapshots: bool | None = None
    docs: bool | None = None
    docsSystem: str | None = None
    repo: str | None = None
    ownership: str | None = None
    testLicense: str | None = None


@tag("purescript")
@dataclass(frozen=True)
class PurescriptProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    quarantine: bool = False
    license: str | None = "AGPL"
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    publish: bool = True
    repo: str | None = None
    ownership: str | None = None
    testLicense: str | None = None


@tag("data")
@dataclass(frozen=True)
class DataProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    quarantine: bool = False
    publish: bool = True
    repo: str | None = None
    ownership: str | None = None
    testLicense: str | None = None
    preserveLegalFiles: bool | None = None


@tag("premake")
@dataclass(frozen=True)
class PremakeProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    quarantine: bool = False
    publish: bool = True
    repo: str | None = None
    ownership: str | None = None
    testLicense: str | None = None


@tag("gradle")
@dataclass(frozen=True)
class GradleProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    quarantine: bool = False
    publish: bool = True
    buildModel: str | None = None
    gradleProjectName: str | None = None
    artifactId: str | None = None
    gradlePluginId: str | None = None
    platforms: list[str] | None = None
    targets: typing.Annotated[list[GradleTargetCommand] | None, DecodeWith(_decode_gradle_target_commands)] = None
    dependencies: list[DependencyInput] | None = None
    sourceSetDependencies: typing.Annotated[
        dict[str, list[DependencyInput]] | None,
        DecodeWith(_decode_gradle_source_set_dependencies),
    ] = None
    sourceSets: typing.Annotated[
        dict[str, GradleSourceSetCommand] | None,
        DecodeWith(_decode_gradle_source_sets),
    ] = None
    buildInlineFile: str | None = None
    kotlinFreeCompilerArgs: list[str] | None = None
    dokkaSuppressSourceSets: list[str] | None = None
    features: list[FeatureCommand] | None = None
    publishTarget: str | None = None
    publishSnapshots: bool | None = None
    docs: bool | None = None
    docsSystem: str | None = None
    versionFromRepo: bool = False
    jvmPolicy: str | None = None
    jvmTaskPolicies: dict[str, str] | None = None
    repo: str | None = None
    ownership: str | None = None
    testLicense: str | None = None


@tag("fsharp")
@dataclass(frozen=True)
class FsharpProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    quarantine: bool = False
    publish: bool = True
    projectKind: str | None = None
    targetFramework: str | None = None
    targetFrameworks: list[str] | None = None
    sdk: str | None = None
    outputType: str | None = None
    assemblyName: str | None = None
    rootNamespace: str | None = None
    packageId: str | None = None
    packageTags: list[str] | None = None
    generateDocumentationFile: bool | None = None
    nullable: bool | None = None
    implicitUsings: bool | None = None
    langVersion: str | None = None
    dependencies: list[str] | None = None
    publishTarget: str | None = None
    publishSnapshots: bool | None = None
    docs: bool | None = None
    docsSystem: str | None = None
    repo: str | None = None
    ownership: str | None = None
    testLicense: str | None = None


@tag("csharp")
@dataclass(frozen=True)
class CsharpProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    copyright_holder: str | None = None
    copyright_year_start: int | None = None
    quarantine: bool = False
    publish: bool = True
    projectKind: str | None = None
    targetFramework: str | None = None
    targetFrameworks: list[str] | None = None
    sdk: str | None = None
    outputType: str | None = None
    assemblyName: str | None = None
    rootNamespace: str | None = None
    packageId: str | None = None
    packageTags: list[str] | None = None
    generateDocumentationFile: bool | None = None
    nullable: bool | None = None
    implicitUsings: bool | None = None
    langVersion: str | None = None
    dependencies: list[str] | None = None
    publishTarget: str | None = None
    publishSnapshots: bool | None = None
    docs: bool | None = None
    docsSystem: str | None = None
    repo: str | None = None
    ownership: str | None = None
    testLicense: str | None = None


RepoProjectCommand = (
    PythonProjectCommand
    | PurescriptProjectCommand
    | DataProjectCommand
    | PremakeProjectCommand
    | GradleProjectCommand
    | FsharpProjectCommand
    | CsharpProjectCommand
)


@tag("repo")
@dataclass(frozen=True)
class RepoCommand:
    dir_name: str
    repo: str | None = None
    gradleRootProjectName: str | None = None
    projectVersion: str | None = None
    defaultKotlinVersion: str | None = None
    supportedKotlinVersions: list[str] | None = None
    dotnetSdkVersion: str | None = None
    defaultTargetFramework: str | None = None
    solutionName: str | None = None
    useCentralPackageManagement: bool | None = None
    jvmPolicy: str | None = None
    docsProject: str | None = None
    projects: list[RepoProjectCommand] | None = None


BuiltinTopLevelCommand = (
    ChecksDisableCommand
    | ChecksIgnoreFindingCommand
    | DefineCommand
    | OpenaiKeyCommand
    | GithubTokenCommand
    | GithubSshKeyCommand
    | AnthropicKeyCommand
    | JetbrainsMarketplaceTokenCommand
    | PypiTokenCommand
    | NugetApiKeyCommand
    | MavenUsernameCommand
    | MavenPasswordCommand
    | MavenGpgPrivateKeyCommand
    | MavenGpgPassphraseCommand
    | MavenGpgKeyIdCommand
    | JitpackCookieCommand
    | DefineBackupTargetCommand
    | BackupPolicyCommand
    | DefaultMavenProjectGroupCommand
    | DefaultCompanyEmailCommand
    | DefaultCompanyLegalNameCommand
    | DefaultCompanyShortNameCommand
    | CodeOwnerCommand
    | GitUserCommand
    | GitCensorCommand
    | JvmVersionCommand
    | JvmDefaultsCommand
    | PythonDefaultsCommand
    | DefineMavenRepoCommand
    | DefineKotlinPluginCommand
    | AddDefaultGradlePluginCommand
    | DefineMavenLibraryCommand
    | DefineMavenLibraryGroupCommand
    | PythonProjectCommand
    | PurescriptProjectCommand
    | DataProjectCommand
    | PremakeProjectCommand
    | GradleProjectCommand
    | FsharpProjectCommand
    | CsharpProjectCommand
    | RepoCommand
)


BUILTIN_TOPLEVEL_COMMAND_TYPES: tuple[type[object], ...] = (
    ChecksDisableCommand,
    ChecksIgnoreFindingCommand,
    DefineCommand,
    OpenaiKeyCommand,
    GithubTokenCommand,
    GithubSshKeyCommand,
    AnthropicKeyCommand,
    JetbrainsMarketplaceTokenCommand,
    PypiTokenCommand,
    NugetApiKeyCommand,
    MavenUsernameCommand,
    MavenPasswordCommand,
    MavenGpgPrivateKeyCommand,
    MavenGpgPassphraseCommand,
    MavenGpgKeyIdCommand,
    JitpackCookieCommand,
    DefineBackupTargetCommand,
    BackupPolicyCommand,
    DefaultMavenProjectGroupCommand,
    DefaultCompanyEmailCommand,
    DefaultCompanyLegalNameCommand,
    DefaultCompanyShortNameCommand,
    CodeOwnerCommand,
    GitUserCommand,
    GitCensorCommand,
    JvmVersionCommand,
    JvmDefaultsCommand,
    PythonDefaultsCommand,
    DefineMavenRepoCommand,
    DefineKotlinPluginCommand,
    AddDefaultGradlePluginCommand,
    DefineMavenLibraryCommand,
    DefineMavenLibraryGroupCommand,
    PythonProjectCommand,
    PurescriptProjectCommand,
    DataProjectCommand,
    PremakeProjectCommand,
    GradleProjectCommand,
    FsharpProjectCommand,
    CsharpProjectCommand,
    RepoCommand,
)


TopLevelTarget = type[object] | UnionType


def make_top_level_target(extra_command_types: Sequence[type[object]]) -> TopLevelTarget:
    command_types: tuple[type[object], ...] = tuple(BUILTIN_TOPLEVEL_COMMAND_TYPES) + tuple(extra_command_types)
    if not command_types:
        raise ValueError("No command types provided")
    if len(command_types) == 1:
        return command_types[0]
    target: TopLevelTarget = command_types[0]
    for item in command_types[1:]:
        target = target | item
    return target


__all__ = [
    "BUILTIN_TOPLEVEL_COMMAND_TYPES",
    "BuiltinTopLevelCommand",
    "ChecksDisableCommand",
    "ChecksIgnoreFindingCommand",
    "CodeOwnerCommand",
    "Const",
    "BackupPolicyCommand",
    "DataProjectCommand",
    "CsharpProjectCommand",
    "DefaultMavenProjectGroupCommand",
    "DefineBackupTargetCommand",
    "DefineCommand",
    "AddDefaultGradlePluginCommand",
    "DefineKotlinPluginCommand",
    "DefineMavenLibraryCommand",
    "DefineMavenLibraryGroupCommand",
    "DefineMavenRepoCommand",
    "DependencyInput",
    "DepCall",
    "FeatureCommand",
    "GitCensorCommand",
    "GithubSshKeyCommand",
    "GithubTokenCommand",
    "GitUserCommand",
    "GradleProjectCommand",
    "GradlePluginCommand",
    "GradleSourceSetCommand",
    "GradleTargetCommand",
    "IntellijPluginCommand",
    "JetbrainsMarketplaceTokenCommand",
    "JitpackCookieCommand",
    "JvmDefaultsCommand",
    "KmpAndroidLibraryCommand",
    "KmpComposeCommand",
    "KmpJvmRunEntryCommand",
    "KmpJvmRunsCommand",
    "JvmKotlinAgentCommand",
    "JvmKotlinApplicationCommand",
    "JvmKotlinLibraryCommand",
    "JvmScalaLibraryCommand",
    "JvmVersionCommand",
    "KotlinCompilerGradlePluginCommand",
    "KotlinCompilerPluginCommand",
    "KotlinSerializationCommand",
    "LibraryGroupChild",
    "MavenCoordinateExpr",
    "MavenGpgKeyIdCommand",
    "MavenGpgPassphraseCommand",
    "MavenGpgPrivateKeyCommand",
    "MavenPasswordCommand",
    "MavenUsernameCommand",
    "NugetApiKeyCommand",
    "OpenaiKeyCommand",
    "PaperPluginCommand",
    "PypiTokenCommand",
    "PremakeProjectCommand",
    "RepoCommand",
    "RepoProjectCommand",
    "FsharpProjectCommand",
    "PurescriptProjectCommand",
    "PythonDefaultsCommand",
    "PythonApplicationCommand",
    "PythonDeptryCommand",
    "PythonFeatureCommand",
    "PythonImportlinterCommand",
    "PythonProjectCommand",
    "ShadowJarCommand",
    "Value",
    "VarName",
    "AnthropicKeyCommand",
    "make_top_level_target",
]
