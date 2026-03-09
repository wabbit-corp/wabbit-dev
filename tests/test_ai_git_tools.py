from __future__ import annotations

import subprocess
from pathlib import Path

from dev.ai import _render_readme_prompt_template, is_allowed_git_tool_command, run_safe_git_tool_command


def test_is_allowed_git_tool_command_accepts_read_only_patterns() -> None:
    assert is_allowed_git_tool_command("git status --short")
    assert is_allowed_git_tool_command("git diff --staged --name-status")
    assert is_allowed_git_tool_command("git log --oneline -n 10")
    assert is_allowed_git_tool_command("git show HEAD --stat")


def test_is_allowed_git_tool_command_rejects_mutating_patterns() -> None:
    assert not is_allowed_git_tool_command("git add .")
    assert not is_allowed_git_tool_command("git commit -m test")
    assert not is_allowed_git_tool_command("rm -rf /")


def test_run_safe_git_tool_command_executes_read_only_command(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True, text=True)

    result = run_safe_git_tool_command("git status --short", repo_path=tmp_path)

    assert result["ok"] is True
    assert result["returncode"] == 0
    stdout = result["stdout"]
    assert isinstance(stdout, str)
    assert "README.md" in stdout


def test_run_safe_git_tool_command_rejects_disallowed_command(tmp_path: Path) -> None:
    result = run_safe_git_tool_command("git add .", repo_path=tmp_path)
    assert result["ok"] is False


def test_render_readme_prompt_template_renders_company_contact_values(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "root.clj").write_text(
        "\n".join(
            [
                '(default-company-email "legal@example.com")',
                '(default-company-legal-name "Example Legal Co")',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "root.private.clj").write_text('(github-token "dummy")\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rendered = _render_readme_prompt_template(
        "<notes>\n<<notes>>\n</notes>\n"
        "For commercial use, please contact <<company_legal_name>> "
        "(at <<legal_contact_email>>) for licensing terms.\n"
        "Literal placeholder: {{project-name}}\n"
        "Dependency: <<project_id>>\n",
        project_id="demo-lib",
        notes="Some notes",
    )

    assert "Some notes" in rendered
    assert "Example Legal Co" in rendered
    assert "legal@example.com" in rendered
    assert "{{project-name}}" in rendered
    assert "demo-lib" in rendered
