from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Sequence, TypeVar, Union
import typing
import re

from mu.typed import MuDecodeContext, MuDecodeError, MuDeserialize, mu_tag
from mu.types import SAtom, SExpr, SStr


T = TypeVar("T")


@dataclass(frozen=True)
class Const(Generic[T]):
    value: T


@dataclass(frozen=True)
class VarName:
    name: str


Value = Const[T] | VarName


@dataclass(frozen=True)
class MavenCoordinateExpr:
    group_id: str
    artifact_id: str
    version: Value[str]
    suffix: str | None = None


_VAR_PATTERN = re.compile(r"^\$\{([^:{}]+)\}$")


def _decode_symbol_atom(expr: SExpr, _ctx: MuDecodeContext) -> str:
    if not isinstance(expr, SAtom):
        raise MuDecodeError(
            path=_ctx.path,
            expected="symbol atom",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )
    return expr.value


def _decode_issue_name_or_star(expr: SExpr, ctx: MuDecodeContext) -> str:
    if isinstance(expr, SStr):
        value = expr.value
    elif isinstance(expr, SAtom):
        value = expr.value
    else:
        raise MuDecodeError(
            path=ctx.path,
            expected="issue id string (E_...) or *",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )

    if value == "*" or re.fullmatch(r"E_[A-Z0-9_]+", value):
        return value

    raise MuDecodeError(
        path=ctx.path,
        expected="issue id string (E_...) or *",
        got=value,
        span=getattr(expr, "span", None),
    )


