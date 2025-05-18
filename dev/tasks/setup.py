from typing import List, Dict, Tuple
from enum import Enum
from dataclasses import dataclass
import dataclasses

from pathlib import Path
import os, io
import re

import git
from git import Repo
import github

import jinja2

import dev.io
from dev.messages import info, error, warning, ask
from dev.config import (
    load_config,
    GradleProject,
    Project,
    PythonProject,
    PurescriptProject,
    DataProject,
    PremakeProject,
    Version,
    Config,
    Dependency,
    DependencyTarget,
    OwnershipType,
)
from dev.banner import create_banner
from dev.base import Scope
from dev.ai import suggest_commit_name

import dev.git_changes
from dev.git_changes import compute_repo_diffs, FileType, ChangeType, FileDiff


class RepoSetupMode(Enum):
    PROD = "prod"
    DEV = "dev"
    IJ = "ij"


@dataclass
class RepoInfo:
    organization: str
    name: str
    is_private: bool

    @property
    def full_name(self) -> str:
        return f"{self.organization}/{self.name}"

    @property
    def is_public(self) -> bool:
        return not self.is_private


@dataclass
class RepoSetupContext:
    config: Config
    known_repo_names: List[str]
    known_github_repos: Dict[str, RepoInfo]

    repo_template: Path

    licenses: Dict[str, str]

    gitignore_template: jinja2.Template
    cla: jinja2.Template
    cla_explanations: jinja2.Template
    contributor_privacy_policy: jinja2.Template

    settings_template: jinja2.Template
    subproject_settings_template: jinja2.Template
    build_template: jinja2.Template
    subproject_build_template: jinja2.Template
    gradle_gitignore_template: jinja2.Template
    gradle_properties_template: jinja2.Template
    python_gitignore_template: jinja2.Template
    purescript_gitignore_template: jinja2.Template

    mode: RepoSetupMode


def _make_dependency_strings(
    ctx: RepoSetupContext, project: Project
) -> Tuple[List[str], List[str]]:
    other_dependencies: List[str] = []
    project_dependencies: List[str] = []
    for dep in project.resolved_dependencies:
        match dep.target:
            case DependencyTarget.Maven(_, _):
                other_dependencies.append(dep.as_string())

            case DependencyTarget.JarFile(_):
                other_dependencies.append(dep.as_string())

            case DependencyTarget.Project(name):
                subproject = ctx.config.defined_projects[name]

                has_github_repo = subproject.github_repo is not None
                artifact_name = subproject.artifact_name
                artifact_dep = Dependency(
                    scope=dep.scope,
                    target=DependencyTarget.Maven(
                        artifact=artifact_name, maven_repo=None
                    ),
                )

                if has_github_repo and ctx.mode != RepoSetupMode.IJ:
                    project_dependencies.append(artifact_dep.as_string())
                else:
                    project_dependencies.append(
                        f"{dep.as_string()} // {subproject.version}"
                    )

    return project_dependencies, other_dependencies


