from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from dev.config import GradleProject, IntellijPlugin, PythonProject, find_workspace_root, load_config
from dev.discoverability import unknown_name_message
from dev.messages import accent, command_text, error, heading, info, success, warning
from dev.repo_resolution import resolve_project_ids

if TYPE_CHECKING:
    from dev.config import Config, Project

MIN_PYTHON = (3, 12)


class DoctorStatus(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class DoctorFinding:
    key: str
    label: str
    status: DoctorStatus
    detail: str
    fix: str | None = None


@dataclass
class DoctorContext:
    cwd: Path = field(default_factory=Path.cwd)
    selected_targets: tuple[str, ...] | None = None
    workspace_root: Path | None = field(init=False)
    root_clj: Path = field(init=False)
    root_private_clj: Path = field(init=False)
    _config_loaded: bool = field(default=False, init=False)
    _config: Config | None = field(default=None, init=False)
    _config_error: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.workspace_root = find_workspace_root(self.cwd)
        config_root = self.workspace_root if self.workspace_root is not None else self.cwd.resolve()
        self.root_clj = config_root / "root.clj"
        self.root_private_clj = config_root / "root.private.clj"

    def load_config(self) -> Config | None:
        if self._config_loaded:
            return self._config

        self._config_loaded = True
        try:
            self._config = load_config(self.cwd)
        except Exception as ex:  # pragma: no cover - kept broad for doctor resilience
            self._config_error = f"{type(ex).__name__}: {ex}"
            self._config = None
        return self._config


def _first_present(*values: str | None) -> str | None:
    for value in values:
        if value is not None and value.strip():
            return value
    return None


def _in_virtualenv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix) or bool(os.environ.get("VIRTUAL_ENV"))


def _determine_publish_target(project: Project) -> str:
    if isinstance(project, GradleProject):
        if project.publish_target == "jetbrains-marketplace" or "intellij-plugin" in project.resolved_features:
            return "intellij-marketplace"
        if project.publish_target == "jitpack":
            return "jitpack"
        if project.publish_target == "maven-central":
            return "maven-central"
        return "skip"
    if isinstance(project, PythonProject):
        if project.publish_target == "pypi":
            return "pypi"
        return "skip"
    return "skip"


def _selected_projects(config: Config, ctx: DoctorContext) -> list[Project]:
    if not ctx.selected_targets:
        return list(config.defined_projects.values())

    try:
        project_ids = resolve_project_ids(config, ctx.selected_targets)
    except ValueError:
        return list(config.defined_projects.values())
    return [config.defined_projects[project_id] for project_id in project_ids]


def _workspace_root_finding(ctx: DoctorContext) -> DoctorFinding:
    if ctx.workspace_root is None:
        return DoctorFinding(
            key="workspace-root",
            label="Workspace root",
            status=DoctorStatus.FAIL,
            detail=f"No root.clj was found in {ctx.cwd} or any parent directory.",
            fix="Run the command from a workspace directory that contains root.clj somewhere above it.",
        )

    if ctx.workspace_root.resolve() == ctx.cwd.resolve():
        return DoctorFinding(
            key="workspace-root",
            label="Workspace root",
            status=DoctorStatus.PASS,
            detail=f"Current directory is the workspace root: {ctx.cwd}",
        )

    return DoctorFinding(
        key="workspace-root",
        label="Workspace root",
        status=DoctorStatus.PASS,
        detail=f"Resolved workspace root {ctx.workspace_root} from current directory {ctx.cwd}.",
    )


def _root_clj_finding(ctx: DoctorContext) -> DoctorFinding:
    if ctx.root_clj.is_file():
        return DoctorFinding(
            key="root-clj",
            label="root.clj",
            status=DoctorStatus.PASS,
            detail=f"Found {ctx.root_clj}",
        )
    return DoctorFinding(
        key="root-clj",
        label="root.clj",
        status=DoctorStatus.FAIL,
        detail=f"Missing {ctx.root_clj}",
        fix="Create or restore root.clj, or change into the workspace root before running the command.",
    )