def _decode_maven_coordinate_expr(expr: SExpr, ctx: MuDecodeContext) -> MavenCoordinateExpr:
    if isinstance(expr, SStr):
        raw = expr.value
    elif isinstance(expr, SAtom):
        raw = expr.value
    else:
        raise MuDecodeError(
            path=ctx.path,
            expected="maven coordinate string",
            got=type(expr).__name__,
            span=getattr(expr, "span", None),
        )

    parts = raw.split(":")
    if len(parts) < 3:
        raise MuDecodeError(
            path=ctx.path,
            expected="maven coordinate group:artifact:version[:classifier...]",
            got=raw,
            span=getattr(expr, "span", None),
        )

    group_id, artifact_id = parts[0], parts[1]
    version_text = parts[2]
    suffix = ":".join(parts[3:]) if len(parts) > 3 else None

    if "${" in group_id or "${" in artifact_id or (suffix and "${" in suffix):
        raise MuDecodeError(
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
            raise MuDecodeError(
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


@mu_tag("checks/disable")
@dataclass(frozen=True)
class ChecksDisableCommand:
    error_name: str
    pathspec: str


@mu_tag("checks/ignore-finding")
@dataclass(frozen=True)
class ChecksIgnoreFindingCommand:
    error_name: typing.Annotated[str, MuDeserialize(_decode_issue_name_or_star)]
    pathspec: str
    value: str


@mu_tag("define")
@dataclass(frozen=True)
class DefineCommand:
    name: typing.Annotated[str, MuDeserialize(_decode_symbol_atom)]
    value: Any


@mu_tag("openai-key")
@dataclass(frozen=True)
class OpenaiKeyCommand:
    key: str


@mu_tag("github-token")
@dataclass(frozen=True)
class GithubTokenCommand:
    token: str


@mu_tag("anthropic-key")
@dataclass(frozen=True)
class AnthropicKeyCommand:
    key: str


@mu_tag("jitpack-cookie")
@dataclass(frozen=True)
class JitpackCookieCommand:
    cookie: str


@mu_tag("default-maven-project-group")
@dataclass(frozen=True)
class DefaultMavenProjectGroupCommand:
    group: str


@mu_tag("git-user")
@dataclass(frozen=True)
class GitUserCommand:
    name: str
    email: str


@mu_tag("git-censor")
@dataclass(frozen=True)
class GitCensorCommand:
    name: str | None = None
    email: str | None = None


@mu_tag("jvm-version")
@dataclass(frozen=True)
class JvmVersionCommand:
    version: int | str


@mu_tag("jvm-defaults")
@dataclass(frozen=True)
class JvmDefaultsCommand:
    version: int | str | None = None


@mu_tag("python-defaults")
@dataclass(frozen=True)
class PythonDefaultsCommand:
    line_length: int | str | None = None
    target_version: str | None = None
    coverage_fail_under: int | str | None = None
    coverage_precision: int | str | None = None
    coverage_branch: bool | None = None
    coverage_show_missing: bool | None = None
    coverage_skip_empty: bool | None = None
    coverage_xml_output: str | None = None


@mu_tag("jvm-kotlin-library")
@dataclass(frozen=True)
class JvmKotlinLibraryCommand:
    pass


@mu_tag("jvm-scala-library")
@dataclass(frozen=True)
class JvmScalaLibraryCommand:
    pass


@mu_tag("jvm-kotlin-application")
@dataclass(frozen=True)
class JvmKotlinApplicationCommand:
    main: str
    jar: str | None = None


@mu_tag("paper-plugin")
@dataclass(frozen=True)
class PaperPluginCommand:
    name: str
    main: str
    apiVersion: str


@mu_tag("jvm-kotlin-agent")
@dataclass(frozen=True)
class JvmKotlinAgentCommand:
    main: str
    jar: str | None = None


@mu_tag("intellij-plugin")
@dataclass(frozen=True)
class IntellijPluginCommand:
    pluginName: str


@mu_tag("kotlin-serialization")
@dataclass(frozen=True)
class KotlinSerializationCommand:
    pass


@mu_tag("python-deptry")
@dataclass(frozen=True)
class PythonDeptryCommand:
    package_map: dict[str, str] | None = None
    per_rule_ignores: dict[str, list[str]] | None = None
    auto_package_map: bool = False


@mu_tag("python-importlinter")
@dataclass(frozen=True)
class PythonImportlinterCommand:
    root_packages: list[str] | None = None
    layers: list[str] | None = None


FeatureCommand = (
    JvmKotlinLibraryCommand
    | JvmScalaLibraryCommand
    | JvmKotlinApplicationCommand
    | PaperPluginCommand
    | JvmKotlinAgentCommand
    | IntellijPluginCommand
    | KotlinSerializationCommand
    | PythonDeptryCommand
    | PythonImportlinterCommand
)


@mu_tag("dep")
@dataclass(frozen=True)
class DepCall:
    name: str
    modifier: str | None = None


DependencyInput = bool | None | str | DepCall


@mu_tag("define-maven-repo")
@dataclass(frozen=True)
class DefineMavenRepoCommand:
    name: str
    url: str


@mu_tag("define-kotlin-plugin")
@dataclass(frozen=True)
class DefineKotlinPluginCommand:
    name: str
    value: str
    repo: str | None = None


@mu_tag("define-maven-library")
@dataclass(frozen=True)
class DefineMavenLibraryCommand:
    name: str
    maven_urn: typing.Annotated[MavenCoordinateExpr, MuDeserialize(_decode_maven_coordinate_expr)]
    repo: str | None = None


LibraryGroupChild = bool | None | str | DepCall


@mu_tag("define-maven-library-group")
@dataclass(frozen=True)
class DefineMavenLibraryGroupCommand:
    name: str
    children: list[LibraryGroupChild]


@mu_tag("python")
@dataclass(frozen=True)
class PythonProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    quarantine: bool = False
    publish: bool = True
    requires_python: str | None = None
    dependencies: list[str] | None = None
    dev_dependencies: list[str] | None = None
    scripts: list[str] | None = None
    features: list[FeatureCommand] | None = None
    source_sets: list[Any] | None = None
    line_length: int | str | None = None
    target_version: str | None = None
    test_paths: list[str] | None = None
    ruff_per_file_ignores: dict[str, list[str]] | None = None
    deptry_package_map: dict[str, str] | None = None
    deptry_per_rule_ignores: dict[str, list[str]] | None = None
    importlinter_root_packages: list[str] | None = None
    importlinter_contracts: list[dict[str, Any]] | None = None
    coverage_source: list[str] | None = None
    coverage_omit: list[str] | None = None
    coverage_fail_under: int | str | None = None
    coverage_precision: int | str | None = None
    coverage_branch: bool | None = None
    coverage_show_missing: bool | None = None
    coverage_skip_empty: bool | None = None
    coverage_xml_output: str | None = None
    repo: str | None = None
    ownership: str | None = None


@mu_tag("purescript")
@dataclass(frozen=True)
class PurescriptProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    quarantine: bool = False
    license: str | None = "AGPL"
    publish: bool = True
    repo: str | None = None
    ownership: str | None = None


@mu_tag("data")
@dataclass(frozen=True)
class DataProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    quarantine: bool = False
    publish: bool = True
    repo: str | None = None
    ownership: str | None = None


@mu_tag("premake")
@dataclass(frozen=True)
class PremakeProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    quarantine: bool = False
    publish: bool = True
    repo: str | None = None
    ownership: str | None = None


@mu_tag("gradle")
@dataclass(frozen=True)
class GradleProjectCommand:
    dir_name: str
    version: str
    name: str | None = None
    description: str | None = None
    authors: list[str] | None = None
    license: str | None = "AGPL"
    quarantine: bool = False
    publish: bool = True
    dependencies: list[DependencyInput] | None = None
    features: list[FeatureCommand] | None = None
    repo: str | None = None
    ownership: str | None = None


BuiltinTopLevelCommand = (
    ChecksDisableCommand
    | ChecksIgnoreFindingCommand
    | DefineCommand
    | OpenaiKeyCommand
    | GithubTokenCommand
    | AnthropicKeyCommand
    | JitpackCookieCommand
    | DefaultMavenProjectGroupCommand
    | GitUserCommand
    | GitCensorCommand
    | JvmVersionCommand
    | JvmDefaultsCommand
    | PythonDefaultsCommand
    | DefineMavenRepoCommand
    | DefineKotlinPluginCommand
    | DefineMavenLibraryCommand
    | DefineMavenLibraryGroupCommand
    | PythonProjectCommand
    | PurescriptProjectCommand
    | DataProjectCommand
    | PremakeProjectCommand
    | GradleProjectCommand
)


BUILTIN_TOPLEVEL_COMMAND_TYPES: tuple[type[Any], ...] = (
    ChecksDisableCommand,
    ChecksIgnoreFindingCommand,
    DefineCommand,
    OpenaiKeyCommand,
    GithubTokenCommand,
    AnthropicKeyCommand,
    JitpackCookieCommand,
    DefaultMavenProjectGroupCommand,
    GitUserCommand,
    GitCensorCommand,
    JvmVersionCommand,
    JvmDefaultsCommand,
    PythonDefaultsCommand,
    DefineMavenRepoCommand,
    DefineKotlinPluginCommand,
    DefineMavenLibraryCommand,
    DefineMavenLibraryGroupCommand,
    PythonProjectCommand,
    PurescriptProjectCommand,
    DataProjectCommand,
    PremakeProjectCommand,
    GradleProjectCommand,
)


def make_top_level_target(extra_command_types: Sequence[type[Any]]) -> Any:
    command_types = tuple(BUILTIN_TOPLEVEL_COMMAND_TYPES) + tuple(extra_command_types)
    if not command_types:
        raise ValueError("No command types provided")
    if len(command_types) == 1:
        return command_types[0]
    return Union[command_types]


__all__ = [
    "BUILTIN_TOPLEVEL_COMMAND_TYPES",
    "BuiltinTopLevelCommand",
    "ChecksDisableCommand",
    "ChecksIgnoreFindingCommand",
    "Const",
    "DataProjectCommand",
    "DefaultMavenProjectGroupCommand",
    "DefineCommand",
    "DefineKotlinPluginCommand",
    "DefineMavenLibraryCommand",
    "DefineMavenLibraryGroupCommand",
    "DefineMavenRepoCommand",
    "DependencyInput",
    "DepCall",
    "FeatureCommand",
    "GitCensorCommand",
    "GithubTokenCommand",
    "GitUserCommand",
    "GradleProjectCommand",
    "IntellijPluginCommand",
    "JitpackCookieCommand",
    "JvmDefaultsCommand",
    "JvmKotlinAgentCommand",
    "JvmKotlinApplicationCommand",
    "JvmKotlinLibraryCommand",
    "JvmScalaLibraryCommand",
    "JvmVersionCommand",
    "KotlinSerializationCommand",
    "LibraryGroupChild",
    "MavenCoordinateExpr",
    "OpenaiKeyCommand",
    "PaperPluginCommand",
    "PremakeProjectCommand",
    "PurescriptProjectCommand",
    "PythonDefaultsCommand",
    "PythonDeptryCommand",
    "PythonImportlinterCommand",
    "PythonProjectCommand",
    "Value",
    "VarName",
    "AnthropicKeyCommand",
    "make_top_level_target",
]
