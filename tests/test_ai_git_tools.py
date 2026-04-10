from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import openai
import pytest
from openai.types.chat import (
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from openai.types.responses import ResponseFunctionToolCall

from dev.ai import (
    OpenAIChatClientLike,
    agent_call,
    agent_tools,
    is_allowed_git_tool_command,
    render_readme_prompt_template,
    run_safe_git_tool_command,
    suggest_commit_name,
)
from dev.json_types import JSONValue


@dataclass
class FakeMessage:
    content: str | None
    tool_calls: list[ChatCompletionMessageFunctionToolCall] | None


@dataclass
class FakeChoice:
    message: FakeMessage
    finish_reason: str | None


@dataclass
class FakeChatResponse:
    choices: list[FakeChoice]


class FakeCompletions:
    def __init__(
        self,
        queued_responses: list[FakeChatResponse],
        *,
        captured_messages: list[list[ChatCompletionMessageParam]] | None = None,
    ) -> None:
        self._queued_responses = queued_responses
        self._captured_messages = captured_messages

    def create(
        self,
        *,
        messages: list[ChatCompletionMessageParam],
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        tools: list[ChatCompletionToolParam] | None = None,
        tool_choice: str | None = None,
    ) -> FakeChatResponse:
        del model, max_tokens, temperature, top_p, tools, tool_choice
        if self._captured_messages is not None:
            self._captured_messages.append(list(messages))
        assert self._queued_responses
        return self._queued_responses.pop(0)


@dataclass
class FakeChatNamespace:
    completions: FakeCompletions


@dataclass
class FakeChatClient:
    chat: FakeChatNamespace


@dataclass
class FakeResponsesOutput:
    id: str
    output: list[ResponseFunctionToolCall]
    output_text: str


class FakeResponsesApi:
    def __init__(self, responses: list[FakeResponsesOutput]) -> None:
        self._responses = responses

    def create(self, **_kwargs: JSONValue) -> FakeResponsesOutput:
        assert self._responses
        return self._responses.pop(0)


def _make_tool_call(
    call_id: str,
    name: str,
    arguments: dict[str, JSONValue],
) -> ChatCompletionMessageFunctionToolCall:
    return ChatCompletionMessageFunctionToolCall(
        id=call_id,
        type="function",
        function={"name": name, "arguments": json.dumps(arguments)},
    )


def _make_response(message: FakeMessage, finish_reason: str) -> FakeChatResponse:
    return FakeChatResponse(choices=[FakeChoice(message=message, finish_reason=finish_reason)])


def _make_client(
    responses: list[FakeChatResponse],
    *,
    captured_messages: list[list[ChatCompletionMessageParam]] | None = None,
) -> FakeChatClient:
    return FakeChatClient(chat=FakeChatNamespace(completions=FakeCompletions(responses, captured_messages=captured_messages)))


def _last_tool_message_content(messages: list[ChatCompletionMessageParam]) -> str:
    tool_message = messages[-1]
    assert isinstance(tool_message, dict)
    assert tool_message.get("role") == "tool"
    content = tool_message.get("content")
    assert isinstance(content, str)
    return content


def _fail_answer_about_file(
    paths: list[Path],
    question: str,
    /,
    api_key: str | None = None,
    client: openai.Client | OpenAIChatClientLike | None = None,
) -> str:
    del paths, question, api_key, client
    raise AssertionError("answer_about_file should not be called")


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


def test_render_readme_prompt_template_renders_company_contact_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    rendered = render_readme_prompt_template(
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
    tools = agent_tools()
    request_tool = next(tool for tool in tools if tool["function"]["name"] == "request_to_developer")
    parameters = request_tool["function"].get("parameters")
    assert isinstance(parameters, dict)
    required = parameters.get("required")
    assert required == ["paths", "task_or_question"]


def test_agent_call_logs_only_metadata_for_prompt_and_tool_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / "README.md").write_text("TOP SECRET FILE CONTENT\n", encoding="utf-8")

    def fake_answer_about_file(
        paths: list[Path],
        question: str,
        /,
        api_key: str | None = None,
        client: openai.Client | OpenAIChatClientLike | None = None,
    ) -> str:
        del paths, question, api_key, client
        return "SUBORDINATE SECRET RESPONSE"

    monkeypatch.setattr("dev.ai.answer_about_file", fake_answer_about_file)

    first_message = FakeMessage(
        content=None,
        tool_calls=[
            _make_tool_call(
                "call-1",
                "request_to_developer",
                {
                    "paths": ["README.md"],
                    "task_or_question": "USER SECRET TASK",
                },
            )
        ],
    )
    second_message = FakeMessage(
        content=None,
        tool_calls=[
            _make_tool_call(
                "call-2",
                "answer",
                {
                    "result": "FINAL SECRET RESULT",
                },
            )
        ],
    )

    client = _make_client(
        [
            _make_response(first_message, "tool_calls"),
            _make_response(second_message, "tool_calls"),
        ]
    )

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


def test_agent_call_raises_runtime_error_for_unexpected_finish_reason(tmp_path: Path) -> None:
    message = FakeMessage(content="done", tool_calls=None)
    client = _make_client([_make_response(message, "stop")])

    try:
        agent_call(tmp_path, "task", client=client)
        assert False, "Expected agent_call to raise RuntimeError"
    except RuntimeError as ex:
        assert "unexpected finish_reason='stop'" in str(ex)


def test_agent_call_raises_runtime_error_after_max_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("dev.ai.AGENT_CALL_MAX_STEPS", 2)

    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    def fake_answer_about_file(
        paths: list[Path],
        question: str,
        /,
        api_key: str | None = None,
        client: openai.Client | OpenAIChatClientLike | None = None,
    ) -> str:
        del paths, question, api_key, client
        return "answer"

    monkeypatch.setattr("dev.ai.answer_about_file", fake_answer_about_file)

    looping_message = FakeMessage(
        content=None,
        tool_calls=[
            _make_tool_call(
                "call-1",
                "request_to_developer",
                {
                    "paths": ["README.md"],
                    "task_or_question": "inspect",
                },
            )
        ],
    )
    client = _make_client(
        [
            _make_response(looping_message, "tool_calls"),
            _make_response(looping_message, "tool_calls"),
        ]
    )

    try:
        agent_call(tmp_path, "task", client=client)
        assert False, "Expected agent_call to raise RuntimeError"
    except RuntimeError as ex:
        assert "exceeded maximum tool-call steps (2)" in str(ex)


def test_agent_call_rejects_paths_that_escape_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    outside_file = tmp_path.parent / "outside-secret.txt"
    outside_file.write_text("secret\n", encoding="utf-8")

    monkeypatch.setattr("dev.ai.answer_about_file", _fail_answer_about_file)

    captured_messages: list[list[ChatCompletionMessageParam]] = []
    client = _make_client(
        [
            _make_response(
                FakeMessage(
                    content=None,
                    tool_calls=[
                        _make_tool_call(
                            "call-1",
                            "request_to_developer",
                            {
                                "paths": [f"../{outside_file.name}"],
                                "task_or_question": "inspect",
                            },
                        )
                    ],
                ),
                "tool_calls",
            ),
            _make_response(
                FakeMessage(
                    content=None,
                    tool_calls=[_make_tool_call("call-2", "answer", {"result": "done"})],
                ),
                "tool_calls",
            ),
        ],
        captured_messages=captured_messages,
    )

    assert agent_call(tmp_path, "task", client=client) == "done"
    assert "Paths escape repository root" in _last_tool_message_content(captured_messages[1])


def test_agent_call_rejects_symlink_paths_that_resolve_outside_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside_dir = tmp_path.parent / "outside-dir"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret\n", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside_file)

    monkeypatch.setattr("dev.ai.answer_about_file", _fail_answer_about_file)

    captured_messages: list[list[ChatCompletionMessageParam]] = []
    client = _make_client(
        [
            _make_response(
                FakeMessage(
                    content=None,
                    tool_calls=[
                        _make_tool_call(
                            "call-1",
                            "request_to_developer",
                            {
                                "paths": ["link.txt"],
                                "task_or_question": "inspect",
                            },
                        )
                    ],
                ),
                "tool_calls",
            ),
            _make_response(
                FakeMessage(
                    content=None,
                    tool_calls=[_make_tool_call("call-2", "answer", {"result": "done"})],
                ),
                "tool_calls",
            ),
        ],
        captured_messages=captured_messages,
    )

    assert agent_call(tmp_path, "task", client=client) == "done"
    assert "Paths escape repository root" in _last_tool_message_content(captured_messages[1])


def test_agent_call_converts_invalid_tool_json_into_tool_error(tmp_path: Path) -> None:
    captured_messages: list[list[ChatCompletionMessageParam]] = []
    invalid_json_call = ChatCompletionMessageFunctionToolCall(
        id="call-1",
        type="function",
        function={"name": "request_to_developer", "arguments": "{not valid json"},
    )
    client = _make_client(
        [
            _make_response(FakeMessage(content=None, tool_calls=[invalid_json_call]), "tool_calls"),
            _make_response(
                FakeMessage(
                    content=None,
                    tool_calls=[_make_tool_call("call-2", "answer", {"result": "done"})],
                ),
                "tool_calls",
            ),
        ],
        captured_messages=captured_messages,
    )

    assert agent_call(tmp_path, "task", client=client) == "done"
    assert "Invalid JSON tool arguments for request_to_developer" in _last_tool_message_content(captured_messages[1])


def test_agent_call_rejects_known_binary_files_before_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "demo.jar").write_bytes(b"PK\x03\x04jar-bytes")
    monkeypatch.setattr("dev.ai.answer_about_file", _fail_answer_about_file)

    captured_messages: list[list[ChatCompletionMessageParam]] = []
    client = _make_client(
        [
            _make_response(
                FakeMessage(
                    content=None,
                    tool_calls=[
                        _make_tool_call(
                            "call-1",
                            "request_to_developer",
                            {"paths": ["demo.jar"], "task_or_question": "inspect"},
                        )
                    ],
                ),
                "tool_calls",
            ),
            _make_response(
                FakeMessage(
                    content=None,
                    tool_calls=[_make_tool_call("call-2", "answer", {"result": "done"})],
                ),
                "tool_calls",
            ),
        ],
        captured_messages=captured_messages,
    )

    assert agent_call(tmp_path, "task", client=client) == "done"
    assert "Files are not text and cannot be read safely" in _last_tool_message_content(captured_messages[1])