def setup_project(
    ctx: RepoSetupContext, project: Project, interactive: bool = True
) -> None:
    name = project.name

    with Scope() as scope:
        if isinstance(project, GradleProject):
            setup_gradle_project(ctx, project, interactive=interactive)
        elif isinstance(project, PythonProject):
            setup_python_project(ctx, project, interactive=interactive)
        elif isinstance(project, PurescriptProject):
            setup_purescript_project(ctx, project, interactive=interactive)
        elif isinstance(project, PremakeProject):
            pass
            # setup_purescript_project(ctx, project, interactive=interactive)
        elif isinstance(project, DataProject):
            pass
            # warning(f"Skipping specialized setup for data project {name} (not yet implemented).")
        else:
            error(f"No setup function for project: {name}")

        # git push --set-upstream origin master
        # if repo is not None:
        #     if repo.active_branch.name == 'master':
        #         if repo.active_branch.tracking_branch() is None:
        #             repo.git.push('--set-upstream', 'origin', 'master')

        # Each project should have a directory.
        does_dir_exist = project.path.exists()
        if not does_dir_exist:
            error(f"Directory for {project.name} does not exist")
            if not interactive or ask(f"Create directory for {project.name}?"):
                project.path.mkdir()
            else:
                raise Exception("Directory does not exist")

        # Project directory should be a directory (lol).
        if not project.path.is_dir():
            error(f"{project.path} is not a directory")
            return

        is_github_repo_set = False
        if project.github_repo is not None:
            is_github_repo_set = True
            # If set, Github repo should exist.
            if project.github_repo not in ctx.known_repo_names:
                error(f"Remote repository {project.github_repo} does not exist")
                return
        else:
            error(f"Github repository not set for {project.name}")

        # Each project should have a .git directory
        if is_github_repo_set:
            if not (project.path / ".git").exists():
                error(f"{project.name} does not have .git")
                if not interactive or ask(
                    f"Initialize git repository for {project.name}?"
                ):
                    repo = Repo.init(project.path)
                    scope.defer(lambda: repo.close())

                    # Set default user and email
                    repo.config_writer().set_value(
                        "user", "email", ctx.config.default_git_user_email
                    ).set_value(
                        "user", "name", ctx.config.default_git_user_name
                    ).release()
                else:
                    raise Exception(".git does not exist")

            elif not (project.path / ".git").is_dir():
                error(f"{project.name} has a non-directory named .git")
                repo = None
            else:
                repo = Repo(project.path)
                scope.defer(lambda: repo.close())
        else:
            repo = None

        # Check that username and email are set
        if repo is not None:
            config = repo.config_reader()
            if config.has_section("user"):
                current_email = config.get_value("user", "email", default=None)
                current_name = config.get_value("user", "name", default=None)
            else:
                current_email = None
                current_name = None
            config.release()

            if current_email != ctx.config.default_git_user_email:
                warning(
                    f"{project.name} has a different git user email: {current_email}"
                )
                repo.config_writer().set_value(
                    "user", "email", ctx.config.default_git_user_email
                ).release()
            if current_name != ctx.config.default_git_user_name:
                warning(f"{project.name} has a different git user name: {current_name}")
                repo.config_writer().set_value(
                    "user", "name", ctx.config.default_git_user_name
                ).release()

            config = repo.config_reader()
            if config.has_section("user"):
                current_email = config.get_value("user", "email", default=None)
                current_name = config.get_value("user", "name", default=None)
            else:
                current_email = None
                current_name = None
            config.release()
            if current_email != ctx.config.default_git_user_email:
                raise Exception(
                    f"Git user email is not set to {ctx.config.default_git_user_email}"
                )
            if current_name != ctx.config.default_git_user_name:
                raise Exception(
                    f"Git user name is not set to {ctx.config.default_git_user_name}"
                )

        # IF there are no commits, create an initial commit.
        if repo is not None:
            if not repo.head.is_valid():
                # Add .gitignore
                info(f"Initializing {project.name} with .gitignore")
                repo.git.add(".gitignore")
                repo.index.commit("Initial commit")

        # R3.2: The origin remote should be set
        if repo is not None:
            if not repo.remotes:
                origin_url = None
            else:
                try:
                    origin_url = repo.remote("origin").url

                    if not origin_url.startswith("git@github.com:"):
                        error(
                            f"{project.name} has an invalid origin remote: {origin_url}"
                        )
                except ValueError:
                    origin_url = None
                    error(f"{project.name} does not have an origin remote")

            if origin_url is None:
                # Add remote
                repo.create_remote(
                    "origin", f"git@github.com:{project.github_repo}.git"
                )

                if repo.active_branch.name == "master":
                    # Set upstream for master branch
                    repo.git.push("--set-upstream", "origin", "master")

        if (project.path / "src").exists():
            pass

            # ###############################################################
            # # R2.2: Each project should have a README.md file
            # if not (project.path / 'README.md').exists():
            #     error(f"{name} does not have a README.md")

            #     if ask(f"Create README.md for {name}?"):
            #         readme = create_readme(name, Path(name), api_key=config.openai_key)
            #         write_text_file(project.path / 'README.md', readme)
            #         if ask(f"Could you review the README.md for {name}. Accept?"):
            #             pass
            #         else:
            #             os.unlink(project.path / 'README.md')

            # ###############################################################
            # # R3.1: Projects should have a clean git status
            # has_clean_git_status = False
            # if has_git:
            #     status = git_status(path)
            #     if status == []:
            #         has_clean_git_status = True

            #     else:
            #         error(f"{name} has uncommitted changes:", *status)

            #         suggested_commit_message = suggest_commit_name('\n'.join(status), api_key=config.openai_key)

            #         if ask(f"Commit changes for {name} with message: {suggested_commit_message}?"):
            #             subprocess.run(['git', 'add', '.'], cwd=path, check=True)
            #             subprocess.run(['git', 'commit', '-m', suggested_commit_message], cwd=path, check=True)
            #             has_clean_git_status = True

            #     # if os.path.exists(f'{path}/.gitignore'):
            #     #     ignore = read_ignore_file(Path(f'{path}/.gitignore'), extra_positive=['/.git'])
            #     #     # print(ignore.positive, ignore.negative)

            # R3.2: The origin remote should be set

        if (
            repo is not None
            and ctx.mode == RepoSetupMode.PROD
            and repo.active_branch.name == "master"
        ):
            commit_repo_changes(
                project, repo, openai_key=ctx.config.openai_key, interactive=interactive
            )