def _root_private_finding(ctx: DoctorContext) -> DoctorFinding:
    if ctx.root_private_clj.is_file():
        return DoctorFinding(
            key="root-private-clj",
            label="root.private.clj",
            status=DoctorStatus.PASS,
            detail=f"Found {ctx.root_private_clj}",
        )
    return DoctorFinding(
        key="root-private-clj",
        label="root.private.clj",
        status=DoctorStatus.FAIL,
        detail=f"Missing {ctx.root_private_clj}",
        fix="Create root.private.clj with the required local secrets and credentials.",
    )


def _python_version_finding(_ctx: DoctorContext) -> DoctorFinding:
    version = sys.version_info
    version_text = f"{version.major}.{version.minor}.{version.micro}"
    if (version.major, version.minor) >= MIN_PYTHON:
        return DoctorFinding(
            key="python-version",
            label="Python version",
            status=DoctorStatus.PASS,
            detail=f"Running Python {version_text} from {sys.executable}",
        )
    return DoctorFinding(
        key="python-version",
        label="Python version",
        status=DoctorStatus.FAIL,
        detail=f"Running Python {version_text}, but wabbit-dev requires Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+.",
        fix=(
            "Install Python 3.12+ and recreate the virtual environment, for example: "
            "`python3.12 -m venv .venv && . .venv/bin/activate && python3 -m pip install -e .`"
        ),
    )


def _virtualenv_finding(_ctx: DoctorContext) -> DoctorFinding:
    if _in_virtualenv():
        return DoctorFinding(
            key="virtualenv",
            label="Virtualenv",
            status=DoctorStatus.PASS,
            detail=f"Using virtual environment interpreter {sys.executable}",
        )
    return DoctorFinding(
        key="virtualenv",
        label="Virtualenv",
        status=DoctorStatus.WARN,
        detail=f"Using interpreter {sys.executable} outside a virtual environment.",
        fix="Create and activate `.venv`, then install the project with `python3 -m pip install -e .`.",
    )


def _git_finding(_ctx: DoctorContext) -> DoctorFinding:
    git_path = shutil.which("git")
    if git_path is not None:
        return DoctorFinding(
            key="git",
            label="git",
            status=DoctorStatus.PASS,
            detail=f"Found git at {git_path}",
        )
    return DoctorFinding(
        key="git",
        label="git",
        status=DoctorStatus.FAIL,
        detail="git is not available on PATH.",
        fix="Install git and make sure the `git` executable is on PATH. Example on macOS: `brew install git`.",
    )


def _config_finding(ctx: DoctorContext) -> DoctorFinding:
    if not ctx.root_clj.is_file() or not ctx.root_private_clj.is_file():
        return DoctorFinding(
            key="config",
            label="Config load",
            status=DoctorStatus.WARN,
            detail="Skipped because root.clj or root.private.clj is missing.",
        )

    config = ctx.load_config()
    if config is not None:
        return DoctorFinding(
            key="config",
            label="Config load",
            status=DoctorStatus.PASS,
            detail="Loaded root.clj and root.private.clj successfully.",
        )

    return DoctorFinding(
        key="config",
        label="Config load",
        status=DoctorStatus.FAIL,
        detail=f"Failed to parse workspace config: {ctx._config_error}",
        fix="Fix the config error and re-run `dev config check`.",
    )


