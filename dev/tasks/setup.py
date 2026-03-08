import io
import os
from dataclasses import dataclass
from pathlib import Path

import jinja2
from git import Repo

import dev.io
from dev.ai import ensure_semver_impact_line, suggest_commit_name
from dev.base import Scope
from dev.build_order import toposort_projects
from dev.caching import DEFAULT_CACHE_DB_PATH, cache
from dev.config import (
    Config,
    DataProject,
    GradleProject,
    PremakeProject,
    ProjectDependencyTarget,
    Project,
    PurescriptProject,
    PythonProject,
    load_config,
    project_repo_root,
)
from dev.git_changes import ChangeType, FileDiff, FileType, compute_repo_diffs
from dev.licenses import load_license_texts
from dev.messages import ask, error, info, warning
from dev.tasks import setup_common, setup_kotlin, setup_python
from dev.tasks.setup_common import RepoSetupMode, render_template


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
    known_repo_names: list[str]
    known_github_repos: dict[str, RepoInfo]
    is_github_api_available: bool

    repo_template: Path

    licenses: dict[str, str]
    coc: str

    gitignore_template: jinja2.Template
    cla: jinja2.Template
    cla_explanations: jinja2.Template
    contributor_privacy_policy: jinja2.Template

    settings_template: jinja2.Template
    subproject_settings_template: jinja2.Template
    build_template: jinja2.Template
    subproject_build_template: jinja2.Template
    subproject_build_kmp_template: jinja2.Template
    gradle_gitignore_template: jinja2.Template
    gradle_properties_template: jinja2.Template
    python_gitignore_template: jinja2.Template
    purescript_gitignore_template: jinja2.Template
    python_pyproject_template: jinja2.Template
    python_pyrightconfig_template: jinja2.Template
    python_mkdocs_template: jinja2.Template
    python_docs_index_template: jinja2.Template
    python_docs_installation_template: jinja2.Template
    python_docs_development_template: jinja2.Template
    python_contributing_template: jinja2.Template
    python_docs_quality_workflow_template: jinja2.Template
    python_docs_deploy_workflow_template: jinja2.Template
    python_codespell_ignore_words_template: jinja2.Template
    python_build_executable_template: jinja2.Template

    mode: RepoSetupMode