def setup_python_project(
    ctx: RepoSetupContext, project: PythonProject, interactive: bool = True
) -> None:
    dev.io.write_text_file(
        project.path / ".gitignore",
        render_template(ctx.gitignore_template)
        + "\n"
        + render_template(ctx.python_gitignore_template),
    )


def setup_purescript_project(
    ctx: RepoSetupContext, project: PurescriptProject, interactive: bool = True
) -> None:
    dev.io.write_text_file(
        project.path / ".gitignore",
        render_template(ctx.gitignore_template)
        + "\n"
        + render_template(ctx.purescript_gitignore_template),
    )


def setup_gradle_project(
    ctx: RepoSetupContext, project: GradleProject, interactive: bool = True
) -> None:
    project_dependencies, other_dependencies = _make_dependency_strings(ctx, project)

    # subproject_dev_dependencies = [
    #     dataclasses.replace(dep, artifact=ctx.config.defined_projects[dep.name].artifact_name).as_string(local_project_ref=True)
    #     if ctx.config.defined_projects[dep.name].github_repo is None or ctx.mode == SetupMode.IJ
    #     else dataclasses.replace(dep, artifact=ctx.config.defined_projects[dep.name].artifact_name).as_string(local_project_ref=False)
    #     for dep in project.resolved_dependencies if dep.is_subproject
    # ]

    result = render_template(
        ctx.subproject_build_template,
        project_name=project.name,
        project_group=project.group_name,
        project_version=project.version,
        repositories=project.resolved_maven_repositories,
        kotlin_version=ctx.config.plugins["kotlin-jvm"].version,
        shadow_version=ctx.config.plugins["shadow"].version,
        features=project.resolved_features,
        project_dependencies=project_dependencies,
        other_dependencies=other_dependencies,
        mode=ctx.mode.value,
        serialization_library=ctx.config.libraries[
            "kotlinx-serialization-core"
        ].maven_urn.__str__(),
    )
    result = re.sub(r"\n\s*\n", "\n\n", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r"\{\n\n", "{\n", result)
    result = re.sub(r"\n\n\}", "\n}", result)
    result = result.strip()
    result = result + "\n"
    dev.io.write_text_file(project.path / "build.gradle.kts", result)

    match ctx.mode:
        case RepoSetupMode.IJ:
            dev.io.delete_if_exists(project.path / "settings.gradle.kts")
            dev.io.touch(project.path / ".is-ij-mode")
            dev.io.delete_if_exists(project.path / ".is-dev-mode")

        case RepoSetupMode.DEV:
            dev.io.write_text_file(
                project.path / "settings.gradle.kts",
                render_template(ctx.settings_template, project_name=project.name),
            )
            dev.io.delete_if_exists(project.path / ".is-ij-mode")
            dev.io.touch(project.path / ".is-dev-mode")

        case RepoSetupMode.PROD:
            dev.io.write_text_file(
                project.path / "settings.gradle.kts",
                render_template(
                    ctx.subproject_settings_template, project_name=project.name
                ),
            )
            dev.io.delete_if_exists(project.path / ".is-ij-mode")
            dev.io.delete_if_exists(project.path / ".is-dev-mode")

    # dev.io.write_text_file(project.path / 'CLA.md', ctx.cla.render(
    #     company_name=ctx.config.company_name,
    # ))
    dev.io.write_text_file(
        project.path / ".gitignore",
        render_template(ctx.gitignore_template)
        + "\n"
        + render_template(ctx.gradle_gitignore_template),
    )
    dev.io.write_text_file(
        project.path / "gradle.properties",
        render_template(ctx.gradle_properties_template),
    )

    if project.ownership == OwnershipType.WABBIT:
        dev.io.write_text_file(project.path / "LICENSE.md", ctx.licenses["AGPL"])

    dev.io.copy(
        ctx.repo_template / "gradle-files" / "gradlew", project.path / "gradlew"
    )
    dev.io.copy(
        ctx.repo_template / "gradle-files" / "gradlew.bat", project.path / "gradlew.bat"
    )
    dev.io.copy(
        ctx.repo_template
        / "gradle-files"
        / "gradle"
        / "wrapper"
        / "gradle-wrapper.jar",
        project.path / "gradle" / "wrapper" / "gradle-wrapper.jar",
    )
    dev.io.copy(
        ctx.repo_template
        / "gradle-files"
        / "gradle"
        / "wrapper"
        / "gradle-wrapper.properties",
        project.path / "gradle" / "wrapper" / "gradle-wrapper.properties",
    )

    create_banner(
        image_path=ctx.repo_template / "banner4c.png",
        font_path=ctx.repo_template / "CooperHewitt-Light.otf",
        main_text=project.name,
        subtitle_text=None,
        background_color=(0, 0, 0, 0),
        output_path=project.path / ".banner.png",
        font_size=60,
        subtitle_font_size=None,
        padding=40,
    )


