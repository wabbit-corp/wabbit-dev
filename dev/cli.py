import argparse
import asyncio
import logging
import os
import re
import sys
import textwrap
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Literal, NoReturn, Protocol, TypedDict, Unpack

from dev.bootstrap import canonical_rerun_command, maybe_reexec_to_workspace_venv
from dev.config import Config
from dev.discoverability import did_you_mean_suffix
from dev.json_types import JSONValue
from dev.messages import command_text, heading
from dev.tasks.completion import register_action_metadata, register_parser_child, register_parser_metadata

##################################################################################################
# Main
##################################################################################################

type ArgParser = argparse.ArgumentParser


class ParserKwargs(TypedDict, total=False):
    help: str
    description: str
    epilog: str
    formatter_class: type[argparse.HelpFormatter]


class ArgumentKwargs(TypedDict, total=False):
    action: str
    nargs: int | str | None
    type: Callable[[str], str | int | float] | str
    choices: Iterable[str]
    required: bool
    help: str
    metavar: str | tuple[str, ...]
    dest: str
    version: str
    default: JSONValue


class AddParser(Protocol):
    def __call__(self, name: str, **kwargs: Unpack[ParserKwargs]) -> ArgParser: ...


_INVALID_CHOICE_RE = re.compile(r"invalid choice: '([^']+)' \(choose from (.+)\)")
_CONFIG_CONTEXT_COMMANDS = {
    "where",
    "config/check",
    "doctor",
    "docs/check",
    "docs/snippets",
    "setup",
    "release/verify",
    "dep/graph",
    "dep/updates",
    "publish",
    "build",
    "clean",
    "cloc",
    "status",
    "commit",
    "push",
    "project/list",
    "project/show",
    "project/deps",
    "project/repo",
    "project/targets",
    "check",
    "spdx/headers",
    "secrets/scan",
    "contributors/audit",
}


class SuggestingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        match = _INVALID_CHOICE_RE.search(message)
        if match is not None:
            invalid = match.group(1)
            choices = [choice.strip().strip("'") for choice in match.group(2).split(",") if choice.strip().strip("'")]
            suggestion = did_you_mean_suffix(invalid, choices)
            if suggestion:
                message = f"{message}.{suggestion}"
        super().error(message)


class HelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    pass


def _add_argument(
    parser: argparse.ArgumentParser,
    *args: str,
    completion_kind: str | None = None,
    completion_allow_files: bool = False,
    completion_blocks_positionals: bool = False,
    **kwargs: Unpack[ArgumentKwargs],
) -> argparse.Action:
    action = parser.add_argument(*args, **kwargs)
    register_action_metadata(
        action,
        kind=completion_kind,
        allow_files=completion_allow_files,
        blocks_positionals=completion_blocks_positionals,
    )
    return action


def _doc(text: str) -> str:
    return textwrap.dedent(text).strip()


def _epilog(*, examples: Sequence[str] = (), notes: Sequence[str] = ()) -> str | None:
    sections: list[str] = []
    if examples:
        sections.append("Examples:\n" + "\n".join(f"  {example}" for example in examples))
    if notes:
        sections.append("Notes:\n" + "\n".join(f"  - {note}" for note in notes))
    if not sections:
        return None
    return "\n\n".join(sections)


def _normalize_cli_argv(raw_argv: Sequence[str], commands: "Commands") -> list[str]:
    argv = list(raw_argv)
    if not argv:
        return []

    if argv[0] == "check":
        if len(argv) == 1:
            return ["check", "run"]
        second = argv[1]
        if second in {"run", "list", "describe"}:
            return argv
        return ["check", "run", *argv[1:]]

    valid_paths = set(commands.parsers) | set(commands.subparsers)
    normalized: list[str] = []
    current_parts: list[str] = []
    index = 0

    while index < len(argv):
        token = argv[index]

        if token == "help" and index == len(argv) - 1:
            current_path = "/".join(current_parts)
            if not current_parts or current_path in valid_paths:
                normalized.append("--help")
                return normalized

        if token == "--" or token.startswith("-"):
            normalized.extend(argv[index:])
            return normalized

        if "/" in token:
            split_parts = [part for part in token.split("/") if part]
            split_path = "/".join([*current_parts, *split_parts])
            if split_parts and split_path in valid_paths:
                normalized.extend(split_parts)
                current_parts.extend(split_parts)
                index += 1
                continue

        candidate_path = "/".join([*current_parts, token])
        if candidate_path in valid_paths:
            normalized.append(token)
            current_parts.append(token)
            index += 1
            continue

        normalized.extend(argv[index:])
        return normalized

    return normalized


def _namespace_string_list(args: argparse.Namespace, key: str) -> list[str]:
    raw_value = args.__dict__.get(key)
    match raw_value:
        case []:
            return []
        case [str() as first, *rest] if all(isinstance(item, str) for item in rest):
            return [first, *rest]
        case _:
            return []


def _command_tokens(command_path: str, args: argparse.Namespace) -> list[str]:
    match command_path:
        case "where":
            tokens = ["where"]
            if args.json:
                tokens.append("--json")
            return tokens
        case "config/check":
            return ["config", "check"]
        case "doctor":
            tokens = ["doctor"]
            only_values = _namespace_string_list(args, "only")
            for value in only_values:
                tokens.extend(["--only", value])
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "docs/check":
            tokens = ["docs", "check"]
            if args.semantic:
                tokens.append("--semantic")
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "docs/snippets":
            tokens = ["docs", "snippets"]
            if args.verify:
                tokens.append("--verify")
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "setup":
            tokens = ["setup"]
            if args.dev:
                tokens.append("--dev")
            if args.local:
                tokens.append("--local")
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "release/verify":
            tokens = ["release", "verify"]
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "completion/bash":
            return ["completion", "bash"]
        case "completion/zsh":
            return ["completion", "zsh"]
        case "dep/updates":
            return ["dep", "updates"]
        case "dep/graph":
            tokens = ["dep", "graph"]
            if args.artifacts:
                tokens.append("--artifacts")
            tokens.extend(args.targets or [])
            return tokens
        case "publish":
            tokens = ["publish"]
            if args.dry_run:
                tokens.append("--dry-run")
            tokens.extend(args.targets or [])
            return tokens
        case "build":
            tokens = ["build"]
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "clean":
            return ["clean", *(args.targets or [])]
        case "cloc":
            return ["cloc", *(args.targets or [])]
        case "status":
            tokens = ["status"]
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "commit":
            tokens = ["commit"]
            if args.dry_run:
                tokens.append("--dry-run")
            tokens.extend(args.targets or [])
            return tokens
        case "push":
            tokens = ["push"]
            if args.dry_run:
                tokens.append("--dry-run")
            tokens.extend(args.targets or [])
            return tokens
        case "project/list":
            return ["project", "list"]
        case "project/show":
            tokens = ["project", "show"]
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "project/deps":
            tokens = ["project", "deps"]
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "project/repo":
            tokens = ["project", "repo"]
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "project/targets":
            tokens = ["project", "targets"]
            if args.json:
                tokens.append("--json")
            tokens.extend(args.targets or [])
            return tokens
        case "check/run":
            tokens = ["check"]
            if args.fix:
                tokens.append("--fix")
            if args.project_or_dir_or_file is not None:
                tokens.append(args.project_or_dir_or_file)
            tokens.extend(args.checks or [])
            return tokens
        case "check/list":
            tokens = ["check", "list"]
            if args.json:
                tokens.append("--json")
            return tokens
        case "check/describe":
            tokens = ["check", "describe", args.check]
            if args.json:
                tokens.append("--json")
            return tokens
        case "spdx/headers":
            tokens = ["spdx", "headers"]
            if args.fix:
                tokens.append("--fix")
            if args.project_or_dir_or_file is not None:
                tokens.append(args.project_or_dir_or_file)
            return tokens
        case "secrets/scan":
            tokens = ["secrets", "scan"]
            if args.target is not None:
                tokens.append(args.target)
            return tokens
        case "contributors/audit":
            return ["contributors", "audit"]
        case _:
            return [part for part in command_path.split("/") if part]


