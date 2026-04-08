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


async def async_main() -> int:
    if sys.platform.lower() == "win32":
        os.system("color")
        os.system("chcp 65001 > nul")
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore

    logging.basicConfig(level=logging.INFO, format="%(message)s")

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
            notes=[
                "Use this when a command fails due to missing config, tools, or credentials.",
            ],
        ),
    ) as cmd:
        del cmd

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
            "setup --local app-datatron",
            "setup --dev kotlin-web-openai",
            notes=[
                "With no project arguments, setup processes every configured project.",
                "`--local` writes local composite-build overlays for multi-repo development.",
                "`--dev` switches to the DEV setup mode; the default is PROD.",
            ],
        ),
    ) as cmd:
        cmd.add_argument(
            "projects",
            metavar="PROJECT",
            type=str,
            nargs="*",
            help="Project IDs from root.clj. Omit to process every configured project.",
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
        cmd.add_argument(
            "path",
            metavar="PATH",
            type=str,
            nargs="+",
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
            "dep graph --artifacts kotlin-web-openai",
        ),
    ) as cmd:
        cmd.add_argument(
            "project",
            metavar="PROJECT",
            type=str,
            nargs="?",
            default=".",
            help="Optional project ID from root.clj. Omit to graph the full workspace.",
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
            notes=[
                "Credentials are loaded from root.private.clj and, for some publish flows, environment variables.",
                "Projects with no publish target are skipped rather than treated as errors.",
            ],
        ),
    ) as cmd:
        cmd.add_argument(
            "project",
            metavar="PROJECT",
            type=str,
            nargs="?",
            help="Optional project ID from root.clj. Omit to publish every publishable project.",
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
            "build kotlin-web-openai app-wabbit-dev",
            notes=[
                "Only Gradle and Python projects are buildable through this command.",
            ],
        ),
    ) as cmd:
        cmd.add_argument(
            "projects",
            metavar="PROJECT",
            type=str,
            nargs="*",
            help="Project IDs from root.clj. Omit to build every buildable configured project.",
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
        cmd.add_argument(
            "folders",
            metavar="FOLDER",
            type=str,
            nargs="+",
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
            notes=[
                "When a project is supplied it must be a project ID from root.clj.",
            ],
        ),
    ) as cmd:
        cmd.add_argument(
            "project",
            metavar="PROJECT",
            type=str,
            nargs="?",
            help="Optional project ID from root.clj. Omit to clean every configured project.",
        )

    with commands(
        "cloc",
        help="Summarize lines of code for a configured project or path.",
        description=_doc(
            """
            Run `cloc` and print language totals.

            For configured projects, the command focuses on source directories that
            matter for that project type. When given an arbitrary path, it runs
            `cloc` directly on that path.
            """
        ),
        epilog=examples("cloc", "cloc app-wabbit-dev", "cloc app-wabbit-dev/dev"),
    ) as cmd:
        cmd.add_argument(
            "project_or_dir_or_file",
            metavar="TARGET",
            type=str,
            nargs="?",
            help="Optional configured project ID or filesystem path.",
        )

    with commands(
        "status",
        help="Show tracked working-tree changes for a project or git path.",
        description=_doc(
            """
            Print the tracked files that differ between the git index and working
            tree.

            This is closest to the unstaged portion of `git status` for a single
            repository path.
            """
        ),
        epilog=examples(
            "status app-wabbit-dev",
            "status ./app-wabbit-dev",
            notes=[
                "The command reports tracked working-tree changes. Untracked files are not shown.",
            ],
        ),
    ) as cmd:
        cmd.add_argument(
            "target",
            metavar="TARGET",
            type=str,
            help="A configured project ID from root.clj, or any path inside a git repository.",
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
            notes=[
                "This command requires an OpenAI key in root.private.clj.",
                "The commit message policy is repository-specific and enforced by the commit workflow.",
            ],
        ),
    ) as cmd:
        cmd.add_argument(
            "project",
            metavar="PROJECT",
            type=str,
            nargs="?",
            help="Optional project ID from root.clj. Omit to process every configured project.",
        )

    with commands(
        "push",
        help="Push origin/master and tags for one repo or all configured repos.",
        description=_doc(
            """
            Push tags plus the `master` branch to `origin`.

            With `.` the command walks every configured project repo and pushes
            each distinct repository once. With any other value it pushes the repo
            resolved from that configured project ID or path.
            """
        ),
        epilog=examples(
            "push .",
            "push app-wabbit-dev",
            "push ./app-wabbit-dev",
            notes=[
                "The branch target is currently hard-coded to `master`.",
            ],
        ),
    ) as cmd:
        cmd.add_argument(
            "project",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=".",
            help="Use `.` for all configured repos, or provide a configured project ID or path.",
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
        epilog=examples("project list", "project show app-wabbit-dev"),
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
        help="Show detailed metadata for one configured project.",
        description=_doc(
            """
            Print the resolved metadata for a single project.

            This includes the project type, path, repo root, resolved
            dependencies, publish target, docs system, JVM policy, and the main
            generated files that `setup` is expected to manage.
            """
        ),
        epilog=examples("project show app-wabbit-dev", "project show jeeves/client"),
    ) as cmd:
        cmd.add_argument(
            "project",
            metavar="PROJECT",
            type=str,
            help="Configured project ID from root.clj.",
        )

    with commands(
        "check",
        help="Run repository and source checks.",
        description=_doc(
            """
            Run the configured check suite against a project, directory, or file.

            Targets can be:

            - a filesystem path
            - a project ID prefixed with `:`
            - `:root` to check every configured project path
            """
        ),
        epilog=examples(
            "check --list",
            "check --describe SpdxHeaderCheck",
            "check",
            "check app-wabbit-dev/dev/cli.py",
            "check :app-wabbit-dev",
            "check :root --fix",
            "check . SpdxHeaderCheck",
            notes=[
                "Use `--list` to browse loaded checks and `--describe <check>` for issue IDs and suppression examples.",
                "Explicit check names use the Python class names registered by the check modules.",
                "Checks honor `.gitignore`, `.checkignore`, and suppressions configured in root.clj.",
            ],
        ),
    ) as cmd:
        cmd.add_argument(
            "--list",
            action="store_true",
            help="List all loaded checks with their scope, auto-fix support, and short summary.",
        )
        cmd.add_argument(
            "--describe",
            metavar="CHECK",
            help="Show issue IDs, config commands, and suppression examples for one check.",
        )
        cmd.add_argument(
            "project_or_dir_or_file",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=".",
            help="Filesystem path, `:project-id`, or `:root`. Defaults to the current directory.",
        )
        cmd.add_argument(
            "checks",
            metavar="CHECK",
            type=str,
            nargs="*",
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
        ),
    ) as cmd:
        cmd.add_argument(
            "project_or_dir_or_file",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=".",
            help="Configured project ID or filesystem path to inspect.",
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
            notes=[
                "Targets can be a filesystem path, `:project-id`, or `:root`.",
            ],
        ),
    ) as cmd:
        cmd.add_argument(
            "target",
            metavar="TARGET",
            type=str,
            nargs="?",
            default=".",
            help="Filesystem path, `:project-id`, or `:root`. Defaults to the current directory.",
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
    if command_path == "setup" and args.projects:
        selected_projects = tuple(args.projects)
    elif command_path == "build" and args.projects:
        selected_projects = tuple(args.projects)
    elif command_path in {"publish", "commit", "clean", "project/show"} and args.project:
        selected_projects = (args.project,)
    elif command_path == "dep/graph" and args.project != ".":
        selected_projects = (args.project,)

    if not preflight_for_command(command_path, prog=prog, projects=selected_projects):
        return 2

    try:
        match command_path:
            case "doctor":
                from dev.tasks.doctor import doctor

                return doctor()

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
                setup(mode, projects=args.projects)

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
                    focus_project_name=args.project if args.project != "." else None,
                    include_artifacts=args.artifacts,
                )

            case "publish":
                from dev.tasks.publish import publish_main

                await publish_main(args.project)

            case "build":
                from dev.tasks.build import build

                build(args.projects)

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

                cloc(args.project_or_dir_or_file)

            case "clean":
                from dev.tasks.clean import clean

                clean(args.project)

            case "status":
                from dev.tasks.status import status

                status(args.target)

            case "commit":
                from dev.tasks.commit import commit

                project_name = args.project
                assert project_name is None or isinstance(project_name, str), f"Expected str|None, got {type(project_name)}"
                commit(project_name)

            case "push":
                from dev.tasks.push import push

                push(args.project)

            case "project/list":
                from dev.tasks.project_list import list_projects

                list_projects()

            case "project/show":
                from dev.tasks.project_list import show_project

                show_project(args.project)

            case "check":
                from dev.tasks.check import check_main, describe_check, list_checks

                if args.list:
                    if args.project_or_dir_or_file != "." or args.checks or args.describe is not None or args.fix:
                        raise ValueError("`check --list` does not accept TARGET, CHECK, --describe, or --fix.")
                    return list_checks()

                if args.describe is not None:
                    if args.project_or_dir_or_file != "." or args.checks or args.fix:
                        raise ValueError("`check --describe` does not accept TARGET, CHECK, or --fix.")
                    return describe_check(args.describe)

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

    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))
