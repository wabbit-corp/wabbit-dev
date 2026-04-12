from __future__ import annotations

from dev.template_assets import repo_template_path


def test_python_gitignore_template_includes_standard_qa_artifacts() -> None:
    template_path = repo_template_path("python-files", "gitignore.jinja2")
    content = template_path.read_text(encoding="utf-8")

    assert ".mypy_cache/" in content
    assert ".ruff_cache/" in content
    assert ".hypothesis/" in content
    assert "coverage.xml" in content