def _gradle_finding(ctx: DoctorContext) -> DoctorFinding:
    config = ctx.load_config()
    gradle_binary = shutil.which("gradle")

    if config is None:
        if gradle_binary is not None:
            return DoctorFinding(
                key="gradle",
                label="Gradle",
                status=DoctorStatus.PASS,
                detail=f"Found global Gradle at {gradle_binary}",
            )
        return DoctorFinding(
            key="gradle",
            label="Gradle",
            status=DoctorStatus.WARN,
            detail="Skipped wrapper-aware Gradle checks because the workspace config could not be loaded.",
        )

    gradle_projects = [project for project in _selected_projects(config, ctx) if isinstance(project, GradleProject)]
    if not gradle_projects:
        return DoctorFinding(
            key="gradle",
            label="Gradle",
            status=DoctorStatus.PASS,
            detail="No selected Gradle projects require Gradle.",
        )

    wrappers = sorted(
        {
            project.effective_gradle_root / "gradlew"
            for project in gradle_projects
            if (project.effective_gradle_root / "gradlew").is_file()
        }
    )
    if wrappers:
        return DoctorFinding(
            key="gradle",
            label="Gradle",
            status=DoctorStatus.PASS,
            detail=f"Found {len(wrappers)} Gradle wrapper(s), for example {wrappers[0]}",
        )
    if gradle_binary is not None:
        return DoctorFinding(
            key="gradle",
            label="Gradle",
            status=DoctorStatus.PASS,
            detail=f"No wrapper was found, but global Gradle is available at {gradle_binary}",
        )
    return DoctorFinding(
        key="gradle",
        label="Gradle",
        status=DoctorStatus.FAIL,
        detail="Gradle projects are configured, but neither `gradle` nor any `gradlew` wrapper was found.",
        fix="Install Gradle or run `dev setup` in the repos that should contain generated Gradle wrappers.",
    )


def _cloc_finding(_ctx: DoctorContext) -> DoctorFinding:
    cloc_path = shutil.which("cloc")
    if cloc_path is not None:
        return DoctorFinding(
            key="cloc",
            label="cloc",
            status=DoctorStatus.PASS,
            detail=f"Found cloc at {cloc_path}",
        )
    return DoctorFinding(
        key="cloc",
        label="cloc",
        status=DoctorStatus.WARN,
        detail="cloc is not available on PATH.",
        fix="Install cloc if you use the `cloc` command. Example on macOS: `brew install cloc`.",
    )


def _commit_openai_finding(ctx: DoctorContext) -> DoctorFinding:
    config = ctx.load_config()
    if config is None:
        return DoctorFinding(
            key="commit-openai",
            label="Commit credentials",
            status=DoctorStatus.WARN,
            detail="Skipped because the workspace config could not be loaded.",
        )
    if config.openai_key:
        return DoctorFinding(
            key="commit-openai",
            label="Commit credentials",
            status=DoctorStatus.PASS,
            detail="OpenAI key is configured for AI-generated commit messages.",
        )
    return DoctorFinding(
        key="commit-openai",
        label="Commit credentials",
        status=DoctorStatus.FAIL,
        detail="The OpenAI key required by `commit` is missing.",
        fix='Add `(openai-key "...")` to root.private.clj.',
    )


def _contributors_identity_finding(ctx: DoctorContext) -> DoctorFinding:
    config = ctx.load_config()
    if config is None:
        return DoctorFinding(
            key="contributors-identity",
            label="Contributor audit baseline",
            status=DoctorStatus.WARN,
            detail="Skipped because the workspace config could not be loaded.",
        )
    if config.default_git_user_name and config.default_git_user_email:
        return DoctorFinding(
            key="contributors-identity",
            label="Contributor audit baseline",
            status=DoctorStatus.PASS,
            detail=f"Expected contributor identity is {config.default_git_user_name} <{config.default_git_user_email}>",
        )
    return DoctorFinding(
        key="contributors-identity",
        label="Contributor audit baseline",
        status=DoctorStatus.FAIL,
        detail="The default git user name/email used by `contributors audit` is not configured.",
        fix='Add `(git-user "Your Name" "you@example.com")` to root.private.clj or root.clj.',
    )


