from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def _ensure_wabbit_cli_importable() -> bool:
    workspace_root = Path(__file__).resolve().parents[2]
    project_root = workspace_root / "python-wabbit-cli"
    package_root = project_root / "wabbit_cli"
    if not package_root.is_dir():
        return False
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)
    return True


async def maybe_run_typed_cli(argv: Sequence[str], *, prog: str) -> int | None:
    if not argv:
        return None
    if argv[0] not in {"docs", "release"}:
        return None
    if not _ensure_wabbit_cli_importable():
        return None

    from wabbit_cli import Argument, Command, CommandValue, Issue, ParsedValues, Validated, flag, positional, succeed

    @dataclass(frozen=True)
    class DocsCheckRequest:
        targets: list[str]
        semantic: bool
        json_output: bool

    @dataclass(frozen=True)
    class DocsSnippetsRequest:
        targets: list[str]
        verify: bool
        json_output: bool

    @dataclass(frozen=True)
    class ReleaseVerifyRequest:
        targets: list[str]
        json_output: bool

    TypedRequest = DocsCheckRequest | DocsSnippetsRequest | ReleaseVerifyRequest | None

    def _string_list(value: CommandValue) -> list[str]:
        match value:
            case [*items] if all(isinstance(item, str) for item in items):
                return [item for item in items if isinstance(item, str)]
            case str() as item:
                return [item]
            case _:
                return []

    def _bool_value(values: ParsedValues, name: str, default: bool = False) -> bool:
        raw = values.option_or(name, default)
        assert isinstance(raw, bool)
        return raw

    def _docs_check_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            DocsCheckRequest(
                targets=_string_list(values.positional("target")),
                semantic=_bool_value(values, "--semantic"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _docs_snippets_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            DocsSnippetsRequest(
                targets=_string_list(values.positional("target")),
                verify=_bool_value(values, "--verify"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _release_verify_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            ReleaseVerifyRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _unused_decode(_values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(None)

    def _root_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        match values.command_path:
            case ["docs", "check"]:
                return _docs_check_decode(values)
            case ["docs", "snippets"]:
                return _docs_snippets_decode(values)
            case ["release", "verify"]:
                return _release_verify_decode(values)
            case _:
                return _unused_decode(values)

    docs_check_command = Command(
        name="check",
        header="Check project documentation links, sections, snippets, and optional semantic quality.",
        options=(
            flag(long="semantic", help="Add an LLM-based advisory review for semantic docs quality issues."),
            flag(long="json", help="Emit a machine-readable docs report instead of human-oriented output."),
        ),
        positionals=(positional(Argument.string(), "target", help="Optional project or repo targets.", repeated=True),),
        decode=_unused_decode,
    )
    docs_snippets_command = Command(
        name="snippets",
        header="Check fenced documentation snippets with optional project-specific deeper verification.",
        options=(
            flag(long="verify", help="Enable deeper project-specific snippet verification."),
            flag(long="json", help="Emit a machine-readable snippet report instead of human-oriented output."),
        ),
        positionals=(positional(Argument.string(), "target", help="Optional project or repo targets.", repeated=True),),
        decode=_unused_decode,
    )
    docs_command = Command(
        name="docs",
        header="Validate project documentation quality.",
        subcommands=(docs_check_command, docs_snippets_command),
        decode=_unused_decode,
        help_on_empty=True,
    )
    release_verify_command = Command(
        name="verify",
        header="Verify publishable Python and Gradle projects and inspect release metadata.",
        options=(flag(long="json", help="Emit a machine-readable release verification report."),),
        positionals=(positional(Argument.string(), "target", help="Optional project or repo targets.", repeated=True),),
        decode=_unused_decode,
    )
    release_command = Command(
        name="release",
        header="Verify release readiness for publishable projects.",
        subcommands=(release_verify_command,),
        decode=_unused_decode,
        help_on_empty=True,
    )
    root = Command(
        name=prog,
        header="Wabbit development toolkit.",
        subcommands=(docs_command, release_command),
        decode=_root_decode,
    )

    def _on_parsed(request: TypedRequest, _issues: Sequence[Issue]) -> int:
        match request:
            case DocsCheckRequest(targets=targets, semantic=semantic, json_output=json_output):
                from dev.tasks.docs_check import docs_check

                return docs_check(targets, semantic=semantic, json_output=json_output)
            case DocsSnippetsRequest(targets=targets, verify=verify, json_output=json_output):
                from dev.tasks.docs_check import docs_snippets

                return docs_snippets(targets, verify=verify, json_output=json_output)
            case ReleaseVerifyRequest(targets=targets, json_output=json_output):
                from dev.tasks.release_verify import release_verify

                return release_verify(targets, json_output=json_output)
            case None:
                return 0

    return root.run(list(argv), on_parsed=_on_parsed)
