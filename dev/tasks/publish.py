#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Async-based Topological Gradle+JitPack Publish Flow with re-rendering logic.

Usage in dev.py:
    parser.add_parser('publish').set_defaults(func=lambda args: asyncio.run(publish_main(args.project)))
"""

from typing import List, Dict, Tuple, Optional, Any

import os
import asyncio
import textwrap
import time
from pathlib import Path
from collections import defaultdict, deque
import git

from dev.caching import cache, NO_CACHE
from dev.config import (
    load_config,
    GradleProject,
    Version,
)
from dev.git_changes import (
    compute_repo_diffs,
    ChangeType
)
from dev.messages import info, warning, error, success, ask
from dev.ai import suggest_commit_name, suggest_version_number
from dev.jitpack import JitPackAPI, BuildStatus, JitPackNotFoundError, JitPackAuthError, JitPackAPIError
from dev.tasks.setup import setup_project, commit_repo_changes, create_repo_setup_context, RepoSetupContext, RepoSetupMode
from dev.build_order import toposort_projects

def get_latest_version(repo) -> Tuple[Version | None, git.Commit | None]:
    #print(repo)
    # List known tags.
    versions: List[Tuple[Version, git.Commit]] = []
    # print(repo.tags)
    for tag in repo.tags:
        tag_name = tag.name
        tag_commit = tag.object
        # print(tag_name, tag_commit, type(tag_commit))

        if isinstance(tag_commit, git.objects.tag.TagObject):
            tag_commit = tag_commit.object
            # print(tag_commit, type(tag_commit))

        if not isinstance(tag_commit, git.Commit):
            continue
        tag_version = Version.parse_or_null(tag_name)
        if tag_version is not None:
            versions.append((tag_version, tag_commit))
    versions.sort(key=lambda x: x[0], reverse=True)

    # print(versions)

    if versions:
        latest_version = versions[0][0]
        latest_version_commit = versions[0][1]
    else:
        latest_version = None
        latest_version_commit = None
    
    return latest_version, latest_version_commit

##############################################################################
# 2. Updating root.clj (naive string search)
##############################################################################

def set_project_version_in_root_clj(project_name: str,
                                    current_version: str,
                                    new_version: str,
                                    root_file: str = "root.clj"):
    """
    Finds a form like:
      (gradle "my-project"
        :version "X.Y.Z"
        ...)
    and replaces the version with `new_version`, only if the existing version
    matches `current_version`.
    If not found or mismatched, raises ValueError.

    :param project_name: The string after (gradle "<project_name>"
    :param current_version: The version we expect to see (extra safety check)
    :param new_version: The version we want to set
    :param root_file: File path to the .clj config
    """

    if not os.path.isfile(root_file):
        raise ValueError(f"No {root_file} found, cannot update version for {project_name}.")

    with open(root_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    updated_lines = []
    in_target_gradle_block = False  # True if we are inside the (gradle "project_name" ...) form
    found_and_replaced = False
    block_start_index = None  # The index of the line containing (gradle "project_name"

    project_types = ["gradle", "python", "data", "purescript"]
    import re
    re_project_type_no_name = re.compile(rf"\((?:{'|'.join(project_types)})\s+\"[^\"]+\"")
    re_project_type = re.compile(rf"\((?:{'|'.join(project_types)})\s+\"{project_name}\"")
    
    # We'll walk through lines, and once we detect `(gradle "project_name"`,
    # we know we are in that block until the matching `)` or until we see next (gradle ...
    for i, line in enumerate(lines):
        # Check if we hit a new gradle form. If we were in a block already,
        # end that block (even if not closed) to avoid messing up the next project.
        # if "(gradle \"" in line or "(python \"" in line or "(data \"" in line or "(purescript \"" in line:

        if re_project_type_no_name.match(line):
            # If we hit another gradle form while already in the target block
            # without seeing a closing paren, we forcibly end the old block.
            in_target_gradle_block = False

            # Now see if this is our target form
            if re_project_type.match(line):
                in_target_gradle_block = True
                block_start_index = i

        if in_target_gradle_block:
            # We are inside the block we want. Look for `:version "<something>"`
            # If found, check if <something> == current_version, replace with new_version.
            if ":version " in line:
                # Attempt a very simple parse: look for :version "
                version_marker = ':version "'
                idx = line.find(version_marker)
                if idx != -1:
                    start_idx = idx + len(version_marker)
                    end_idx = line.find('"', start_idx)
                    if end_idx != -1:
                        existing_version = line[start_idx:end_idx]
                        # Check if it matches
                        if existing_version != current_version:
                            raise ValueError(
                                f"Found :version \"{existing_version}\" but expected \"{current_version}\" "
                                f"for project '{project_name}'. Aborting update."
                            )
                        # Replace with new_version
                        before = line[:start_idx]
                        after = line[end_idx:]
                        line = before + new_version + after
                        found_and_replaced = True

            # If this line closes the gradle form with a `)`, we assume we have left the block
            # This is naive, but for typical usage it should be enough.
            if ')' in line:
                in_target_gradle_block = False

        updated_lines.append(line)

    if not found_and_replaced:
        raise ValueError(
            f"Could not find a matching (gradle \"{project_name}\") block with "
            f":version \"{current_version}\" in {root_file}. Nothing updated."
        )

    with open(root_file, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)

    print(f"Updated version for '{project_name}' from '{current_version}' to '{new_version}' in {root_file}")

##############################################################################
# 3. Poll JitPack Build (Async)
##############################################################################

async def poll_jitpack_build_status(api: JitPackAPI, group_id: str, artifact_id: str, version: str) -> bool | None:
    """
    Asynchronously poll JitPack for build status. Return True if success,
    False if error, or None if not found/timed out.
    """
    start = time.time()
    time_limit = 1200  # 20 minutes
    last_status = None

    while time.time() - start < time_limit:
        try:
            versions = await api.get_versions(group_id, artifact_id, 'reload')
        except JitPackNotFoundError:
            error(f"JitPack build not found for {group_id}:{artifact_id}:{version}")
            continue
        except JitPackAuthError:
            error("JitPackAuthError: Check your session cookie or token!")
            raise
        except JitPackAPIError as e:
            warning(f"JitPackAPIError: {e}")
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
        elif status == BuildStatus.OK:
            return True
        elif status in (BuildStatus.BUILDING, BuildStatus.QUEUED, BuildStatus.UNKNOWN):
            await asyncio.sleep(10)
            continue

    # while time.time() - start < time_limit:
    #     try:
    #         build_info = await api.get_build_info(group_id, artifact_id, version)
    #         if build_info is None:
    #             await asyncio.sleep(10)
    #             continue
    #     except JitPackAuthError:
    #         error("JitPackAuthError: Check your session cookie or token!")
    #         raise
    #     except JitPackAPIError as e:
    #         warning(f"JitPackAPIError: {e}")
    #         await asyncio.sleep(10)
    #         continue

    #     if build_info is None:
    #         await asyncio.sleep(10)
    #         continue

    #     status = build_info.status

    #     if status != last_status:
    #         info(f"JitPack build status for {group_id}:{artifact_id}:{version}: {status}")
    #         last_status = status

    #     if status == BuildStatus.OK:
    #         return True
    #     elif status == BuildStatus.ERROR:
    #         return False
    #     elif status in (BuildStatus.BUILDING, BuildStatus.QUEUED, BuildStatus.UNKNOWN):
    #         await asyncio.sleep(10)
    #         continue

    return None  # Timed out

def _check_jitpack_status_cached_ttl(status) -> int:
    """
    Custom TTL policy function for JitPack status cache.
    If the status is OK, return a longer TTL (e.g., 1 hour).
    If the status is ERROR, return a shorter TTL (e.g., 5 minutes).
    If the status is None, return NO_CACHE.
    """
    if status == BuildStatus.OK:
        return 3600  # 1 hour
    elif status == BuildStatus.ERROR:
        return 10  # 10 seconds
    else:
        return NO_CACHE


@cache(path=".dev.cache.db", ttl=3600, exclude_params=['jitpack_api'], ttl_policy_func=_check_jitpack_status_cached_ttl) # Cache for 1 hour by default
async def _check_jitpack_status_cached(
    jitpack_api: JitPackAPI,
    group_id: str,
    artifact_id: str,
    version: str,
    expected_commit_sha: str
) -> Optional[BuildStatus]:
    """
    Checks JitPack for the status of a specific version/commit using get_versions.
    Returns the BuildStatus if found and commit matches, otherwise None.
    This function is cached.
    """
    expected_commit_prefix = expected_commit_sha[:7]
    info(f"CACHE CHECK: Querying JitPack status for {group_id}:{artifact_id}:{version} ({expected_commit_prefix})")
    try:
        # Use 'reload' to ensure we query JitPack directly before caching
        versions = await jitpack_api.get_versions(group_id, artifact_id, 'reload')
    except JitPackNotFoundError:
        info(f"CACHE CHECK: JitPack resource not found for {group_id}:{artifact_id}")
        return None # Not found on JitPack
    except (JitPackAuthError, JitPackAPIError) as e:
        warning(f"CACHE CHECK: API error fetching versions: {e}")
        return None # Don't cache API errors reliably
    except Exception as e:
        error(f"CACHE CHECK: Unexpected error fetching versions: {e}")
        return None

    version_obj = next((v for v in versions if v.version == version), None)

    if version_obj:
        current_commit_prefix = (version_obj.commit or "")[:7]
        if current_commit_prefix == expected_commit_prefix:
            status = version_obj.status
            info(f"CACHE CHECK: Found version {version} ({current_commit_prefix}), status: {status}")
            # Optionally adjust TTL based on status here if decorator supported it,
            # otherwise, rely on the default TTL (1 hour). A successful 'OK' will likely
            # be hit again within the hour if needed, effectively extending its cache life.
            return status
        else:
            info(f"CACHE CHECK: Found version {version}, but commit mismatch (found {current_commit_prefix}, expected {expected_commit_prefix})")
            return None # Commit doesn't match
    else:
        info(f"CACHE CHECK: Version {version} not found in JitPack response")
        return None # Version not listed

##############################################################################
# 4. Single-Project Publish Flow (Fully Async)
##############################################################################

class PublishError(Exception):
    pass

class Timer:
    def __init__(self, name: str = None):
        self.name = name
        
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        elapsed_time = time.time() - self.start_time
        if self.name:
            info(f"{self.name} took {elapsed_time:.2f} seconds")
        else:
            info(f"Elapsed time: {elapsed_time:.2f} seconds")
        return False  # Do not suppress exceptions

async def publish_single_project(proj: GradleProject, jitpack_api: JitPackAPI, repo_setup_context: RepoSetupContext, openai_key: str = None) -> bool:
    """
    Publish a single GradleProject to JitPack. Steps:
      1) local changes => optional commit
      2) bump version => update root.clj => re-render => commit
      3) tag & push
      4) poll JitPack
    """
    path = proj.path

    assert not proj.quarantine, f"Project {proj.name} is in quarantine. Cannot publish."

    with Timer(f'Step 1: getting info for {proj.name}'):
        if proj.github_repo is None:
            raise PublishError(f"Project {proj.name} has no GitHub repository set.")
        
        repo_info = repo_setup_context.known_github_repos.get(proj.github_repo)

        if repo_info is None:
            raise PublishError(f"Project {proj.name} has no actual GitHub repository.\n"
                               f"Known repos: {repo_setup_context.known_github_repos.keys()}\n"
                               f"Target repo: {proj.github_repo}")

        repo_is_private = repo_info.is_private
        if repo_is_private:
            info(f"Project {proj.name} is configured as private. JitPack steps will be skipped.")

        try:
            repo = git.Repo(path)
        except git.InvalidGitRepositoryError as e:
            raise PublishError(f"Invalid Git repository at {path}") from e

        # Current branch
        current_branch = repo.active_branch
        if current_branch.name != "master":
            raise PublishError(f"Project {proj.name} is not on the master branch. Please switch to the master branch before publishing.")

        # No working tree (bare repo).
        repo_working_tree_dir = repo.working_tree_dir
        if repo_working_tree_dir is None:
            raise PublishError(f"Cannot publish project {proj.name} with a bare repository.")

        # No commits.
        if not repo.head.is_valid():
            raise PublishError(f"Cannot publish project {proj.name} with no commits.")

        info(f"----- PUBLISHING {proj.name} -----")

        last_repo_version, last_repo_version_tag_commit = get_latest_version(repo)

    # Step 2: version bump
    with Timer(f'Step 2: version bump for {proj.name}'):
        config_version = proj.version
        if not config_version:
            raise PublishError(f"Project {proj.name} has no version set.")
        
        info(f"Current config version for {proj.name}: {config_version}")
        if last_repo_version:
            info(f"Latest repo version for {proj.name}: {last_repo_version} at {last_repo_version_tag_commit}")

        if last_repo_version and last_repo_version > config_version:
            # This may mean that the version in the config is outdated.
            info(f"Version in config is outdated for {proj.name}.")
            if ask("Bump version in config to match repo? [Y/n]", result_type="YN"):
                new_version_str = str(last_repo_version)
                set_project_version_in_root_clj(proj.name, str(config_version), new_version_str, "root.clj")
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
        
        # We set up the project again to ensure the new version is reflected in the build.gradle
        # This will also ensure that all changes up to this point are committed.
        setup_project(repo_setup_context, proj)

        assert last_repo_version is None or config_version >= last_repo_version
        assert config_version == proj.version

        if last_repo_version_tag_commit is not None:
            if str(last_repo_version_tag_commit) != str(repo.head.commit):
                commits = list(repo.iter_commits(f"{last_repo_version_tag_commit}..HEAD"))[::-1]
                commit_msgs = [c.message.strip() for c in commits]
                info('\n\n'.join(textwrap.indent(m, "> ", lambda line: True) for m in commit_msgs))
                recommended, rationale, commit_rationales = suggest_version_number(commit_msgs, config_version.__str__(), api_key=openai_key)
                info(f"AI recommended version for {proj.name}: {recommended} (Reason: {rationale})")
                info('\n'.join(f"  * {m}" for m in commit_rationales))

                recommended_version = Version.parse(recommended)
                if recommended_version < last_repo_version:
                    raise PublishError(f"Recommended version {recommended_version} is not greater than the last tag {last_repo_version} for {proj.name}.")
                elif recommended_version == last_repo_version:
                    info(f"Recommended version {recommended_version} is the same as the last tag for {proj.name}.")
                    # info("Incrementing the patch version.")
                    # recommended_version = recommended_version.next_patch()
                    pass
            else:
                info(f"No new commits since last tag for {proj.name}.")
                recommended_version = config_version
        else:
            commits = list(repo.iter_commits("HEAD"))[::-1]
            commit_msgs = [c.message.strip() for c in commits]
            info('\n\n'.join(textwrap.indent(m, "> ", lambda line: True) for m in commit_msgs))
            recommended, rationale, commit_rationales = suggest_version_number(commit_msgs, config_version.__str__(), api_key=openai_key)
            info(f"AI recommended version for {proj.name}: {recommended} (Reason: {rationale})")
            info('\n'.join(f"  * {m}" for m in commit_rationales))
            recommended_version = Version.parse(recommended)

        if recommended_version != config_version:
            # The new yes/no logic
            # 'y' => keep recommended; 'n' => ask user for custom
            interactive = False
            if not interactive or ask(f"Use the recommended version {recommended_version.__str__()}? [Y/n]", result_type="YN"):
                new_version: Version = recommended_version
            else:
                user_input = input("Enter desired version: ").strip()
                if not user_input:
                    raise PublishError("No version entered.")
                new_version = Version.parse(user_input)

            new_version_str = new_version.__str__()

            # Step 2: Bump version
            info(f"Bumping version for {proj.name} to {new_version_str.__str__()} ...")

            # Update root.clj
            set_project_version_in_root_clj(proj.name, config_version.__str__(), new_version_str, "root.clj")
            proj.version = new_version

            # Step 2.5: Re-render build.gradle + other files
            # This will also commit the changes.
            info(f"Re-generating build.gradle for {proj.name} ...")
            setup_project(repo_setup_context, proj, interactive=False)
        else:
            new_version_str = config_version.__str__()
            new_version = config_version

        tag_name = new_version_str
        if last_repo_version != new_version:
            # Step 3: Tag & push
            existing_tags = [t.name for t in repo.tags]
            if tag_name in existing_tags:
                warning(f"Tag {tag_name} already exists for {proj.name}.")
                # Optionally remove or do nothing. We'll do nothing for now.
            else:
                repo.create_tag(tag_name, message=f"Release {tag_name}")
                tag_commit = repo.head.commit
        else:
            tag_commit = last_repo_version_tag_commit


    with Timer(f'Step 3: push for {proj.name}'):
        # push
        try:
            repo.git.push("origin", "master")
            repo.git.push("origin", f"refs/tags/{tag_name}")
            success(f"Pushed commit & tag {tag_name} for {proj.name}")
        except Exception as e:
            error(f"Failed to push {proj.name}: {e}")
            return False
    
    # Optional push to JitPack
    if repo_is_private:
        success(f"Skipped JitPack steps for private repository {proj.name}.")
        return True
    
    if proj.publish is False:
        success(f"Skipping JitPack publish for {proj.name}.")
        return True
    

    if not isinstance(proj, GradleProject): 
        warning(f"Skipping publishing to jitpack for {proj.name}: not a Gradle project.")
        return True
        

    # Step 4: poll JitPack
    with Timer(f'Step 4: poll JitPack for {proj.name}'):
        github_org = proj.github_repo.split("/")[0]
        group_id = f"com.github.{github_org}"
        artifact_id = proj.name

        info(f"Checking JitPack status for {group_id}:{artifact_id}:{tag_name} (commit {tag_commit.hexsha[:7]})")

        cached_status = await _check_jitpack_status_cached(jitpack_api, group_id, artifact_id, tag_name, tag_commit.hexsha)

        build_ok = None
        if cached_status == BuildStatus.OK:
            success(f"JitPack build status for {tag_name} is OK (cached).")
            build_ok = True
            return True
        elif cached_status == BuildStatus.ERROR:
            error(f"JitPack build status for {tag_name} is Error (cached).")
            # Optionally show log if cached? For now, just report error.
            build_ok = False
            return False
        else:
            refs = await jitpack_api.get_refs(group_id, artifact_id)
            info(refs)
            # [Ref(name='1.1.1', commit='207051c'), Ref(name='1.0.0', commit='569e7f3'), Ref(name='master', commit='207051c')]
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
            versions = await jitpack_api.get_versions(group_id, artifact_id, 'reload')
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
        
        elif build_ok is False:
            log = await jitpack_api.get_build_log(group_id, artifact_id, tag_name)
            import termcolor
            for line in log.splitlines():
                if line.startswith('e: '):
                    line = termcolor.colored(line[3:], 'red')
                    print(f'  - {line}')
            error(f"JitPack build failed for {proj.name}, version {tag_name}")
            return False
        
        else:
            error(f"JitPack timed out or not found for {proj.name}, version {tag_name}")
            return False

##############################################################################
# 5. The Main "publish" Command - Async
##############################################################################

async def publish_main(project_name=None):
    config = load_config()
    repo_setup_mode = RepoSetupMode.PROD
    repo_setup_context = create_repo_setup_context(config, repo_setup_mode)

    # Use an async context for JitPackAPI
    async with JitPackAPI(session_cookie=config.jitpack_cookie) as jitpack_api:
        all_projects = {
            name: p
            for name, p in config.defined_projects.items()
        }

        if project_name and project_name not in all_projects:
            error(f"No such Gradle project: {project_name}")
            return

        order = toposort_projects(all_projects, target_project=project_name)
        if not order:
            error("No projects to publish or cycle in dependencies.")
            return

        success("Topological order of projects to publish:\n  " + ", ".join(order))

        for name in order:
            proj = all_projects[name]

            if proj.github_repo is None:
                warning(f"Skipping {proj.name}: no GitHub repository set.")
                continue

            ok = await publish_single_project(proj, jitpack_api, repo_setup_context, openai_key=config.openai_key)
            if not ok:
                warning(f"Stopped after {proj.name} failed.")
                break
        else:
            success("All selected projects published successfully.")