def _publish_target_projects(config: Config, target_name: str, ctx: DoctorContext) -> list[Project]:
    return [
        project
        for project in _selected_projects(config, ctx)
        if _determine_publish_target(project) == target_name
    ]


def _publish_pypi_finding(ctx: DoctorContext) -> DoctorFinding:
    config = ctx.load_config()
    if config is None:
        return DoctorFinding(
            key="publish-pypi",
            label="Publish / PyPI",
            status=DoctorStatus.WARN,
            detail="Skipped because the workspace config could not be loaded.",
        )
    projects = _publish_target_projects(config, "pypi", ctx)
    if not projects:
        return DoctorFinding(
            key="publish-pypi",
            label="Publish / PyPI",
            status=DoctorStatus.PASS,
            detail="No PyPI publish targets are configured.",
        )
    if config.pypi_token or os.environ.get("TWINE_PASSWORD"):
        return DoctorFinding(
            key="publish-pypi",
            label="Publish / PyPI",
            status=DoctorStatus.PASS,
            detail=f"PyPI credentials are available for {len(projects)} project(s).",
        )
    names = ", ".join(project.project_id or project.name for project in projects[:3])
    return DoctorFinding(
        key="publish-pypi",
        label="Publish / PyPI",
        status=DoctorStatus.FAIL,
        detail=f"Missing PyPI credentials for {len(projects)} project(s), including {names}.",
        fix='Add `(pypi-token "...")` to root.private.clj or export `TWINE_USERNAME`/`TWINE_PASSWORD`.',
    )


def _publish_maven_central_finding(ctx: DoctorContext) -> DoctorFinding:
    config = ctx.load_config()
    if config is None:
        return DoctorFinding(
            key="publish-maven-central",
            label="Publish / Maven Central",
            status=DoctorStatus.WARN,
            detail="Skipped because the workspace config could not be loaded.",
        )
    projects = _publish_target_projects(config, "maven-central", ctx)
    if not projects:
        return DoctorFinding(
            key="publish-maven-central",
            label="Publish / Maven Central",
            status=DoctorStatus.PASS,
            detail="No Maven Central publish targets are configured.",
        )
    username = _first_present(os.environ.get("MAVEN_USERNAME"), config.maven_username)
    password = _first_present(os.environ.get("MAVEN_PASSWORD"), config.maven_password)
    gpg_key = _first_present(os.environ.get("MAVEN_GPG_PRIVATE_KEY"), config.maven_gpg_private_key)
    gpg_passphrase = _first_present(os.environ.get("MAVEN_GPG_PASSPHRASE"), config.maven_gpg_passphrase)
    if username and password and gpg_key and gpg_passphrase:
        return DoctorFinding(
            key="publish-maven-central",
            label="Publish / Maven Central",
            status=DoctorStatus.PASS,
            detail=f"Maven Central credentials are available for {len(projects)} project(s).",
        )
    missing: list[str] = []
    if not username:
        missing.append("maven-username")
    if not password:
        missing.append("maven-password")
    if not gpg_key:
        missing.append("maven-gpg-private-key")
    if not gpg_passphrase:
        missing.append("maven-gpg-passphrase")
    return DoctorFinding(
        key="publish-maven-central",
        label="Publish / Maven Central",
        status=DoctorStatus.FAIL,
        detail=f"Missing Maven Central publishing material: {', '.join(missing)}.",
        fix=(
            "Set the missing values in root.private.clj or export the matching "
            "`MAVEN_*` environment variables."
        ),
    )