def test_agent_call_reports_decode_errors_for_unknown_binary_files(tmp_path: Path) -> None:
    (tmp_path / "mystery.binx").write_bytes(b"\xff\xfe\xfa\xfb")

    captured_messages: list[list[ChatCompletionMessageParam]] = []
    client = _make_client(
        [
            _make_response(
                FakeMessage(
                    content=None,
                    tool_calls=[
                        _make_tool_call(
                            "call-1",
                            "request_to_developer",
                            {"paths": ["mystery.binx"], "task_or_question": "inspect"},
                        )
                    ],
                ),
                "tool_calls",
            ),
            _make_response(
                FakeMessage(
                    content=None,
                    tool_calls=[_make_tool_call("call-2", "answer", {"result": "done"})],
                ),
                "tool_calls",
            ),
        ],
        captured_messages=captured_messages,
    )

    assert agent_call(tmp_path, "task", client=client) == "done"
    assert "not valid UTF-8 text" in _last_tool_message_content(captured_messages[1])


def test_agent_call_processes_other_tool_calls_before_returning_answer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subordinate_calls: list[tuple[list[Path], str]] = []

    def fake_answer_about_file(
        paths: list[Path],
        question: str,
        /,
        api_key: str | None = None,
        client: openai.Client | OpenAIChatClientLike | None = None,
    ) -> str:
        del api_key, client
        subordinate_calls.append((paths, question))
        return "subordinate answer"

    monkeypatch.setattr("dev.ai.answer_about_file", fake_answer_about_file)

    first_message = FakeMessage(
        content=None,
        tool_calls=[
            _make_tool_call("call-1", "answer", {"result": "done"}),
            _make_tool_call(
                "call-2",
                "request_to_developer",
                {"paths": ["README.md"], "task_or_question": "inspect"},
            ),
        ],
    )
    client = _make_client([_make_response(first_message, "tool_calls")])

    assert agent_call(tmp_path, "task", client=client) == "done"
    assert len(subordinate_calls) == 1
    assert subordinate_calls[0][0] == [tmp_path / "README.md"]
    assert subordinate_calls[0][1] == "inspect"


def test_suggest_commit_name_raises_when_model_never_returns_final_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    queued_responses = [
        FakeResponsesOutput(
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

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            del api_key
            self.responses = FakeResponsesApi(queued_responses)

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
