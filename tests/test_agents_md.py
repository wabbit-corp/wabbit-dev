from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mu.parser import parse


def _make_python_project(path: Path, *, project_id: str, repo_id: str | None = None, repo_root: Path | None = None):
    from dev.config import OwnershipType, PythonProject

    return PythonProject(
        path=path,
        name=path.name,
        version=None,
        description=None,
        authors=[],
        license=None,
        github_repo="org/demo",
        requires_python=None,
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        application=None,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=False,
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
        project_id=project_id,
        repo_id=repo_id,
        repo_root=repo_root,
        docs_enabled=True,
        docs_system="mkdocs",
    )


def test_write_repo_agents_file_creates_starter_when_missing(tmp_path: Path) -> None:
    import dev.agents_md as agents_md
    from dev.config import Config, RepoDefinition

    repo_root = tmp_path / "demo"
    repo_root.mkdir()
    (repo_root / "BUILD.md").write_text("# Build\n", encoding="utf-8")

    project = _make_python_project(repo_root, project_id="demo")
    config = Config(raw=parse("()"))
    config.defined_projects["demo"] = project
    config.defined_repos["demo"] = RepoDefinition(
        repo_id="demo",
        path=repo_root,
        github_repo="org/demo",
        gradle_root_project_name=None,
        jvm_policy=None,
        project_ids=["demo"],
    )

    assert agents_md.write_repo_agents_file(config, repo_root, [project]) is True

    agents_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_text.startswith("# AGENTS\n")
    assert "Add repo-specific instructions above or below the managed facts block." in agents_text
    assert agents_md.AGENTS_MANAGED_FACTS_BEGIN in agents_text
    assert "`dev where`" in agents_text
    assert "`dev setup demo`" in agents_text
    assert "`BUILD.md`" in agents_text
    assert "./dev" not in agents_text


def test_write_repo_agents_file_leaves_existing_manual_file_without_markers_untouched(tmp_path: Path) -> None:
    import dev.agents_md as agents_md
    from dev.config import Config

    repo_root = tmp_path / "demo"
    repo_root.mkdir()
    agents_path = repo_root / "AGENTS.md"
    original_text = "# AGENTS\n\nHuman-authored instructions only.\n"
    agents_path.write_text(original_text, encoding="utf-8")

    project = _make_python_project(repo_root, project_id="demo")
    config = Config(raw=parse("()"))
    config.defined_projects["demo"] = project

    assert agents_md.write_repo_agents_file(config, repo_root, [project]) is False
    assert agents_path.read_text(encoding="utf-8") == original_text


def test_write_repo_agents_file_updates_only_managed_block(tmp_path: Path) -> None:
    import dev.agents_md as agents_md
    from dev.config import Config, RepoDefinition

    repo_root = tmp_path / "demo"
    repo_root.mkdir()
    (repo_root / "SPECIFICATION.md").write_text("# Spec\n", encoding="utf-8")

    project = _make_python_project(repo_root, project_id="demo", repo_id="demo", repo_root=repo_root)
    config = Config(raw=parse("()"))
    config.defined_projects["demo"] = project
    config.defined_repos["demo"] = RepoDefinition(
        repo_id="demo",
        path=repo_root,
        github_repo="org/demo",
        gradle_root_project_name=None,
        jvm_policy=None,
        project_ids=["demo"],
    )

    agents_path = repo_root / "AGENTS.md"
    agents_path.write_text(
        "\n".join(
            [
                "# AGENTS",
                "",
                "Manual intro",
                "",
                agents_md.AGENTS_MANAGED_FACTS_BEGIN,
                "## Generated Facts",
                "",
                "- stale block",
                agents_md.AGENTS_MANAGED_FACTS_END,
                "",
                "Manual footer",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert agents_md.write_repo_agents_file(config, repo_root, [project]) is True

    agents_text = agents_path.read_text(encoding="utf-8")
    assert "Manual intro" in agents_text
    assert "Manual footer" in agents_text
    assert "- stale block" not in agents_text
    assert "`dev project show demo`" in agents_text
    assert "`SPECIFICATION.md`" in agents_text


def test_write_repo_agents_file_reports_multiple_managed_blocks_with_file_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dev.agents_md as agents_md
    from dev.config import Config

    repo_root = tmp_path / "demo"
    repo_root.mkdir()

    project = _make_python_project(repo_root, project_id="demo")
    config = Config(raw=parse("()"))
    config.defined_projects["demo"] = project

    agents_path = repo_root / "AGENTS.md"
    original_text = "\n".join(
        [
            "# AGENTS",
            "",
            agents_md.AGENTS_MANAGED_FACTS_BEGIN,
            "first block",
            agents_md.AGENTS_MANAGED_FACTS_END,
            "",
            agents_md.AGENTS_MANAGED_FACTS_BEGIN,
            "second block",
            agents_md.AGENTS_MANAGED_FACTS_END,
            "",
        ]
    )
    agents_path.write_text(original_text, encoding="utf-8")

    warnings: list[str] = []
    monkeypatch.setattr(agents_md, "warning", warnings.append)

    assert agents_md.write_repo_agents_file(config, repo_root, [project]) is False
    assert agents_path.read_text(encoding="utf-8") == original_text
    assert warnings == [f"Skipping malformed AGENTS.md managed block in {agents_path}: found 2 managed blocks"]


def test_setup_writes_repo_root_agents_for_repo_managed_project(tmp_path: Path, monkeypatch) -> None:
    import dev.tasks.setup as setup_module
    from dev.config import Config, RepoDefinition

    repo_root = tmp_path / "demo"
    project_path = repo_root / "pkg"
    project_path.mkdir(parents=True)

    project = _make_python_project(project_path, project_id="demo/pkg", repo_id="demo", repo_root=repo_root)

    config = Config(raw=parse("()"))
    config.defined_projects["demo/pkg"] = project
    config.defined_repos["demo"] = RepoDefinition(
        repo_id="demo",
        path=repo_root,
        github_repo="org/demo",
        gradle_root_project_name=None,
        jvm_policy=None,
        project_ids=["demo/pkg"],
    )

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, mode: SimpleNamespace(config=config, mode=mode),
    )
    monkeypatch.setattr(setup_module, "toposort_projects", lambda _projects, target_project=None: ["demo/pkg"])
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)

    result = setup_module.setup(setup_module.RepoSetupMode.PROD, interactive=False, project="demo/pkg")

    assert result == 0
    assert (repo_root / "AGENTS.md").is_file()
    assert not (project_path / "AGENTS.md").exists()