def _publish_intellij_finding(ctx: DoctorContext) -> DoctorFinding:
    config = ctx.load_config()
    if config is None:
        return DoctorFinding(
            key="publish-intellij",
            label="Publish / JetBrains Marketplace",
            status=DoctorStatus.WARN,
            detail="Skipped because the workspace config could not be loaded.",
        )
    projects = _publish_target_projects(config, "intellij-marketplace", ctx)
    if not projects:
        return DoctorFinding(
            key="publish-intellij",
            label="Publish / JetBrains Marketplace",
            status=DoctorStatus.PASS,
            detail="No JetBrains Marketplace publish targets are configured.",
        )

    env_names = {"JETBRAINS_MARKETPLACE_TOKEN"}
    for project in projects:
        feature = project.resolved_features.get("intellij-plugin") if isinstance(project, GradleProject) else None
        if isinstance(feature, IntellijPlugin) and feature.marketplaceTokenEnv:
            env_names.add(feature.marketplaceTokenEnv)

    has_token = bool(config.jetbrains_marketplace_token)
    if not has_token:
        has_token = any(os.environ.get(env_name) for env_name in env_names)
    if has_token:
        return DoctorFinding(
            key="publish-intellij",
            label="Publish / JetBrains Marketplace",
            status=DoctorStatus.PASS,
            detail=f"Marketplace token is available for {len(projects)} project(s).",
        )
    env_hint = ", ".join(sorted(env_names))
    return DoctorFinding(
        key="publish-intellij",
        label="Publish / JetBrains Marketplace",
        status=DoctorStatus.FAIL,
        detail="Missing JetBrains Marketplace token.",
        fix=(
            'Add `(jetbrains-marketplace-token "...")` to root.private.clj or export one of '
            f"the expected environment variables: {env_hint}."
        ),
    )


def _publish_jitpack_finding(ctx: DoctorContext) -> DoctorFinding:
    config = ctx.load_config()
    if config is None:
        return DoctorFinding(
            key="publish-jitpack",
            label="Publish / JitPack",
            status=DoctorStatus.WARN,
            detail="Skipped because the workspace config could not be loaded.",
        )
    projects = _publish_target_projects(config, "jitpack", ctx)
    if not projects:
        return DoctorFinding(
            key="publish-jitpack",
            label="Publish / JitPack",
            status=DoctorStatus.PASS,
            detail="No JitPack publish targets are configured.",
        )
    if config.openai_key:
        return DoctorFinding(
            key="publish-jitpack",
            label="Publish / JitPack",
            status=DoctorStatus.PASS,
            detail="OpenAI key is available for JitPack release version recommendations.",
        )
    return DoctorFinding(
        key="publish-jitpack",
        label="Publish / JitPack",
        status=DoctorStatus.FAIL,
        detail="JitPack publishing requires an OpenAI key for version recommendations.",
        fix='Add `(openai-key "...")` to root.private.clj before running `dev publish`.',
    )


CHECKS: dict[str, Callable[[DoctorContext], DoctorFinding]] = {
    "workspace-root": _workspace_root_finding,
    "root-clj": _root_clj_finding,
    "root-private-clj": _root_private_finding,
    "python-version": _python_version_finding,
    "virtualenv": _virtualenv_finding,
    "git": _git_finding,
    "config": _config_finding,
    "gradle": _gradle_finding,
    "cloc": _cloc_finding,
    "commit-openai": _commit_openai_finding,
    "contributors-identity": _contributors_identity_finding,
    "publish-pypi": _publish_pypi_finding,
    "publish-maven-central": _publish_maven_central_finding,
    "publish-intellij": _publish_intellij_finding,
    "publish-jitpack": _publish_jitpack_finding,
}

FULL_CHECK_ORDER = (
    "workspace-root",
    "root-clj",
    "root-private-clj",
    "python-version",
    "virtualenv",
    "git",
    "config",
    "gradle",
    "cloc",
    "contributors-identity",
    "commit-openai",
    "publish-pypi",
    "publish-maven-central",
    "publish-intellij",
    "publish-jitpack",
)

