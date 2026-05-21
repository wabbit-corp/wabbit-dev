import subprocess
from dataclasses import dataclass

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from dev.config import Config, load_config
from dev.failure_context import contextualize_failure
from dev.git_env import configured_git_ssh, git_subprocess_env
from dev.messages import accent, error, info, muted, style, success
from dev.repo_resolution import ResolvedRepoTarget, configured_repo_targets, resolve_repo_targets
from dev.repo_status import local_tracking_state


@dataclass(frozen=True)
class PushTargetState:
    branch_name: str | None
    upstream_name: str | None
    remote_name: str | None
    remote_branch_name: str | None
    ahead_count: int
    behind_count: int
    created_upstream: bool = False


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


def _describe_tracking(state: PushTargetState) -> str:
    branch_name = state.branch_name if state.branch_name is not None else "detached HEAD"
    if state.upstream_name is None:
        return accent(branch_name)

    counts = f"ahead {state.ahead_count}, behind {state.behind_count}"
    if state.ahead_count or state.behind_count:
        counts = style(counts, "yellow", attrs=("bold",))
    else:
        counts = muted(counts)
    return f"{accent(branch_name)} -> {accent(state.upstream_name)} | {counts}"


def _describe_dirty_state(repo: Repo) -> str:
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=False):
        return style("worktree dirty", "yellow", attrs=("bold",))
    return style("worktree clean", "green")


def _format_push_status(
    action: str,
    state: PushTargetState,
    repo: Repo,
    *,
    target_name: str | None = None,
) -> str:
    prefix = f"{target_name}: " if target_name is not None else ""
    return f"{prefix}{action} | {_describe_tracking(state)} | {_describe_dirty_state(repo)}"


def _strip_target_prefix(target_name: str, message: str) -> str:
    prefix = f"{target_name}: "
    if message.startswith(prefix):
        return message[len(prefix) :]
    return message


def _github_ssh_url(github_repo: str | None) -> str | None:
    if github_repo is None:
        return None
    repo_text = github_repo.strip()
    if not repo_text:
        return None
    if "://" in repo_text or repo_text.startswith("git@"):
        return repo_text
    return f"git@github.com:{repo_text}.git"


