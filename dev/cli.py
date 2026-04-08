import argparse
import asyncio
import logging
import os
import re
import sys
import textwrap
from collections.abc import Callable, Sequence

from dev.discoverability import did_you_mean_suffix

##################################################################################################
# Main
##################################################################################################

type ArgParser = argparse.ArgumentParser
type AddParser = Callable[..., ArgParser]

_INVALID_CHOICE_RE = re.compile(r"invalid choice: '([^']+)' \(choose from (.+)\)")


class SuggestingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        match = _INVALID_CHOICE_RE.search(message)
        if match is not None:
            invalid = match.group(1)
            choices = [
                choice.strip().strip("'")
                for choice in match.group(2).split(",")
                if choice.strip().strip("'")
            ]
            suggestion = did_you_mean_suffix(invalid, choices)
            if suggestion:
                message = f"{message}.{suggestion}"
        super().error(message)


class HelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    pass


def _add_argument(
    parser: argparse.ArgumentParser,
    *args: object,
    completion_kind: str | None = None,
    completion_allow_files: bool = False,
    completion_blocks_positionals: bool = False,
    **kwargs: object,
) -> argparse.Action:
    action = parser.add_argument(*args, **kwargs)
    setattr(action, "_completion_kind", completion_kind)
    setattr(action, "_completion_allow_files", completion_allow_files)
    setattr(action, "_completion_blocks_positionals", completion_blocks_positionals)
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


