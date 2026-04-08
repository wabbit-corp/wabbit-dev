from __future__ import annotations

import inspect
import json
import re
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import TypeVar

import pathspec

from dev.base import Module
from dev.checks.base import (
    Check,
    CheckFailedWithReportedIssues,
    DirectoryCheck,
    FileCheck,
    FileContext,
    Issue,
    IssueList,
    IssueType,
    ProjectCheck,
    RepoCheck,
    ScopedFindingIgnoreRule,
    ScopedReadSuppressions,
    Severity,
    known_issue_types,
)
from dev.config import Project, find_workspace_root, load_config
from dev.discoverability import did_you_mean_suffix, unknown_name_message
from dev.messages import error, info, warning
from dev.repo_resolution import inferred_project_targets, resolve_check_paths

E_GITIGNORE_WITHOUT_REPO = IssueType(
    "E_GITIGNORE_WITHOUT_REPO",
    "Gitignore file found without a git repository.",
)

_ISSUE_ID_RE = re.compile(r"\b(E_[A-Z0-9_]+)\b")


@dataclass(frozen=True)
class CheckCatalogEntry:
    name: str
    kind: str
    summary: str
    fixable: str
    issue_types: tuple[IssueType, ...]
    config_commands: tuple[str, ...]


def _load_optional_config(start: str | Path = ".") -> object | None:
    if find_workspace_root(Path(start)) is None:
        return None
    return load_config(Path(start))


def _load_check_modules(config: object | None) -> dict[str, Module]:
    if config is not None and hasattr(config, "modules"):
        return config.modules

    try:
        return Module.load_modules()
    except Exception as ex:
        warning(f"Failed to auto-load checks without config: {ex}")
        return {}


def _load_all_checks(config: object | None) -> dict[str, Check]:
    modules = _load_check_modules(config)
    return {
        check_name: check
        for check_name, check in modules.items()
        if isinstance(check, Check)
    }


def _check_kind(check: Check) -> str:
    if isinstance(check, RepoCheck):
        return "repo"
    if isinstance(check, ProjectCheck):
        return "project"
    if isinstance(check, DirectoryCheck):
        return "directory"
    if isinstance(check, FileCheck):
        return "file"
    return "check"


