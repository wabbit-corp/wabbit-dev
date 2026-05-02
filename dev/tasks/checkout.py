from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dev.config import Config, find_workspace_root, load_config, project_repo_root
from dev.failure_context import contextualize_failure
from dev.git_env import git_subprocess_env
from dev.messages import accent, error, info, muted, success, warning
from dev.repo_resolution import configured_repo_targets, inferred_repo_targets, resolve_repo_targets


@dataclass(frozen=True)
class CheckoutResult:
    name: str
    path: Path
    github_repo: str | None
    clone_url: str | None
    status: str
    details: str

    def to_payload(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "path": str(self.path.resolve()),
            "githubRepo": self.github_repo,
            "cloneUrl": self.clone_url,
            "status": self.status,
            "details": self.details,
        }


def _github_repo_for_target(config: Config, target_name: str) -> str | None:
    if target_name in config.defined_repos:
        return config.defined_repos[target_name].github_repo
    if target_name in config.defined_projects:
        project = config.defined_projects[target_name]
        repo_root = project_repo_root(project).resolve()
        for repo_definition in config.defined_repos.values():
            if repo_definition.path.resolve() == repo_root:
                return repo_definition.github_repo
        return project.github_repo
    return None


def _clone_url(github_repo: str, *, use_ssh: bool) -> str:
    if use_ssh:
        return f"git@github.com:{github_repo}.git"
    return f"https://github.com/{github_repo}.git"


def _path_state(path: Path) -> str:
    if not path.exists():
        return "missing"
    if not path.is_dir():
        return "non-directory"
    if (path / ".git").is_dir():
        return "git"
    try:
        next(path.iterdir())
    except StopIteration:
        return "empty-directory"
    return "non-empty-directory"


def checkout_resolved_target(
    config: Config,
    target_name: str,
    *,
    dry_run: bool = False,
) -> CheckoutResult:
    if target_name not in config.defined_repos and target_name not in config.defined_projects:
        target_path = Path(target_name).expanduser()
        return CheckoutResult(
            name=target_name,
            path=target_path,
            github_repo=None,
            clone_url=None,
            status="failed",
            details="target is not a configured repo or project in root.clj",
        )

    path = Path(
        config.defined_repos[target_name].path
        if target_name in config.defined_repos
        else project_repo_root(config.defined_projects[target_name])
    ).resolve()
    github_repo = _github_repo_for_target(config, target_name)
    path_state = _path_state(path)
    clone_url = (
        _clone_url(github_repo, use_ssh=bool(config.github_ssh_key and config.github_ssh_key.strip()))
        if github_repo is not None
        else None
    )

    if path_state == "git":
        return CheckoutResult(
            name=target_name,
            path=path,
            github_repo=github_repo,
            clone_url=clone_url,
            status="skipped",
            details="repository already exists locally",
        )
    if path_state == "non-directory":
        return CheckoutResult(
            name=target_name,
            path=path,
            github_repo=github_repo,
            clone_url=clone_url,
            status="failed",
            details="target path exists but is not a directory",
        )
    if path_state == "non-empty-directory":
        return CheckoutResult(
            name=target_name,
            path=path,
            github_repo=github_repo,
            clone_url=clone_url,
            status="failed",
            details="target path exists, is not a git repository, and is not empty",
        )
    if github_repo is None:
        return CheckoutResult(
            name=target_name,
            path=path,
            github_repo=None,
            clone_url=None,
            status="skipped",
            details="no GitHub repo configured in root.clj",
        )
    if dry_run:
        return CheckoutResult(
            name=target_name,
            path=path,
            github_repo=github_repo,
            clone_url=clone_url,
            status="would-clone",
            details=f"would clone into {path}",
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ("git", "clone", clone_url, str(path)),
        check=False,
        capture_output=True,
        text=True,
        env=git_subprocess_env(config),
    )
    if completed.returncode != 0:
        detail_parts = [part.strip() for part in (completed.stderr, completed.stdout) if part and part.strip()]
        details = detail_parts[0] if detail_parts else f"`git clone` failed with exit code {completed.returncode}"
        return CheckoutResult(
            name=target_name,
            path=path,
            github_repo=github_repo,
            clone_url=clone_url,
            status="failed",
            details=details,
        )

    return CheckoutResult(
        name=target_name,
        path=path,
        github_repo=github_repo,
        clone_url=clone_url,
        status="cloned",
        details=f"cloned {github_repo}",
    )


def checkout(targets: str | list[str] | None = None, *, dry_run: bool = False, json_output: bool = False) -> int:
    requested_targets = [targets] if isinstance(targets, str) else list(targets or [])
    payload: dict[str, object] = {
        "requestedTargets": list(requested_targets),
        "inferredTargets": [],
        "repos": [],
    }

    if find_workspace_root() is None:
        payload["error"] = "No config file found. Run inside a configured workspace."
        if json_output:
            print(json.dumps(payload, indent=2))
            return 1
        error(contextualize_failure(str(payload["error"]), ["checkout"]))
        return 1

    config = load_config()
    effective_targets = inferred_repo_targets(config, requested_targets)
    if requested_targets == [] and effective_targets is not None:
        payload["inferredTargets"] = list(effective_targets)

    if not effective_targets:
        repo_targets = configured_repo_targets(config)
        target_names = [target.name for target in repo_targets]
    else:
        try:
            repo_targets = resolve_repo_targets(effective_targets, config=config)
        except ValueError as ex:
            payload["error"] = str(ex)
            if json_output:
                print(json.dumps(payload, indent=2))
                return 1
            error(contextualize_failure(str(ex), ["checkout", *effective_targets]))
            return 1
        target_names = [target.name for target in repo_targets]

    if dry_run and not json_output:
        info(f"Dry run: would checkout {len(target_names)} repository/repositories")

    results = [checkout_resolved_target(config, target_name, dry_run=dry_run) for target_name in target_names]
    payload["repos"] = [result.to_payload() for result in results]

    exit_code = 0
    if not json_output:
        for result in results:
            line = f"{accent(result.name)}: {result.details} ({muted(result.path)})"
            if result.status in {"cloned", "would-clone"}:
                success(line) if result.status == "cloned" else info(line)
            elif result.status == "skipped":
                warning(line)
            else:
                error(line)
                exit_code = 1
    else:
        print(json.dumps(payload, indent=2))

    if json_output:
        return 1 if any(result.status == "failed" for result in results) else 0
    return exit_code


__all__ = [
    "CheckoutResult",
    "checkout",
    "checkout_resolved_target",
]
