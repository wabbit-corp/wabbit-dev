from __future__ import annotations

from pathlib import Path

from dev.changelog import (
    find_markdown_changelog,
    markdown_changelog_section_for_version,
    render_markdown_section_as_plain_text,
    resolve_intellij_change_notes,
    resolve_repo_changelog_change_notes,
)


def test_find_markdown_changelog_uses_repo_root_only(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    project_path = repo_root / "plugin"
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    assert find_markdown_changelog(repo_root) is None


def test_markdown_changelog_section_for_version_requires_standard_heading() -> None:
    changelog_text = "\n".join(
        [
            "# Changelog",
            "",
            "## [0.1.0] - 2026-04-13",
            "",
            "Non-standard heading.",
            "",
        ]
    )

    assert markdown_changelog_section_for_version(changelog_text, "0.1.0") is None


def test_resolve_repo_changelog_change_notes_uses_standard_repo_section(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "CHANGELOG.md").write_text(
        "\n".join(
            [
                "# Changelog",
                "",
                "## 0.1.0 - 2026-04-13",
                "",
                "Initial public release.",
                "",
                "- Adds IDE integration.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    notes = resolve_repo_changelog_change_notes(repo_root=repo_root, project_version="0.1.0")

    assert notes == "Initial public release.\n\n- Adds IDE integration."


def test_resolve_intellij_change_notes_falls_back_to_configured_override(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    notes = resolve_intellij_change_notes(
        repo_root=repo_root,
        project_version="0.1.0",
        configured_change_notes="Manual fallback.",
    )

    assert notes == "Manual fallback."


def test_render_markdown_section_as_plain_text_strips_inline_markdown() -> None:
    section = markdown_changelog_section_for_version(
        "\n".join(
            [
                "# Changelog",
                "",
                "## 0.1.0 - 2026-04-13",
                "",
                "Use **bold**, `code`, and [docs](https://example.com).",
                "",
            ]
        ),
        "0.1.0",
    )

    assert section is not None
    assert render_markdown_section_as_plain_text(section) == "Use bold, code, and docs (https://example.com)."