def _normalize_summary(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    cleaned = re.sub(r"\s*\(\{[^}]+\}\)", "", cleaned)
    cleaned = re.sub(r"\{[^}]+\}", "value", cleaned)
    cleaned = cleaned.replace("'value'", "value").replace('"value"', "value")
    cleaned = cleaned.strip(" -*")
    return cleaned.rstrip(".") + "." if cleaned else ""


def _humanize_check_name(name: str) -> str:
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", name.removesuffix("Check")).strip().lower()
    if not words:
        return name
    return f"Check {words}."


def _issue_types_for_check(check: Check) -> tuple[IssueType, ...]:
    module = inspect.getmodule(check.__class__)
    if module is None:
        return ()

    issue_types_by_name = {
        name: value
        for name, value in vars(module).items()
        if isinstance(value, IssueType)
    }
    if not issue_types_by_name:
        return ()

    try:
        source = inspect.getsource(check.__class__)
    except OSError:
        source = ""

    ordered_ids: list[str] = []
    seen: set[str] = set()
    for issue_id in _ISSUE_ID_RE.findall(source):
        for value in issue_types_by_name.values():
            if value.id != issue_id or value.id in seen:
                continue
            ordered_ids.append(value.id)
            seen.add(value.id)

    if ordered_ids:
        ordered: list[IssueType] = []
        for issue_id in ordered_ids:
            for value in issue_types_by_name.values():
                if value.id == issue_id:
                    ordered.append(value)
                    break
        return tuple(ordered)

    if len(issue_types_by_name) == 1:
        return tuple(issue_types_by_name.values())

    return ()


def _config_commands_for_check(check: Check) -> tuple[str, ...]:
    try:
        registrations = check.register_typed_config_commands()
    except Exception:
        return ()

    tags = [
        tag
        for registration in registrations
        if (tag := getattr(registration.command_type, "__mu_tag__", None)) is not None
    ]
    return tuple(tags)


def _check_fixable(check: Check) -> str:
    try:
        source = inspect.getsource(check.__class__)
    except OSError:
        return "unknown"

    if "fix=" in source or ".fixable(" in source:
        return "yes"
    return "no"


def _check_summary(check: Check, issue_types: Sequence[IssueType]) -> str:
    raw_doc = check.__class__.__doc__
    if raw_doc:
        doc = inspect.cleandoc(raw_doc)
        first_paragraph = doc.split("\n\n", 1)[0].replace("\n", " ")
        if ":" in first_paragraph:
            head, tail = first_paragraph.split(":", 1)
            if "- " in tail:
                return _normalize_summary(head)
        sentence_match = re.search(r"(.+?[.?!])(?:\s|$)", first_paragraph)
        if sentence_match is not None:
            return _normalize_summary(sentence_match.group(1))
        return _normalize_summary(first_paragraph)
    if issue_types:
        return _normalize_summary(issue_types[0].message)
    return _humanize_check_name(check.__class__.__name__)


def _catalog_entry(check: Check) -> CheckCatalogEntry:
    issue_types = _issue_types_for_check(check)
    return CheckCatalogEntry(
        name=check.__class__.__name__,
        kind=_check_kind(check),
        summary=_check_summary(check, issue_types),
        fixable=_check_fixable(check),
        issue_types=issue_types,
        config_commands=_config_commands_for_check(check),
    )


def _catalog(config: object | None = None) -> dict[str, CheckCatalogEntry]:
    checks = _load_all_checks(config)
    return {
        name: _catalog_entry(check)
        for name, check in checks.items()
    }


def load_check_catalog(config: object | None = None) -> dict[str, CheckCatalogEntry]:
    return _catalog(config)


def list_check_names(config: object | None = None) -> list[str]:
    return sorted(load_check_catalog(config))


def _config_target_choices(config: object | None) -> list[str]:
    if config is None or not hasattr(config, "defined_projects") or not hasattr(config, "defined_repos"):
        return []
    return list(dict.fromkeys([*config.defined_projects.keys(), *config.defined_repos.keys()]))


def _issue_type_payload(issue_type: IssueType) -> dict[str, str]:
    return {
        "id": issue_type.id,
        "message": issue_type.message,
        "severity": issue_type.severity.value,
    }


def _check_catalog_payload(entry: CheckCatalogEntry) -> dict[str, object]:
    return {
        "name": entry.name,
        "kind": entry.kind,
        "summary": entry.summary,
        "fixable": entry.fixable,
        "configCommands": list(entry.config_commands),
        "issueTypes": [_issue_type_payload(issue_type) for issue_type in entry.issue_types],
    }


def list_checks(*, json_output: bool = False) -> int:
    catalog = _catalog(_load_optional_config())
    if not catalog:
        warning("No checks were loaded.")
        return 1

    entries = sorted(catalog.values(), key=lambda entry: (entry.kind, entry.name))
    if json_output:
        print(json.dumps({"checks": [_check_catalog_payload(entry) for entry in entries]}, indent=2))
        return 0

    name_width = max(len(entry.name) for entry in entries)
    kind_width = max(len(entry.kind) for entry in entries)
    fix_width = max(len(entry.fixable) for entry in entries)

    print(f"Available checks ({len(entries)}):")
    for entry in entries:
        print(
            f"  {entry.name.ljust(name_width)}  "
            f"{entry.kind.ljust(kind_width)}  "
            f"fix:{entry.fixable.ljust(fix_width)}  "
            f"{entry.summary}"
        )
    print()
    print("Run `check --describe <check>` for issue IDs, config knobs, and suppression examples.")
    return 0


def describe_check(check_name: str, *, json_output: bool = False) -> int:
    catalog = _catalog(_load_optional_config())
    entry = catalog.get(check_name)
    if entry is None:
        raise ValueError(unknown_name_message("check", check_name, catalog))

    issue_id = entry.issue_types[0].id if entry.issue_types else "E_SOME_ISSUE"
    payload = {
        "check": {
            **_check_catalog_payload(entry),
            "suppressionExamples": {
                "rootCljDisable": f'(checks/disable "{issue_id}" "**/*")',
                "rootCljIgnoreFinding": f'(checks/ignore-finding "{issue_id}" "**/*" "needle")',
                "inlineIgnore": f"# check:ignore {issue_id}" if entry.kind == "file" else None,
                "inlineIgnoreValue": f"# check:ignore {issue_id} value=needle" if entry.kind == "file" else None,
            },
        }
    }
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Check: {entry.name}")
    print(f"Kind: {entry.kind}")
    print(f"Summary: {entry.summary}")
    print(f"Auto-fix support: {entry.fixable}")
    if entry.config_commands:
        print("Config commands:")
        for command in entry.config_commands:
            print(f"  - {command}")
    else:
        print("Config commands: none")

    if entry.issue_types:
        print("Issue types:")
        for issue_type in entry.issue_types:
            print(f"  - {issue_type.id}: {issue_type.message}")
    else:
        print("Issue types: not detected automatically")

    print("Suppression examples:")
    print(f'  - root.clj disable: (checks/disable "{issue_id}" "**/*")')
    print(f'  - root.clj ignore finding text: (checks/ignore-finding "{issue_id}" "**/*" "needle")')
    if entry.kind == "file":
        print(f"  - inline ignore (content-based checks only): # check:ignore {issue_id}")
        print(f"  - inline ignore specific value: # check:ignore {issue_id} value=needle")
    return 0


def secrets_scan(
    project_or_dir_or_file: str | None = None,
    fix: bool = False,
) -> int:
    return check_main(project_or_dir_or_file, ["HighEntropyStringCheck"], fix)


def check_main(
    project_or_dir_or_file: str | None,
    enabled_checks: list[str] | None = None,
    fix: bool = False,
) -> int:
    """
    Main function to run checks on the project.
    """

    lookup_target = project_or_dir_or_file or "."
    config = _load_optional_config(lookup_target)
    if config is None:
        warning("No config file found. Some checks may not have sufficient context to run.")

    effective_target = lookup_target
    if project_or_dir_or_file is None and config is not None:
        inferred_targets = inferred_project_targets(config)
        if inferred_targets is not None:
            effective_target = inferred_targets[0]

    config_root = (
        config.workspace_root
        if config is not None and hasattr(config, "workspace_root") and config.workspace_root is not None
        else Path.cwd().resolve()
    )

    projects_by_path: dict[Path, Project] = {}
    if config is not None:
        for project in config.defined_projects.values():
            projects_by_path[project.path.resolve()] = project

    root_paths = resolve_check_paths(effective_target, config=config)

    for path in root_paths:
        if not path.exists():
            suggestion = did_you_mean_suffix(effective_target, _config_target_choices(config))
            raise ValueError(f"Path does not exist: {path}.{suggestion}")

    all_checks = _load_all_checks(config)

    for check_name in enabled_checks or []:
        if check_name not in all_checks:
            raise ValueError(unknown_name_message("check", check_name, all_checks))

    check_set = set(enabled_checks) if enabled_checks else set(all_checks.keys())
    all_checks = {k: v for k, v in all_checks.items() if k in check_set}

    TCheck = TypeVar("TCheck", bound=Check)

    def sort_checks_typed(checks: Sequence[TCheck]) -> list[TCheck]:
        return sorted(
            checks,
            key=lambda c: (getattr(c, "order", 1000), c.__class__.__name__),
        )

    repo_checks: list[RepoCheck] = sort_checks_typed([v for v in all_checks.values() if isinstance(v, RepoCheck)])
    project_checks: list[ProjectCheck] = sort_checks_typed(
        [v for v in all_checks.values() if isinstance(v, ProjectCheck)]
    )
    file_checks: list[FileCheck] = sort_checks_typed([v for v in all_checks.values() if isinstance(v, FileCheck)])
    dir_checks: list[DirectoryCheck] = sort_checks_typed(
        [v for v in all_checks.values() if isinstance(v, DirectoryCheck)]
    )

    disabled_checks: dict[str, pathspec.PathSpec] = {}
    ignored_findings: list[tuple[str, pathspec.PathSpec, str]] = []
    known_types = known_issue_types()
    if config is not None:
        patterns_by_error_name: dict[str, list[str]] = {}
        for error_name, pattern in config.disabled_checks:
            assert isinstance(error_name, str), f"Expected string, got {type(error_name)}"
            assert isinstance(pattern, str), f"Expected string, got {type(pattern)}"
            assert (
                error_name in known_types or error_name == "*"
            ), f"Unknown error type in disabled_checks: {repr(error_name)}"

            if error_name == "*":
                for known_error in known_types:
                    if known_error not in patterns_by_error_name:
                        patterns_by_error_name[known_error] = []
                    patterns_by_error_name[known_error].append(pattern)
            else:
                if error_name not in patterns_by_error_name:
                    patterns_by_error_name[error_name] = []
                patterns_by_error_name[error_name].append(pattern)

        for error_name, patterns in patterns_by_error_name.items():
            disabled_checks[error_name] = pathspec.PathSpec.from_lines(
                pathspec.patterns.gitwildmatch.GitWildMatchPattern, patterns
            )

        for error_name, pattern, value in config.ignored_findings:
            assert isinstance(error_name, str), f"Expected string, got {type(error_name)}"
            assert isinstance(pattern, str), f"Expected string, got {type(pattern)}"
            assert isinstance(value, str), f"Expected string, got {type(value)}"
            assert (
                error_name in known_types or error_name == "*"
            ), f"Unknown error type in ignored_findings: {repr(error_name)}"
            ignored_findings.append(
                (
                    error_name,
                    pathspec.PathSpec.from_lines(
                        pathspec.patterns.gitwildmatch.GitWildMatchPattern,
                        [pattern],
                    ),
                    value,
                )
            )

    # print(f"Disabled checks: {disabled_checks}")

    def issue_message(issue: Issue, report_format_error: bool = False) -> str:
        try:
            return issue.issue_type.message.format(**(issue.data or {}))
        except Exception as e:
            if report_format_error:
                error(f"Error formatting issue message: {e} with type: {issue.issue_type} and data: {issue.data}")
            return issue.issue_type.message

    def issue_relative_path(path: Path) -> str:
        abs_path = path.absolute()
        try:
            rel_path = abs_path.relative_to(config_root)
        except ValueError:
            rel_path = abs_path
        return str(rel_path)

    def is_check_disabled(issue: Issue) -> bool:
        if issue.location is not None and issue.issue_type.id in disabled_checks:
            spec = disabled_checks[issue.issue_type.id]
            result = spec.match_file(issue_relative_path(issue.location.path))
            if result:
                return True

        if issue.location is not None and ignored_findings:
            path_text = issue_relative_path(issue.location.path)
            message = issue_message(issue, report_format_error=False)
            for error_name, spec, value in ignored_findings:
                if error_name != "*" and error_name != issue.issue_type.id:
                    continue
                if not spec.match_file(path_text):
                    continue
                if value in message:
                    return True

        return False

    def scoped_read_suppressions_for(path: Path) -> ScopedReadSuppressions | None:
        if not ignored_findings:
            return None
        relative_path = issue_relative_path(path)
        scoped_rules: list[ScopedFindingIgnoreRule] = []
        for error_name, spec, value in ignored_findings:
            if not spec.match_file(relative_path):
                continue
            scoped_rules.append(
                ScopedFindingIgnoreRule(
                    issue_id=error_name,
                    value=value,
                )
            )
        if not scoped_rules:
            return None
        return ScopedReadSuppressions(config_ignores=tuple(scoped_rules))

    has_errors = False

    def report(issue: Issue | IssueList | list[Issue]) -> None:
        nonlocal has_errors
        if isinstance(issue, IssueList) or isinstance(issue, list):
            for i in issue:
                report(i)
            return

        if is_check_disabled(issue):
            return

        msg = ""

        msg += f"[{issue.issue_type.id}] "
        msg += "(fixable) " if issue.fix else ""

        if issue.location is not None:
            msg += str(issue.location.path)
            if issue.location.lines:
                msg += ":"
                msg += ",".join(
                    f"{line[0]}-{line[1]}" if line[0] != line[1] else str(line[0])
                    for line in issue.location.lines.ranges
                )
            msg += " > "
        else:
            msg += "> "

        msg += issue_message(issue, report_format_error=True)

        if issue.issue_type.severity not in (Severity.INFO, Severity.WARNING):
            has_errors = True

        # data_str = (
        #     ", ".join(f"{k}={v}" for k, v in issue.data.items() if v is not None)
        #     if issue.data
        #     else ""
        # )
        # if data_str:
        #     msg += f" ({data_str})"

        error(msg)

    @dataclass(frozen=True)
    class RepoContext:
        root: Path
        ignore: list[str] = field(default_factory=list)

        def with_ignore(self, ignore: list[str]) -> RepoContext:
            return RepoContext(
                root=self.root,
                ignore=self.ignore + ignore,
            )

        @cached_property
        def spec(self) -> pathspec.PathSpec:
            """
            Returns a pathspec.PathSpec object for the ignore patterns.
            """
            from pathspec import PathSpec
            from pathspec.patterns.gitwildmatch import GitWildMatchPattern

            return PathSpec.from_lines(
                GitWildMatchPattern,
                self.ignore,
            )

    def read_ignore_patterns(path: Path) -> list[str]:
        """
        Reads a gitignore-style ignore file and returns active patterns.
        """
        with path.open("rt", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    def find_repo_root(path: Path) -> Path | None:
        current = path.absolute()
        if current.is_file():
            current = current.parent
        while True:
            if (current / ".git").exists():
                return current
            if current.parent == current:
                return None
            current = current.parent

    seen_repo_roots: set[Path] = set()

    def maybe_run_repo_checks(repo_root: Path, project: Project | None) -> None:
        resolved = repo_root.resolve()
        if resolved in seen_repo_roots:
            return
        for check in repo_checks:
            issues = check.check(repo_root, project=project)
            report(issues)
        seen_repo_roots.add(resolved)

    # print(f"project_paths: {projects_by_path.keys()}")

    def go(path: Path, project: Project | None = None, repo: RepoContext | None = None) -> None:
        if repo is not None:
            if repo.spec.match_file(path.relative_to(repo.root)):
                # info(f"Skipping {path} due to .gitignore")
                return

        if path.is_dir():
            # It could be a project
            # print(f"path: {repr(path)} -> {path in projects_by_path}")
            if not project:
                project_at_path = projects_by_path.get(path.resolve())
            else:
                project_at_path = None
            if project_at_path is not None:
                for project_check in project_checks:
                    issues = project_check.check(path, project_at_path)
                    report(issues)
                project = project_at_path

            # It could be a repo
            if (path / ".git").exists():
                repo = RepoContext(
                    root=path,
                    ignore=["/.git"],
                )
                maybe_run_repo_checks(path, project)

            if (path / ".gitignore").exists():
                if repo is None:
                    report(E_GITIGNORE_WITHOUT_REPO.at(path))
                else:
                    ignore = read_ignore_patterns(path / ".gitignore")
                    repo = repo.with_ignore(ignore)

            if (path / ".checkignore").exists():
                if repo is None:
                    repo = RepoContext(
                        root=path,
                        ignore=["/.git"],
                    )
                ignore = read_ignore_patterns(path / ".checkignore")
                repo = repo.with_ignore(ignore)

            accumulated_issues = IssueList()
            for directory_check in dir_checks:
                # FIXME: File Context?
                ctx = FileContext(path=path, check_name=directory_check.__class__.__name__)
                try:
                    directory_check.check(ctx=ctx)
                except CheckFailedWithReportedIssues:
                    pass  # Issues already reported in context
                accumulated_issues.extend(ctx.issues)
            report(accumulated_issues)

            for child in path.iterdir():
                if repo is not None:
                    if repo.spec.match_file(child.relative_to(repo.root)):
                        # info(f"Skipping {child} due to .gitignore")
                        continue
                go(child, project=project, repo=repo)

        else:
            if repo is None:
                repo_root = find_repo_root(path)
                if repo_root is not None:
                    repo = RepoContext(root=repo_root, ignore=["/.git"])
                    project_at_root = projects_by_path.get(repo_root.resolve())
                    maybe_run_repo_checks(repo_root, project_at_root)

            file_scope = project.get_coarse_file_scope(path) if project else None
            project_type = project.coarse_project_type if project else None

            accumulated_issues = IssueList()
            scoped_suppressions = scoped_read_suppressions_for(path)
            for file_check in file_checks:
                # print(f"Checking {path} with {check} {ctx}")
                ctx = FileContext(
                    check_name=file_check.__class__.__name__,
                    path=path,
                    project=project,
                    project_type=project_type,
                    file_scope=file_scope,
                    scoped_read_suppressions=scoped_suppressions,
                )
                try:
                    file_check.check(ctx=ctx)
                except CheckFailedWithReportedIssues:
                    pass  # Issues already reported in context
                accumulated_issues.extend(ctx.issues)

            for issue in accumulated_issues:
                report(issue)
                if issue.fix and fix and is_check_disabled(issue) is False:
                    info("Fixing")
                    issue.fix()

    for path in root_paths:
        go(path)

    return 1 if has_errors else 0


if __name__ == "__main__":
    parser = ArgumentParser(
        description=(
            "Run the loaded repository, project, directory, and file checks "
            "against a path or configured project, or inspect the available checks."
        ),
        epilog=(
            "Examples:\n"
            "  check.py --list\n"
            "  check.py --describe SpdxHeaderCheck\n"
            "  check.py .\n"
            "  check.py :root --fix\n"
            "  check.py app-wabbit-dev/dev/cli.py --checks SpdxHeaderCheck"
        ),
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "project_or_dir_or_file",
        type=str,
        nargs="?",
        default=".",
        help="Project or directory or file to check.",
    )
    parser.add_argument("--list", action="store_true", help="List all loaded checks and a short summary for each.")
    parser.add_argument(
        "--describe",
        metavar="CHECK",
        help="Show issue IDs, config commands, and suppression examples for a named check.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="When used with --list or --describe, emit JSON instead of text.",
    )
    parser.add_argument("--checks", nargs="+", default=[], help="List of checks to run.")
    parser.add_argument("--fix", action="store_true", help="Fix issues found during checks.")

    args = parser.parse_args()
    try:
        if args.list:
            raise SystemExit(list_checks(json_output=args.json))
        if args.describe is not None:
            raise SystemExit(describe_check(args.describe, json_output=args.json))
        if args.json:
            raise ValueError("`--json` currently requires either `--list` or `--describe`.")
        raise SystemExit(check_main(args.project_or_dir_or_file, args.checks, args.fix))
    except ValueError as ex:
        parser.exit(2, f"{parser.prog}: error: {ex}\n")


__all__ = [
    "Module",
    "E_GITIGNORE_WITHOUT_REPO",
    "check_main",
    "describe_check",
    "load_check_catalog",
    "list_check_names",
    "list_checks",
    "secrets_scan",
]
