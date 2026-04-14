from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from dev.generated_files import SETUP_GENERATED_MARKER
from dev.tasks.setup_common import RepoSetupMode


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=repo, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def _last_commit_message(repo: Path) -> str:
    return _git(repo, "log", "-1", "--pretty=%B").strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


def _managed_gradle_file_text(body: str) -> str:
    return f"// {SETUP_GENERATED_MARKER}\n//\n{body}"


def _managed_xml_file_text(body: str) -> str:
    return f"<!-- {SETUP_GENERATED_MARKER} -->\n<!-- -->\n{body}"


def _demo_project(repo_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        name="demo",
        project_id="demo",
        path=repo_root,
        repo_root=repo_root,
        quarantine=False,
    )


def test_auto_commit_setup_only_commits_allowed_tracked_changes(tmp_path: Path) -> None:
    import dev.tasks.setup as setup_module

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    (repo_root / "root.clj").write_text('(workspace "demo")\n', encoding="utf-8")
    (repo_root / ".gitignore").write_text("build/\n", encoding="utf-8")
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text("plugins {}\n"),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    (repo_root / "root.clj").write_text('(workspace "demo-updated")\n', encoding="utf-8")
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text('plugins { id("java") }\n'),
        encoding="utf-8",
    )

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=repo_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        mode=RepoSetupMode.PROD,
        workspace_root=repo_root,
    )

    assert len(results) == 1
    assert results[0].status == "committed"
    assert set(results[0].changed_paths) == {"build.gradle.kts", "root.clj"}
    assert _git(repo_root, "status", "--short").strip() == ""
    assert _last_commit_message(repo_root) == "chore: update generated build configuration\n\nSemver Impact: NONE"


def test_auto_commit_setup_only_skips_when_untracked_files_exist(tmp_path: Path) -> None:
    import dev.tasks.setup as setup_module

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text("plugins {}\n"),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text('plugins { id("java") }\n'),
        encoding="utf-8",
    )
    (repo_root / "notes.txt").write_text("draft\n", encoding="utf-8")

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=repo_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        mode=RepoSetupMode.PROD,
        workspace_root=repo_root,
    )

    assert len(results) == 1
    assert results[0].status == "skipped"
    assert results[0].message == "Repo has changes outside the setup-only auto-commit scope."
    assert results[0].changed_paths == ("notes.txt",)


def test_auto_commit_setup_only_commits_allowed_untracked_managed_files(tmp_path: Path) -> None:
    import dev.tasks.setup as setup_module

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text("plugins {}\n"),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    (repo_root / "kotlin-conventions.md").write_text(
        _managed_xml_file_text("# Kotlin Conventions\n"),
        encoding="utf-8",
    )

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=repo_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        mode=RepoSetupMode.LOCAL,
        workspace_root=repo_root,
    )

    assert len(results) == 1
    assert results[0].status == "committed"
    assert results[0].changed_paths == ("kotlin-conventions.md",)
    assert _git(repo_root, "status", "--short").strip() == ""
    assert _last_commit_message(repo_root) == "chore: refresh generated repo guidance\n\nSemver Impact: NONE"


def test_auto_commit_setup_only_commits_agents_managed_block_updates(tmp_path: Path) -> None:
    import dev.agents_md as agents_md
    import dev.tasks.setup as setup_module

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    (repo_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "# AGENTS",
                "",
                "Add repo-specific instructions above or below the managed facts block. "
                "Keep manual guidance outside the generated markers.",
                "",
                agents_md.AGENTS_MANAGED_FACTS_BEGIN,
                "## Generated Facts",
                "",
                "- stale block",
                agents_md.AGENTS_MANAGED_FACTS_END,
                "",
            ]
        ),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    (repo_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "# AGENTS",
                "",
                "Add repo-specific instructions above or below the managed facts block. "
                "Keep manual guidance outside the generated markers.",
                "",
                agents_md.AGENTS_MANAGED_FACTS_BEGIN,
                "## Generated Facts",
                "",
                "- refreshed block",
                agents_md.AGENTS_MANAGED_FACTS_END,
                "",
            ]
        ),
        encoding="utf-8",
    )

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=repo_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        mode=RepoSetupMode.LOCAL,
        workspace_root=repo_root,
    )

    assert len(results) == 1
    assert results[0].status == "committed"
    assert results[0].changed_paths == ("AGENTS.md",)
    assert _git(repo_root, "status", "--short").strip() == ""
    assert _last_commit_message(repo_root) == "chore: refresh generated repo guidance\n\nSemver Impact: NONE"


