from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from pathlib import Path
import pathspec
from functools import cached_property
from argparse import ArgumentParser

from dev.checks.base import (
    RepoCheck,
    FileCheck,
    DirectoryCheck,
    ProjectCheck,
    Issue,
    IssueType,
    FileContext,
    IssueList,
    CheckFailedWithReportedIssues,
)
from dev.config import load_config, Config, Project
from dev.messages import error, info, warning

E_GITIGNORE_WITHOUT_REPO = IssueType(
    "E_GITIGNORE_WITHOUT_REPO",
    "Gitignore file found without a git repository.",
)


def check_main(
    project_or_dir_or_file: str,
    enabled_checks: List[str] | None = None,
    fix: bool = False,
) -> None:
    """
    Main function to run checks on the project.
    """

    config_path = Path("./root.clj").absolute()
    config = load_config() if config_path.exists() else None
    if config is None:
        warning(
            "No config file found. Some checks may not have sufficient context to run."
        )

    projects_by_path: Dict[Path, Project] = {}
    if config is not None:
        for project in config.defined_projects.values():
            projects_by_path[project.path] = project

    root_paths: List[Path] = []
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
        Check,
        RepoCheck,
        FileCheck,
        DirectoryCheck,
        ProjectCheck,
        Check,
    )
    from importlib import import_module
    from dev.checks.base import _KNOWN_TYPES

    # Get the file location of base.py to discover all checks
    if config is not None:
        all_checks: Dict[str, Check] = {}
        for check_name, check in config.modules.items():
            if isinstance(check, Check):
                all_checks[check_name] = check
        for check_name in enabled_checks or []:
            if check_name not in all_checks:
                raise ValueError(f"Unknown check: {check_name}")
        check_set = set(enabled_checks) if enabled_checks else set(all_checks.keys())
        all_checks = {k: v for k, v in all_checks.items() if k in check_set}
        repo_checks: list[RepoCheck] = [
            v for k, v in all_checks.items() if isinstance(v, RepoCheck)
        ]
        project_checks: list[ProjectCheck] = [
            v for k, v in all_checks.items() if isinstance(v, ProjectCheck)
        ]
        file_checks: list[FileCheck] = [
            v for k, v in all_checks.items() if isinstance(v, FileCheck)
        ]
        dir_checks: list[DirectoryCheck] = [
            v for k, v in all_checks.items() if isinstance(v, DirectoryCheck)
        ]

    disabled_checks: dict[str, pathspec.PathSpec] = {}
    if config is not None:
        patterns_by_error_name: Dict[str, List[str]] = {}
        for error_name, pattern in config.disabled_checks:
            assert isinstance(
                error_name, str
            ), f"Expected string, got {type(error_name)}"
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

    # print(f"Disabled checks: {disabled_checks}")

    def is_check_disabled(issue: Issue) -> bool:
        if issue.issue_type.id not in disabled_checks:
            return False
        spec = disabled_checks[issue.issue_type.id]
        if issue.location is None:
            return False
        path = issue.location.path.absolute()
        rel_path = path.relative_to(config_path.parent)
        result = spec.match_file(str(rel_path))
        # print(f"Checking if {rel_path} is ignored for {issue.issue_type.id} by {[p.pattern for p in spec.patterns]}: {result}")
        return result

    def report(issue: Issue | IssueList | List) -> None:
        if isinstance(issue, IssueList) or isinstance(issue, list):
            for i in issue:
                report(i)
            return

        if is_check_disabled(issue):
            return

        msg = ""

        msg += "[{issue_type}] ".format(issue_type=issue.issue_type.id)
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

        try:
            msg += issue.issue_type.message.format(**(issue.data or {}))
        except Exception as e:
            error(
                f"Error formatting issue message: {e} with type: {issue.issue_type} and data: {issue.data}"
            )
            msg += issue.issue_type.message

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
        ignore: List[str] = field(default_factory=list)

        def with_ignore(self, ignore: List[str]) -> RepoContext:
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

    def read_gitignore(path: Path) -> List[str]:
        """
        Reads the .gitignore file and returns a list of patterns to ignore.
        """
        with path.open() as f:
            return [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]

    # print(f"project_paths: {projects_by_path.keys()}")

    def go(
        path: Path, project: Project | None = None, repo: RepoContext | None = None
    ) -> None:
        if repo is not None:
            if repo.spec.match_file(path.relative_to(repo.root)):
                # info(f"Skipping {path} due to .gitignore")
                return

        if path.is_dir():
            # It could be a project
            # print(f"path: {repr(path)} -> {path in projects_by_path}")
            if not project:
                project_at_path = projects_by_path.get(path)
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

                for check in repo_checks:
                    issues = check.check(repo.root, project=project)
                    report(issues)

            if (path / ".gitignore").exists():
                if repo is None:
                    report(E_GITIGNORE_WITHOUT_REPO.at(path))
                else:
                    ignore = read_gitignore(path / ".gitignore")
                    repo = repo.with_ignore(ignore)

            accumulated_issues = IssueList()
            for check in dir_checks:
                # FIXME: File Context?
                ctx = FileContext(path=path, check_name=check.__class__.__name__)
                try:
                    check.check(ctx=ctx)
                except CheckFailedWithReportedIssues as e:
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
            file_scope = project.get_coarse_file_scope(path) if project else None
            project_type = project.coarse_project_type if project else None

            accumulated_issues = IssueList()
            for check in file_checks:
                # print(f"Checking {path} with {check} {ctx}")
                ctx = FileContext(
                    check_name=check.__class__.__name__,
                    path=path,
                    project_type=project_type,
                    file_scope=file_scope,
                )
                try:
                    check.check(ctx=ctx)
                except CheckFailedWithReportedIssues as e:
                    pass  # Issues already reported in context
                accumulated_issues.extend(ctx.issues)

            for issue in accumulated_issues:
                report([issue])
                if issue.fix and fix and is_check_disabled(issue) is False:
                    info(f"Fixing")
                    issue.fix()

    for path in root_paths:
        go(path)


if __name__ == "__main__":
    parser = ArgumentParser(description="Run checks on the project.")
    parser.add_argument(
        "project_or_dir_or_file",
        type=str,
        help="Project or directory or file to check.",
    )
    parser.add_argument(
        "--checks", nargs="+", default=[], help="List of checks to run."
    )
    parser.add_argument(
        "--fix", action="store_true", help="Fix issues found during checks."
    )

    args = parser.parse_args()

    check_main(args.project_or_dir_or_file, args.checks, args.fix)