def _format_failure_context() -> str:
    try:
        from dev.repo_resolution import format_workspace_context, resolve_workspace_context

        return format_workspace_context(resolve_workspace_context())
    except Exception:
        from dev.bootstrap import find_workspace_root

        cwd = Path.cwd().resolve()
        workspace_root = find_workspace_root(cwd)
        workspace_root_text = str(workspace_root) if workspace_root is not None else "-"
        return "\n".join(
            [
                "Resolved context:",
                f"  cwd: {cwd}",
                f"  workspace root: {workspace_root_text}",
                "  current project: -",
                "  current repo: -",
            ]
        )


def _print_failure_context(command_path: str, *, args: argparse.Namespace) -> None:
    if command_path not in _CONFIG_CONTEXT_COMMANDS:
        return

    print(_format_failure_context(), file=sys.stderr)
    rerun_command = canonical_rerun_command(_command_tokens(command_path, args))
    if rerun_command is None:
        return

    print(file=sys.stderr)
    print(heading("Retry from workspace root:", stream=sys.stderr), file=sys.stderr)
    print(f"  {command_text(rerun_command, stream=sys.stderr)}", file=sys.stderr)


def _guidance_target(args: argparse.Namespace) -> str | None:
    if hasattr(args, "targets"):
        targets = args.targets
        if isinstance(targets, list) and targets and isinstance(targets[0], str):
            return targets[0]

    if hasattr(args, "target"):
        target = args.target
        if isinstance(target, str) and target not in {".", ":root"}:
            return target

    if hasattr(args, "project_or_dir_or_file"):
        project_or_dir_or_file = args.project_or_dir_or_file
        if isinstance(project_or_dir_or_file, str) and project_or_dir_or_file not in {".", ":root"}:
            return project_or_dir_or_file

    return None


def _load_workspace_config() -> Config | None:
    from dev.config import find_workspace_root, load_config

    if find_workspace_root() is None:
        return None
    try:
        return load_config()
    except Exception:
        return None


def _apply_context_defaults(command_path: str, args: argparse.Namespace) -> None:
    config = _load_workspace_config()
    if config is None:
        return

    from dev.repo_resolution import inferred_project_targets, inferred_repo_targets

    if command_path in {
        "docs/check",
        "docs/snippets",
        "setup",
        "build",
        "release/verify",
        "clean",
        "cloc",
        "dep/graph",
        "project/show",
        "project/deps",
        "project/targets",
    }:
        targets = getattr(args, "targets", None)
        if isinstance(targets, list) and not targets:
            inferred_targets = inferred_project_targets(config)
            if inferred_targets is not None:
                args.targets = inferred_targets

    if command_path in {"project/repo", "status"}:
        targets = getattr(args, "targets", None)
        if isinstance(targets, list) and not targets:
            inferred_targets = inferred_repo_targets(config)
            if inferred_targets is not None:
                args.targets = inferred_targets

    if command_path == "check/run" and getattr(args, "project_or_dir_or_file", None) is None:
        inferred_targets = inferred_project_targets(config)
        if inferred_targets is not None:
            args.project_or_dir_or_file = inferred_targets[0]

    if command_path == "spdx/headers" and getattr(args, "project_or_dir_or_file", None) is None:
        inferred_targets = inferred_project_targets(config)
        if inferred_targets is not None:
            args.project_or_dir_or_file = inferred_targets[0]

    if command_path == "secrets/scan" and getattr(args, "target", None) is None:
        inferred_targets = inferred_project_targets(config)
        if inferred_targets is not None:
            args.target = inferred_targets[0]


def _print_next_steps(command_path: str, *, prog: str, args: argparse.Namespace) -> None:
    if getattr(args, "json", False):
        return

    target = _guidance_target(args)
    steps: list[str]
    match command_path:
        case "doctor":
            steps = [
                f"{prog} config check",
                f"{prog} project list",
                f"{prog} doctor --json",
            ]
        case "setup":
            if target is not None:
                steps = [f"{prog} project show {target}", f"{prog} build {target}", f"{prog} check {target}"]
            else:
                steps = [f"{prog} project list", f"{prog} build", f"{prog} check :root"]
        case "release/verify":
            if target is not None:
                steps = [f"{prog} publish --dry-run {target}", f"{prog} publish {target}", f"{prog} status {target}"]
            else:
                steps = [f"{prog} publish --dry-run", f"{prog} project list", f"{prog} status"]
        case "build":
            if target is not None:
                steps = [f"{prog} check {target}", f"{prog} status {target}", f"{prog} publish --dry-run {target}"]
            else:
                steps = [f"{prog} check :root", f"{prog} project list", f"{prog} publish --dry-run"]
        case "publish":
            if getattr(args, "dry_run", False):
                steps = [
                    f"{prog} publish {target}" if target else f"{prog} publish",
                    f"{prog} status {target}" if target else f"{prog} project list",
                    f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run",
                ]
            else:
                steps = [
                    f"{prog} status {target}" if target else f"{prog} project list",
                    f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run",
                    f"{prog} push {target}" if target else f"{prog} push",
                ]
        case "project/show":
            if target is None:
                return
            steps = [f"{prog} project deps {target}", f"{prog} project targets {target}", f"{prog} build {target}"]
        case "commit":
            if getattr(args, "dry_run", False):
                steps = [
                    f"{prog} commit {target}" if target else f"{prog} commit",
                    f"{prog} status {target}" if target else f"{prog} project list",
                    f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run",
                ]
            else:
                steps = [
                    f"{prog} status {target}" if target else f"{prog} project list",
                    f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run",
                    f"{prog} push {target}" if target else f"{prog} push",
                ]
        case "push":
            if getattr(args, "dry_run", False):
                steps = [
                    f"{prog} push {target}" if target else f"{prog} push",
                    f"{prog} status {target}" if target else f"{prog} project list",
                ]
            else:
                steps = [
                    f"{prog} status {target}" if target else f"{prog} project list",
                    f"{prog} project repo {target}" if target else f"{prog} project list",
                ]
        case _:
            return

    print()
    print(heading("Next useful commands:"))
    for step in steps:
        print(f"  {command_text(step)}")