PREFLIGHT_CHECKS: dict[str, tuple[str, ...]] = {
    "setup": ("workspace-root", "root-clj", "root-private-clj", "python-version", "config"),
    "release/verify": ("workspace-root", "root-clj", "root-private-clj", "python-version", "git", "config", "gradle"),
    "build": ("workspace-root", "root-clj", "root-private-clj", "python-version", "config", "gradle"),
    "publish": (
        "workspace-root",
        "root-clj",
        "root-private-clj",
        "python-version",
        "git",
        "config",
        "gradle",
        "publish-pypi",
        "publish-maven-central",
        "publish-intellij",
        "publish-jitpack",
    ),
    "commit": ("workspace-root", "root-clj", "root-private-clj", "python-version", "git", "config", "commit-openai"),
    "clean": ("workspace-root", "root-clj", "root-private-clj", "config"),
    "project/list": ("workspace-root", "root-clj", "root-private-clj", "config"),
    "project/show": ("workspace-root", "root-clj", "root-private-clj", "config"),
    "project/deps": ("workspace-root", "root-clj", "root-private-clj", "config"),
    "project/repo": ("workspace-root", "root-clj", "root-private-clj", "config"),
    "project/targets": ("workspace-root", "root-clj", "root-private-clj", "config"),
    "dep/graph": ("workspace-root", "root-clj", "root-private-clj", "config"),
    "dep/updates": ("workspace-root", "root-clj", "root-private-clj", "config"),
    "contributors/audit": (
        "workspace-root",
        "root-clj",
        "root-private-clj",
        "git",
        "config",
        "contributors-identity",
    ),
}

DRY_RUN_PREFLIGHT_CHECKS: dict[str, tuple[str, ...]] = {
    **PREFLIGHT_CHECKS,
    "publish": ("workspace-root", "root-clj", "root-private-clj", "python-version", "git", "config", "gradle"),
    "commit": ("workspace-root", "root-clj", "root-private-clj", "python-version", "git", "config"),
}


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


DOCTOR_ONLY_GROUPS: dict[str, tuple[str, ...]] = {
    **PREFLIGHT_CHECKS,
    "release": PREFLIGHT_CHECKS["release/verify"],
    "project": _ordered_unique(
        (
            *PREFLIGHT_CHECKS["project/list"],
            *PREFLIGHT_CHECKS["project/show"],
            *PREFLIGHT_CHECKS["project/deps"],
            *PREFLIGHT_CHECKS["project/repo"],
            *PREFLIGHT_CHECKS["project/targets"],
        )
    ),
    "dep": _ordered_unique((*PREFLIGHT_CHECKS["dep/graph"], *PREFLIGHT_CHECKS["dep/updates"])),
}


def doctor_only_choices() -> tuple[str, ...]:
    return tuple(sorted({*CHECKS, *DOCTOR_ONLY_GROUPS}))


def resolve_doctor_check_ids(only: Sequence[str] | None = None) -> tuple[str, ...]:
    if not only:
        return FULL_CHECK_ORDER

    resolved: list[str] = []
    choices = doctor_only_choices()
    for value in only:
        if value in CHECKS:
            resolved.append(value)
            continue
        if value in DOCTOR_ONLY_GROUPS:
            resolved.extend(DOCTOR_ONLY_GROUPS[value])
            continue
        raise ValueError(unknown_name_message("doctor check or command", value, choices))
    return _ordered_unique(resolved)


def collect_doctor_findings(
    *,
    check_ids: tuple[str, ...] = FULL_CHECK_ORDER,
    ctx: DoctorContext | None = None,
) -> list[DoctorFinding]:
    active_ctx = DoctorContext() if ctx is None else ctx
    return [CHECKS[check_id](active_ctx) for check_id in check_ids]


def _emit_finding(finding: DoctorFinding) -> None:
    label = heading(finding.label)
    if finding.status == DoctorStatus.PASS:
        success(f"{label}: {finding.detail}")
    elif finding.status == DoctorStatus.WARN:
        warning(f"{label}: {finding.detail}")
    else:
        error(f"{label}: {finding.detail}")

    if finding.fix:
        info(f"{accent('Fix', 'yellow')}: {finding.fix}")


