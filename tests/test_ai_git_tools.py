from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

from openai.types.responses import ResponseFunctionToolCall

from dev.ai import (
    _agent_tools,
    _render_readme_prompt_template,
    agent_call,
    is_allowed_git_tool_command,
    run_safe_git_tool_command,
    suggest_commit_name,
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


def test_agent_call_raises_runtime_error_for_unexpected_finish_reason(
    tmp_path: Path,
) -> None:
    message = SimpleNamespace(content="done", tool_calls=None)
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")]),
    ]

    class FakeCompletions:
        def __init__(self, queued_responses: list[SimpleNamespace]) -> None:
            self._queued_responses = queued_responses

        def create(self, **_kwargs: object) -> SimpleNamespace:
            assert self._queued_responses
            return self._queued_responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(responses)))

    try:
        agent_call(tmp_path, "task", client=client)
        assert False, "Expected agent_call to raise RuntimeError"
    except RuntimeError as ex:
        assert "unexpected finish_reason='stop'" in str(ex)


def test_agent_call_raises_runtime_error_after_max_steps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("dev.ai.AGENT_CALL_MAX_STEPS", 2)

    def make_tool_call(call_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            type="function",
            id=call_id,
            function=SimpleNamespace(
                name="request_to_developer",
                arguments=json.dumps(
                    {
                        "paths": ["README.md"],
                        "task_or_question": "inspect",
                    }
                ),
            ),
        )

    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr("dev.ai.answer_about_file", lambda *_args, **_kwargs: "answer")

    looping_message = SimpleNamespace(content=None, tool_calls=[make_tool_call("call-1")])
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=looping_message, finish_reason="tool_calls")]),
        SimpleNamespace(choices=[SimpleNamespace(message=looping_message, finish_reason="tool_calls")]),
    ]

    class FakeCompletions:
        def __init__(self, queued_responses: list[SimpleNamespace]) -> None:
            self._queued_responses = queued_responses

        def create(self, **_kwargs: object) -> SimpleNamespace:
            assert self._queued_responses
            return self._queued_responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(responses)))

    try:
        agent_call(tmp_path, "task", client=client)
        assert False, "Expected agent_call to raise RuntimeError"
    except RuntimeError as ex:
        assert "exceeded maximum tool-call steps (2)" in str(ex)


def test_agent_call_rejects_paths_that_escape_repo_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    outside_file = tmp_path.parent / "outside-secret.txt"
    outside_file.write_text("secret\n", encoding="utf-8")

    def fail_answer_about_file(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("answer_about_file should not be called for escaped paths")

    monkeypatch.setattr("dev.ai.answer_about_file", fail_answer_about_file)

    captured_messages: list[object] = []

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
                    "paths": [f"../{outside_file.name}"],
                    "task_or_question": "inspect",
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
                    "result": "done",
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

        def create(self, **kwargs: object) -> SimpleNamespace:
            messages = kwargs.get("messages")
            if messages is not None:
                assert isinstance(messages, list)
                captured_messages.append(list(messages))
            assert self._queued_responses
            return self._queued_responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(responses)))

    assert agent_call(tmp_path, "task", client=client) == "done"

    second_request_messages = captured_messages[1]
    assert isinstance(second_request_messages, list)
    tool_message = second_request_messages[-1]
    assert tool_message["role"] == "tool"
    assert "Paths escape repository root" in tool_message["content"]


def test_agent_call_rejects_symlink_paths_that_resolve_outside_repo_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    outside_dir = tmp_path.parent / "outside-dir"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret\n", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside_file)

    def fail_answer_about_file(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("answer_about_file should not be called for escaped paths")

    monkeypatch.setattr("dev.ai.answer_about_file", fail_answer_about_file)

    captured_messages: list[object] = []

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
                    "paths": ["link.txt"],
                    "task_or_question": "inspect",
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
                    "result": "done",
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

        def create(self, **kwargs: object) -> SimpleNamespace:
            messages = kwargs.get("messages")
            if messages is not None:
                assert isinstance(messages, list)
                captured_messages.append(list(messages))
            assert self._queued_responses
            return self._queued_responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(responses)))

    assert agent_call(tmp_path, "task", client=client) == "done"

    second_request_messages = captured_messages[1]
    assert isinstance(second_request_messages, list)
    tool_message = second_request_messages[-1]
    assert tool_message["role"] == "tool"
    assert "Paths escape repository root" in tool_message["content"]


def test_agent_call_converts_invalid_tool_json_into_tool_error(
    tmp_path: Path,
) -> None:
    captured_messages: list[object] = []

    first_message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                type="function",
                id="call-1",
                function=SimpleNamespace(name="request_to_developer", arguments="{not valid json"),
            )
        ],
    )
    second_message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                type="function",
                id="call-2",
                function=SimpleNamespace(name="answer", arguments=json.dumps({"result": "done"})),
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

        def create(self, **kwargs: object) -> SimpleNamespace:
            messages = kwargs.get("messages")
            if messages is not None:
                assert isinstance(messages, list)
                captured_messages.append(list(messages))
            assert self._queued_responses
            return self._queued_responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(responses)))

    assert agent_call(tmp_path, "task", client=client) == "done"

    second_request_messages = captured_messages[1]
    assert isinstance(second_request_messages, list)
    tool_message = second_request_messages[-1]
    assert tool_message["role"] == "tool"
    assert "Invalid JSON tool arguments for request_to_developer" in tool_message["content"]