def setup_project(
    ctx: RepoSetupContext,
    project: Project,
    interactive: bool = True,
    commit_changes: bool = True,
    allow_push: bool = True,
) -> None:
    name = project.name
    repo_path = project_repo_root(project)
    repo_managed_gradle_project = isinstance(project, GradleProject) and project.effective_gradle_root != project.path

    # Each project should have a directory before project-type setup writes files.
    if not project.path.exists():
        error(f"Directory for {project.name} does not exist")
        if not interactive or ask(f"Create directory for {project.name}?"):
            project.path.mkdir(parents=True, exist_ok=True)
        else:
            raise Exception("Directory does not exist")

    # Project directory should be a directory (lol).
    if not project.path.is_dir():
        error(f"{project.path} is not a directory")
        return

    with Scope() as scope:
        if not project.managed_by_setup and not repo_managed_gradle_project:
            info(f"Skipping file generation for repo-managed project {project.name}")
        else:
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

        if project.github_repo is None:
            error(f"Github repository not set for {project.name}")
            return

        is_github_repo_set = True
        if ctx.is_github_api_available:
            # If set and API is available, Github repo should exist.
            if project.github_repo not in ctx.known_repo_names:
                error(f"Remote repository {project.github_repo} does not exist")
                return
        else:
            warning("GitHub API unavailable; skipping remote existence check.")

        # Each project should have a .git directory
        if is_github_repo_set:
            if not (repo_path / ".git").exists():
                error(f"{project.name} does not have .git")
                if not interactive or ask(f"Initialize git repository for {project.name}?"):
                    repo_path.mkdir(parents=True, exist_ok=True)
                    repo = Repo.init(repo_path)
                    scope.defer(repo.close)

                    # Set default user and email
                    repo.config_writer().set_value("user", "email", ctx.config.default_git_user_email).set_value(
                        "user", "name", ctx.config.default_git_user_name
                    ).release()
                else:
                    raise Exception(".git does not exist")

            elif not (repo_path / ".git").is_dir():
                error(f"{project.name} has a non-directory named .git")
                repo = None
            else:
                repo = Repo(repo_path)
                scope.defer(repo.close)
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
                warning(f"{project.name} has a different git user email: {current_email}")
                repo.config_writer().set_value("user", "email", ctx.config.default_git_user_email).release()
            if current_name != ctx.config.default_git_user_name:
                warning(f"{project.name} has a different git user name: {current_name}")
                repo.config_writer().set_value("user", "name", ctx.config.default_git_user_name).release()

            config = repo.config_reader()
            if config.has_section("user"):
                current_email = config.get_value("user", "email", default=None)
                current_name = config.get_value("user", "name", default=None)
            else:
                current_email = None
                current_name = None
            config.release()
            if current_email != ctx.config.default_git_user_email:
                raise Exception(f"Git user email is not set to {ctx.config.default_git_user_email}")
            if current_name != ctx.config.default_git_user_name:
                raise Exception(f"Git user name is not set to {ctx.config.default_git_user_name}")

        # IF there are no commits, create an initial commit.
        if repo is not None:
            if not repo.head.is_valid():
                # Add .gitignore
                info(f"Initializing {project.name} with .gitignore")
                repo.git.add(".gitignore")
                repo.index.commit("Initial commit")

        # R3.2: The origin remote should be set
        if repo is not None and ctx.mode != RepoSetupMode.LOCAL:
            if not repo.remotes:
                origin_url = None
            else:
                try:
                    origin_url = repo.remote("origin").url

                    if not origin_url.startswith("git@github.com:"):
                        error(f"{project.name} has an invalid origin remote: {origin_url}")
                except ValueError:
                    origin_url = None
                    error(f"{project.name} does not have an origin remote")

            if origin_url is None:
                # Add remote
                repo.create_remote("origin", f"git@github.com:{project.github_repo}.git")

                if repo.active_branch.name == "master":
                    if allow_push:
                        # Set upstream for master branch
                        info(f"Setting upstream for master branch to origin/master for {project.name}")
                        repo.git.push("--set-upstream", "origin", "master")
                    else:
                        info(f"Skipping upstream push/config for {project.name} (allow_push=False)")

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
            commit_changes
            and repo is not None
            and ctx.mode == RepoSetupMode.PROD
            and repo.active_branch.name == "master"
        ):
            commit_repo_changes(project, repo, openai_key=ctx.config.openai_key, interactive=interactive)


def _write_wabbit_legal_files(ctx: setup_common.CommonSetupContext, project: Project) -> None:
    setup_common.write_wabbit_legal_files(ctx, project)


def _write_banner(ctx: setup_common.CommonSetupContext, project: Project) -> None:
    setup_common.write_banner(ctx, project)


def render_python_pyproject(ctx: RepoSetupContext, project: PythonProject) -> str:
    return setup_python.render_python_pyproject(ctx, project)


def render_python_pyrightconfig(ctx: RepoSetupContext, project: PythonProject) -> str:
    return setup_python.render_python_pyrightconfig(ctx, project)


def setup_python_project(ctx: RepoSetupContext, project: PythonProject, interactive: bool = True) -> None:
    # Keep legacy monkeypatch points in tests by routing module-level callbacks.
    setup_python.write_wabbit_legal_files = _write_wabbit_legal_files
    setup_python.write_banner = _write_banner
    setup_python.setup_python_project(ctx, project, interactive=interactive)


def setup_purescript_project(ctx: RepoSetupContext, project: PurescriptProject, interactive: bool = True) -> None:
    del interactive
    dev.io.write_text_file(
        project.path / ".gitignore",
        render_template(ctx.gitignore_template) + "\n" + render_template(ctx.purescript_gitignore_template),
    )
    _write_wabbit_legal_files(ctx, project)
    _write_banner(ctx, project)


def setup_gradle_project(ctx: RepoSetupContext, project: GradleProject, interactive: bool = True) -> None:
    setup_kotlin.setup_gradle_project(ctx, project, interactive=interactive)


def _relative_project_dir(root_path: Path, project_path: Path) -> str:
    return Path(os.path.relpath(project_path.resolve(), start=root_path.resolve())).as_posix()


def _gradle_project_dependencies(config: Config, project: GradleProject) -> list[GradleProject]:
    result: list[GradleProject] = []
    for dependency in project.resolved_dependencies:
        target = dependency.target
        if not isinstance(target, ProjectDependencyTarget):
            continue
        dependency_project = config.defined_projects[target.project]
        if isinstance(dependency_project, GradleProject):
            result.append(dependency_project)
    return result