USED_COMMIT_MESSAGES = {}


def commit_repo_changes(
    project: Project, repo: Repo, openai_key: str = None, interactive: bool = True
) -> None:
    """
    Example function that:
      1) Gathers the repo changes (untracked, staged, unstaged).
      2) Prints warnings/errors.
      3) Optionally stages untracked/unstaged files based on user prompts.
      4) Displays a unified diff for each file that changed (HEAD -> WORKING).
      5) Suggests a commit message.
      6) Optionally commits.
    """

    if project.quarantine:
        # Skip commit if project is in quarantine
        error(f"Skipping commit for {project.name} (quarantine mode)")
        return

    try:
        diffs: List[FileDiff] = compute_repo_diffs(repo)
    except Exception as ex:
        error(f"Cannot proceed: {ex}")
        return

    # -------------------------------------------------------------------------
    # Prompt about untracked files
    # -------------------------------------------------------------------------
    untracked_paths = [d.new_path for d in diffs if d.untracked]
    if untracked_paths:
        error(f"{project.name} has untracked files:", *untracked_paths)
        if not interactive or ask(f"Add untracked files for {project.name}?"):
            repo.git.add(*untracked_paths)
        else:
            raise Exception("Untracked files exist")

    # -------------------------------------------------------------------------
    # Prompt about unstaged changes
    # -------------------------------------------------------------------------
    unstaged_paths = [d.new_path for d in diffs if d.unstaged and not d.untracked]
    if unstaged_paths:
        error(f"{project.name} has unstaged changes:")
        for path in unstaged_paths:
            print(f"  {path}")
        if not interactive or ask(f"Add unstaged changes for {project.name}?"):
            repo.git.add(*unstaged_paths)
        else:
            raise Exception("Unstaged changes exist")

    # -------------------------------------------------------------------------
    # Now let's see if there are changes relative to HEAD (after possible staging).
    # If HEAD is valid and changes exist, warn the user and show diffs.
    # -------------------------------------------------------------------------
    # Re-check changes after staging, so HEAD->WORKING is up to date.
    if repo.head.is_valid():
        post_stage_diffs = repo.head.commit.diff(None)  # HEAD vs. working
        changed_paths = [d.a_path for d in post_stage_diffs if d.a_path]
    else:
        # If HEAD is invalid (no commits), compare index to nothing
        post_stage_diffs = repo.index.diff(None)
        changed_paths = [d.a_path for d in post_stage_diffs]

    if changed_paths:
        warning(f"{project.name}: Changes on master")

        # ---------------------------------------------------------------------
        # Build a user-readable diff summary for HEAD->WORKING
        # using the FileDiff objects from gather_changes again (or we can re-run).
        # We'll do a single pass and write all info into buf.
        # ---------------------------------------------------------------------
        # Re-gather to see final state
        final_diffs: List[FileDiff] = compute_repo_diffs(repo, include_untracked=True)

        buf = io.StringIO()
        for diff_item in final_diffs:
            # Skip unchanged files (shouldn't normally be returned, but check anyway)
            if diff_item.change_type == ChangeType.UNCHANGED:
                continue

            # --- File Path ---
            path_str = ""
            if (
                diff_item.change_type == ChangeType.ADDED
                or diff_item.change_type == ChangeType.UNTRACKED
            ):
                path_str = f"File: {diff_item.new_path} (Added)"
            elif diff_item.change_type == ChangeType.DELETED:
                path_str = f"File: {diff_item.old_path} (Deleted)"
            elif diff_item.change_type == ChangeType.RENAMED:
                path_str = (
                    f"File: {diff_item.old_path} => {diff_item.new_path} (Renamed)"
                )
            else:  # MODIFIED, MODE_CHANGED, TYPE_CHANGED
                path_str = f"File: {diff_item.path}"  # Use the primary path attribute

            print(path_str, file=buf)

            # --- Status & Flags ---
            status_str = diff_item.change_type.name
            flags = []
            if diff_item.staged:
                flags.append("Staged")
            if diff_item.unstaged:
                flags.append("Unstaged")
            if diff_item.untracked:
                flags.append("Untracked")
            if diff_item.partial_staging_suspected:
                flags.append("Partial")

            print(f"  Status: {status_str} [{', '.join(flags)}]", file=buf)

            # --- Mode Change ---
            if (
                diff_item.old_mode is not None
                and diff_item.new_mode is not None
                and diff_item.old_mode != diff_item.new_mode
            ):
                # Only print mode change if it's the *only* change, otherwise it's implied in MODIFIED
                if diff_item.change_type == ChangeType.MODE_CHANGED:
                    print(
                        f"  Mode changed: {oct(diff_item.old_mode)} -> {oct(diff_item.new_mode)}",
                        file=buf,
                    )
                else:
                    # Optionally add a note if mode changed alongside content
                    print(
                        f"  Mode also changed: {oct(diff_item.old_mode)} -> {oct(diff_item.new_mode)}",
                        file=buf,
                    )

            # --- Content Diff (Text/Binary) ---
            is_text_change = diff_item.old_type in (
                FileType.TEXT,
                FileType.EMPTY,
            ) and diff_item.new_type in (FileType.TEXT, FileType.EMPTY)

            if diff_item.binary_different:
                print("  Binary difference detected", file=buf)
            elif is_text_change and diff_item.unified_diff:
                # Show the diff for text changes
                print("  Diff:", file=buf)
                # Simple diff tagging for clarity
                print(f'<diff path="{diff_item.path}">', file=buf)
                # Indent diff lines for readability
                for line in diff_item.unified_diff.splitlines():
                    print(f"    {line}", file=buf)
                print(f"</diff>", file=buf)
            elif (
                not diff_item.binary_different
                and not diff_item.unified_diff
                and diff_item.change_type
                not in (ChangeType.ADDED, ChangeType.DELETED, ChangeType.MODE_CHANGED)
            ):
                # If no binary diff and no text diff, but status is MODIFIED/RENAMED etc.
                # it might be a subtle change (e.g. whitespace only, if diff generation skipped it)
                print(
                    "  Note: Content difference detected, but no textual diff generated (check whitespace/type).",
                    file=buf,
                )
            elif diff_item.change_type == ChangeType.ADDED:
                if diff_item.new_type == FileType.BINARY:
                    print("  New binary file", file=buf)
                elif diff_item.new_type == FileType.EMPTY:
                    print("  New empty file", file=buf)
                elif diff_item.unified_diff:  # New text file with content
                    print("  Diff (New File):", file=buf)
                    print(f'<diff path="{diff_item.path}">', file=buf)
                    for line in diff_item.unified_diff.splitlines():
                        print(f"    {line}", file=buf)
                    print(f"</diff>", file=buf)
                else:  # New text file, but no diff generated (shouldn't happen often)
                    print("  New text file (no diff content found)", file=buf)
            elif diff_item.change_type == ChangeType.DELETED:
                if diff_item.old_type == FileType.BINARY:
                    print("  Deleted binary file", file=buf)
                else:
                    print("  Deleted text/empty file", file=buf)
            # No need for explicit UNCHANGED check here as we skipped it earlier

            print(file=buf)  # blank line after each file

        # --- Process the assembled diff text ---
        final_diff_text = buf.getvalue()
        buf.close()

        # Assuming tiktoken is installed and available
        try:
            import tiktoken

            enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
            num_tokens = len(enc.encode(final_diff_text))
            print(f"Number of tokens in diff text: {num_tokens}")
        except ImportError:
            print("Warning: tiktoken not installed. Cannot calculate token count.")
            num_tokens = len(final_diff_text) // 4  # Rough estimate
            print(f"Estimated token count: ~{num_tokens}")

        import hashlib

        h = hashlib.md5(final_diff_text.encode("utf-8")).hexdigest()
        if h in USED_COMMIT_MESSAGES:
            commit_name = USED_COMMIT_MESSAGES[h]
        else:
            if num_tokens > 100000:  # Example token limit
                # Spawn editor
                editor = os.environ.get("EDITOR", "vim")  # Use vim as fallback
                # Use a more robust temp file location if possible, or ensure .git dir exists
                commit_file_path = Path(repo.working_dir) / ".git" / "COMMIT_EDITMSG"
                commit_file_path.parent.mkdir(exist_ok=True)  # Ensure .git dir exists

                # Create a temporary commit message file
                commit_file_text = (
                    f"\n\n# Commit changes for {project.name}\n# Changes detected:\n"
                )
                # Add a summary of changed files to the commit message template
                for diff_item in final_diffs:
                    if diff_item.change_type != ChangeType.UNCHANGED:
                        commit_file_text += (
                            f"#  {diff_item.change_type.name}: {diff_item.path}\n"
                        )

                try:
                    with open(commit_file_path, "w", encoding="utf-8") as f:
                        f.write(commit_file_text)

                    # Use full path for editor command
                    status = os.system(
                        f'{editor} "{str(commit_file_path)}"'
                    )  # Quote path
                    if status != 0:
                        warning(
                            f"Editor '{editor}' exited with status {status}. Commit message might not be saved."
                        )

                    with open(commit_file_path, "r", encoding="utf-8") as f:
                        # Read the commit message from the file and strip it
                        # of leading/trailing whitespace and comments
                        commit_name = f.read().strip()
                        # Remove comment lines more carefully
                        commit_lines = [
                            line
                            for line in commit_name.splitlines()
                            if not line.strip().startswith("#")
                        ]
                        commit_name = "\n".join(commit_lines).strip()

                    if not commit_name:
                        warning(
                            "Commit message is empty after editing. Aborting commit."
                        )
                        # Handle empty commit message case (e.g., raise error, return None)
                        commit_name = None  # Or raise an exception
                    else:
                        print(
                            f"Using commit message from editor:\n---\n{commit_name}\n---"
                        )

                except Exception as e:
                    warning(f"Error handling commit message editing: {e}")
                    commit_name = f"Error processing commit message for {project.name}"  # Fallback

                finally:
                    # Clean up commit message file if it still exists
                    if commit_file_path.exists():
                        try:
                            commit_file_path.unlink()
                        except OSError as e:
                            warning(
                                f"Could not remove temporary commit file {commit_file_path}: {e}"
                            )

            else:
                print("--- Generated Diff Summary ---")
                print(final_diff_text)
                print("--- End Diff Summary ---")
                # Suggest a commit message using the assembled patch content
                # Ensure suggest_commit_name handles potential errors
                commit_name = suggest_commit_name(final_diff_text, api_key=openai_key)
                print(f"Suggested commit message: {commit_name}")

        # Optionally commit if user agrees

        if interactive:
            while True:
                info(f"Commit message: {commit_name}")
                r = ask(
                    f"Commit changes on master for {project.name}?", result_type="yne"
                )
                if r == "y":
                    USED_COMMIT_MESSAGES[h] = commit_name
                    repo.git.add(all=True)
                    repo.index.commit(commit_name)
                    break
                elif r == "e":
                    # Spawn editor
                    editor = os.environ.get("EDITOR", "vim")
                    commit_file = Path(repo.working_dir) / ".git/COMMIT_EDITMSG"
                    with open(commit_file, "w") as f:
                        f.write(commit_name)
                    os.system(f"{editor} {repo.working_dir}/.git/COMMIT_EDITMSG")
                    with open(commit_file, "r") as f:
                        commit_name = f.read().strip()
                else:
                    raise Exception("Changes on master")
        else:
            repo.git.add(all=True)
            repo.index.commit(commit_name)