def test_agent_call_rejects_known_binary_files_before_reading(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "demo.jar").write_bytes(b"PK\x03\x04jar-bytes")

    def fail_answer_about_file(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("answer_about_file should not be called for known binary files")

    monkeypatch.setattr("dev.ai.answer_about_file", fail_answer_about_file)

    captured_messages: list[object] = []

    first_message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                type="function",
                id="call-1",
                function=SimpleNamespace(
                    name="request_to_developer",
                    arguments=json.dumps({"paths": ["demo.jar"], "task_or_question": "inspect"}),
                ),
            )
        ],
    )
    second_message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                type="function",
                id="call-2",
                function=SimpleNamespace(name="answer", arguments=json.dumps({"result": "done"})),
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

        def create(self, **kwargs: object) -> SimpleNamespace:
            messages = kwargs.get("messages")
            if messages is not None:
                assert isinstance(messages, list)
                captured_messages.append(list(messages))
            assert self._queued_responses
            return self._queued_responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(responses)))

    assert agent_call(tmp_path, "task", client=client) == "done"

    second_request_messages = captured_messages[1]
    assert isinstance(second_request_messages, list)
    tool_message = second_request_messages[-1]
    assert tool_message["role"] == "tool"
    assert "Files are not text and cannot be read safely" in tool_message["content"]


def test_agent_call_reports_decode_errors_for_unknown_binary_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "mystery.binx").write_bytes(b"\xff\xfe\xfa\xfb")

    captured_messages: list[object] = []

    first_message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                type="function",
                id="call-1",
                function=SimpleNamespace(
                    name="request_to_developer",
                    arguments=json.dumps({"paths": ["mystery.binx"], "task_or_question": "inspect"}),
                ),
            )
        ],
    )
    second_message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                type="function",
                id="call-2",
                function=SimpleNamespace(name="answer", arguments=json.dumps({"result": "done"})),
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

        def create(self, **kwargs: object) -> SimpleNamespace:
            messages = kwargs.get("messages")
            if messages is not None:
                assert isinstance(messages, list)
                captured_messages.append(list(messages))
            assert self._queued_responses
            return self._queued_responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(responses)))

    assert agent_call(tmp_path, "task", client=client) == "done"

    second_request_messages = captured_messages[1]
    assert isinstance(second_request_messages, list)
    tool_message = second_request_messages[-1]
    assert tool_message["role"] == "tool"
    assert "not valid UTF-8 text" in tool_message["content"]


def test_agent_call_processes_other_tool_calls_before_returning_answer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subordinate_calls: list[tuple[list[Path], str]] = []

    def fake_answer_about_file(paths: list[Path], question: str, **_kwargs: object) -> str:
        subordinate_calls.append((paths, question))
        return "subordinate answer"

    monkeypatch.setattr("dev.ai.answer_about_file", fake_answer_about_file)

    first_message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                type="function",
                id="call-1",
                function=SimpleNamespace(name="answer", arguments=json.dumps({"result": "done"})),
            ),
            SimpleNamespace(
                type="function",
                id="call-2",
                function=SimpleNamespace(
                    name="request_to_developer",
                    arguments=json.dumps({"paths": ["README.md"], "task_or_question": "inspect"}),
                ),
            ),
        ],
    )
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=first_message, finish_reason="tool_calls")]),
    ]

    class FakeCompletions:
        def __init__(self, queued_responses: list[SimpleNamespace]) -> None:
            self._queued_responses = queued_responses

        def create(self, **_kwargs: object) -> SimpleNamespace:
            assert self._queued_responses
            return self._queued_responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(responses)))

    assert agent_call(tmp_path, "task", client=client) == "done"
    assert len(subordinate_calls) == 1
    assert subordinate_calls[0][0] == [tmp_path / "README.md"]
    assert subordinate_calls[0][1] == "inspect"


def test_suggest_commit_name_raises_when_model_never_returns_final_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    queued_responses = [
        SimpleNamespace(
            id=f"resp-{idx}",
            output=[
                ResponseFunctionToolCall(
                    arguments=json.dumps({"command": "git status --short"}),
                    call_id=f"call-{idx}",
                    name="run_git_command",
                    type="function_call",
                    id=f"fc-{idx}",
                    status="completed",
                )
            ],
            output_text="",
        )
        for idx in range(9)
    ]

    class FakeResponses:
        def __init__(self, responses: list[SimpleNamespace]) -> None:
            self._responses = responses

        def create(self, **_kwargs: object) -> SimpleNamespace:
            assert self._responses
            return self._responses.pop(0)

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            del api_key
            self.responses = FakeResponses(queued_responses)

    monkeypatch.setattr("dev.ai.openai.Client", FakeClient)

    try:
        suggest_commit_name.__wrapped__(  # type: ignore[attr-defined]
            "README.md",
            api_key="dummy",
            repo_path=tmp_path,
        )
        assert False, "Expected suggest_commit_name to raise RuntimeError"
    except RuntimeError as ex:
        assert "did not return a final commit message after 8 tool rounds" in str(ex)
