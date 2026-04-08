from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import dev.io
from dev.config import Config, DataProject, GradleProject, PremakeProject, Project, PurescriptProject, PythonProject
from dev.messages import warning

AGENTS_MANAGED_FACTS_BEGIN = "<!-- BEGIN app-wabbit-dev managed facts -->"
AGENTS_MANAGED_FACTS_END = "<!-- END app-wabbit-dev managed facts -->"

_REFERENCE_DOC_FILENAMES = (
    "SPECIFICATION.md",
    "BUILD.md",
    "CHANGELOG.md",
    "PLAN.md",
)


def _normalize_markdown(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    return normalized + "\n"


def _repo_definition_for_root(config: Config, repo_root: Path) -> object | None:
    repo_root_resolved = repo_root.resolve()
    for repo_definition in config.defined_repos.values():
        if repo_definition.path.resolve() == repo_root_resolved:
            return repo_definition
    return None


def _canonical_target(config: Config, repo_root: Path, repo_projects: Sequence[Project]) -> str:
    repo_definition = _repo_definition_for_root(config, repo_root)
    repo_id = getattr(repo_definition, "repo_id", None)
    if isinstance(repo_id, str) and repo_id:
        return repo_id

    sorted_projects = sorted(
        repo_projects,
        key=lambda project: (
            project.project_id or "",
            project.path.as_posix(),
        ),
    )
    for project in sorted_projects:
        if project.project_id is not None:
            return project.project_id
    return repo_root.name


def _project_type_label(project: Project | object) -> str | None:
    if isinstance(project, PythonProject):
        return "python"
    if isinstance(project, GradleProject):
        if "scala" in project.resolved_features:
            return "scala/kmp" if project.is_kmp else "scala/jvm"
        if "kotlin" in project.resolved_features or project.is_kmp:
            return "kotlin/kmp" if project.is_kmp else "kotlin/jvm"
        return "gradle/kmp" if project.is_kmp else "gradle/jvm"
    if isinstance(project, PurescriptProject):
        return "purescript"
    if isinstance(project, PremakeProject):
        return "premake"
    if isinstance(project, DataProject):
        return "data"
    if isinstance(project, Project):
        return type(project).__name__.removesuffix("Project").lower()
    return None


def _configured_project_types(repo_projects: Sequence[Project | object]) -> list[str]:
    return sorted(
        {
            label
            for project in repo_projects
            if (label := _project_type_label(project)) is not None
        }
    )


def _docs_systems(repo_projects: Sequence[Project | object]) -> list[str]:
    docs_systems: set[str] = set()
    for project in repo_projects:
        if not getattr(project, "docs_enabled", False):
            continue
        docs_systems.add(getattr(project, "docs_system", None) or "enabled")
    return sorted(docs_systems)


def _sanctioned_override_files(repo_projects: Sequence[Project]) -> list[str]:
    overrides: list[str] = []
    if any(isinstance(project, GradleProject) for project in repo_projects):
        overrides.extend(["build.extra.gradle.kts", "settings.local.gradle.kts"])
    if any(isinstance(project, PythonProject) for project in repo_projects):
        overrides.append("pyproject.extra.toml")
    if any(
        isinstance(project, PythonProject) and project.docs_enabled and project.docs_system == "mkdocs"
        for project in repo_projects
    ):
        overrides.append("mkdocs.extra.yml")
    return overrides


def _reference_docs(repo_root: Path) -> list[str]:
    return [name for name in _REFERENCE_DOC_FILENAMES if (repo_root / name).is_file()]


def render_repo_agents_facts_block(config: Config, repo_root: Path, repo_projects: Sequence[Project]) -> str:
    canonical_target = _canonical_target(config, repo_root, repo_projects)
    fact_lines = [
        AGENTS_MANAGED_FACTS_BEGIN,
        "## Generated Facts",
        "",
        "- Workspace config source of truth: `root.clj` at the workspace root.",
        "- Use `dev where` from this repo to confirm the inferred workspace, repo, and project context.",
        (
            f"- Canonical repo target: `{canonical_target}`. Useful entrypoints: "
            f"`dev project show {canonical_target}`, `dev build {canonical_target}`, `dev check {canonical_target}`."
        ),
        f"- Setup-managed files are regenerated with `dev setup {canonical_target}`; avoid hand-editing stamped generated files.",
    ]

    overrides = _sanctioned_override_files(repo_projects)
    if overrides:
        override_list = ", ".join(f"`{path}`" for path in overrides)
        fact_lines.append(f"- Sanctioned override files in this repo: {override_list}.")

    project_types = _configured_project_types(repo_projects)
    docs_systems = _docs_systems(repo_projects)
    if project_types and docs_systems:
        fact_lines.append(
            f"- Configured project types: {', '.join(f'`{project_type}`' for project_type in project_types)}. "
            f"Docs: {', '.join(f'`{docs_system}`' for docs_system in docs_systems)}."
        )
    elif project_types:
        fact_lines.append(
            f"- Configured project types: {', '.join(f'`{project_type}`' for project_type in project_types)}."
        )

    reference_docs = _reference_docs(repo_root)
    if reference_docs:
        fact_lines.append(
            f"- Repo reference docs: {', '.join(f'`{doc_name}`' for doc_name in reference_docs)}."
        )

    fact_lines.append(AGENTS_MANAGED_FACTS_END)
    return _normalize_markdown("\n".join(fact_lines))


def render_repo_agents_starter(config: Config, repo_root: Path, repo_projects: Sequence[Project]) -> str:
    facts_block = render_repo_agents_facts_block(config, repo_root, repo_projects).rstrip("\n")
    return _normalize_markdown(
        "\n".join(
            [
                "# AGENTS",
                "",
                "Add repo-specific instructions above or below the managed facts block. "
                "Keep manual guidance outside the generated markers.",
                "",
                facts_block,
            ]
        )
    )


def _replace_managed_facts_block(existing_text: str, generated_block: str, *, path: Path) -> str | None:
    has_begin = AGENTS_MANAGED_FACTS_BEGIN in existing_text
    has_end = AGENTS_MANAGED_FACTS_END in existing_text

    if not has_begin and not has_end:
        return None
    if has_begin != has_end:
        warning(f"Skipping malformed AGENTS.md markers in {path}")
        return None

    pattern = re.compile(
        re.escape(AGENTS_MANAGED_FACTS_BEGIN) + r".*?" + re.escape(AGENTS_MANAGED_FACTS_END),
        re.DOTALL,
    )
    updated_text, replaced_count = pattern.subn(generated_block.rstrip("\n"), existing_text, count=1)
    if replaced_count != 1:
        warning(f"Skipping malformed AGENTS.md managed block in {path}")
        return None
    return _normalize_markdown(updated_text)


def write_repo_agents_file(config: Config, repo_root: Path, repo_projects: Sequence[Project]) -> bool:
    agents_path = repo_root / "AGENTS.md"
    generated_block = render_repo_agents_facts_block(config, repo_root, repo_projects)

    if agents_path.exists():
        existing_text = agents_path.read_text(encoding="utf-8")
        updated_text = _replace_managed_facts_block(existing_text, generated_block, path=agents_path)
        if updated_text is None or updated_text == _normalize_markdown(existing_text):
            return False
        dev.io.write_text_file(agents_path, updated_text)
        return True

    dev.io.write_text_file(agents_path, render_repo_agents_starter(config, repo_root, repo_projects))
    return True
