from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import pathspec

from dev.base import Module
from dev.checks.base import (
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
)
from dev.config import Project, load_config
from dev.messages import error, info, warning

E_GITIGNORE_WITHOUT_REPO = IssueType(
    "E_GITIGNORE_WITHOUT_REPO",
    "Gitignore file found without a git repository.",
)


def check_main(
    project_or_dir_or_file: str,
    enabled_checks: list[str] | None = None,
    fix: bool = False,
) -> int:
    """
    Main function to run checks on the project.
    """

    config_path = Path("./root.clj").absolute()
    config = load_config() if config_path.exists() else None
    if config is None:
        warning("No config file found. Some checks may not have sufficient context to run.")

    projects_by_path: dict[Path, Project] = {}
    if config is not None:
        for project in config.defined_projects.values():
            projects_by_path[project.path.resolve()] = project

    root_paths: list[Path] = []
    if project_or_dir_or_file.startswith(":"):  # Definitely a project
        if config is None:
            raise ValueError("No config file found. Cannot resolve project paths.")

        project_name = project_or_dir_or_file[1:]
        if project_name == "root":
            for project in config.defined_projects.values():
                root_paths.append(project.path)
        else:
            if project_name not in config.defined_projects:
                raise ValueError(f"Unknown project: {project_name}")
            project = config.defined_projects[project_name]
            root_paths.append(project.path)

    else:  # Could be a project or a path
        root_paths.append(Path(project_or_dir_or_file))

    for path in root_paths:
        if not path.exists():
            raise ValueError(f"Path does not exist: {path}")

    # Gather checks
    from dev.checks.base import (
        _KNOWN_TYPES,
        Check,
        DirectoryCheck,
        FileCheck,
        ProjectCheck,
        RepoCheck,
    )

    all_checks: dict[str, Check] = {}
    modules: dict[str, Module] = {}
    if config is not None:
        modules = config.modules
    else:
        try:
            modules = Module.load_modules()
        except Exception as e:
            warning(f"Failed to auto-load checks without config: {e}")
            modules = {}

    for check_name, check in modules.items():
        if isinstance(check, Check):
            all_checks[check_name] = check

    for check_name in enabled_checks or []:
        if check_name not in all_checks:
            raise ValueError(f"Unknown check: {check_name}")

    check_set = set(enabled_checks) if enabled_checks else set(all_checks.keys())
    all_checks = {k: v for k, v in all_checks.items() if k in check_set}

    def sort_checks(checks: list[Check]) -> list[Check]:
        return sorted(
            checks,
            key=lambda c: (getattr(c, "order", 1000), c.__class__.__name__),
        )

    repo_checks: list[RepoCheck] = sort_checks([v for v in all_checks.values() if isinstance(v, RepoCheck)])
    project_checks: list[ProjectCheck] = sort_checks([v for v in all_checks.values() if isinstance(v, ProjectCheck)])
    file_checks: list[FileCheck] = sort_checks([v for v in all_checks.values() if isinstance(v, FileCheck)])
    dir_checks: list[DirectoryCheck] = sort_checks([v for v in all_checks.values() if isinstance(v, DirectoryCheck)])

    disabled_checks: dict[str, pathspec.PathSpec] = {}
    ignored_findings: list[tuple[str, pathspec.PathSpec, str]] = []
    if config is not None:
        patterns_by_error_name: dict[str, list[str]] = {}
        for error_name, pattern in config.disabled_checks:
            assert isinstance(error_name, str), f"Expected string, got {type(error_name)}"
            assert isinstance(pattern, str), f"Expected string, got {type(pattern)}"
            assert (
                error_name in _KNOWN_TYPES or error_name == "*"
            ), f"Unknown error type in disabled_checks: {repr(error_name)}"

            if error_name == "*":
                for known_error in _KNOWN_TYPES:
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
                error_name in _KNOWN_TYPES or error_name == "*"
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
            rel_path = abs_path.relative_to(config_path.parent)
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

    def report(issue: Issue | IssueList | list) -> None:
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
                for check in project_checks:
                    issues = check.check(path, project_at_path)
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
            for check in dir_checks:
                # FIXME: File Context?
                ctx = FileContext(path=path, check_name=check.__class__.__name__)
                try:
                    check.check(ctx=ctx)
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
            for check in file_checks:
                # print(f"Checking {path} with {check} {ctx}")
                ctx = FileContext(
                    check_name=check.__class__.__name__,
                    path=path,
                    project_type=project_type,
                    file_scope=file_scope,
                    scoped_read_suppressions=scoped_suppressions,
                )
                try:
                    check.check(ctx=ctx)
                except CheckFailedWithReportedIssues:
                    pass  # Issues already reported in context
                accumulated_issues.extend(ctx.issues)

            for issue in accumulated_issues:
                report([issue])
                if issue.fix and fix and is_check_disabled(issue) is False:
                    info("Fixing")
                    issue.fix()

    for path in root_paths:
        go(path)

    return 1 if has_errors else 0


if __name__ == "__main__":
    parser = ArgumentParser(description="Run checks on the project.")
    parser.add_argument(
        "project_or_dir_or_file",
        type=str,
        help="Project or directory or file to check.",
    )
    parser.add_argument("--checks", nargs="+", default=[], help="List of checks to run.")
    parser.add_argument("--fix", action="store_true", help="Fix issues found during checks.")

    args = parser.parse_args()

    raise SystemExit(check_main(args.project_or_dir_or_file, args.checks, args.fix))