def _collect_included_gradle_projects(
    config: Config,
    seed_projects: list[GradleProject],
    mode: RepoSetupMode,
) -> list[GradleProject]:
    included: list[GradleProject] = []
    seen: set[str] = set()
    queue = list(seed_projects)

    while queue:
        project = queue.pop(0)
        project_key = project.project_id or project.effective_gradle_project_name
        if project_key in seen:
            continue
        seen.add(project_key)
        included.append(project)

        for dependency_project in _gradle_project_dependencies(config, project):
            same_repo = dependency_project.effective_repo_root == project.effective_repo_root
            if same_repo or mode == RepoSetupMode.LOCAL:
                queue.append(dependency_project)

    return included


def _write_gradle_root_files(
    ctx: RepoSetupContext,
    *,
    root_path: Path,
    root_project_name: str,
    seed_projects: list[GradleProject],
    write_wrapper: bool,
    write_build: bool = True,
) -> None:
    root_path.mkdir(parents=True, exist_ok=True)
    included_projects = _collect_included_gradle_projects(ctx.config, seed_projects, ctx.mode)
    plugin_versions = setup_kotlin.settings_plugin_versions(ctx)
    if write_build:
        build_text = render_template(
            ctx.build_template,
            **plugin_versions,
        )
        dev.io.write_text_file(root_path / "build.gradle.kts", setup_kotlin.clean_gradle_build_text(build_text))

    settings_text = render_template(
        ctx.settings_template,
        **plugin_versions,
        root_project_name=root_project_name,
        included_projects=[
            {
                "gradle_project_name": included_project.effective_gradle_project_name,
                "project_dir": _relative_project_dir(root_path, included_project.path),
            }
            for included_project in included_projects
            if included_project.path.resolve() != root_path.resolve()
        ],
    )
    dev.io.write_text_file(root_path / "settings.gradle.kts", setup_kotlin.clean_gradle_build_text(settings_text))

    if write_wrapper:
        dev.io.write_text_file(
            root_path / "gradle.properties",
            setup_common.clean_text(render_template(ctx.gradle_properties_template)),
        )
        dev.io.copy(ctx.repo_template / "gradle-files" / "gradlew", root_path / "gradlew")
        dev.io.copy(ctx.repo_template / "gradle-files" / "gradlew.bat", root_path / "gradlew.bat")
        setup_kotlin._mark_executable(root_path / "gradlew")
        dev.io.copy(
            ctx.repo_template / "gradle-files" / "gradle" / "wrapper" / "gradle-wrapper.jar",
            root_path / "gradle" / "wrapper" / "gradle-wrapper.jar",
        )
        dev.io.copy(
            ctx.repo_template / "gradle-files" / "gradle" / "wrapper" / "gradle-wrapper.properties",
            root_path / "gradle" / "wrapper" / "gradle-wrapper.properties",
        )


USED_COMMIT_MESSAGES: dict[str, str] = {}