def _guidance_target(args: argparse.Namespace) -> str | None:
    targets = getattr(args, "targets", None)
    if isinstance(targets, list) and targets:
        return targets[0]

    target = getattr(args, "target", None)
    if isinstance(target, str) and target not in {".", ":root"}:
        return target

    project_or_dir_or_file = getattr(args, "project_or_dir_or_file", None)
    if isinstance(project_or_dir_or_file, str) and project_or_dir_or_file not in {".", ":root"}:
        return project_or_dir_or_file

    return None


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
        case "build":
            if target is not None:
                steps = [f"{prog} check {target}", f"{prog} status {target}", f"{prog} publish --dry-run {target}"]
            else:
                steps = [f"{prog} check :root", f"{prog} project list", f"{prog} publish --dry-run"]
        case "publish":
            if getattr(args, "dry_run", False):
                steps = [f"{prog} publish {target}" if target else f"{prog} publish", f"{prog} status {target}" if target else f"{prog} project list", f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run"]
            else:
                steps = [f"{prog} status {target}" if target else f"{prog} project list", f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run", f"{prog} push {target}" if target else f"{prog} push"]
        case "project/show":
            if target is None:
                return
            steps = [f"{prog} project deps {target}", f"{prog} project targets {target}", f"{prog} build {target}"]
        case "commit":
            if getattr(args, "dry_run", False):
                steps = [f"{prog} commit {target}" if target else f"{prog} commit", f"{prog} status {target}" if target else f"{prog} project list", f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run"]
            else:
                steps = [f"{prog} status {target}" if target else f"{prog} project list", f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run", f"{prog} push {target}" if target else f"{prog} push"]
        case "push":
            if getattr(args, "dry_run", False):
                steps = [f"{prog} push {target}" if target else f"{prog} push", f"{prog} status {target}" if target else f"{prog} project list"]
            else:
                steps = [f"{prog} status {target}" if target else f"{prog} project list", f"{prog} project repo {target}" if target else f"{prog} project list"]
        case _:
            return

    print()
    print("Next useful commands:")
    for step in steps:
        print(f"  {step}")


class Commands:
    def __init__(self, parser: ArgParser) -> None:
        self.root_parser = parser
        self.parsers: dict[str, ArgParser] = {}
        self.subparsers: dict[str, AddParser] = {}

    class Command:
        def __init__(
            self,
            commands: "Commands",
            name: str,
            *,
            help: str | None = None,
            description: str | None = None,
            epilog: str | None = None,
        ) -> None:
            path = name.split("/")
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
                subparsers[""] = root_subparsers.add_parser

            for i in range(1, len(path) + 1):
                p = "/".join(path[:i])
                p0 = "/".join(path[: i - 1])
                if p not in parsers:
                    parser_kwargs: dict[str, object] = {"formatter_class": HelpFormatter}
                    if i == len(path):
                        if help is not None:
                            parser_kwargs["help"] = help
                        if description is not None:
                            parser_kwargs["description"] = description
                        if epilog is not None:
                            parser_kwargs["epilog"] = epilog
                    parsers[p] = subparsers[p0](path[i - 1], **parser_kwargs)
                if p not in subparsers and i != len(path):
                    child_subparsers = parsers[p].add_subparsers(
                        dest=subcommand(i),
                        title="subcommands",
                        metavar="SUBCOMMAND",
                        parser_class=SuggestingArgumentParser,
                    )
                    subparsers[p] = child_subparsers.add_parser

            self.parser = parsers[name]
            self.parser.formatter_class = HelpFormatter
            setattr(self.parser, "_completion_hidden", help == argparse.SUPPRESS)
            if description is not None:
                self.parser.description = description
            if epilog is not None:
                self.parser.epilog = epilog
            self.parser.set_defaults(command_path=name)

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
        name: str,
        *,
        help: str | None = None,
        description: str | None = None,
        epilog: str | None = None,
    ) -> "Commands.Command":
        return Commands.Command(
            self,
            name,
            help=help,
            description=description,
            epilog=epilog,
        )


def build_parser() -> tuple[SuggestingArgumentParser, Commands]:
    parser = SuggestingArgumentParser(
        description=_doc(
            """
            Wabbit development toolkit.

            The CLI reads workspace metadata from root.clj and root.private.clj to
            generate project files, run checks, inspect dependencies, build projects,
            publish releases, and automate repository maintenance tasks.
            """
        ),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    prog = parser.prog
    parser.epilog = _epilog(
        examples=[
            f"{prog} doctor",
            f"{prog} completion bash",
            f"{prog} setup --local app-datatron",
            f"{prog} build app-datatron",
            f"{prog} secrets scan .",
            f"{prog} project list",
        ],
        notes=[
            "Install the package and run `wabbit-dev`, or run it from the repo with `python3 dev.py`.",
            "Most commands expect to run from the workspace root so root.clj can be found.",
        ],
    )
    commands = Commands(parser)

    def examples(*command_examples: str, notes: Sequence[str] = ()) -> str | None:
        return _epilog(
            examples=[f"{prog} {example}" for example in command_examples],
            notes=notes,
        )

    with commands(
        "config",
        help="Validate workspace configuration files.",
        description=_doc(
            """
            Parse and validate the workspace configuration files.

            These commands check that root.clj and root.private.clj can be decoded
            into the internal project model before you rely on setup, build, check,
            or publish workflows.
            """
        ),
        epilog=examples("config check"),
    ) as cmd:
        del cmd

    with commands(
        "completion",
        help="Generate shell completion scripts.",
        description=_doc(
            """
            Generate shell completion scripts for the wabbit-dev CLI.

            The generated completions include top-level commands, nested
            subcommands, configured project and repo IDs, and loaded check names.
            """
        ),
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
        "completion/bash",
        help="Print a bash completion script.",
        description=_doc(
            """
            Print a bash completion script to stdout.

            Source it from your shell profile or interactively to enable command,
            subcommand, target, and check-name completion.
            """
        ),
        epilog=examples("completion bash"),
    ) as cmd:
        del cmd

    with commands(
        "completion/zsh",
        help="Print a zsh completion script.",
        description=_doc(
            """
            Print a zsh completion script to stdout.

            Source it from your shell profile after `compinit` to enable command,
            subcommand, target, and check-name completion.
            """
        ),
        epilog=examples("completion zsh"),
    ) as cmd:
        del cmd

    with commands(
        "completion/query",
        help=argparse.SUPPRESS,
        description=argparse.SUPPRESS,
    ) as cmd:
        cmd.add_argument("shell", help=argparse.SUPPRESS)
        cmd.add_argument("index", type=int, help=argparse.SUPPRESS)
        cmd.add_argument("words", nargs="*", help=argparse.SUPPRESS)

    with commands(
        "config/check",
        help="Parse and validate root.clj and root.private.clj.",
        description=_doc(
            """
            Parse root.clj and root.private.clj and fail fast on invalid command
            forms, unknown references, malformed dependency definitions, or other
            configuration errors.
            """
        ),
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
        description=_doc(
            """
            Run an environment and workspace readiness check.

            `doctor` validates the current working directory, required config
            files, Python version, virtual environment usage, tool availability,
            config loading, and publish/commit credentials.
            """
        ),
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
        "setup",
        help="Generate or refresh project files from root.clj.",
        description=_doc(
            """
            Materialize generated files for configured projects.

            `setup` reads root.clj, resolves project dependencies, and writes the
            managed Gradle, Python, legal, workflow, and repository files needed
            for the selected projects.
            """
        ),
        epilog=examples(
            "setup",
            "setup app-wabbit-dev",
            "setup jeeves",
            "setup ./jeeves/client",
            "setup --local app-datatron",
            "setup --dev kotlin-web-openai",
            notes=[
                "Targets can be project IDs, repo IDs, or paths inside configured projects or repos.",
                "With no targets, setup processes every configured project.",
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
        "llmcopy",
        help="Copy file contents to the clipboard in an LLM-friendly envelope.",
        description=_doc(
            """
            Read one or more files, directories, or glob patterns and copy their
            contents to the clipboard using a `<contents path="...">` wrapper that
            is convenient to paste into external tools or prompts.
            """
        ),
        epilog=examples(
            "llmcopy README.md docs",
            "llmcopy 'dev/tasks/*.py'",
            notes=[
                "Directories are traversed recursively.",
                "The command skips `.git`, `.idea`, and `__pycache__` directories by default.",
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
        description=_doc(
            """
            Analyze the dependency metadata loaded from root.clj.

            Use `dep` subcommands to render project dependency graphs or inspect
            whether configured named libraries have newer upstream versions.
            """
        ),
        epilog=examples("dep graph", "dep updates"),
    ) as cmd:
        del cmd

    with commands(
        "dep/graph",
        help="Render an SVG graph of project dependencies.",
        description=_doc(
            """
            Generate an SVG dependency graph from the project relationships defined
            in root.clj.

            By default the graph includes only configured project-to-project
            edges. Use `--artifacts` to include external Maven artifacts as nodes.
            """
        ),
        epilog=examples(
            "dep graph",
            "dep graph app-datatron",
            "dep graph jeeves",
            "dep graph --artifacts kotlin-web-openai",
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
        "dep/updates",
        help="Check configured libraries for newer upstream versions.",
        description=_doc(
            """
            Compare each named Maven library defined in root.clj against the latest
            versions available from its configured repository and print any newer
            candidates that were found.
            """
        ),
        epilog=examples(
            "dep updates",
            notes=[
                "Only named Maven libraries are checked. Project dependencies are not.",
            ],
        ),
    ) as cmd:
        del cmd

    with commands(
        "publish",
        help="Publish configured projects in dependency order.",
        description=_doc(
            """
            Publish selected projects using the publish target inferred from each
            project's metadata and features.

            Gradle projects can publish to Maven Central, JitPack, or JetBrains
            Marketplace. Python projects can publish to PyPI.
            """
        ),
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
        description=_doc(
            """
            Build selected projects after topologically ordering them by configured
            project dependencies.

            Gradle projects run their `build` task. Python projects are syntax
            checked by compiling discovered `.py` files.
            """
        ),
        epilog=examples(
            "build",
            "build app-datatron",
            "build jeeves",
            "build ./jeeves/client",
            "build kotlin-web-openai app-wabbit-dev",
            notes=[
                "Only Gradle and Python projects are buildable through this command.",
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
        description=_doc(
            """
            Scan one or more folders for duplicate files and duplicate directory
            trees using a staged fingerprinting pipeline designed to minimize I/O.

            The command can optionally compare filesystem directories against zip
            contents and, when requested, perform weaker matching for encrypted zip
            archives using visible metadata.
            """
        ),
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
        description=_doc(
            """
            Query JitPack for refs, commits, versions, build metadata, and build
            logs associated with an artifact.
            """
        ),
        epilog=examples("jitpack info wabbit-corp kotlin-base58"),
    ) as cmd:
        del cmd

    with commands(
        "jitpack/info",
        help="Show refs, commits, versions, and build info for a JitPack artifact.",
        description=_doc(
            """
            Inspect the current JitPack state for an artifact by printing:

            - known refs
            - recent master commits
            - published versions
            - build details and any compiler-style errors discovered in build logs
            """
        ),
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
        description=_doc(
            """
            Remove common generated directories such as `build`, `.gradle`,
            `.pytest_cache`, `.mypy_cache`, `.kotlin`, and Python `__pycache__`
            directories from configured projects.
            """
        ),
        epilog=examples(
            "clean",
            "clean app-wabbit-dev",
            "clean jeeves",
            notes=[
                "Targets can be project IDs, repo IDs, or paths inside configured projects or repos.",
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
        description=_doc(
            """
            Run `cloc` and print language totals.

            For configured targets, the command focuses on source directories that
            matter for each project type. When given an arbitrary path, it runs
            `cloc` directly on that path.
            """
        ),
        epilog=examples("cloc", "cloc app-wabbit-dev", "cloc jeeves", "cloc app-wabbit-dev/dev"),
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
        help="Show tracked working-tree changes for repo targets.",
        description=_doc(
            """
            Print the tracked files that differ between the git index and working
            tree.

            This is closest to the unstaged portion of `git status` for one or
            more resolved repository targets.
            """
        ),
        epilog=examples(
            "status app-wabbit-dev",
            "status jeeves",
            "status ./app-wabbit-dev",
            "status app-wabbit-dev jeeves/client",
            notes=[
                "The command reports tracked working-tree changes. Untracked files are not shown.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="+",
            completion_kind="repo-target",
            completion_allow_files=True,
            help="Repo IDs, project IDs, or paths inside git repositories.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="Emit repo status details as JSON instead of human-oriented text.",
        )

    with commands(
        "commit",
        help="Run setup, stage changes, and create commits for configured projects.",
        description=_doc(
            """
            Run PROD setup for the target projects, group them by repository,
            stage detected changes, and generate commit messages using the OpenAI
            key configured in root.private.clj.
            """
        ),
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
        description=_doc(
            """
            Push tags plus the `master` branch to `origin`.

            With no targets or `.` the command walks every configured project repo
            and pushes each distinct repository once. With explicit targets it
            pushes the repos resolved from those repo IDs, project IDs, or paths.
            """
        ),
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
        description=_doc(
            """
            Explore the projects defined in root.clj and how repo-managed projects
            are grouped under their parent repositories.
            """
        ),
        epilog=examples(
            "project list",
            "project show app-wabbit-dev",
            "project deps jeeves",
            "project repo jeeves",
            "project targets",
        ),
    ) as cmd:
        del cmd

    with commands(
        "project/list",
        help="List configured projects grouped by repository.",
        description=_doc(
            """
            Print every configured project in declaration order, grouping nested
            repo-managed projects under their containing repository and labeling
            each entry by its detected project type.
            """
        ),
        epilog=examples("project list"),
    ) as cmd:
        del cmd

    with commands(
        "project/show",
        help="Show detailed metadata for one or more configured projects.",
        description=_doc(
            """
            Print the resolved metadata for one or more projects.

            This includes the project type, path, repo root, resolved
            dependencies, publish target, docs system, JVM policy, and the main
            generated files that `setup` is expected to manage.
            """
        ),
        epilog=examples(
            "project show app-wabbit-dev",
            "project show jeeves",
            "project show ./jeeves/client",
            "project show app-wabbit-dev --json",
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="+",
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
        "project/deps",
        help="Show resolved dependencies for one or more configured projects.",
        description=_doc(
            """
            Print the resolved dependency list for one or more projects.

            Targets can be individual projects, whole configured repos, or paths
            inside configured projects or repos.
            """
        ),
        epilog=examples(
            "project deps app-wabbit-dev",
            "project deps jeeves",
            "project deps ./jeeves/client",
            "project deps jeeves --json",
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="+",
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
        "project/repo",
        help="Show repository metadata for one or more configured targets.",
        description=_doc(
            """
            Print the repo-level metadata associated with one or more configured
            projects or repos.

            Targets can be project IDs, repo IDs, or paths inside configured
            projects or repos. Repositories are de-duplicated in the output.
            """
        ),
        epilog=examples(
            "project repo app-wabbit-dev",
            "project repo jeeves",
            "project repo ./jeeves/client",
            "project repo jeeves --json",
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "targets",
            metavar="TARGET",
            type=str,
            nargs="+",
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
        "project/targets",
        help="Show Kotlin Multiplatform target platforms for configured projects.",
        description=_doc(
            """
            Print the declared Kotlin Multiplatform target platforms for one or
            more configured projects.

            With no targets, this lists every configured KMP project in
            declaration order. Explicit targets can be project IDs, repo IDs, or
            paths inside configured projects or repos; non-KMP projects are
            ignored.
            """
        ),
        epilog=examples(
            "project targets",
            "project targets kotlin-filesystem",
            "project targets jeeves",
            "project targets kotlin-filesystem --json",
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
        help="Run repository and source checks.",
        description=_doc(
            """
            Run the configured check suite against a project, directory, or file.

            Targets can be:

            - a filesystem path
            - a bare project ID or repo ID
            - a project or repo ID prefixed with `:`
            - `:root` to check every configured project path
            """
        ),
        epilog=examples(
            "check --list",
            "check --list --json",
            "check --describe SpdxHeaderCheck",
            "check --describe SpdxHeaderCheck --json",
            "check",
            "check app-wabbit-dev/dev/cli.py",
            "check app-wabbit-dev",
            "check :app-wabbit-dev",
            "check jeeves",
            "check :root --fix",
            "check . SpdxHeaderCheck",
            notes=[
                "Use `--list` to browse loaded checks and `--describe <check>` for issue IDs and suppression examples.",
                "Explicit check names use the Python class names registered by the check modules.",
                "Checks honor `.gitignore`, `.checkignore`, and suppressions configured in root.clj.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "--list",
            action="store_true",
            completion_blocks_positionals=True,
            help="List all loaded checks with their scope, auto-fix support, and short summary.",
        )
        _add_argument(
            cmd,
            "--describe",
            metavar="CHECK",
            completion_kind="check-name",
            completion_blocks_positionals=True,
            help="Show issue IDs, config commands, and suppression examples for one check.",
        )
        cmd.add_argument(
            "--json",
            action="store_true",
            help="When used with `--list` or `--describe`, emit JSON instead of text.",
        )
        _add_argument(
            cmd,
            "project_or_dir_or_file",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=".",
            completion_kind="check-target",
            completion_allow_files=True,
            help="Filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`.",
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
        "spdx",
        help="SPDX-related quality commands.",
        description=_doc(
            """
            Run SPDX-specific tooling derived from the general check runner.
            """
        ),
        epilog=examples("spdx headers"),
    ) as cmd:
        del cmd

    with commands(
        "spdx/headers",
        help="Audit or fix SPDX file headers.",
        description=_doc(
            """
            Run only the SPDX header check against a project, directory, or file.

            This is a focused shortcut for `check ... SpdxHeaderCheck`.
            """
        ),
        epilog=examples(
            "spdx headers .",
            "spdx headers app-wabbit-dev --fix",
            "spdx headers jeeves",
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "project_or_dir_or_file",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=".",
            completion_kind="check-target",
            completion_allow_files=True,
            help="Filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`.",
        )
        cmd.add_argument(
            "--fix",
            action="store_true",
            help="Insert or normalize SPDX headers when the check can do so safely.",
        )

    with commands(
        "secrets",
        help="Scan for secrets and secret-like strings.",
        description=_doc(
            """
            Run secret-related scanning commands.

            The current implementation uses the internal check runner rather
            than invoking an external secret scanning binary.
            """
        ),
        epilog=examples("secrets scan ."),
    ) as cmd:
        del cmd

    with commands(
        "secrets/scan",
        help="Run the high-entropy-string secret check.",
        description=_doc(
            """
            Run the high-entropy-string secret scan against a target path.

            This is equivalent to running the `HighEntropyStringCheck` through
            the general check runner.
            """
        ),
        epilog=examples(
            "secrets scan .",
            "secrets scan app-wabbit-dev",
            "secrets scan jeeves",
            notes=[
                "Targets can be a filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`.",
            ],
        ),
    ) as cmd:
        _add_argument(
            cmd,
            "target",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=".",
            completion_kind="check-target",
            completion_allow_files=True,
            help="Filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`.",
        )

    with commands(
        "contributors",
        help="Inspect repository contributor identity.",
        description=_doc(
            """
            Run contributor-related repository audits.
            """
        ),
        epilog=examples("contributors audit"),
    ) as cmd:
        del cmd

    with commands(
        "contributors/audit",
        help="Audit git contributor identity mismatches across configured repos.",
        description=_doc(
            """
            Walk configured git repositories and report contributors whose name
            or email does not match the expected default git identity from the
            loaded configuration.
            """
        ),
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

    args = parser.parse_args()
    command_path = getattr(args, "command_path", None)
    if command_path is None:
        parser.print_help()
        return 0

    if command_path in commands.subparsers:
        commands.parsers[command_path].print_help()
        return 0

    from dev.tasks.doctor import preflight_for_command

    selected_projects: tuple[str, ...] | None = None
    if command_path in {"setup", "build", "publish", "commit", "clean", "dep/graph"} and args.targets:
        selected_projects = tuple(args.targets)
    elif command_path in {"project/show", "project/deps", "project/repo", "project/targets"}:
        selected_projects = tuple(args.targets)

    if not preflight_for_command(
        command_path,
        prog=prog,
        projects=selected_projects,
        dry_run=getattr(args, "dry_run", False),
    ):
        return 2

    try:
        exit_code = 0
        match command_path:
            case "completion/bash":
                from dev.tasks.completion import print_completion_script

                exit_code = print_completion_script("bash", prog=prog)

            case "completion/zsh":
                from dev.tasks.completion import print_completion_script

                exit_code = print_completion_script("zsh", prog=prog)

            case "completion/query":
                from dev.tasks.completion import print_completion_query

                return print_completion_query(args.shell, args.index, args.words)

            case "doctor":
                from dev.tasks.doctor import doctor

                exit_code = doctor(json_output=args.json, only=args.only, targets=args.targets)

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

            case "check":
                from dev.tasks.check import check_main, describe_check, list_checks

                if args.list:
                    if args.project_or_dir_or_file != "." or args.checks or args.describe is not None or args.fix:
                        raise ValueError("`check --list` does not accept TARGET, CHECK, --describe, or --fix.")
                    exit_code = list_checks(json_output=args.json)
                    return exit_code

                if args.describe is not None:
                    if args.project_or_dir_or_file != "." or args.checks or args.fix:
                        raise ValueError("`check --describe` does not accept TARGET, CHECK, or --fix.")
                    exit_code = describe_check(args.describe, json_output=args.json)
                    return exit_code

                if args.json:
                    raise ValueError("`check --json` currently requires either `--list` or `--describe`.")

                checks = args.checks
                if not checks:
                    checks = None
                return check_main(args.project_or_dir_or_file, checks, args.fix)

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
    except ValueError as ex:
        print(f"{prog}: error: {ex}", file=sys.stderr)
        return 2

    if command_path in {"doctor", "setup", "build", "publish", "project/show", "commit", "push"}:
        _print_next_steps(command_path, prog=prog, args=args)

    return exit_code


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))