def doctor_payload(
    findings: list[DoctorFinding],
    *,
    ctx: DoctorContext | None = None,
    check_ids: Sequence[str] | None = None,
    requested_only: Sequence[str] | None = None,
) -> dict[str, object]:
    active_ctx = DoctorContext() if ctx is None else ctx
    failures = sum(1 for finding in findings if finding.status == DoctorStatus.FAIL)
    warnings_count = sum(1 for finding in findings if finding.status == DoctorStatus.WARN)
    passes = sum(1 for finding in findings if finding.status == DoctorStatus.PASS)

    return {
        "cwd": str(active_ctx.cwd.resolve()),
        "selectedTargets": list(active_ctx.selected_targets or ()),
        "requestedOnly": list(requested_only or ()),
        "resolvedChecks": list(check_ids or FULL_CHECK_ORDER),
        "summary": {
            "total": len(findings),
            "pass": passes,
            "warn": warnings_count,
            "fail": failures,
        },
        "findings": [
            {
                "key": finding.key,
                "label": finding.label,
                "status": finding.status.value,
                "detail": finding.detail,
                "fix": finding.fix,
            }
            for finding in findings
        ],
    }


def doctor(
    *,
    json_output: bool = False,
    only: Sequence[str] | None = None,
    targets: Sequence[str] | None = None,
) -> int:
    check_ids = resolve_doctor_check_ids(only)
    ctx = DoctorContext(selected_targets=tuple(targets) if targets else None)
    findings = collect_doctor_findings(check_ids=check_ids, ctx=ctx)
    failures = sum(1 for finding in findings if finding.status == DoctorStatus.FAIL)
    warnings_count = sum(1 for finding in findings if finding.status == DoctorStatus.WARN)

    if json_output:
        print(
            json.dumps(
                doctor_payload(
                    findings,
                    ctx=ctx,
                    check_ids=check_ids,
                    requested_only=only,
                ),
                indent=2,
            )
        )
        return 1 if failures else 0

    for finding in findings:
        _emit_finding(finding)

    if failures:
        error(
            f"{heading('Doctor summary')}: "
            f"{accent(failures, 'red')} failing check(s), {accent(warnings_count, 'yellow')} warning(s)."
        )
        return 1
    if warnings_count:
        warning(
            f"{heading('Doctor summary')}: "
            f"{accent(warnings_count, 'yellow')} warning(s), no blocking failures."
        )
        return 0

    success(f"{heading('Doctor summary')}: no problems found.")
    return 0


def preflight_for_command(
    command_path: str,
    *,
    prog: str,
    projects: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> bool:
    check_ids = DRY_RUN_PREFLIGHT_CHECKS.get(command_path) if dry_run else PREFLIGHT_CHECKS.get(command_path)
    if check_ids is None:
        return True

    findings = collect_doctor_findings(
        check_ids=check_ids,
        ctx=DoctorContext(selected_targets=projects),
    )
    failures = [finding for finding in findings if finding.status == DoctorStatus.FAIL]
    if not failures:
        return True

    display_command = command_path.replace("/", " ")
    error(f"Preflight checks failed for `{command_text(display_command)}`.")
    for finding in failures:
        _emit_finding(finding)
    target_suffix = f" {' '.join(projects)}" if projects else ""
    info(
        f"Run `{command_text(f'{prog} doctor --only {command_path}{target_suffix}')}` for targeted diagnostics, "
        f"or `{command_text(f'{prog} doctor')}` for a full environment check."
    )
    return False


__all__ = [
    "DoctorContext",
    "DoctorFinding",
    "DoctorStatus",
    "collect_doctor_findings",
    "doctor",
    "doctor_only_choices",
    "doctor_payload",
    "preflight_for_command",
    "resolve_doctor_check_ids",
]