def commit_repo_changes(
    project: Project,
    repo: Repo,
    openai_key: str | None = None,
    interactive: bool = True,
    add_files: bool = True,
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
        diffs: list[FileDiff] = compute_repo_diffs(repo)
    except Exception as ex:
        error(f"Cannot proceed: {ex}")
        return

    if add_files:
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

    # Re-gather changes after optional staging and use this as the single source of truth.
    final_diffs: list[FileDiff] = compute_repo_diffs(repo, include_untracked=True)
    has_changes = any(diff_item.change_type != ChangeType.UNCHANGED for diff_item in final_diffs)

    if has_changes:
        warning(f"{project.name}: Changes on master")

        # ---------------------------------------------------------------------
        # Build a user-readable diff summary for HEAD->WORKING
        # using the FileDiff objects from gather_changes again (or we can re-run).
        # We'll do a single pass and write all info into buf.
        # ---------------------------------------------------------------------
        buf = io.StringIO()
        for diff_item in final_diffs:
            # Skip unchanged files (shouldn't normally be returned, but check anyway)
            if diff_item.change_type == ChangeType.UNCHANGED:
                continue

            # --- File Path ---
            path_str = ""
            if diff_item.change_type == ChangeType.ADDED or diff_item.change_type == ChangeType.UNTRACKED:
                path_str = f"File: {diff_item.new_path} (Added)"
            elif diff_item.change_type == ChangeType.DELETED:
                path_str = f"File: {diff_item.old_path} (Deleted)"
            elif diff_item.change_type == ChangeType.RENAMED:
                path_str = f"File: {diff_item.old_path} => {diff_item.new_path} (Renamed)"
            else:  # MODIFIED, MODE_CHANGED, TYPE_CHANGED
                path_str = f"File: {diff_item.path}"  # Use the primary path attribute

            print(path_str, file=buf)

            # --- Status & Flags ---
            status_str = diff_item.change_type.name
            flags: list[str] = []
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
                print("</diff>", file=buf)
            elif (
                not diff_item.binary_different
                and not diff_item.unified_diff
                and diff_item.change_type not in (ChangeType.ADDED, ChangeType.DELETED, ChangeType.MODE_CHANGED)
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
                    print("</diff>", file=buf)
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
            tiktoken = __import__("tiktoken")
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
                commit_file_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure .git dir exists

                # Create a temporary commit message file
                commit_file_text = f"\n\n# Commit changes for {project.name}\n# Changes detected:\n"
                # Add a summary of changed files to the commit message template
                for diff_item in final_diffs:
                    if diff_item.change_type != ChangeType.UNCHANGED:
                        commit_file_text += f"#  {diff_item.change_type.name}: {diff_item.path}\n"

                try:
                    with open(commit_file_path, "w", encoding="utf-8") as f:
                        f.write(commit_file_text)

                    # Use full path for editor command
                    status = os.system(f'{editor} "{str(commit_file_path)}"')  # Quote path
                    if status != 0:
                        warning(f"Editor '{editor}' exited with status {status}. Commit message might not be saved.")

                    with open(commit_file_path, encoding="utf-8") as f:
                        # Read the commit message from the file and strip it
                        # of leading/trailing whitespace and comments
                        commit_name = f.read().strip()
                        # Remove comment lines more carefully
                        commit_lines = [line for line in commit_name.splitlines() if not line.strip().startswith("#")]
                        commit_name = "\n".join(commit_lines).strip()

                    if not commit_name:
                        warning("Commit message is empty after editing. Aborting commit.")
                        # Handle empty commit message case (e.g., raise error, return None)
                        commit_name = None  # Or raise an exception
                    else:
                        print(f"Using commit message from editor:\n---\n{commit_name}\n---")

                except Exception as e:
                    warning(f"Error handling commit message editing: {e}")
                    commit_name = f"Error processing commit message for {project.name}"  # Fallback

                finally:
                    # Clean up commit message file if it still exists
                    if commit_file_path.exists():
                        try:
                            commit_file_path.unlink()
                        except OSError as e:
                            warning(f"Could not remove temporary commit file {commit_file_path}: {e}")

            else:
                print("--- Generated Diff Summary ---")
                print(final_diff_text)
                print("--- End Diff Summary ---")
                # Suggest a commit message using the assembled patch content
                # Ensure suggest_commit_name handles potential errors
                api_key = openai_key if openai_key is not None else ""
                try:
                    repo_working_tree = repo.working_tree_dir
                except AttributeError:
                    repo_working_tree = None
                repo_path = str(repo_working_tree) if repo_working_tree is not None else None
                commit_name = suggest_commit_name(
                    final_diff_text,
                    api_key=api_key,
                    repo_path=repo_path,
                )
                print(f"Suggested commit message: {commit_name}")

        if commit_name is not None:
            commit_name = ensure_semver_impact_line(commit_name)
        else:
            commit_name = ensure_semver_impact_line(f"Update {project.name}")

        # Optionally commit if user agrees

        if interactive:
            while True:
                info(f"Commit message: {commit_name}")
                r = ask(f"Commit changes on master for {project.name}?", result_type="yne")
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
                    with open(commit_file) as f:
                        commit_name = f.read().strip()
                    if commit_name:
                        commit_name = ensure_semver_impact_line(commit_name)
                else:
                    raise Exception("Changes on master")
        else:
            repo.git.add(all=True)
            repo.index.commit(commit_name)


def get_coc_file() -> str:
    import requests

    # https://raw.githubusercontent.com/wabbit-corp/code-of-excellence/refs/heads/master/CODE_OF_CONDUCT.md
    coc_url = (
        "https://raw.githubusercontent.com/wabbit-corp/code-of-excellence/"  # check:ignore E_HARDCODED_URL
        "refs/heads/master/CODE_OF_CONDUCT.md"
    )
    try:
        response = requests.get(coc_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as ex:
        error(f"Failed to fetch CoC file: {ex}")
        raise RuntimeError("Failed to fetch CoC file") from ex

    return str(response.text)


get_coc_file = cache(path=DEFAULT_CACHE_DB_PATH, ttl=7 * 24 * 3600)(get_coc_file)


def create_repo_setup_context(config: Config, mode: RepoSetupMode) -> RepoSetupContext:
    from github import Github
    from github.GithubException import GithubException
    from requests.exceptions import RequestException

    all_repos = []
    known_repo_names: list[str] = []
    known_github_repos: dict[str, RepoInfo] = {}
    is_github_api_available = False

    if not config.github_token:
        warning("GitHub token not set; proceeding without GitHub API.")
    else:
        try:
            gh = Github(login_or_token=config.github_token, retry=0)

            # list(wabbit_corp_org.get_repos()) + list(corsaircraft_org.get_repos()) +
            # list(sir_wabbit_org.get_repos()) + \
            all_repos = list(gh.get_user().get_repos())
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
                print(f"Repo: {repo.name} ({repo.full_name}) - {repo.private} - {repo.clone_url}")

            is_github_api_available = True
        except TimeoutError as ex:
            warning(f"GitHub API timed out; proceeding without API: {ex}")
        except (GithubException, RequestException, OSError) as ex:
            warning(f"GitHub API unavailable; proceeding without API: {ex}")
        except ValueError as ex:
            warning(f"GitHub API error; proceeding without API: {ex}")

    if not is_github_api_available:
        all_repos = []
        known_repo_names = []
        known_github_repos = {}

    repo_template = Path("data-repo-template")

    coc = get_coc_file()

    return RepoSetupContext(
        config=config,
        known_repo_names=known_repo_names,
        known_github_repos=known_github_repos,
        repo_template=repo_template,
        is_github_api_available=is_github_api_available,
        licenses=load_license_texts(repo_template / "legal" / "licenses"),
        gitignore_template=dev.io.read_template(repo_template / "gitignore.jinja2"),
        cla=dev.io.read_template(repo_template / "legal" / "cla" / "v1.0.0" / "CLA.md"),
        cla_explanations=dev.io.read_template(repo_template / "legal" / "cla" / "v1.0.0" / "CLA_EXPLANATIONS.md"),
        coc=coc,
        contributor_privacy_policy=dev.io.read_template(
            repo_template / "legal" / "contributor-privacy" / "v1.0.0" / "CONTRIBUTOR_PRIVACY.md"
        ),
        gradle_gitignore_template=dev.io.read_template(repo_template / "gradle-files" / "gitignore.jinja2"),
        settings_template=dev.io.read_template(repo_template / "gradle-files" / "settings.gradle.kts.jinja2"),
        subproject_settings_template=dev.io.read_template(
            repo_template / "gradle-files" / "subproject-settings.gradle.kts.jinja2"
        ),
        build_template=dev.io.read_template(repo_template / "gradle-files" / "build.gradle.kts.jinja2"),
        subproject_build_template=dev.io.read_template(
            repo_template / "gradle-files" / "subproject-build.gradle.kts.jinja2"
        ),
        subproject_build_kmp_template=dev.io.read_template(
            repo_template / "gradle-files" / "subproject-build-kmp.gradle.kts.jinja2"
        ),
        gradle_properties_template=dev.io.read_template(repo_template / "gradle-files" / "gradle.properties.jinja2"),
        python_gitignore_template=dev.io.read_template(repo_template / "python-files" / "gitignore.jinja2"),
        purescript_gitignore_template=dev.io.read_template(repo_template / "purescript-files" / "gitignore.jinja2"),
        python_pyproject_template=dev.io.read_template(repo_template / "python-files" / "pyproject.toml.jinja2"),
        python_pyrightconfig_template=dev.io.read_template(
            repo_template / "python-files" / "pyrightconfig.json.jinja2"
        ),
        python_mkdocs_template=dev.io.read_template(repo_template / "python-files" / "mkdocs.yml.jinja2"),
        python_docs_index_template=dev.io.read_template(repo_template / "python-files" / "docs" / "index.md.jinja2"),
        python_docs_installation_template=dev.io.read_template(
            repo_template / "python-files" / "docs" / "installation.md.jinja2"
        ),
        python_docs_development_template=dev.io.read_template(
            repo_template / "python-files" / "docs" / "development.md.jinja2"
        ),
        python_contributing_template=dev.io.read_template(repo_template / "python-files" / "CONTRIBUTING.md.jinja2"),
        python_docs_quality_workflow_template=dev.io.read_template(
            repo_template / "python-files" / ".github" / "workflows" / "docs-quality.yml.jinja2"
        ),
        python_docs_deploy_workflow_template=dev.io.read_template(
            repo_template / "python-files" / ".github" / "workflows" / "docs-deploy.yml.jinja2"
        ),
        python_codespell_ignore_words_template=dev.io.read_template(
            repo_template / "python-files" / ".codespell-ignore-words.txt.jinja2"
        ),
        python_build_executable_template=dev.io.read_template(
            repo_template / "python-files" / "scripts" / "build_executable.py.jinja2"
        ),
        mode=mode,
    )


def setup(mode: RepoSetupMode, *, interactive: bool = True, project: str | None = None) -> None:
    config = load_config()
    ctx = create_repo_setup_context(config, mode)

    if project is None:
        selected_project_names = list(config.defined_projects.keys())
    else:
        selected_project_names = toposort_projects(config.defined_projects, target_project=project)
    selected_projects = [config.defined_projects[name] for name in selected_project_names]

    if project is None:
        info(f"Setting up projects in {mode.value} mode")
    else:
        info(f"Setting up {project} and its dependencies in {mode.value} mode")

    gradle_projects = [project_item for project_item in selected_projects if isinstance(project_item, GradleProject)]
    if gradle_projects:
        target_project = config.defined_projects.get(project) if project is not None else None
        if isinstance(target_project, GradleProject) and mode != RepoSetupMode.LOCAL:
            workspace_seed_projects = [
                project_item
                for project_item in gradle_projects
                if project_item.effective_repo_root == target_project.effective_repo_root
            ]
        else:
            workspace_seed_projects = gradle_projects
        workspace_root_name = config.default_maven_project_group or "workspace"
        _write_gradle_root_files(
            ctx,
            root_path=Path("."),
            root_project_name=workspace_root_name,
            seed_projects=workspace_seed_projects,
            write_wrapper=False,
            write_build=True,
        )

        repo_ids_to_write = {
            project_item.repo_id
            for project_item in gradle_projects
            if project_item.repo_id is not None and project_item.effective_gradle_root != Path(".")
        }
        for repo_id in sorted(repo_ids_to_write):
            repo_definition = config.defined_repos.get(repo_id)
            if repo_definition is None:
                continue
            repo_gradle_projects = [
                defined_project
                for defined_project in config.defined_projects.values()
                if isinstance(defined_project, GradleProject) and defined_project.repo_id == repo_id
            ]
            if not repo_gradle_projects:
                continue
            _write_gradle_root_files(
                ctx,
                root_path=repo_definition.path,
                root_project_name=repo_definition.gradle_root_project_name or repo_id,
                seed_projects=repo_gradle_projects,
                write_wrapper=True,
                write_build=False,
            )

    for setup_project_item in selected_projects:
        setup_project(ctx, setup_project_item, interactive=interactive)

    if mode == RepoSetupMode.LOCAL:
        standalone_gradle_projects = [
            project_item
            for project_item in selected_projects
            if isinstance(project_item, GradleProject) and project_item.effective_gradle_root == project_item.path
        ]
        for standalone_project in standalone_gradle_projects:
            _write_gradle_root_files(
                ctx,
                root_path=standalone_project.path,
                root_project_name=standalone_project.effective_gradle_project_name,
                seed_projects=[standalone_project],
                write_wrapper=False,
                write_build=False,
            )

    if project is None:
        project_dirs: list[str] = []
        for project_item in selected_projects:
            relative_parts = project_item.path.parts
            if relative_parts and relative_parts[0] == ".":
                relative_parts = relative_parts[1:]
            if relative_parts:
                project_dirs.append(relative_parts[0])
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


__all__ = [
    "RepoSetupMode",
    "RepoSetupContext",
    "create_repo_setup_context",
    "setup",
]