class Commands:
    def __init__(self, parser: ArgParser) -> None:
        self.root_parser = parser
        self.parsers: dict[str, ArgParser] = {}
        self.subparsers: dict[str, AddParser] = {}

    @staticmethod
    def _normalize_name(name: str | Sequence[str], extra_parts: Sequence[str] = ()) -> str:
        if isinstance(name, str):
            parts = tuple(part for part in name.split("/") if part)
        else:
            parts = tuple(str(part) for part in name if str(part))
        if extra_parts:
            parts = (*parts, *extra_parts)
        return "/".join(parts)

    class Command:
        def __init__(
            self,
            commands: "Commands",
            name: str | Sequence[str],
            *name_parts: str,
            help: str | None = None,
            description: str | None = None,
            epilog: str | None = None,
        ) -> None:
            normalized_name = commands._normalize_name(name, name_parts)
            path = normalized_name.split("/")
            parsers = commands.parsers
            subparsers = commands.subparsers

            def subcommand(i: int) -> str:
                if i == 0:
                    return "command"
                return ("sub" * i) + "command"

            if "" not in parsers:
                parsers[""] = commands.root_parser

            if "" not in subparsers:
                root_subparsers = commands.root_parser.add_subparsers(
                    dest="command",
                    title="commands",
                    metavar="COMMAND",
                    parser_class=SuggestingArgumentParser,
                )
                subparsers[""] = root_subparsers.add_parser  # type: ignore[reportArgumentType]

            for i in range(1, len(path) + 1):
                p = "/".join(path[:i])
                p0 = "/".join(path[: i - 1])
                if p not in parsers:
                    parser_kwargs: ParserKwargs = {"formatter_class": HelpFormatter}
                    if i == len(path):
                        if help is not None:
                            parser_kwargs["help"] = help
                        if description is not None:
                            parser_kwargs["description"] = description
                        if epilog is not None:
                            parser_kwargs["epilog"] = epilog
                    parsers[p] = subparsers[p0](path[i - 1], **parser_kwargs)
                    register_parser_child(parsers[p0], path[i - 1], parsers[p])
                if p not in subparsers and i != len(path):
                    child_subparsers = parsers[p].add_subparsers(
                        dest=subcommand(i),
                        title="subcommands",
                        metavar="SUBCOMMAND",
                        parser_class=SuggestingArgumentParser,
                    )
                    subparsers[p] = child_subparsers.add_parser  # type: ignore[reportArgumentType]

            self.parser = parsers[normalized_name]
            self.parser.formatter_class = HelpFormatter
            register_parser_metadata(self.parser, hidden=help == argparse.SUPPRESS)
            if description is not None:
                self.parser.description = description
            if epilog is not None:
                self.parser.epilog = epilog
            self.parser.set_defaults(command_path=normalized_name)

        def __enter__(self) -> ArgParser:
            return self.parser

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: object | None,
        ) -> None:
            del exc_type, exc_value, traceback

    def __call__(
        self,
        name: str | Sequence[str],
        *name_parts: str,
        help: str | None = None,
        description: str | None = None,
        epilog: str | None = None,
    ) -> "Commands.Command":
        return Commands.Command(
            self,
            name,
            *name_parts,
            help=help,
            description=description,
            epilog=epilog,
        )