def create_repo_setup_context(config: Config, mode: RepoSetupMode) -> RepoSetupContext:
    from github import Github

    assert config.github_token is not None, "Github token is not set"
    github = Github(login_or_token=config.github_token)

    # list(wabbit_corp_org.get_repos()) + list(corsaircraft_org.get_repos()) +
    # list(sir_wabbit_org.get_repos()) + \
    all_repos = list(github.get_user().get_repos())
    known_repo_names = [r.full_name for r in all_repos]
    known_github_repos = {
        r.full_name: RepoInfo(
            organization=r.owner.login,
            name=r.name,
            is_private=r.private,
        )
        for r in all_repos
    }

    for repo in all_repos:
        print(
            f"Repo: {repo.name} ({repo.full_name}) - {repo.private} - {repo.clone_url}"
        )

    repo_template = Path("data-repo-template")

    return RepoSetupContext(
        config=config,
        known_repo_names=known_repo_names,
        known_github_repos=known_github_repos,
        repo_template=repo_template,
        licenses={
            "AGPL": dev.io.read_text_file(
                repo_template / "legal" / "licenses" / "AGPL.md"
            ),
        },
        gitignore_template=dev.io.read_template(repo_template / "gitignore.jinja2"),
        cla=dev.io.read_template(repo_template / "legal" / "cla" / "v1.0.0" / "CLA.md"),
        cla_explanations=dev.io.read_template(
            repo_template / "legal" / "cla" / "v1.0.0" / "CLA_EXPLANATIONS.md"
        ),
        contributor_privacy_policy=dev.io.read_template(
            repo_template
            / "legal"
            / "contributor-privacy"
            / "v1.0.0"
            / "CONTRIBUTOR_PRIVACY.md"
        ),
        gradle_gitignore_template=dev.io.read_template(
            repo_template / "gradle-files" / "gitignore.jinja2"
        ),
        settings_template=dev.io.read_template(
            repo_template / "gradle-files" / "settings.gradle.kts.jinja2"
        ),
        subproject_settings_template=dev.io.read_template(
            repo_template / "gradle-files" / "subproject-settings.gradle.kts.jinja2"
        ),
        build_template=dev.io.read_template(
            repo_template / "gradle-files" / "build.gradle.kts.jinja2"
        ),
        subproject_build_template=dev.io.read_template(
            repo_template / "gradle-files" / "subproject-build.gradle.kts.jinja2"
        ),
        gradle_properties_template=dev.io.read_template(
            repo_template / "gradle-files" / "gradle.properties.jinja2"
        ),
        python_gitignore_template=dev.io.read_template(
            repo_template / "python-files" / "gitignore.jinja2"
        ),
        purescript_gitignore_template=dev.io.read_template(
            repo_template / "purescript-files" / "gitignore.jinja2"
        ),
        mode=mode,
    )