def _unique_text(values: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is None or value in result:
            continue
        result.append(value)
    return result


def _configured_github_repos(config: Config, resolved_target: ResolvedRepoTarget) -> list[str]:
    configured: list[str | None] = []

    defined_repos = getattr(config, "defined_repos", {})
    if resolved_target.repo_id is not None and resolved_target.repo_id in defined_repos:
        configured.append(getattr(defined_repos[resolved_target.repo_id], "github_repo", None))

    defined_projects = getattr(config, "defined_projects", {})
    for project_id in resolved_target.project_ids:
        project = defined_projects.get(project_id)
        if project is not None:
            configured.append(getattr(project, "github_repo", None))

    return _unique_text(configured)


def _quarantine_summary(config: Config, resolved_target: ResolvedRepoTarget) -> str:
    defined_projects = getattr(config, "defined_projects", {})
    projects = [
        defined_projects[project_id]
        for project_id in resolved_target.project_ids
        if project_id in defined_projects
    ]
    if not projects:
        return "no project metadata"

    quarantined = [project.name for project in projects if getattr(project, "quarantine", False)]
    if not quarantined:
        return "false"
    if len(quarantined) == len(projects):
        return "true"
    return f"mixed ({len(quarantined)}/{len(projects)} quarantined: {', '.join(quarantined)})"


def _local_remote_url(repo: Repo, remote_name: str) -> str | None:
    try:
        return repo.git.remote("get-url", remote_name).strip() or None
    except GitCommandError:
        return None


def _remote_reachability(repo: Repo, config: Config, remote_url: str | None) -> str:
    if remote_url is None:
        return "not checked (no configured GitHub repo)"

    cwd = repo.working_tree_dir
    if cwd is None:
        return "not checked (bare repo)"

    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", remote_url],
            cwd=cwd,
            env=git_subprocess_env(config),
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return "no (git ls-remote timed out)"
    except OSError as ex:
        return f"no (failed to run git ls-remote: {ex})"

    if result.returncode == 0:
        return "yes"

    detail = (result.stderr or result.stdout).strip().splitlines()
    if not detail:
        return f"no (git ls-remote exited {result.returncode})"
    return f"no ({detail[-1]})"


def _push_failure_diagnostics(
    repo: Repo,
    resolved_target: ResolvedRepoTarget,
    *,
    config: Config,
    tracking_upstream: str | None,
    remote_name: str | None,
) -> str:
    configured_repos = _configured_github_repos(config, resolved_target)
    configured_repo_text = ", ".join(configured_repos) if configured_repos else "missing"
    configured_remote_url = _github_ssh_url(configured_repos[0]) if len(configured_repos) == 1 else None
    configured_remote_text = configured_remote_url or ("ambiguous" if len(configured_repos) > 1 else "missing")

    effective_remote_name = remote_name or "origin"
    local_remote_url = _local_remote_url(repo, effective_remote_name)
    local_remote_text = local_remote_url or f"missing {effective_remote_name}"
    remote_match_text = "not checked"
    if configured_remote_url is not None:
        remote_match_text = "yes" if local_remote_url == configured_remote_url else "no"

    reachable_text = _remote_reachability(repo, config, configured_remote_url)
    upstream_text = tracking_upstream or "missing"

    return (
        "diagnostics: "
        f"root.clj repo={configured_repo_text}; "
        f"quarantine={_quarantine_summary(config, resolved_target)}; "
        f"local {effective_remote_name}={local_remote_text}; "
        f"configured remote={configured_remote_text}; "
        f"origin matches root.clj={remote_match_text}; "
        f"configured remote reachable={reachable_text}; "
        f"upstream={upstream_text}"
    )


def _with_push_diagnostics(
    message: str,
    repo: Repo,
    resolved_target: ResolvedRepoTarget,
    *,
    config: Config,
    tracking_upstream: str | None,
    remote_name: str | None = None,
) -> str:
    return (
        f"{message}\n"
        f"    {_push_failure_diagnostics(repo, resolved_target, config=config, tracking_upstream=tracking_upstream, remote_name=remote_name)}"
    )


def _remote_ref_exists(repo: Repo, remote_ref: str) -> bool:
    try:
        repo.git.rev_parse("--verify", "--quiet", remote_ref)
        return True
    except GitCommandError:
        return False


def _remote_heads(repo: Repo, remote_target: str) -> dict[str, str]:
    output = repo.git.ls_remote("--heads", remote_target)
    heads: dict[str, str] = {}
    for raw_line in output.splitlines():
        commit, _, ref_name = raw_line.partition("\t")
        branch_name = ref_name.removeprefix("refs/heads/")
        if commit and branch_name:
            heads[branch_name] = commit
    return heads


def _has_related_history(repo: Repo, branch_name: str, remote_ref: str) -> bool:
    try:
        repo.git.merge_base(branch_name, remote_ref)
        return True
    except GitCommandError:
        return False


def _try_configure_missing_upstream(
    repo: Repo,
    resolved_target: ResolvedRepoTarget,
    *,
    config: Config,
    branch_name: str,
    dry_run: bool,
) -> tuple[bool, str | None, bool]:
    configured_repos = _configured_github_repos(config, resolved_target)
    configured_remote_url = _github_ssh_url(configured_repos[0]) if len(configured_repos) == 1 else None
    if configured_remote_url is None:
        return False, None, False

    local_origin_url = _local_remote_url(repo, "origin")
    origin_repair_message: str | None = None
    if local_origin_url is None:
        origin_repair_message = f"add origin {configured_remote_url}"
    elif local_origin_url != configured_remote_url:
        origin_repair_message = f"set origin from {local_origin_url} to {configured_remote_url}"

    if dry_run and origin_repair_message is not None:
        with configured_git_ssh(repo.git, config):
            remote_heads = _remote_heads(repo, configured_remote_url)
        remote_ref = f"origin/{branch_name}"
        if branch_name in remote_heads:
            action = f"would {origin_repair_message} and set upstream for {branch_name} to {remote_ref}"
        elif not remote_heads:
            action = f"would {origin_repair_message} and create upstream branch {remote_ref} from local {branch_name}"
        else:
            branch_list = ", ".join(sorted(remote_heads))
            action = (
                f"would {origin_repair_message}, but {remote_ref} is missing and remote has other branches: "
                f"{branch_list}"
            )
        return (
            False,
            _with_push_diagnostics(
                f"{resolved_target.name}: {action}",
                repo,
                resolved_target,
                config=config,
                tracking_upstream=None,
                remote_name="origin",
            ),
            False,
        )

    if origin_repair_message is not None:
        if local_origin_url is None:
            repo.git.remote("add", "origin", configured_remote_url)
        else:
            repo.git.remote("set-url", "origin", configured_remote_url)

    try:
        with configured_git_ssh(repo.git, config):
            repo.git.fetch("--prune", "--quiet", "origin")
    except GitCommandError as ex:
        return (
            False,
            _with_push_diagnostics(
                f"{resolved_target.name}: branch {branch_name} has no configured upstream and failed to refresh origin ({ex})",
                repo,
                resolved_target,
                config=config,
                tracking_upstream=None,
                remote_name="origin",
            ),
            False,
        )

    remote_ref = f"origin/{branch_name}"
    with configured_git_ssh(repo.git, config):
        remote_heads = _remote_heads(repo, "origin")

    if branch_name not in remote_heads:
        if remote_heads:
            branch_list = ", ".join(sorted(remote_heads))
            return (
                False,
                _with_push_diagnostics(
                    f"{resolved_target.name}: branch {branch_name} has no configured upstream and {remote_ref} is missing; remote has other branches: {branch_list}",
                    repo,
                    resolved_target,
                    config=config,
                    tracking_upstream=None,
                    remote_name="origin",
                ),
                False,
            )
        if dry_run:
            return (
                False,
                _with_push_diagnostics(
                    f"{resolved_target.name}: would create upstream branch {remote_ref} from local {branch_name}",
                    repo,
                    resolved_target,
                    config=config,
                    tracking_upstream=None,
                    remote_name="origin",
                ),
                False,
            )
        with configured_git_ssh(repo.git, config):
            repo.git.push("-u", "origin", f"{branch_name}:{branch_name}")
        return True, None, True

    if not _remote_ref_exists(repo, remote_ref):
        return (
            False,
            _with_push_diagnostics(
                f"{resolved_target.name}: branch {branch_name} has no configured upstream and failed to resolve fetched {remote_ref}",
                repo,
                resolved_target,
                config=config,
                tracking_upstream=None,
                remote_name="origin",
            ),
            False,
        )

    if not _has_related_history(repo, branch_name, remote_ref):
        return (
            False,
            _with_push_diagnostics(
                f"{resolved_target.name}: branch {branch_name} has no configured upstream and {remote_ref} has unrelated history",
                repo,
                resolved_target,
                config=config,
                tracking_upstream=None,
                remote_name="origin",
            ),
            False,
        )

    if dry_run:
        return (
            False,
            _with_push_diagnostics(
                f"{resolved_target.name}: would set upstream for {branch_name} to {remote_ref}",
                repo,
                resolved_target,
                config=config,
                tracking_upstream=None,
                remote_name="origin",
            ),
            False,
        )

    repo.git.branch("--set-upstream-to", remote_ref, branch_name)
    return True, None, False


def _configured_remote_url_for_target(config: Config, resolved_target: ResolvedRepoTarget) -> str | None:
    configured_repos = _configured_github_repos(config, resolved_target)
    return _github_ssh_url(configured_repos[0]) if len(configured_repos) == 1 else None


def _repair_origin_for_configured_remote(
    repo: Repo,
    resolved_target: ResolvedRepoTarget,
    *,
    config: Config,
    dry_run: bool,
    tracking_upstream: str | None,
) -> str | None:
    configured_remote_url = _configured_remote_url_for_target(config, resolved_target)
    if configured_remote_url is None:
        return None

    local_origin_url = _local_remote_url(repo, "origin")
    if local_origin_url == configured_remote_url:
        return None

    if local_origin_url is None:
        action = f"add origin {configured_remote_url}"
    else:
        action = f"set origin from {local_origin_url} to {configured_remote_url}"

    if dry_run:
        return _with_push_diagnostics(
            f"{resolved_target.name}: would {action}",
            repo,
            resolved_target,
            config=config,
            tracking_upstream=tracking_upstream,
            remote_name="origin",
        )

    if local_origin_url is None:
        repo.git.remote("add", "origin", configured_remote_url)
    else:
        repo.git.remote("set-url", "origin", configured_remote_url)
    return None


def _tracking_state_for_push(
    repo: Repo,
    resolved_target: ResolvedRepoTarget,
    *,
    config: Config,
    dry_run: bool = False,
) -> tuple[PushTargetState | None, str | None]:
    tracking = local_tracking_state(repo)
    remote_name, remote_branch_name = _parse_upstream_target(tracking.upstream_name)
    branch_name = tracking.branch_name
    target_name = resolved_target.name
    created_upstream = False

    if branch_name is None:
        return None, _with_push_diagnostics(
            f"{target_name}: cannot push detached HEAD",
            repo,
            resolved_target,
            config=config,
            tracking_upstream=tracking.upstream_name,
            remote_name=remote_name,
        )
    if tracking.upstream_name is None:
        configured, configure_error, created_upstream = _try_configure_missing_upstream(
            repo,
            resolved_target,
            config=config,
            branch_name=branch_name,
            dry_run=dry_run,
        )
        if configure_error is not None:
            return None, configure_error
        if configured:
            tracking = local_tracking_state(repo)
            remote_name, remote_branch_name = _parse_upstream_target(tracking.upstream_name)
        if tracking.upstream_name is None:
            return None, _with_push_diagnostics(
                f"{target_name}: branch {branch_name} has no configured upstream",
                repo,
                resolved_target,
                config=config,
                tracking_upstream=tracking.upstream_name,
                remote_name=remote_name,
            )
    if remote_name is None or remote_branch_name is None:
        return None, _with_push_diagnostics(
            f"{target_name}: could not parse upstream branch {tracking.upstream_name!r}",
            repo,
            resolved_target,
            config=config,
            tracking_upstream=tracking.upstream_name,
            remote_name=remote_name,
        )
    if remote_name == "origin":
        origin_repair_error = _repair_origin_for_configured_remote(
            repo,
            resolved_target,
            config=config,
            dry_run=dry_run,
            tracking_upstream=tracking.upstream_name,
        )
        if origin_repair_error is not None:
            return None, origin_repair_error

    try:
        with configured_git_ssh(repo.git, config):
            repo.git.fetch("--prune", "--quiet", remote_name)
    except GitCommandError as ex:
        return None, _with_push_diagnostics(
            f"{target_name}: failed to refresh {remote_name} ({ex})",
            repo,
            resolved_target,
            config=config,
            tracking_upstream=tracking.upstream_name,
            remote_name=remote_name,
        )

    refreshed = local_tracking_state(repo)
    refreshed_remote_name, refreshed_remote_branch_name = _parse_upstream_target(refreshed.upstream_name)
    if refreshed.branch_name is None:
        return None, _with_push_diagnostics(
            f"{target_name}: cannot push detached HEAD",
            repo,
            resolved_target,
            config=config,
            tracking_upstream=refreshed.upstream_name,
            remote_name=refreshed_remote_name,
        )
    if refreshed.upstream_name is None:
        return None, _with_push_diagnostics(
            f"{target_name}: branch {refreshed.branch_name} has no configured upstream",
            repo,
            resolved_target,
            config=config,
            tracking_upstream=refreshed.upstream_name,
            remote_name=refreshed_remote_name,
        )
    if refreshed_remote_name is None or refreshed_remote_branch_name is None:
        return None, _with_push_diagnostics(
            f"{target_name}: could not parse upstream branch {refreshed.upstream_name!r}",
            repo,
            resolved_target,
            config=config,
            tracking_upstream=refreshed.upstream_name,
            remote_name=refreshed_remote_name,
        )

    ahead_count = refreshed.ahead_count if refreshed.ahead_count is not None else 0
    behind_count = refreshed.behind_count if refreshed.behind_count is not None else 0
    return (
        PushTargetState(
            branch_name=refreshed.branch_name,
            upstream_name=refreshed.upstream_name,
            remote_name=refreshed_remote_name,
            remote_branch_name=refreshed_remote_branch_name,
            ahead_count=ahead_count,
            behind_count=behind_count,
            created_upstream=created_upstream,
        ),
        None,
    )


def push_resolved_repo_target(
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
        state, error_message = _tracking_state_for_push(repo, resolved_target, config=config, dry_run=dry_run)
        if error_message is not None:
            return False, error_message
        if state is None:
            return False, f"{resolved_target.name}: could not resolve push state"

        description = _describe_tracking(state)
        if state.behind_count > 0 and state.ahead_count > 0:
            return False, f"{resolved_target.name}: cannot push diverged branch {description}"
        if state.behind_count > 0:
            return False, f"{resolved_target.name}: cannot push branch behind upstream {description}"
        if state.ahead_count == 0:
            if state.created_upstream:
                return True, _format_push_status(
                    "pushed and set upstream",
                    state,
                    repo,
                    target_name=resolved_target.name,
                )
            return True, _format_push_status("up to date", state, repo, target_name=resolved_target.name)
        if dry_run:
            return True, _format_push_status("would push", state, repo)

        remote_name = state.remote_name
        remote_branch_name = state.remote_branch_name
        branch_name = state.branch_name
        if remote_name is None or remote_branch_name is None or branch_name is None:
            return False, f"{resolved_target.name}: incomplete push state for {description}"

        with configured_git_ssh(repo.git, config):
            repo.git.push(remote_name, f"{branch_name}:{remote_branch_name}")
        return True, _format_push_status("pushed", state, repo, target_name=resolved_target.name)
    except GitCommandError as ex:
        return False, f"{resolved_target.name}: push failed ({ex})"
    finally:
        repo.close()


def push(targets: str | list[str] | None = None, *, dry_run: bool = False) -> int:
    config = load_config()
    requested_targets = [targets] if isinstance(targets, str) else targets
    if not requested_targets or requested_targets == ["."]:
        repo_targets = list(configured_repo_targets(config))
    else:
        if "." in requested_targets:
            error("`push .` cannot be combined with other targets.")
            return 1
        try:
            repo_targets = resolve_repo_targets(requested_targets, config=config)
        except ValueError as ex:
            error(contextualize_failure(str(ex), ["push", *requested_targets]))
            return 1

    if dry_run:
        info(f"Dry run: would push {len(repo_targets)} repository/repositories")
    exit_code = 0
    for resolved_target in repo_targets:
        ok, message = push_resolved_repo_target(config, resolved_target, dry_run=dry_run)
        if dry_run:
            display_message = _strip_target_prefix(resolved_target.name, message)
            print(f"  {accent(resolved_target.name)}: {muted(display_message)} ({muted(resolved_target.path)})")
            continue
        if ok:
            success(message)
            continue
        error(message)
        exit_code = 1
    return exit_code
