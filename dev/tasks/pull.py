from dataclasses import dataclass

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from dev.config import Config, load_config
from dev.failure_context import contextualize_failure
from dev.git_env import configured_git_ssh
from dev.messages import accent, error, info, muted, success
from dev.repo_resolution import ResolvedRepoTarget, configured_repo_targets, resolve_repo_targets
from dev.repo_status import local_tracking_state


@dataclass(frozen=True)
class PullTargetState:
    branch_name: str
    upstream_name: str
    remote_name: str
    remote_branch_name: str
    ahead_count: int
    behind_count: int


def _parse_upstream_target(upstream_name: str | None) -> tuple[str | None, str | None]:
    match upstream_name:
        case None:
            return None, None
        case str(text):
            match text.split("/", 1):
                case [remote_name, remote_branch_name] if remote_name and remote_branch_name:
                    return remote_name, remote_branch_name
                case _:
                    return None, None


def _describe_tracking(state: PullTargetState) -> str:
    return f"{state.branch_name} -> {state.upstream_name} (ahead {state.ahead_count}, behind {state.behind_count})"


def _tracking_state_for_pull(
    repo: Repo,
    target_name: str,
    *,
    config: Config,
) -> tuple[PullTargetState | None, str | None]:
    tracking = local_tracking_state(repo)
    remote_name, remote_branch_name = _parse_upstream_target(tracking.upstream_name)

    if tracking.branch_name is None:
        return None, f"{target_name}: cannot pull detached HEAD"
    if tracking.upstream_name is None:
        return None, f"{target_name}: branch {tracking.branch_name} has no configured upstream"
    if remote_name is None or remote_branch_name is None:
        return None, f"{target_name}: could not parse upstream branch {tracking.upstream_name!r}"

    try:
        with configured_git_ssh(repo.git, config):
            repo.git.fetch("--prune", "--quiet", remote_name)
    except GitCommandError as ex:
        return None, f"{target_name}: failed to refresh {remote_name} ({ex})"

    refreshed = local_tracking_state(repo)
    refreshed_remote_name, refreshed_remote_branch_name = _parse_upstream_target(refreshed.upstream_name)
    if refreshed.branch_name is None:
        return None, f"{target_name}: cannot pull detached HEAD"
    if refreshed.upstream_name is None:
        return None, f"{target_name}: branch {refreshed.branch_name} has no configured upstream"
    if refreshed_remote_name is None or refreshed_remote_branch_name is None:
        return None, f"{target_name}: could not parse upstream branch {refreshed.upstream_name!r}"

    return (
        PullTargetState(
            branch_name=refreshed.branch_name,
            upstream_name=refreshed.upstream_name,
            remote_name=refreshed_remote_name,
            remote_branch_name=refreshed_remote_branch_name,
            ahead_count=refreshed.ahead_count if refreshed.ahead_count is not None else 0,
            behind_count=refreshed.behind_count if refreshed.behind_count is not None else 0,
        ),
        None,
    )


def pull_resolved_repo_target(
    config: Config,
    resolved_target: ResolvedRepoTarget,
    *,
    dry_run: bool = False,
) -> tuple[bool, str]:
    path = resolved_target.path
    if not path.exists():
        return False, f"{resolved_target.name}: repo path does not exist"

    try:
        repo = Repo(path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError) as ex:
        return False, f"{resolved_target.name}: failed to open git repo ({ex})"

    try:
        state, error_message = _tracking_state_for_pull(repo, resolved_target.name, config=config)
        if error_message is not None:
            return False, error_message
        if state is None:
            return False, f"{resolved_target.name}: could not resolve pull state"

        description = _describe_tracking(state)
        if state.behind_count > 0 and repo.is_dirty(index=True, working_tree=True, untracked_files=True):
            return False, f"{resolved_target.name}: cannot pull with local changes {description}"
        if state.behind_count > 0 and state.ahead_count > 0:
            return False, f"{resolved_target.name}: cannot pull diverged branch {description}"
        if state.behind_count == 0:
            return True, f"{resolved_target.name}: already up to date {description}"
        if dry_run:
            return True, f"would fast-forward {description}"

        with configured_git_ssh(repo.git, config):
            repo.git.merge("--ff-only", f"{state.remote_name}/{state.remote_branch_name}")
        return True, f"{resolved_target.name}: fast-forwarded {description}"
    except GitCommandError as ex:
        return False, f"{resolved_target.name}: pull failed ({ex})"
    finally:
        repo.close()


def pull(targets: str | list[str] | None = None, *, dry_run: bool = False) -> int:
    config = load_config()
    requested_targets = [targets] if isinstance(targets, str) else targets
    if not requested_targets or requested_targets == ["."]:
        repo_targets = list(configured_repo_targets(config))
    else:
        if "." in requested_targets:
            error("`pull .` cannot be combined with other targets.")
            return 1
        try:
            repo_targets = resolve_repo_targets(requested_targets, config=config)
        except ValueError as ex:
            error(contextualize_failure(str(ex), ["pull", *requested_targets]))
            return 1

    if dry_run:
        info(f"Dry run: would pull {len(repo_targets)} repository/repositories")
    exit_code = 0
    for resolved_target in repo_targets:
        ok, message = pull_resolved_repo_target(config, resolved_target, dry_run=dry_run)
        if dry_run:
            print(f"  {accent(resolved_target.name)}: {muted(message)} ({muted(resolved_target.path)})")
            continue
        if ok:
            success(message)
            continue
        error(message)
        exit_code = 1
    return exit_code
