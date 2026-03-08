from __future__ import annotations

import asyncio
import textwrap
import time

import git

from dev.ai import suggest_version_number
from dev.caching import DEFAULT_CACHE_DB_PATH, NO_CACHE, NoCacheSentinel, cache
from dev.config import GradleProject, Version
from dev.jitpack import BuildStatus, JitPackAPI, JitPackAPIError, JitPackAuthError, JitPackNotFoundError
from dev.messages import ask, error, info, success, warning
from dev.tasks.publish_common import (
    PublishError,
    Timer,
    format_commit_message,
    get_latest_version,
    resolve_tag_commit,
    set_project_version_in_root_clj,
)
from dev.tasks.setup import RepoSetupContext, setup_project


async def poll_jitpack_build_status(api: JitPackAPI, group_id: str, artifact_id: str, version: str) -> bool | None:
    start = time.time()
    time_limit = 1200
    last_status = None

    while time.time() - start < time_limit:
        try:
            versions = await api.get_versions(group_id, artifact_id, "reload")
        except JitPackNotFoundError:
            error(f"JitPack build not found for {group_id}:{artifact_id}:{version}")
            await asyncio.sleep(3)
            continue
        except JitPackAuthError:
            error("JitPackAuthError: Check your session cookie or token!")
            raise
        except JitPackAPIError as ex:
            warning(f"JitPackAPIError: {ex}")
            await asyncio.sleep(10)
            continue

        version_obj = next((v for v in versions if v.version == version), None)
        if version_obj is None:
            await asyncio.sleep(10)
            continue

        status = version_obj.status
        if last_status != status:
            print(version_obj)
            info(f"JitPack build status for {group_id}:{artifact_id}:{version}: {status}")
            last_status = status
        if status == BuildStatus.ERROR:
            return False
        if status == BuildStatus.OK:
            return True
        if status in (BuildStatus.BUILDING, BuildStatus.QUEUED, BuildStatus.UNKNOWN):
            await asyncio.sleep(10)
            continue

    return None


def _check_jitpack_status_cached_ttl(status: object) -> float | NoCacheSentinel | None:
    if status == BuildStatus.OK:
        return 3600.0
    if status == BuildStatus.ERROR:
        return 10.0
    return NO_CACHE


_jitpack_status_cache_decorator = cache(
    path=DEFAULT_CACHE_DB_PATH,
    ttl=3600,
    exclude_params=["jitpack_api"],
    ttl_policy_func=_check_jitpack_status_cached_ttl,
)


@_jitpack_status_cache_decorator
async def _check_jitpack_status_cached(
    jitpack_api: JitPackAPI,
    group_id: str,
    artifact_id: str,
    version: str,
    expected_commit_sha: str,
) -> BuildStatus | None:
    expected_commit_prefix = expected_commit_sha[:7]
    info(f"CACHE CHECK: Querying JitPack status for {group_id}:{artifact_id}:{version} ({expected_commit_prefix})")
    try:
        versions = await jitpack_api.get_versions(group_id, artifact_id, "reload")
    except JitPackNotFoundError:
        info(f"CACHE CHECK: JitPack resource not found for {group_id}:{artifact_id}")
        return None
    except (JitPackAuthError, JitPackAPIError) as ex:
        warning(f"CACHE CHECK: API error fetching versions: {ex}")
        return None
    except Exception as ex:
        error(f"CACHE CHECK: Unexpected error fetching versions: {ex}")
        return None

    version_obj = next((v for v in versions if v.version == version), None)
    if version_obj is None:
        info(f"CACHE CHECK: Version {version} not found in JitPack response")
        return None

    current_commit_prefix = (version_obj.commit or "")[:7]
    if current_commit_prefix != expected_commit_prefix:
        info(
            f"CACHE CHECK: Found version {version}, but commit mismatch "
            f"(found {current_commit_prefix}, expected {expected_commit_prefix})"
        )
        return None

    status = version_obj.status
    info(f"CACHE CHECK: Found version {version} ({current_commit_prefix}), status: {status}")
    return status


