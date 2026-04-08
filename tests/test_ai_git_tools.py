from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

from dev.ai import (
    _agent_tools,
    _render_readme_prompt_template,
    agent_call,
    is_allowed_git_tool_command,
    run_safe_git_tool_command,
)


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


def test_agent_tools_require_task_or_question() -> None:
    tools = _agent_tools()
    request_tool = next(tool for tool in tools if tool["function"]["name"] == "request_to_developer")

    required = request_tool["function"]["parameters"]["required"]

    assert required == ["paths", "task_or_question"]


def test_agent_call_logs_only_metadata_for_prompt_and_tool_results(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    (tmp_path / "README.md").write_text("TOP SECRET FILE CONTENT\n", encoding="utf-8")

    def fake_answer_about_file(*_args: object, **_kwargs: object) -> str:
        return "SUBORDINATE SECRET RESPONSE"

    monkeypatch.setattr("dev.ai.answer_about_file", fake_answer_about_file)

    def make_tool_call(call_id: str, name: str, arguments: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            type="function",
            id=call_id,
            function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
        )

    first_message = SimpleNamespace(
        content=None,
        tool_calls=[
            make_tool_call(
                "call-1",
                "request_to_developer",
                {
                    "paths": ["README.md"],
                    "task_or_question": "USER SECRET TASK",
                },
            )
        ],
    )
    second_message = SimpleNamespace(
        content=None,
        tool_calls=[
            make_tool_call(
                "call-2",
                "answer",
                {
                    "result": "FINAL SECRET RESULT",
                },
            )
        ],
    )

    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=first_message, finish_reason="tool_calls")]),
        SimpleNamespace(choices=[SimpleNamespace(message=second_message, finish_reason="tool_calls")]),
    ]

    class FakeCompletions:
        def __init__(self, queued_responses: list[SimpleNamespace]) -> None:
            self._queued_responses = queued_responses

        def create(self, **_kwargs: object) -> SimpleNamespace:
            assert self._queued_responses
            return self._queued_responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(responses)))

    caplog.set_level(logging.INFO)

    result = agent_call(tmp_path, "USER SECRET TASK", client=client)

    assert result == "FINAL SECRET RESULT"
    assert "USER SECRET TASK" not in caplog.text
    assert "SUBORDINATE SECRET RESPONSE" not in caplog.text
    assert "FINAL SECRET RESULT" not in caplog.text
    assert "TOP SECRET FILE CONTENT" not in caplog.text
    assert "README.md" not in caplog.text
    assert "Starting agent_call with file_count=1" in caplog.text
    assert "Calling tool request_to_developer with paths_count=1" in caplog.text
    assert "Tool request_to_developer returned string chars=27" in caplog.text