def build_parser() -> tuple[SuggestingArgumentParser, Commands]:
    parser = SuggestingArgumentParser(
        prog="dev",
        description=_doc("""
            Wabbit development toolkit.

            The CLI reads workspace metadata from root.clj and root.private.clj to
            generate project files, run checks, inspect dependencies, build projects,
            publish releases, and automate repository maintenance tasks.
            """),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    prog = parser.prog
    parser.epilog = _epilog(
        examples=[
            f"{prog} doctor",
            f"{prog} where",
            f"{prog} completion bash",
            f"{prog} setup --local app-datatron",
            f"{prog} build app-datatron",
            f"{prog} secrets scan .",
            f"{prog} project list",
        ],
        notes=[
            "Install the package and run `dev` (or `wabbit-dev`) from anywhere in the workspace.",
            "When a workspace `.venv` exists next to `root.clj`, the launcher prefers it automatically.",
            "Config-driven commands walk upward from the current directory to find root.clj and root.private.clj.",
        ],
    )
    commands = Commands(parser)

    def examples(*command_examples: str, notes: Sequence[str] = ()) -> str | None:
        return _epilog(
            examples=[f"{prog} {example}" for example in command_examples],
            notes=notes,
        )

    with commands(
        "where",
        help="Show the workspace, repo, and project context inferred from the current directory.",
        description=_doc("""
            Print the CLI context inferred from the current working directory.

            This shows the resolved workspace root, current configured project,
            current repo target, and the commands that inherit those defaults
            when you omit explicit targets.
            """),
        epilog=examples("where", "where --json"),
    ) as cmd:
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit the resolved cwd context as JSON.",
        )

    with commands(
        "config",
        help="Validate workspace configuration files.",
        description=_doc("""
            Parse and validate the workspace configuration files.

            These commands check that root.clj and root.private.clj can be decoded
            into the internal project model before you rely on setup, build, check,
            or publish workflows.
            """),
        epilog=examples("config check"),
    ) as cmd:
        del cmd

    with commands(
        "completion",
        help="Generate shell completion scripts.",
        description=_doc("""
            Generate shell completion scripts for the dev CLI.

            The generated completions include top-level commands, nested
            subcommands, configured project and repo IDs, and loaded check names.
            """),
        epilog=examples(
            "completion bash",
            "completion zsh",
            notes=[
                f"Use `source <({prog} completion bash)` for bash.",
                f"Use `autoload -Uz compinit && compinit && source <({prog} completion zsh)` for zsh.",
                "Completions query the current workspace config at completion time, so project and repo IDs stay up to date.",
            ],
        ),
    ) as cmd:
        del cmd

    with commands(
        "completion",
        "bash",
        help="Print a bash completion script.",
        description=_doc("""
            Print a bash completion script to stdout.

            Source it from your shell profile or interactively to enable command,
            subcommand, target, and check-name completion.
            """),
        epilog=examples("completion bash"),
    ) as cmd:
        del cmd

    with commands(
        "completion",
        "zsh",
        help="Print a zsh completion script.",
        description=_doc("""
            Print a zsh completion script to stdout.

            Source it from your shell profile after `compinit` to enable command,
            subcommand, target, and check-name completion.
            """),
        epilog=examples("completion zsh"),
    ) as cmd:
        del cmd

    with commands(
        "completion",
        "query",
        help=argparse.SUPPRESS,
        description=argparse.SUPPRESS,
    ) as cmd:
        cmd.add_argument("shell", help=argparse.SUPPRESS)
        cmd.add_argument("index", type=int, help=argparse.SUPPRESS)
        cmd.add_argument("words", nargs="*", help=argparse.SUPPRESS)

    with commands(
        "config",
        "check",
        help="Parse and validate root.clj and root.private.clj.",
        description=_doc("""
            Parse root.clj and root.private.clj and fail fast on invalid command
            forms, unknown references, malformed dependency definitions, or other
            configuration errors.
            """),
        epilog=examples(
            "config check",
            notes=[
                "This command validates configuration only. It does not build or modify projects.",
            ],
        ),
    ) as cmd:
        del cmd

    with commands(
        "doctor",
        help="Diagnose workspace, toolchain, and credential readiness.",
        description=_doc("""
            Run an environment and workspace readiness check.

            `doctor` validates the current working directory, required config
            files, Python version, virtual environment usage, tool availability,
            config loading, and publish/commit credentials.
            """),
        epilog=examples(
            "doctor",
            "doctor app-wabbit-dev",
            "doctor --only publish app-wabbit-dev",
            "doctor --only gradle --only config",
            "doctor --json",
            notes=[
                "Use this when a command fails due to missing config, tools, or credentials.",
                "Targets scope project- and publish-related checks to the selected project closure.",
                "`--only` accepts either raw check IDs such as `gradle` or command groups such as `build`, `publish`, or `commit`.",
                "Use `--json` for scripts, editor integrations, or CI diagnostics.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Optional project IDs, repo IDs, or paths used to scope project-related checks.",
        )
        _add_argument(
            cmd,
            "--only",
            action="append",
            metavar="CHECK_OR_COMMAND",
            completion_kind="doctor-only",
            help="Limit the report to one check ID or command readiness group. Repeatable.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit the doctor report as JSON instead of human-oriented text.",
        )

    with commands(
        "docs",
        help="Validate project documentation quality.",
        description=_doc("""
            Run deterministic and optional semantic documentation checks.

            Use `docs check` to validate markdown links, docs section coverage,
            docs hooks, code snippets, and optionally LLM-based semantic quality.
            """),
        epilog=examples("docs check", "docs check --semantic app-wabbit-dev"),
    ) as cmd:
        del cmd

    with commands(
        "docs",
        "check",
        help="Check project documentation links, sections, snippets, and optional semantic quality.",
        description=_doc("""
            Validate docs for one or more configured projects.

            The deterministic layer checks internal links, external links and
            badges, README section coverage, docs-generation hooks, and
            compileable or parseable code snippets. `--semantic` adds an
            LLM-based advisory pass for issues such as weak quickstarts or
            misleading examples.
            """),
        epilog=examples(
            "docs check",
            "docs check app-wabbit-dev",
            "docs check --semantic app-wabbit-dev",
            "docs check --json jeeves",
            notes=[
                "Targets can be project IDs, repo IDs, or paths inside configured projects or repos.",
                "With no targets from inside a configured project or repo, docs check defaults to that current project or repo.",
                "`--semantic` is advisory by design and requires an OpenAI key.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths. Omit to check the current inferred project or repo, or the full workspace from root.",
        )
        cmd.add_argument(
            "--semantic",
            action="store_true",
            help="Add an LLM-based advisory review for semantic docs quality issues.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit a machine-readable docs report instead of human-oriented output.",
        )

    with commands(
        "docs",
        "snippets",
        help="Check fenced documentation snippets with optional project-specific deeper verification.",
        description=_doc("""
            Validate fenced code blocks extracted from README and docs markdown files.

            By default this command stays fast: it syntax-checks or parses
            supported snippet languages such as Python, shell, JSON, TOML, and
            YAML. `--verify` enables deeper project-level verification when the
            project type supports it, such as project-specific Python snippet
            tests or a single coarse Gradle verification build.
            """),
        epilog=examples(
            "docs snippets",
            "docs snippets app-wabbit-dev",
            "docs snippets --verify python-lang-mu",
            "docs snippets --verify kotlin-data",
            "docs snippets --json jeeves",
            notes=[
                "Targets can be project IDs, repo IDs, or paths inside configured projects or repos.",
                "The default mode is intentionally cheap and syntax-oriented.",
                "`--verify` enables deeper project-specific snippet verification when the project type supports it.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths. Omit to inspect the current inferred project or repo, or the full workspace from root.",
        )
        cmd.add_argument(
            "--verify",
            action="store_true",
            help="Enable deeper project-specific snippet verification beyond the default syntax checks.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit a machine-readable snippet report instead of human-oriented output.",
        )

    with commands(
        "setup",
        help="Generate or refresh project files from root.clj.",
        description=_doc("""
            Materialize generated files for configured projects.

            `setup` reads root.clj, resolves project dependencies, and writes the
            managed Gradle, Python, legal, workflow, and repository files needed
            for the selected projects.
            """),
        epilog=examples(
            "setup",
            "setup app-wabbit-dev",
            "setup jeeves",
            "setup ./jeeves/client",
            "setup --local app-datatron",
            "setup --dev kotlin-web-openai",
            notes=[
                "Targets can be project IDs, repo IDs, or paths inside configured projects or repos.",
                "With no targets from the workspace root, setup processes every configured project.",
                "With no targets inside a configured project or repo, setup defaults to that current project or repo.",
                "`--local` writes local composite-build overlays for multi-repo development.",
                "`--dev` switches to the DEV setup mode; the default is PROD.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths. Omit to process every configured project.",
        )
        cmd.add_argument(
            "--dev",
            action="store_true",
            help="Run setup in DEV mode instead of the default PROD mode.",
        )
        cmd.add_argument(
            "--local",
            action="store_true",
            help="Run setup in LOCAL mode and generate local dependency overlays.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit a machine-readable setup summary instead of human-oriented progress output.",
        )

    with commands(
        "release",
        help="Verify release readiness for publishable projects.",
        description=_doc("""
            Run release-oriented verification for publishable projects.

            `release verify` uses project-type-specific verification backends to
            confirm that selected artifacts can be built and pass their
            publish-facing sanity checks without actually uploading them.
            """),
        epilog=examples("release verify", "release verify app-wabbit-dev", "release verify --json jeeves"),
    ) as cmd:
        del cmd

    with commands(
        "release",
        "verify",
        help="Verify publishable Python and Gradle projects without uploading them.",
        description=_doc("""
            Verify release readiness in dependency order for the selected targets.

            Python projects build wheel and sdist artifacts, run `twine check`,
            run `check-manifest`, and inspect artifact metadata and packaged
            files. Gradle projects first check whether cross-repo project
            dependencies are already available from Maven Central, then run
            publication-oriented verification tasks in PROD-style dependency
            resolution and restore local overlays afterward when needed.
            """),
        epilog=examples(
            "release verify",
            "release verify app-wabbit-dev",
            "release verify jeeves",
            "release verify --json app-wabbit-dev",
            notes=[
                "Targets can be project IDs, repo IDs, or paths inside configured projects or repos.",
                "With no targets from inside a configured project or repo, release verify defaults to that current project or repo.",
                "Gradle verification skips expensive builds when required cross-repo project dependencies are not yet available from Maven Central.",
                "Projects that are quarantined, publish-disabled, or not yet supported by release verification are reported instead of crashing the command.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths. Omit to verify the current inferred project or repo, or the full workspace from root.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit a machine-readable release verification report instead of human-oriented progress output.",
        )

    with commands(
        "llmcopy",
        help="Copy file contents to the clipboard in an LLM-friendly envelope and report GPT-5.4 token totals.",
        description=_doc("""
            Read one or more files, directories, or glob patterns and copy their
            contents to the clipboard using a `<contents path="...">` wrapper that
            is convenient to paste into external tools or prompts. After copying,
            report the total token count using GPT-5.4 tokenization.
            """),
        epilog=examples(
            "llmcopy README.md docs",
            "llmcopy 'dev/tasks/*.py'",
            notes=[
                "Directories are traversed recursively.",
                "The command skips `.git`, `.idea`, and `__pycache__` directories by default.",
                "The success summary includes the total GPT-5.4 token count for the copied payload.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "path",
            metavar="PATH",
            type=str,
            nargs="+",
            completion_kind="path",
            completion_allow_files=True,
            help="Files, directories, or glob patterns to include in the clipboard bundle.",
        )

    with commands(
        "dep",
        help="Inspect dependency definitions and graphs.",
        description=_doc("""
            Analyze the dependency metadata loaded from root.clj.

            Use `dep` subcommands to render project dependency graphs or inspect
            whether configured named libraries have newer upstream versions.
            """),
        epilog=examples("dep graph", "dep updates"),
    ) as cmd:
        del cmd

    with commands(
        "dep",
        "graph",
        help="Render an SVG graph of project dependencies.",
        description=_doc("""
            Generate an SVG dependency graph from the project relationships defined
            in root.clj.

            By default the graph includes only configured project-to-project
            edges. Use `--artifacts` to include external Maven artifacts as nodes.
            """),
        epilog=examples(
            "dep graph",
            "dep graph app-datatron",
            "dep graph jeeves",
            "dep graph --artifacts kotlin-web-openai",
            notes=[
                "With no targets from inside a configured project or repo, the graph defaults to that current project or repo.",
                "From the workspace root, omitting targets still graphs the full workspace.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths. Omit to graph the full workspace.",
        )
        cmd.add_argument(
            "--artifacts",
            action="store_true",
            default=False,
            help="Include external dependency artifacts in addition to project nodes.",
        )

    with commands(
        "dep",
        "updates",
        help="Check configured Maven libraries and pinned Python deps for newer upstream versions.",
        description=_doc("""
            Compare named Maven libraries defined in root.clj and exact-pinned
            Python project dependencies against the latest versions available
            from their upstream repositories, then print any newer candidates
            that were found.
            """),
        epilog=examples(
            "dep updates",
            notes=[
                "Only named Maven libraries and exact-pinned Python requirements are checked.",
                "Direct URL/file dependencies and non-exact Python version ranges are skipped.",
            ],
        ),
    ) as cmd:
        del cmd

    with commands(
        "publish",
        help="Publish configured projects in dependency order.",
        description=_doc("""
            Publish selected projects using the publish target inferred from each
            project's metadata and features.

            Gradle projects can publish to Maven Central, JitPack, or JetBrains
            Marketplace. Python projects can publish to PyPI.
            """),
        epilog=examples(
            "publish",
            "publish app-wabbit-dev",
            "publish jeeves",
            "publish --dry-run app-wabbit-dev",
            notes=[
                "Credentials are loaded from root.private.clj and, for some publish flows, environment variables.",
                "Projects with no publish target are skipped rather than treated as errors.",
                "`--dry-run` prints the publish order and target for each selected project without uploading anything.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths. Omit to publish every publishable configured project.",
        )
        cmd.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the publish plan without uploading artifacts or contacting publish targets.",
        )

    with commands(
        "build",
        help="Build configured Gradle or Python projects in dependency order.",
        description=_doc("""
            Build selected projects after topologically ordering them by configured
            project dependencies.

            Gradle projects run their `build` task. Python projects are syntax
            checked by compiling discovered `.py` files.
            """),
        epilog=examples(
            "build",
            "build app-datatron",
            "build jeeves",
            "build ./jeeves/client",
            "build kotlin-web-openai app-wabbit-dev",
            notes=[
                "Only Gradle and Python projects are buildable through this command.",
                "With no targets from inside a configured project or repo, build defaults to that current project or repo.",
                "From the workspace root, omitting targets still builds every buildable configured project.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths. Omit to build every buildable configured project.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit a machine-readable build report instead of human-oriented progress output.",
        )

    with commands(
        "duplicates",
        help="Find duplicate files and directory trees.",
        description=_doc("""
            Scan one or more folders for duplicate files and duplicate directory
            trees using a staged fingerprinting pipeline designed to minimize I/O.

            The command can optionally compare filesystem directories against zip
            contents and, when requested, perform weaker matching for encrypted zip
            archives using visible metadata.
            """),
        epilog=examples(
            "duplicates app-wabbit-dev app-wabbit-code",
            "duplicates . --exclude '*.png' '*.jpg' --size 4096",
            "duplicates archives --zip-contents --weak-encrypted-zip",
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "folders",
            metavar="FOLDER",
            type=str,
            nargs="+",
            completion_kind="path",
            completion_allow_files=True,
            help="Folders to scan for duplicate files and directory trees.",
        )
        cmd.add_argument(
            "-e",
            "--exclude",
            metavar="PATTERN",
            type=str,
            default=[],
            nargs="+",
            help="Git-style filename filters to exclude from scanning.",
        )
        cmd.add_argument(
            "-f",
            "--filter",
            metavar="PATTERN",
            type=str,
            default=[],
            nargs="+",
            help="Restrict scanning to files matching one or more filename filters.",
        )
        cmd.add_argument(
            "-s",
            "--size",
            metavar="BYTES",
            type=int,
            default=1,
            help="Minimum file size to include in duplicate file reporting.",
        )
        cmd.add_argument(
            "--no-default-excludes",
            action="store_true",
            help="Do not automatically exclude common metadata directories like `.git` or `__pycache__`.",
        )
        cmd.add_argument(
            "--zip-contents",
            action="store_true",
            help="Also compare directory trees against zip archive contents.",
        )
        cmd.add_argument(
            "--weak-encrypted-zip",
            action="store_true",
            help="Allow metadata-only comparison of encrypted zip entries when zip contents are enabled.",
        )

    with commands(
        "jitpack",
        help="Inspect JitPack metadata for an artifact.",
        description=_doc("""
            Query JitPack for refs, commits, versions, build metadata, and build
            logs associated with an artifact.
            """),
        epilog=examples("jitpack info wabbit-corp kotlin-base58"),
    ) as cmd:
        del cmd

    with commands(
        "jitpack",
        "info",
        help="Show refs, commits, versions, and build info for a JitPack artifact.",
        description=_doc("""
            Inspect the current JitPack state for an artifact by printing:

            - known refs
            - recent master commits
            - published versions
            - build details and any compiler-style errors discovered in build logs
            """),
        epilog=examples(
            "jitpack info wabbit-corp kotlin-base58",
            "jitpack info wabbit-corp kotlin-base58 0.1.0",
        ),
    ) as cmd:
        cmd.add_argument(
            "group",
            metavar="GROUP",
            type=str,
            nargs=1,
            help="JitPack group or GitHub owner/organization.",
        )
        cmd.add_argument(
            "artifact",
            metavar="ARTIFACT",
            type=str,
            nargs=1,
            help="JitPack artifact or repository name.",
        )
        cmd.add_argument(
            "version",
            metavar="VERSION",
            type=str,
            nargs="?",
            help="Optional version to narrow the output to a single build.",
        )

    with commands(
        "clean",
        help="Delete generated caches and build outputs for configured projects.",
        description=_doc("""
            Remove common generated directories such as `build`, `.gradle`,
            `.pytest_cache`, `.mypy_cache`, `.kotlin`, and Python `__pycache__`
            directories from configured projects.
            """),
        epilog=examples(
            "clean",
            "clean app-wabbit-dev",
            "clean jeeves",
            notes=[
                "Targets can be project IDs, repo IDs, or paths inside configured projects or repos.",
                "With no targets from inside a configured project or repo, clean defaults to that current project or repo.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths. Omit to clean every configured project.",
        )

    with commands(
        "cloc",
        help="Summarize lines of code for configured targets or paths.",
        description=_doc("""
            Run `cloc` and print language totals.

            For configured targets, the command focuses on source directories that
            matter for each project type. When given an arbitrary path, it runs
            `cloc` directly on that path.
            """),
        epilog=examples(
            "cloc",
            "cloc app-wabbit-dev",
            "cloc jeeves",
            "cloc app-wabbit-dev/dev",
            notes=[
                "With no targets from inside a configured project or repo, cloc defaults to that current project or repo.",
                "From the workspace root, omitting targets still analyzes every configured project.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="path-or-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or filesystem paths. Omit to analyze every configured project.",
        )

    with commands(
        "status",
        help="Show repo status for selected targets.",
        description=_doc("""
            Print a repo status summary similar to `git status --short`.

            The output includes staged changes, unstaged changes, and untracked
            files for one or more resolved repository targets.
            """),
        epilog=examples(
            "status",
            "status app-wabbit-dev",
            "status jeeves",
            "status ./app-wabbit-dev",
            "status app-wabbit-dev jeeves/client",
            notes=[
                "With no targets from inside a configured project or repo, status defaults to that current repo.",
                "From the workspace root, omitting targets inspects every configured repo.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="repo-target",
            completion_allow_files=True,
            help="Repo IDs, project IDs, or paths inside git repositories.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit staged, unstaged, and untracked repo status details as JSON.",
        )

    with commands(
        "commit",
        help="Run setup, stage changes, and create commits for configured projects.",
        description=_doc("""
            Run PROD setup for the target projects, group them by repository,
            stage detected changes, and generate commit messages using the OpenAI
            key configured in root.private.clj.
            """),
        epilog=examples(
            "commit",
            "commit app-wabbit-dev",
            "commit jeeves",
            "commit --dry-run app-wabbit-dev",
            notes=[
                "This command requires an OpenAI key in root.private.clj.",
                "The commit message policy is repository-specific and enforced by the commit workflow.",
                "`--dry-run` shows the setup order and repo commit grouping without modifying files or creating commits.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths. Omit to process every configured project.",
        )
        cmd.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the setup and repo commit plan without modifying files or creating commits.",
        )

    with commands(
        "push",
        help="Push origin/master and tags for selected repos or all configured repos.",
        description=_doc("""
            Push tags plus the `master` branch to `origin`.

            With no targets or `.` the command walks every configured project repo
            and pushes each distinct repository once. With explicit targets it
            pushes the repos resolved from those repo IDs, project IDs, or paths.
            """),
        epilog=examples(
            "push",
            "push .",
            "push app-wabbit-dev",
            "push jeeves",
            "push ./app-wabbit-dev",
            "push --dry-run jeeves",
            notes=[
                "The branch target is currently hard-coded to `master`.",
                "With no targets, `push` behaves like `push .` and pushes every configured repo once.",
                "`--dry-run` prints the resolved repo targets without pushing branch or tag updates.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="push-target",
            completion_allow_files=True,
            help="Use `.` for all configured repos, or provide repo IDs, project IDs, or paths.",
        )
        cmd.add_argument(
            "--dry-run",
            action="store_true",
            help="Print which repos would be pushed without sending branch or tag updates.",
        )

    with commands(
        "project",
        help="Inspect the configured project inventory.",
        description=_doc("""
            Explore the projects defined in root.clj and how repo-managed projects
            are grouped under their parent repositories.
            """),
        epilog=examples(
            "project list",
            "project repo",
            "project show app-wabbit-dev",
            "project deps jeeves",
            "project repo jeeves",
            "project targets",
        ),
    ) as cmd:
        del cmd

    with commands(
        "project",
        "list",
        help="List configured projects grouped by repository.",
        description=_doc("""
            Print every configured project in declaration order, grouping nested
            repo-managed projects under their containing repository and labeling
            each entry by its detected project type.
            """),
        epilog=examples("project list"),
    ) as cmd:
        del cmd

    with commands(
        "project",
        "show",
        help="Show detailed metadata for one or more configured projects.",
        description=_doc("""
            Print the resolved metadata for one or more projects.

            This includes the project type, path, repo root, resolved
            dependencies, publish target, docs system, JVM policy, and the main
            generated files that `setup` is expected to manage.
            """),
        epilog=examples(
            "project show",
            "project show app-wabbit-dev",
            "project show jeeves",
            "project show ./jeeves/client",
            "project show app-wabbit-dev --json",
            notes=[
                "With no targets from inside a configured project or repo, the command defaults to that current project or repo.",
                "From the workspace root, pass an explicit target to avoid dumping the entire workspace.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths inside configured projects or repos.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit project metadata as JSON.",
        )

    with commands(
        "project",
        "deps",
        help="Show resolved dependencies for one or more configured projects.",
        description=_doc("""
            Print the resolved dependency list for one or more projects.

            Targets can be individual projects, whole configured repos, or paths
            inside configured projects or repos.
            """),
        epilog=examples(
            "project deps",
            "project deps app-wabbit-dev",
            "project deps jeeves",
            "project deps ./jeeves/client",
            "project deps jeeves --json",
            notes=[
                "With no targets from inside a configured project or repo, the command defaults to that current project or repo.",
                "From the workspace root, pass an explicit target to avoid dumping the entire workspace.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths inside configured projects or repos.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit resolved dependencies as JSON.",
        )

    with commands(
        "project",
        "repo",
        help="Show repository metadata for one or more configured targets.",
        description=_doc("""
            Print the repo-level metadata associated with one or more configured
            projects or repos.

            Targets can be project IDs, repo IDs, or paths inside configured
            projects or repos. Repositories are de-duplicated in the output.
            """),
        epilog=examples(
            "project repo",
            "project repo app-wabbit-dev",
            "project repo jeeves",
            "project repo ./jeeves/client",
            "project repo jeeves --json",
            notes=[
                "With no targets from inside a configured project or repo, the command defaults to that current repo.",
                "From the workspace root, omitting targets lists every configured repo.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="repo-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths inside configured projects or repos.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit repo metadata as JSON.",
        )

    with commands(
        "project",
        "targets",
        help="Show Kotlin Multiplatform target platforms for configured projects.",
        description=_doc("""
            Print the declared Kotlin Multiplatform target platforms for one or
            more configured projects.

            With no targets, this lists every configured KMP project in
            declaration order. Explicit targets can be project IDs, repo IDs, or
            paths inside configured projects or repos; non-KMP projects are
            ignored.
            """),
        epilog=examples(
            "project targets",
            "project targets kotlin-filesystem",
            "project targets jeeves",
            "project targets kotlin-filesystem --json",
            notes=[
                "With no targets from inside a configured project or repo, the command defaults to that current project or repo.",
                "From the workspace root, omitting targets still lists every configured KMP project.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="*",
            completion_kind="project-target",
            completion_allow_files=True,
            help="Project IDs, repo IDs, or paths inside configured projects or repos. Omit to list every KMP project.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit KMP target platform data as JSON.",
        )

    with commands(
        "check",
        help="Run repository and source checks, or inspect the loaded check catalog.",
        description=_doc("""
            Run the configured check suite against a project, directory, or file.

            Use bare `check` to execute checks, `check list` to browse the
            loaded catalog, and `check describe` to inspect one check in detail.
            """),
        epilog=examples(
            "check",
            "check app-wabbit-dev/dev/cli.py",
            "check app-wabbit-dev",
            "check :app-wabbit-dev",
            "check jeeves",
            "check :root --fix",
            "check . SpdxHeaderCheck",
            "check list",
            "check list --json",
            "check describe SpdxHeaderCheck",
            "check describe SpdxHeaderCheck --json",
            notes=[
                "When TARGET is omitted from inside a configured project or repo, the command defaults to that current project or repo.",
                "Use `check list` to browse loaded checks and `check describe <check>` for issue IDs and suppression examples.",
                "Explicit check names use the Python class names registered by the check modules.",
                "Checks honor `.gitignore`, `.checkignore`, and suppressions configured in root.clj.",
            ],
        ),
    ) as cmd:
        del cmd

    with commands(
        "check",
        "run",
        help=argparse.SUPPRESS,
        description=_doc("""
            Run the configured check suite against a project, directory, or file.
            """),
        epilog=examples(
            "check",
            "check app-wabbit-dev/dev/cli.py",
            "check app-wabbit-dev",
            "check :root --fix",
            "check . SpdxHeaderCheck",
        ),
    ) as cmd:
        register_parser_metadata(cmd, hidden=True)
        _add_argument(
            cmd,
            "project_or_dir_or_file",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=None,
            completion_kind="check-target",
            completion_allow_files=True,
            help="Filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`. Omit to infer the current configured project or repo when possible.",
        )
        _add_argument(
            cmd,
            "checks",
            metavar="CHECK",
            type=str,
            nargs="*",
            completion_kind="check-name",
            help="Optional explicit check class names. Omit to run every loaded check.",
        )
        cmd.add_argument(
            "--fix",
            action="store_true",
            help="Apply fixes for issues that provide an automatic fix callback.",
        )

    with commands(
        "check",
        "list",
        help="List the loaded checks with scope, fixability, and summaries.",
        description=_doc("""
            List the checks currently loaded from the workspace and check modules.
            """),
        epilog=examples("check list", "check list --json"),
    ) as cmd:
        _add_argument(
            cmd,
            "--json",
            action="store_true",
            help="Emit the check catalog as JSON instead of text.",
        )

    with commands(
        "check",
        "describe",
        help="Show issue IDs, config knobs, and suppression examples for one check.",
        description=_doc("""
            Print detailed information about one loaded check, including issue
            IDs, typed config commands, and suppression examples.
            """),
        epilog=examples("check describe SpdxHeaderCheck", "check describe SpdxHeaderCheck --json"),
    ) as cmd:
        _add_argument(
            cmd,
            "check",
            metavar="CHECK",
            type=str,
            completion_kind="check-name",
            help="The loaded check class name to inspect.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit the detailed check description as JSON instead of text.",
        )

    with commands(
        "spdx",
        help="SPDX-related quality commands.",
        description=_doc("""
            Run SPDX-specific tooling derived from the general check runner.
            """),
        epilog=examples("spdx headers"),
    ) as cmd:
        del cmd

    with commands(
        "spdx",
        "headers",
        help="Audit or fix SPDX file headers.",
        description=_doc("""
            Run only the SPDX header check against a project, directory, or file.

            This is a focused shortcut for `check ... SpdxHeaderCheck`.
            """),
        epilog=examples(
            "spdx headers .",
            "spdx headers app-wabbit-dev --fix",
            "spdx headers jeeves",
            notes=[
                "When TARGET is omitted from inside a configured project or repo, the command defaults to that current project or repo.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "project_or_dir_or_file",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=None,
            completion_kind="check-target",
            completion_allow_files=True,
            help="Filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`. Omit to infer the current configured project or repo when possible.",
        )
        cmd.add_argument(
            "--fix",
            action="store_true",
            help="Insert or normalize SPDX headers when the check can do so safely.",
        )

    with commands(
        "secrets",
        help="Scan for secrets and secret-like strings.",
        description=_doc("""
            Run secret-related scanning commands.

            The current implementation uses the internal check runner rather
            than invoking an external secret scanning binary.
            """),
        epilog=examples("secrets scan ."),
    ) as cmd:
        del cmd

    with commands(
        "secrets",
        "scan",
        help="Run the high-entropy-string secret check.",
        description=_doc("""
            Run the high-entropy-string secret scan against a target path.

            This is equivalent to running the `HighEntropyStringCheck` through
            the general check runner.
            """),
        epilog=examples(
            "secrets scan .",
            "secrets scan app-wabbit-dev",
            "secrets scan jeeves",
            notes=[
                "Targets can be a filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`.",
                "When TARGET is omitted from inside a configured project or repo, the command defaults to that current project or repo.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "target",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=None,
            completion_kind="check-target",
            completion_allow_files=True,
            help="Filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`. Omit to infer the current configured project or repo when possible.",
        )

    with commands(
        "contributors",
        help="Inspect repository contributor identity.",
        description=_doc("""
            Run contributor-related repository audits.
            """),
        epilog=examples("contributors audit"),
    ) as cmd:
        del cmd

    with commands(
        "contributors",
        "audit",
        help="Audit git contributor identity mismatches across configured repos.",
        description=_doc("""
            Walk configured git repositories and report contributors whose name
            or email does not match the expected default git identity from the
            loaded configuration.
            """),
        epilog=examples(
            "contributors audit",
            notes=[
                "The expected identity comes from `(git-user ...)` in the loaded workspace config.",
            ],
        ),
    ) as cmd:
        del cmd

    return parser, commands


async def async_main() -> int:
    if sys.platform.lower() == "win32":
        os.system("color")
        os.system("chcp 65001 > nul")
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser, commands = build_parser()
    prog = parser.prog

    normalized_argv = _normalize_cli_argv(sys.argv[1:], commands)
    from dev.typed_cli import maybe_run_typed_cli

    typed_exit_code = await maybe_run_typed_cli(normalized_argv, prog=prog)
    if typed_exit_code is not None:
        return typed_exit_code

    args = parser.parse_args(normalized_argv)
    command_path = getattr(args, "command_path", None)
    if command_path is None:
        parser.print_help()
        return 0

    if command_path in commands.subparsers:
        commands.parsers[command_path].print_help()
        return 0

    _apply_context_defaults(command_path, args)

    from dev.tasks.doctor import preflight_for_command

    selected_projects: tuple[str, ...] | None = None
    if (
        command_path
        in {
            "docs/check",
            "docs/snippets",
            "setup",
            "release/verify",
            "build",
            "publish",
            "commit",
            "clean",
            "dep/graph",
        }
        and args.targets
    ):
        selected_projects = tuple(args.targets)
    elif command_path in {"project/show", "project/deps", "project/repo", "project/targets"}:
        selected_projects = tuple(args.targets)

    if not preflight_for_command(
        command_path,
        prog=prog,
        projects=selected_projects,
        dry_run=getattr(args, "dry_run", False),
    ):
        _print_failure_context(command_path, args=args)
        return 2

    try:
        exit_code = 0
        match command_path:
            case "where":
                from dev.tasks.where import show_where

                exit_code = show_where(json_output=args.json)

            case "completion/bash":
                from dev.tasks.completion import print_completion_script

                exit_code = print_completion_script("bash", prog=prog)

            case "completion/zsh":
                from dev.tasks.completion import print_completion_script

                exit_code = print_completion_script("zsh", prog=prog)

            case "completion/query":
                from dev.tasks.completion import print_completion_query

                return print_completion_query(parser, args.shell, args.index, args.words)

            case "doctor":
                from dev.tasks.doctor import doctor

                exit_code = doctor(json_output=args.json, only=args.only, targets=args.targets)

            case "docs/check":
                from dev.tasks.docs_check import docs_check

                exit_code = docs_check(args.targets, semantic=args.semantic, json_output=args.json)

            case "docs/snippets":
                from dev.tasks.docs_check import docs_snippets

                exit_code = docs_snippets(
                    args.targets,
                    verify=args.verify,
                    json_output=args.json,
                )

            case "config/check":
                from dev.tasks.check_config import check_config

                check_config()

            case "setup":
                from dev.tasks.setup import RepoSetupMode, setup

                if args.local:
                    mode = RepoSetupMode.LOCAL
                elif args.dev:
                    mode = RepoSetupMode.DEV
                else:
                    mode = RepoSetupMode.PROD
                exit_code = setup(mode, projects=args.targets, json_output=args.json)

            case "release/verify":
                from dev.tasks.release_verify import release_verify

                exit_code = release_verify(args.targets, json_output=args.json)

            case "llmcopy":
                from dev.tasks.llmcopy import llmcopy

                llmcopy(args.path)

            case "jitpack/info":
                from dev.tasks.jitpack import get_jitpack_info

                await get_jitpack_info(args.group[0], args.artifact[0], args.version)

            case "dep/updates":
                from dev.tasks.dep_updates import check_for_updates

                check_for_updates()

            case "dep/graph":
                from dev.tasks.dep_graph import get_project_dependencies

                get_project_dependencies(
                    focus_project_names=args.targets or None,
                    include_artifacts=args.artifacts,
                )

            case "publish":
                from dev.tasks.publish import publish_main

                exit_code = await publish_main(args.targets, dry_run=args.dry_run)

            case "build":
                from dev.tasks.build import build

                exit_code = build(args.targets, json_output=args.json)

            case "duplicates":
                from dev.tasks.duplicates import check_for_duplicates

                check_for_duplicates(
                    args.folders,
                    args.exclude,
                    args.filter,
                    args.size,
                    args.no_default_excludes,
                    include_zip_contents=args.zip_contents,
                    include_weak_encrypted_zip=args.weak_encrypted_zip,
                )

            case "cloc":
                from dev.tasks.cloc import cloc

                cloc(args.targets)

            case "clean":
                from dev.tasks.clean import clean

                clean(args.targets)

            case "status":
                from dev.tasks.status import status

                exit_code = status(args.targets, json_output=args.json)

            case "commit":
                from dev.tasks.commit import commit

                exit_code = commit(args.targets, dry_run=args.dry_run)

            case "push":
                from dev.tasks.push import push

                exit_code = push(args.targets, dry_run=args.dry_run)

            case "project/list":
                from dev.tasks.project_list import list_projects

                list_projects()

            case "project/show":
                from dev.tasks.project_list import show_projects

                show_projects(args.targets, json_output=args.json)

            case "project/deps":
                from dev.tasks.project_list import show_project_dependencies

                show_project_dependencies(args.targets, json_output=args.json)

            case "project/repo":
                from dev.tasks.project_list import show_project_repos

                show_project_repos(args.targets, json_output=args.json)

            case "project/targets":
                from dev.tasks.project_list import show_project_targets

                show_project_targets(args.targets, json_output=args.json)

            case "check/run":
                from dev.tasks.check import check_main

                checks = args.checks
                if not checks:
                    checks = None
                return check_main(args.project_or_dir_or_file, checks, args.fix)

            case "check/list":
                from dev.tasks.check import list_checks

                return list_checks(json_output=args.json)

            case "check/describe":
                from dev.tasks.check import describe_check

                return describe_check(args.check, json_output=args.json)

            case "spdx/headers":
                from dev.tasks.spdx_headers import spdx_headers

                return spdx_headers(args.project_or_dir_or_file, args.fix)

            case "secrets/scan":
                from dev.tasks.check import secrets_scan

                return secrets_scan(args.target)

            case "contributors/audit":
                from dev.tasks.contributors_audit import audit_contributors

                return audit_contributors()

            case _:
                raise ValueError(f"Unknown command: {command_path}")
    except ModuleNotFoundError as ex:
        print(f"{prog}: error: Missing Python dependency: {ex.name!r}.", file=sys.stderr)
        _print_failure_context(command_path, args=args)
        return 2
    except ValueError as ex:
        print(f"{prog}: error: {ex}", file=sys.stderr)
        _print_failure_context(command_path, args=args)
        return 2

    if command_path in {"doctor", "setup", "release/verify", "build", "publish", "project/show", "commit", "push"}:
        _print_next_steps(command_path, prog=prog, args=args)

    return exit_code


def main(*, launch_mode: Literal["script", "module"] = "script") -> None:
    maybe_reexec_to_workspace_venv(launch_mode=launch_mode)
    raise SystemExit(asyncio.run(async_main()))