def test_auto_commit_setup_only_skips_nonmanaged_tracked_changes(tmp_path: Path) -> None:
    import dev.tasks.setup as setup_module

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    (repo_root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text("plugins {}\n"),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    (repo_root / "README.md").write_text("# Demo\n\nUpdated.\n", encoding="utf-8")

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=repo_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        mode=RepoSetupMode.PROD,
        workspace_root=repo_root,
    )

    assert len(results) == 1
    assert results[0].status == "skipped"
    assert results[0].message == "Repo has changes outside the setup-only auto-commit scope."
    assert results[0].changed_paths == ("README.md",)


def test_auto_commit_setup_only_allows_local_mode_for_canonical_managed_changes(
    tmp_path: Path,
) -> None:
    import dev.tasks.setup as setup_module

    workspace_root = tmp_path
    repo_root = workspace_root / "repo"
    _init_repo(repo_root)
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text("plugins {}\n"),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text('plugins { id("java") }\n'),
        encoding="utf-8",
    )

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=workspace_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        mode=RepoSetupMode.LOCAL,
        workspace_root=workspace_root,
    )

    assert len(results) == 1
    assert results[0].status == "committed"
    assert results[0].changed_paths == ("build.gradle.kts",)
    assert _last_commit_message(repo_root) == "chore: update generated build configuration\n\nSemver Impact: NONE"


def test_auto_commit_setup_only_skips_local_mode_nuget_config_changes(
    tmp_path: Path,
) -> None:
    import dev.tasks.setup as setup_module

    workspace_root = tmp_path
    repo_root = workspace_root / "repo"
    _init_repo(repo_root)
    (repo_root / "NuGet.config").write_text(
        _managed_xml_file_text("<configuration />\n"),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    local_feed_path = workspace_root / ".nuget-local-feed"
    (repo_root / "NuGet.config").write_text(
        _managed_xml_file_text(
            "<configuration>\n"
            "  <packageSources>\n"
            f'    <add key="local" value="{local_feed_path}" />\n'
            "  </packageSources>\n"
            "</configuration>\n"
        ),
        encoding="utf-8",
    )

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=workspace_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        mode=RepoSetupMode.LOCAL,
        workspace_root=workspace_root,
    )

    assert len(results) == 1
    assert results[0].status == "skipped"
    assert results[0].message == "Repo has local-only setup changes after setup."
    assert results[0].changed_paths == ("NuGet.config",)


def test_auto_commit_setup_only_skips_local_mode_cross_repo_dotnet_project_references(
    tmp_path: Path,
) -> None:
    import dev.tasks.setup as setup_module

    workspace_root = tmp_path
    repo_root = workspace_root / "repo"
    external_repo_root = workspace_root / "dep-repo"
    _init_repo(repo_root)
    project_file = repo_root / "src" / "App" / "App.fsproj"
    project_file.parent.mkdir(parents=True, exist_ok=True)
    (external_repo_root / "src" / "Dep").mkdir(parents=True, exist_ok=True)
    project_file.write_text(
        _managed_xml_file_text('<Project Sdk="Microsoft.NET.Sdk">\n</Project>\n'),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    project_file.write_text(
        _managed_xml_file_text(
            '<Project Sdk="Microsoft.NET.Sdk">\n'
            "  <ItemGroup>\n"
            '    <ProjectReference Include="../../../../dep-repo/src/Dep/Dep.fsproj" />\n'
            "  </ItemGroup>\n"
            "</Project>\n"
        ),
        encoding="utf-8",
    )

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=workspace_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        mode=RepoSetupMode.LOCAL,
        workspace_root=workspace_root,
    )

    assert len(results) == 1
    assert results[0].status == "skipped"
    assert results[0].message == "Repo has local-only setup changes after setup."
    assert results[0].changed_paths == ("src/App/App.fsproj",)
