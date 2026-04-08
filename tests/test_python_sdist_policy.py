from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_python_sdist_policy_includes_standard_release_support_files(tmp_path: Path) -> None:
    from dev.python_sdist_policy import python_sdist_include_entries

    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")
    (tmp_path / "mkdocs.yml").write_text("site_name: demo\n", encoding="utf-8")
    (tmp_path / "dev.py").write_text("print('demo')\n", encoding="utf-8")
    (tmp_path / ".banner.png").write_bytes(b"png")
    (tmp_path / ".checkignore").write_text("tmp\n", encoding="utf-8")
    (tmp_path / ".codespell-ignore-words.txt").write_text("codex\n", encoding="utf-8")
    (tmp_path / ".entropyignore").write_text("entropy\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("dist/\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "release-checklist").mkdir()
    (tmp_path / "docs-research").mkdir()

    include_paths = [entry.path for entry in python_sdist_include_entries(tmp_path)]

    assert "README.md" in include_paths
    assert "CHANGELOG.md" in include_paths
    assert "mkdocs.yml" in include_paths
    assert "dev.py" in include_paths
    assert ".banner.png" in include_paths
    assert ".checkignore" in include_paths
    assert ".codespell-ignore-words.txt" in include_paths
    assert ".entropyignore" in include_paths
    assert "docs" in include_paths
    assert "scripts" in include_paths
    assert "tests" in include_paths
    assert "release-checklist" in include_paths
    assert ".gitignore" not in include_paths
    assert "docs-research" not in include_paths


def test_python_sdist_policy_excludes_local_and_workspace_noise(tmp_path: Path) -> None:
    from dev.python_sdist_policy import python_check_manifest_ignore_patterns, python_sdist_exclude_patterns

    exclude_patterns = python_sdist_exclude_patterns(tmp_path)
    check_manifest_ignore_patterns = python_check_manifest_ignore_patterns(tmp_path)

    assert ".llm/**" in exclude_patterns
    assert "docs-research/**" in exclude_patterns
    assert "tmp-*/**" in exclude_patterns
    assert "site/**" in exclude_patterns

    assert ".github/**" in check_manifest_ignore_patterns
    assert ".gitignore" in check_manifest_ignore_patterns
    assert ".llm/**" in check_manifest_ignore_patterns


def _toml_string_array(items: list[str]) -> str:
    if not items:
        return "[]"
    lines = ["["]
    for item in items:
        lines.append(f'    "{item}",')
    lines.append("]")
    return "\n".join(lines)


def _toml_inline_table_array(entries: list[object]) -> str:
    if not entries:
        return "[]"
    lines = ["["]
    for entry in entries:
        path = getattr(entry, "path")
        formats = getattr(entry, "formats")
        lines.append(f'    {{ path = "{path}", format = {_toml_string_array(list(formats))} }},')
    lines.append("]")
    return "\n".join(lines)


def test_check_manifest_passes_with_generated_pyproject_policy_and_no_manifest(tmp_path: Path) -> None:
    from dev.python_sdist_policy import (
        python_check_manifest_ignore_patterns,
        python_sdist_exclude_patterns,
        python_sdist_include_entries,
    )

    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("__version__ = '0.1.0'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")
    (tmp_path / "LICENSE.md").write_text("license\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# docs\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "release.py").write_text("print('release')\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (tmp_path / "docs-research").mkdir()
    (tmp_path / "docs-research" / "notes.md").write_text("# notes\n", encoding="utf-8")
    (tmp_path / ".llm").mkdir()
    (tmp_path / ".llm" / "prompt.md").write_text("# prompt\n", encoding="utf-8")
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("<h1>site</h1>\n", encoding="utf-8")

    include_entries = python_sdist_include_entries(tmp_path)
    exclude_patterns = python_sdist_exclude_patterns(tmp_path)
    check_manifest_ignore_patterns = python_check_manifest_ignore_patterns(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.poetry]",
                'name = "demo"',
                'version = "0.1.0"',
                'description = "Demo"',
                'authors = ["Dev <dev@example.com>"]',
                'license = "MIT"',
                'readme = "README.md"',
                'packages = [{ include = "demo" }]',
                f"include = {_toml_inline_table_array(include_entries)}",
                f"exclude = {_toml_string_array(exclude_patterns)}",
                "",
                "[tool.check-manifest]",
                f"ignore = {_toml_string_array(check_manifest_ignore_patterns)}",
                "",
                "[tool.poetry.dependencies]",
                'python = ">=3.12"',
                "",
                "[build-system]",
                'requires = ["poetry-core>=1.7.0"]',
                'build-backend = "poetry.core.masonry.api"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [sys.executable, "-m", "check_manifest"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert "no MANIFEST.in found" not in combined_output
    assert "missing from sdist" not in combined_output
