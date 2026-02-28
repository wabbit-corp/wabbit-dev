from __future__ import annotations

import re
import typing
from collections.abc import Sequence
from dataclasses import dataclass
from types import UnionType

from mu.typed import DecodeContext, DecodeError, DecodeWith, tag
from mu.types import AtomExpr, Expr, StringExpr


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


@tag("anthropic-key")
@dataclass(frozen=True)
class AnthropicKeyCommand:
    key: str


@tag("jitpack-cookie")
@dataclass(frozen=True)
class JitpackCookieCommand:
    cookie: str


@tag("default-maven-project-group")
@dataclass(frozen=True)
class DefaultMavenProjectGroupCommand:
    group: str


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


@tag("jvm-scala-library")
@dataclass(frozen=True)
class JvmScalaLibraryCommand:
    pass


@tag("jvm-kotlin-application")
@dataclass(frozen=True)
class JvmKotlinApplicationCommand:
    main: str
    jar: str | None = None


@tag("paper-plugin")
@dataclass(frozen=True)
class PaperPluginCommand:
    name: str
    main: str
    apiVersion: str


@tag("jvm-kotlin-agent")
@dataclass(frozen=True)
class JvmKotlinAgentCommand:
    main: str
    jar: str | None = None


@tag("intellij-plugin")
@dataclass(frozen=True)
class IntellijPluginCommand:
    pluginName: str


@tag("kotlin-serialization")
@dataclass(frozen=True)
class KotlinSerializationCommand:
    pass


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
    | JvmScalaLibraryCommand
    | JvmKotlinApplicationCommand
    | PaperPluginCommand
    | JvmKotlinAgentCommand
    | IntellijPluginCommand
    | KotlinSerializationCommand
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
    repo: str | None = None
    ownership: str | None = None


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
    publish: bool = True
    repo: str | None = None
    ownership: str | None = None


@tag("data")
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


@tag("premake")
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


@tag("gradle")
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


BUILTIN_TOPLEVEL_COMMAND_TYPES: tuple[type[object], ...] = (
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
    "PythonApplicationCommand",
    "PythonDeptryCommand",
    "PythonFeatureCommand",
    "PythonImportlinterCommand",
    "PythonProjectCommand",
    "Value",
    "VarName",
    "AnthropicKeyCommand",
    "make_top_level_target",
]