async def publish_gradle_project_to_jetpack(
    proj: GradleProject,
    jitpack_api: JitPackAPI,
    repo_setup_context: RepoSetupContext,
    openai_key: str | None = None,
) -> bool:
    path = proj.effective_repo_root
    project_id = proj.project_id or proj.name
    assert not proj.quarantine, f"Project {proj.name} is in quarantine. Cannot publish."

    with Timer(f"Step 1: getting info for {proj.name}"):
        if proj.github_repo is None:
            raise PublishError(f"Project {proj.name} has no GitHub repository set.")

        github_repo = proj.github_repo
        repo_info = repo_setup_context.known_github_repos.get(github_repo)
        if repo_info is None:
            raise PublishError(
                f"Project {proj.name} has no actual GitHub repository.\n"
                f"Known repos: {repo_setup_context.known_github_repos.keys()}\n"
                f"Target repo: {github_repo}"
            )

        repo_is_private = repo_info.is_private
        if repo_is_private:
            info(f"Project {proj.name} is configured as private. JitPack steps will be skipped.")

        try:
            repo = git.Repo(path)
        except git.InvalidGitRepositoryError as ex:
            raise PublishError(f"Invalid Git repository at {path}") from ex

        current_branch = repo.active_branch
        if current_branch.name != "master":
            raise PublishError(
                f"Project {proj.name} is not on the master branch. Please switch to the master branch before publishing."
            )

        repo_working_tree_dir = repo.working_tree_dir
        if repo_working_tree_dir is None:
            raise PublishError(f"Cannot publish project {proj.name} with a bare repository.")

        if not repo.head.is_valid():
            raise PublishError(f"Cannot publish project {proj.name} with no commits.")

        info(f"----- PUBLISHING {proj.name} -----")
        last_repo_version, last_repo_version_tag_commit = get_latest_version(repo)

    with Timer(f"Step 2: version bump for {proj.name}"):
        config_version = proj.version
        if not config_version:
            raise PublishError(f"Project {proj.name} has no version set.")

        info(f"Current config version for {proj.name}: {config_version}")
        if last_repo_version:
            info(f"Latest repo version for {proj.name}: {last_repo_version} at {last_repo_version_tag_commit}")

        if last_repo_version and last_repo_version > config_version:
            info(f"Version in config is outdated for {proj.name}.")
            if ask("Bump version in config to match repo? [Y/n]", result_type="YN"):
                new_version_str = str(last_repo_version)
                set_project_version_in_root_clj(project_id, str(config_version), new_version_str, "root.clj")
                config_version = last_repo_version
                info(f"Updated config version for {proj.name} to {new_version_str}")
                proj.version = last_repo_version
            else:
                raise PublishError(f"Version mismatch for {proj.name}. Aborting.")
        elif last_repo_version and last_repo_version < config_version:
            info(f"Version in config is ahead of repo for {proj.name}.")
        elif last_repo_version and last_repo_version == config_version:
            info(f"Version in config matches repo for {proj.name}.")
        elif not last_repo_version:
            info(f"No tags found for {proj.name}.")

        setup_project(repo_setup_context, proj)

        assert last_repo_version is None or config_version >= last_repo_version
        assert config_version == proj.version

        if openai_key is None:
            raise PublishError("OpenAI key is required for AI-based version recommendations.")

        if last_repo_version_tag_commit is not None:
            if str(last_repo_version_tag_commit) != str(repo.head.commit):
                commits = list(repo.iter_commits(f"{last_repo_version_tag_commit}..HEAD"))[::-1]
                commit_msgs = [format_commit_message(c.message) for c in commits]
                info("\n\n".join(textwrap.indent(m, "> ", lambda line: True) for m in commit_msgs))
                recommended, rationale, commit_rationales = suggest_version_number(
                    commit_msgs, str(config_version), api_key=openai_key
                )
                info(f"AI recommended version for {proj.name}: {recommended} (Reason: {rationale})")
                info("\n".join(f"  * {m}" for m in commit_rationales))

                recommended_version = Version.parse(recommended)
                assert last_repo_version is not None
                if recommended_version < last_repo_version:
                    raise PublishError(
                        f"Recommended version {recommended_version} is not greater than "
                        f"the last tag {last_repo_version} for {proj.name}."
                    )
                if recommended_version == last_repo_version:
                    info(f"Recommended version {recommended_version} is the same as the last tag for {proj.name}.")
            else:
                info(f"No new commits since last tag for {proj.name}.")
                recommended_version = config_version
        else:
            commits = list(repo.iter_commits("HEAD"))[::-1]
            commit_msgs = [format_commit_message(c.message) for c in commits]
            info("\n\n".join(textwrap.indent(m, "> ", lambda line: True) for m in commit_msgs))
            recommended, rationale, commit_rationales = suggest_version_number(
                commit_msgs, str(config_version), api_key=openai_key
            )
            info(f"AI recommended version for {proj.name}: {recommended} (Reason: {rationale})")
            info("\n".join(f"  * {m}" for m in commit_rationales))
            recommended_version = Version.parse(recommended)

        if recommended_version != config_version:
            interactive = False
            if not interactive or ask(
                f"Use the recommended version {recommended_version}? [Y/n]",
                result_type="YN",
            ):
                new_version: Version = recommended_version
            else:
                user_input = input("Enter desired version: ").strip()
                if not user_input:
                    raise PublishError("No version entered.")
                new_version = Version.parse(user_input)

            new_version_str = str(new_version)
            info(f"Bumping version for {proj.name} to {new_version_str} ...")
            set_project_version_in_root_clj(project_id, str(config_version), new_version_str, "root.clj")
            proj.version = new_version

            info(f"Re-generating build.gradle for {proj.name} ...")
            setup_project(repo_setup_context, proj, interactive=False)
        else:
            new_version_str = str(config_version)
            new_version = config_version

        tag_name = new_version_str
        if last_repo_version != new_version:
            tag_commit = resolve_tag_commit(repo, tag_name, proj.name)
        else:
            assert last_repo_version_tag_commit is not None
            tag_commit = last_repo_version_tag_commit

    with Timer(f"Step 3: push for {proj.name}"):
        try:
            repo.git.push("origin", "master")
            repo.git.push("origin", f"refs/tags/{tag_name}")
            success(f"Pushed commit & tag {tag_name} for {proj.name}")
        except Exception as ex:
            error(f"Failed to push {proj.name}: {ex}")
            return False

    if repo_is_private:
        success(f"Skipped JitPack steps for private repository {proj.name}.")
        return True

    if proj.publish is False:
        success(f"Skipping JitPack publish for {proj.name}.")
        return True

    with Timer(f"Step 4: poll JitPack for {proj.name}"):
        github_org = github_repo.split("/")[0]
        group_id = f"com.github.{github_org}"
        artifact_id = proj.effective_artifact_id

        info(f"Checking JitPack status for {group_id}:{artifact_id}:{tag_name} (commit {tag_commit.hexsha[:7]})")

        cached_status = await _check_jitpack_status_cached(
            jitpack_api, group_id, artifact_id, tag_name, tag_commit.hexsha
        )

        build_ok = None
        if cached_status == BuildStatus.OK:
            success(f"JitPack build status for {tag_name} is OK (cached).")
            return True
        if cached_status == BuildStatus.ERROR:
            error(f"JitPack build status for {tag_name} is Error (cached).")
            return False

        refs = await jitpack_api.get_refs(group_id, artifact_id)
        info(refs)
        found_build_for_wrong_commit = False
        ref_was_found = False
        for ref in refs:
            if ref.name == tag_name:
                if str(tag_commit).startswith(ref.commit):
                    ref_was_found = True
                else:
                    found_build_for_wrong_commit = True

        await asyncio.sleep(1)
        versions = await jitpack_api.get_versions(group_id, artifact_id)
        await asyncio.sleep(1)
        versions = await jitpack_api.get_versions(group_id, artifact_id, "reload")
        info(versions)

        if not ref_was_found:
            warning(f"JitPack ref not found for {group_id}:{artifact_id}:{tag_name}")
        else:
            success(f"JitPack ref found for {group_id}:{artifact_id}:{tag_name}")

        if found_build_for_wrong_commit:
            error(f"JitPack build found for {group_id}:{artifact_id}:{tag_name} but with a different commit.")
            if ask("Remove build on JitPack? [Y/n]", result_type="YN"):
                try:
                    await jitpack_api.delete_build(group_id, artifact_id, tag_name)
                    success("Build removed. Fix code and re-run if needed.")
                except Exception as ex:
                    error(f"Failed to remove build: {ex}")
                    return False

        success(f"Polling JitPack for {group_id}:{artifact_id}:{tag_name} ...")
        await jitpack_api.force_build(group_id, artifact_id, tag_name)
        build_ok = await poll_jitpack_build_status(jitpack_api, group_id, artifact_id, tag_name)

        if build_ok is True:
            success(f"JitPack build success for {proj.name}, version {tag_name}")
            return True
        if build_ok is False:
            log = await jitpack_api.get_build_log(group_id, artifact_id, tag_name)
            import termcolor

            for line in log.splitlines():
                if line.startswith("e: "):
                    line = termcolor.colored(line[3:], "red")
                    print(f"  - {line}")
            error(f"JitPack build failed for {proj.name}, version {tag_name}")
            return False

        error(f"JitPack timed out or not found for {proj.name}, version {tag_name}")
        return False


__all__ = [
    "poll_jitpack_build_status",
    "publish_gradle_project_to_jetpack",
]