def render_template(template: jinja2.Template, **kwargs) -> str:
    result = template.render(**kwargs)
    result = result.rstrip() + "\n"
    return result


def setup(mode: RepoSetupMode) -> None:
    config = load_config()
    ctx = create_repo_setup_context(config, mode)

    info(f"Setting up projects in {mode.value} mode")

    # For convenience, we generate top-level settings.gradle.kts, build.gradle.kts
    # if any Gradle projects exist. Then we handle each project individually.
    any_gradle = any(
        isinstance(p, GradleProject) for p in config.defined_projects.values()
    )
    if any_gradle:
        gradle_build = render_template(ctx.build_template)
        dev.io.write_text_file(Path("build.gradle.kts"), gradle_build)

        gradle_subprojects = [
            p.name
            for p in config.defined_projects.values()
            if isinstance(p, GradleProject)
        ]
        result = render_template(ctx.settings_template, subprojects=gradle_subprojects)
        dev.io.write_text_file(Path("settings.gradle.kts"), result)

    defined_projects = config.defined_projects
    for name, project in defined_projects.items():
        setup_project(ctx, project, interactive=True)

    project_dirs = [p.path.name for p in defined_projects.values()]
    ignored_dirs = [
        "build",
        ".gradle",
        "gradle",
        ".idea",
        ".git",
        ".idea",
        ".vscode",
        ".venv",
        ".llm",
        ".kotlin",
        ".ipynb_checkpoints",
    ]

    def is_ignored_dir(dir: Path) -> bool:
        return dir.name in ignored_dirs or dir.name.startswith("tmp.")

    for dir in sorted(Path(".").iterdir()):
        if dir.is_dir() and dir.name not in project_dirs and not is_ignored_dir(dir):
            warning(f"Found unexpected directory: {dir}")

    info("All projects set up complete.")
