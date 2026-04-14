import hashlib
import json
import logging
import os
import re
import shlex
import subprocess
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn, Protocol

import jinja2
import openai
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
)
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses.function_tool_param import FunctionToolParam
from openai.types.responses.response_input_item_param import FunctionCallOutput
from openai.types.responses.response_input_param import ResponseInputParam
from openai.types.shared_params.reasoning import Reasoning

from dev.caching import DEFAULT_CACHE_DB_PATH, cache
from dev.commit_policy import ensure_semver_impact_line
from dev.config import load_config
from dev.file_properties import get_expected_file_properties
from dev.io import read_ignore_file, read_text_file, walk_files
from dev.json_types import JSONValue
from dev.json_utils import as_dict, as_list, as_string_list
from dev.template_assets import repo_template_path

# Keep this prompt aligned with AGENTS.md > Commit Message Policy.
SUGGEST_COMMIT_PROMPT = textwrap.dedent("""
I have made some changes to a repository.

Modified files:
```
{modified}
```

Please propose a commit message in plain text. Structure it like a normal commit message:
- A concise subject line.
- Optionally, one or more lines of explanation or context about the changes that can be **directly** inferred.

Finally, at the end of the commit message, explicitly include a line stating the recommended semantic version impact in the format:

    Semver Impact: MAJOR
    (or MINOR, or PATCH, or NONE)

**Important**:
1. **Public/Runtime code vs. Test/Dev changes**:
   - If the diff only changes test or dev dependencies (e.g., `testImplementation`,
     `devDependencies`, build config, docs, comments, etc.), assume **NONE** impact
     because it does not affect the public API.
   - If a library version is changed in runtime or compile scope from X.Y.Z to X'.Y'.Z', follow the standard rules:
     - If X' != X, it’s **MAJOR**.
     - Else if Y' != Y, it’s **MINOR**.
     - Else if Z' != Z, it’s **PATCH**.
   - If multiple libraries or parts of the code are changed, always pick the highest overall impact. For example:
     - If **any** change crosses a major boundary (X' != X), label the entire commit **MAJOR**.
     - Otherwise, if **any** change crosses a minor boundary (Y' != Y), label it **MINOR**.
     - Otherwise, if only patch-level changes are involved, label it **PATCH**.
   - Use **MAJOR** if something in the code itself clearly breaks backward compatibility (e.g. removing or renaming a public API).
   - Use **MINOR** if new functionality is added or if a library’s minor version changed (and it’s not strictly confined to test or dev).
   - Use **PATCH** if the only changes are bug fixes, docs, test updates, or a library patch-level change in runtime scope.
   - Use **NONE** if the changes are trivial (e.g. build config changes that do not affect published code, test/dev dependencies, doc-only updates, README updates, etc.).

2. **No speculation**:
   - Do not guess about side effects, backward compatibility concerns, or any hidden features. Only summarize what is visible from the diff.

3. **Output format**:
   - Your response must be a JSON object like:
     {
         "full_commit_message": "<your commit message here>"
     }
""").strip()

COMMITTING_MODEL = "gpt-5.4-mini"
CHAT_MODEL = "gpt-5-chat-latest"
README_PROMPT_TEMPLATE_ENV = jinja2.Environment(
    autoescape=False,
    keep_trailing_newline=True,
    undefined=jinja2.StrictUndefined,
    variable_start_string="<<",
    variable_end_string=">>",
)


GIT_TOOL_TIMEOUT_SECONDS = 15
GIT_TOOL_MAX_OUTPUT_CHARS = 12000
AGENT_CALL_MAX_STEPS = 1024
GIT_TOOL_ALLOWED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^git status(?: --short)?(?: --branch)?$"),
    re.compile(r"^git diff(?: --staged| --cached)?(?: --name-only| --name-status| --stat)?$"),
    re.compile(r"^git diff(?: --staged| --cached)? -- [A-Za-z0-9_./-]+$"),
    re.compile(r"^git log --oneline -n [1-9][0-9]?$"),
    re.compile(r"^git show [A-Za-z0-9^~._/-]+(?: --stat| --name-status)?$"),
    re.compile(r"^git rev-parse --abbrev-ref HEAD$"),
    re.compile(r"^git ls-files(?: --others --exclude-standard)?$"),
)


class ChatCompletionMessageLike(Protocol):
    @property
    def content(self) -> str | None: ...

    @property
    def tool_calls(self) -> Sequence[ChatCompletionMessageFunctionToolCall] | None: ...


class ChatCompletionChoiceLike(Protocol):
    @property
    def message(self) -> ChatCompletionMessageLike: ...

    @property
    def finish_reason(self) -> str | None: ...


class ChatCompletionResponseLike(Protocol):
    @property
    def choices(self) -> list[ChatCompletionChoiceLike]: ...


class ChatCompletionsLike(Protocol):
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
    ) -> ChatCompletionResponseLike: ...


class ChatNamespaceLike(Protocol):
    @property
    def completions(self) -> ChatCompletionsLike: ...


class OpenAIChatClientLike(Protocol):
    @property
    def chat(self) -> ChatNamespaceLike: ...


def _normalize_tool_command(command: str) -> str:
    return " ".join(command.strip().split())


def _clip_tool_output(text: str) -> str:
    if len(text) <= GIT_TOOL_MAX_OUTPUT_CHARS:
        return text
    return text[: GIT_TOOL_MAX_OUTPUT_CHARS - 20] + "\n...[truncated]"


def is_allowed_git_tool_command(command: str) -> bool:
    normalized = _normalize_tool_command(command)
    return any(pattern.fullmatch(normalized) for pattern in GIT_TOOL_ALLOWED_PATTERNS)


def _required_readme_template_value(value: str | None, setting_name: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"{setting_name} is required to render the README prompt template")
    return value.strip()


def _render_readme_prompt_template(template_text: str, *, project_id: str, notes: str) -> str:
    config = load_config()
    template = README_PROMPT_TEMPLATE_ENV.from_string(template_text)
    return template.render(
        project_id=project_id,
        notes=notes,
        company_legal_name=_required_readme_template_value(
            config.default_company_legal_name,
            "default-company-legal-name",
        ),
        legal_contact_email=_required_readme_template_value(
            config.default_company_email,
            "default-company-email",
        ),
    )


def render_readme_prompt_template(template_text: str, *, project_id: str, notes: str) -> str:
    return _render_readme_prompt_template(template_text, project_id=project_id, notes=notes)


def run_safe_git_tool_command(command: str, /, repo_path: Path | str | None) -> dict[str, object]:
    normalized = _normalize_tool_command(command)
    if not normalized:
        return {"ok": False, "error": "Command is empty"}

    if repo_path is None:
        return {"ok": False, "error": "Repository path is required for git tool commands"}

    if not is_allowed_git_tool_command(normalized):
        return {"ok": False, "error": f"Command is not allowed: {normalized}"}

    repo_root = Path(repo_path)
    if not repo_root.is_dir():
        return {"ok": False, "error": f"Repository path does not exist: {repo_root}"}

    args = shlex.split(normalized)
    if not args or args[0] != "git":
        return {"ok": False, "error": "Only git commands are allowed"}

    try:
        completed = subprocess.run(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=GIT_TOOL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out after {GIT_TOOL_TIMEOUT_SECONDS}s"}
    except OSError as ex:
        return {"ok": False, "error": f"Failed to execute command: {ex}"}

    return {
        "ok": True,
        "command": normalized,
        "returncode": completed.returncode,
        "stdout": _clip_tool_output(completed.stdout),
        "stderr": _clip_tool_output(completed.stderr),
    }


def _extract_full_commit_message(message_content: str | None) -> str:
    if message_content is None:
        return "Unknown"
    stripped = message_content.strip()
    if not stripped:
        return "Unknown"

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped

    payload_obj = as_dict(payload)
    if payload_obj is None:
        return stripped

    full_commit_message: object | None = payload_obj.get("full_commit_message")
    if isinstance(full_commit_message, str) and full_commit_message.strip():
        return full_commit_message
    return stripped


def _assistant_message_to_param(
    message: ChatCompletionMessageLike | ChatCompletionMessage,
) -> ChatCompletionAssistantMessageParam:
    assistant_message: ChatCompletionAssistantMessageParam = {"role": "assistant"}

    if message.content is not None:
        assistant_message["content"] = message.content

    if message.tool_calls:
        tool_calls: list[ChatCompletionMessageFunctionToolCallParam] = []
        for tool_call in message.tool_calls:
            if not isinstance(tool_call, ChatCompletionMessageFunctionToolCall):
                continue
            tool_calls.append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
            )
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls

    if "content" not in assistant_message and "tool_calls" not in assistant_message:
        assistant_message["content"] = ""

    return assistant_message


def suggest_commit_name(modified: str, /, api_key: str, repo_path: Path | str | None = None) -> str:
    assert modified.strip(), "No modified files"
    client = openai.Client(api_key=api_key)
    normalized_repo_path = str(repo_path) if repo_path is not None else None

    h = hashlib.sha256()
    h.update(
        json.dumps(
            {
                "modified": modified,
                "prompt": SUGGEST_COMMIT_PROMPT,
                "repo_path": normalized_repo_path,
                "model": COMMITTING_MODEL,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    key = h.hexdigest()

    prompt = SUGGEST_COMMIT_PROMPT.replace("{modified}", modified)
    prompt += "\n\nYou may call the `run_git_command` tool for additional repository context."
    prompt += " Use only read-only git queries; never attempt writes."

    tools: list[FunctionToolParam] = [
        {
            "type": "function",
            "name": "run_git_command",
            "description": "Run a read-only git command and return stdout/stderr and return code.",
            "strict": False,
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "A single git command, e.g. 'git status --short'.",
                    }
                },
                "required": ["command"],
            },
        },
    ]

    tool_calls_log: list[dict[str, object]] = []
    final_message_content: str | None = None
    reasoning: Reasoning = {"effort": "high"}

    response = client.responses.create(
        model=COMMITTING_MODEL,
        input=prompt,
        reasoning=reasoning,
        tools=tools,
        tool_choice="auto",
    )

    for _ in range(8):
        function_calls: list[ResponseFunctionToolCall] = [
            item for item in response.output if isinstance(item, ResponseFunctionToolCall)
        ]
        if not function_calls:
            final_message_content = response.output_text
            break

        tool_outputs: ResponseInputParam = []
        for tool_call in function_calls:
            tool_name = tool_call.name
            args_text = tool_call.arguments
            tool_arguments_raw: object
            try:
                tool_arguments_raw = json.loads(args_text)
            except json.JSONDecodeError:
                tool_arguments_raw = {}
            tool_arguments_obj = as_dict(tool_arguments_raw)

            if tool_name != "run_git_command":
                tool_result: dict[str, object] = {"ok": False, "error": f"Unknown tool: {tool_name}"}
            else:
                command_arg = None if tool_arguments_obj is None else tool_arguments_obj.get("command")
                if not isinstance(command_arg, str):
                    tool_result = {"ok": False, "error": "Missing or invalid tool argument: command"}
                else:
                    tool_result = run_safe_git_tool_command(command_arg, repo_path=normalized_repo_path)

            tool_calls_log.append(
                {
                    "name": tool_name,
                    "arguments": tool_arguments_obj,
                    "result": tool_result,
                }
            )

            tool_output: FunctionCallOutput = {
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": json.dumps(tool_result, ensure_ascii=False),
            }
            tool_outputs.append(tool_output)

        response = client.responses.create(
            model=COMMITTING_MODEL,
            previous_response_id=response.id,
            input=tool_outputs,
        )

    # we are going to save a log of the response
    os.makedirs(".llm/logs/suggest_commit_name", exist_ok=True)
    with open(f".llm/logs/suggest_commit_name/{key}.json", "w") as f:
        json.dump(
            {
                "prompt": SUGGEST_COMMIT_PROMPT,
                "modified": modified,
                "repo_path": normalized_repo_path,
                "model": COMMITTING_MODEL,
                "tool_calls": tool_calls_log,
                "response": final_message_content,
            },
            f,
            indent=2,
        )

    if final_message_content is None:
        raise RuntimeError(
            "suggest_commit_name failed: model did not return a final commit message after 8 tool rounds"
        )

    return ensure_semver_impact_line(_extract_full_commit_message(final_message_content))


SUGGEST_VERSION_NUMBER = textwrap.dedent("""
Since the last release {last_version}, here are the commit messages:

{commits}

Analyze the commits and suggest the next version number according to semantic versioning.
Some commits may explicitly mention the version impact (e.g., "Semver Impact: MINOR"), but you should consider
all changes and follow these rules strictly:

1. For each commit, determine its impact:
   - **MAJOR** if it explicitly mentions a breaking change, "breaks binary compatibility", or "may break binary compatibility."
   - **MINOR** if it adds backward-compatible functionality or is labeled "Semver Impact: MINOR."
   - **PATCH** if it fixes a bug or is labeled "Semver Impact: PATCH" (and does not include major/minor changes).
   - **NONE** for purely internal refactors (build scripts, docs, .gitignore, README.md, etc.) that do not affect the public API or functionality.

2. The overall release’s new version is determined by the single highest level of impact among all commits:
   - If any commit is MAJOR, do a major bump from {last_version} (X → X+1, reset minor and patch to 0).
   - Else if any commit is MINOR, do a minor bump (X.Y.Z → X.(Y+1).0).
   - Else if any commit is PATCH, do a patch bump (X.Y.Z → X.Y.(Z+1)).
   - Else, if all are NONE, keep the same version (no bump).

3. Do not skip minor or patch versions; only increment the relevant segment of {last_version}.

Return only the new version and a short rationale in plain text.

Respond with a JSON object like:
{
    // Explain whether the changes have a major, minor, patch, or none impact according to semantic versioning.
    "commit_rationales": [
        "<rationale for the first commit>",
        "<rationale for the second commit>",
        ...
    ],

    // The rationale for the version number based on "commit_rationales".
    "rationale": "<rationale for the version number>",

    // The new version number based on "rationale", "commit_rationales", and "last_version".
    "version": "<new version number>"
}
""").strip()


def suggest_version_number(commits: list[str], last_version: str, /, api_key: str) -> tuple[str, str, list[str]]:
    assert commits, "No commits"
    client = openai.Client(api_key=api_key)

    commits_str = "\n\n".join("```\n" + commit + "\n```" for commit in commits)

    h = hashlib.sha256()
    h.update(
        json.dumps(
            {
                "prompt": SUGGEST_VERSION_NUMBER,
                "commits": commits,
                "last_version": last_version,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    key = h.hexdigest()

    reasoning: Reasoning = {"effort": "high"}
    response = client.responses.create(
        model=COMMITTING_MODEL,
        input=SUGGEST_VERSION_NUMBER.replace("{commits}", commits_str).replace("{last_version}", str(last_version)),
        reasoning=reasoning,
        text={"format": {"type": "json_object"}},
    )

    message_content = response.output_text
    assert message_content is not None, "Response content is missing"
    payload = json.loads(message_content)
    payload_obj = as_dict(payload)
    assert payload_obj is not None, "Response is not a JSON object"
    version: object | None = payload_obj.get("version")
    rationale: object | None = payload_obj.get("rationale")
    commit_rationales_raw: object | None = payload_obj.get("commit_rationales")
    assert isinstance(version, str), "Version number is missing or invalid"
    assert isinstance(rationale, str), "Rationale is missing or invalid"
    commit_rationales_raw_list = as_list(commit_rationales_raw)
    assert commit_rationales_raw_list is not None, "Commit rationales are missing or invalid"
    commit_rationales: list[str] = []
    for item in commit_rationales_raw_list:
        assert isinstance(item, str), "Commit rationales must be a list of strings"
        commit_rationales.append(item)

    os.makedirs(".llm/logs/suggest_version_number", exist_ok=True)
    with open(f".llm/logs/suggest_version_number/{key}.json", "w") as f:
        json.dump(
            {
                "prompt": SUGGEST_VERSION_NUMBER,
                "last_version": last_version,
                "commits": commits,
                "model": COMMITTING_MODEL,
                "response": message_content,
            },
            f,
            indent=2,
        )

    return version, rationale, commit_rationales


suggest_commit_name = cache(path=DEFAULT_CACHE_DB_PATH, ttl=7 * 24 * 3600)(suggest_commit_name)
suggest_version_number = cache(path=DEFAULT_CACHE_DB_PATH, ttl=7 * 24 * 3600)(suggest_version_number)


# SUMMARIZE_BUILD_LOG = textwrap.dedent(
# """
# You are given a build log from a CI/CD pipeline. The log contains the following information:

# {log}

# Analyze the log and extract the following information:
# * The build status (success or failure).
# * The build duration.

# Respond with a JSON object like:
# {
#     // Explain whether the changes have a major, minor, patch, or none impact according to semantic versioning.
#     "commit_rationales": [
#         "<rationale for the first commit>",
#         "<rationale for the second commit>",
#         ...
#     ],

#     // The rationale for the version number based on "commit_rationales".
#     "rationale": "<rationale for the version number>",

#     // The new version number based on "rationale", "commit_rationales", and "last_version".
#     "version": "<new version number>"
# }
# """).strip()


def answer_about_file(
    paths: list[Path],
    question: str,
    /,
    api_key: str | None = None,
    client: openai.Client | OpenAIChatClientLike | None = None,
) -> str:
    if client is None:
        assert api_key is not None, "API key is required"
        client = openai.Client(api_key=api_key)

    prompt = ""
    for path in paths:
        assert os.path.isfile(path), f"File {path} does not exist"
        try:
            file_text = read_text_file(path)
        except UnicodeDecodeError as ex:
            raise ValueError(f"File is not valid UTF-8 text: {path}") from ex
        except OSError as ex:
            raise ValueError(f"Could not read file {path}: {ex}") from ex
        prompt += f"<file path='{path}'>\n"
        prompt += f"```\n{file_text}\n```\n"
        prompt += "</file>\n\n"

    prompt += "Answer the following question based on the context of the files:\n"
    prompt += f"<question>{question}</question>\n"

    response = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a 10x software developer, matching in skill and experience to John Carmack.",
            },
            {"role": "user", "content": prompt},
        ],
        model=CHAT_MODEL,
        max_tokens=8000,
        temperature=1.0,
        top_p=0.90,
    )

    content = response.choices[0].message.content
    return content or ""


def _agent_tools() -> list[ChatCompletionToolParam]:
    return [
        {
            "type": "function",
            "function": {
                "name": "request_to_developer",
                "description": "Request your subordinate software developer to perform an analysis a set of files in the repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A short list of file paths to ask questions about.",
                        },
                        "task_or_question": {
                            "type": "string",
                            "description": "What has to be done. Has to be extremely detailed: provide ALL the context you have.",
                        },
                    },
                    "required": ["paths", "task_or_question"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "answer",
                "description": "Once you are ready, provide the final result of the task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "string",
                            "description": "A complete and detailed answer to the originally posed task.",
                        }
                    },
                    "required": ["result"],
                },
            },
        },
    ]


def agent_tools() -> list[ChatCompletionToolParam]:
    return _agent_tools()


def _summarize_agent_tool_arguments(tool_name: str, tool_arguments: object) -> str:
    tool_arguments_obj = as_dict(tool_arguments)
    if tool_arguments_obj is None:
        return "invalid-arguments"

    if tool_name == "request_to_developer":
        raw_paths = tool_arguments_obj.get("paths")
        paths = as_string_list(raw_paths)
        task_or_question = tool_arguments_obj.get("task_or_question")
        task_length = len(task_or_question) if isinstance(task_or_question, str) else 0
        return f"paths_count={len(paths)} task_chars={task_length}"

    if tool_name == "answer":
        result = tool_arguments_obj.get("result")
        result_length = len(result) if isinstance(result, str) else 0
        return f"result_chars={result_length}"

    return f"keys={','.join(sorted(tool_arguments_obj))}"


def _summarize_agent_tool_result(result: object) -> str:
    if isinstance(result, str):
        return f"string chars={len(result)}"

    result_obj = as_dict(result)
    if result_obj is not None:
        return f"dict keys={','.join(sorted(result_obj))}"

    return f"type={type(result).__name__}"


def _raise_agent_call_error(message: str) -> NoReturn:
    raise RuntimeError(f"agent_call failed: {message}")


def _agent_text_file_error(path: Path) -> str | None:
    props = get_expected_file_properties(path)
    if props is not None and not props.is_text:
        return f"Files are not text and cannot be read safely: {[path.as_posix()]}"
    return None


def _resolve_repo_scoped_path(root: Path, relative_path: str) -> Path | None:
    try:
        candidate = (root / relative_path).resolve()
        candidate.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


def agent_call(
    root: Path,
    task: str,
    /,
    api_key: str | None = None,
    client: openai.Client | OpenAIChatClientLike | None = None,
) -> str:
    if client is None:
        assert api_key is not None, "API key is required"
        client = openai.Client(api_key=api_key)

    tools = _agent_tools()

    def list_files(root: Path) -> list[str]:
        if not root.is_dir():
            return []
        ignore = read_ignore_file(
            root / ".gitignore",
            extra_positive=[
                ".git",
                "*.jar",
                "/gradle/",
                "/gradlew.bat",
                "/gradlew",
                ".gitignore",
                "LICENSE.md",
                "gradle.properties",
            ],
        )
        files: list[str] = []
        for path in walk_files(root, predicate=lambda t: not ignore(t)):
            files.append(path.relative_to(root).as_posix())
        return files

    known_files = list_files(root)

    def answer(paths: list[str], question: str) -> str | dict[str, str]:
        paths = [path for path in paths if path]
        if not paths:
            return {"error": "No file were provided"}

        resolved_paths: dict[str, Path] = {}
        escaped_paths: list[str] = []
        for path in paths:
            resolved_path = _resolve_repo_scoped_path(root, path)
            if resolved_path is None:
                escaped_paths.append(path)
                continue
            resolved_paths[path] = resolved_path

        if escaped_paths:
            return {
                "error": (
                    f"Paths escape repository root: {escaped_paths}. " "Please provide repository-relative file paths."
                )
            }

        non_existent_files = [path for path, resolved_path in resolved_paths.items() if not resolved_path.exists()]
        if non_existent_files:
            return {"error": f"Files do not exist: {non_existent_files}. Known files: {known_files}"}

        non_file_paths = [path for path, resolved_path in resolved_paths.items() if not os.path.isfile(resolved_path)]
        if non_file_paths:
            return {
                "error": f"Paths are directories: {non_file_paths}. Please provide paths to files, not directories."
            }

        non_text_files: list[str] = []
        for path, resolved_path in resolved_paths.items():
            text_error = _agent_text_file_error(resolved_path)
            if text_error is not None:
                non_text_files.append(path)
        if non_text_files:
            return {
                "error": f"Files are not text and cannot be read safely: {non_text_files}. Please provide text files."
            }

        try:
            return answer_about_file(list(resolved_paths.values()), question, api_key=api_key, client=client)
        except ValueError as ex:
            return {"error": str(ex)}

    initial_prompt = ""
    initial_prompt += "You are given a repository with the following files:\n"
    initial_prompt += f"<existing-files>{json.dumps(known_files)}</existing-files>\n\n"
    initial_prompt += "Solve the task by asking questions about the files in the repository.\n"
    initial_prompt += "There is no limit to the number of questions you can ask, so make sure to "
    initial_prompt += "ask as many questions as you need to clarify everything.\n\n"
    initial_prompt += f"<task>{task}</task>\n\n"

    logging.info("Starting agent_call with file_count=%d task_chars=%d", len(known_files), len(task))

    messages: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": "You are a 10x software developer, matching in skill and experience to John Carmack.",
        },
        {"role": "user", "content": initial_prompt},
    ]

    for step in range(AGENT_CALL_MAX_STEPS):
        response = client.chat.completions.create(
            messages=messages,
            model=CHAT_MODEL,
            max_tokens=4000,
            temperature=1.0,
            top_p=0.95,
            tools=tools,
            tool_choice="required",
        )

        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        if finish_reason != "tool_calls":
            _raise_agent_call_error(f"unexpected finish_reason={finish_reason!r} at step {step + 1}")
        messages.append(_assistant_message_to_param(message))

        if message.tool_calls:
            pending_answer_result: str | None = None
            for tool_call in message.tool_calls:
                assert tool_call.type == "function", f"Unknown tool call type: {tool_call.type}"
                tool_id = tool_call.id
                tool_function = tool_call.function

                tool_name = tool_function.name
                invalid_arguments_error: str | None = None
                try:
                    tool_arguments: JSONValue | None = json.loads(tool_function.arguments)
                except json.JSONDecodeError as ex:
                    tool_arguments = None
                    invalid_arguments_error = ex.msg

                logging.info(
                    "Calling tool %s with %s",
                    tool_name,
                    _summarize_agent_tool_arguments(tool_name, tool_arguments),
                )

                if tool_arguments is None:
                    result: JSONValue = {
                        "error": f"Invalid JSON tool arguments for {tool_name}: {invalid_arguments_error or 'invalid JSON'}",
                    }
                    logging.info("Tool %s returned %s", tool_name, _summarize_agent_tool_result(result))
                    invalid_json_message: ChatCompletionToolMessageParam = {
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                    messages.append(invalid_json_message)
                    continue

                if tool_name == "request_to_developer":
                    match tool_arguments:
                        case {"paths": list() as raw_paths, "task_or_question": str() as question}:
                            paths: list[str] = []
                            invalid_paths = False
                            for raw_path in raw_paths:
                                if isinstance(raw_path, str):
                                    paths.append(raw_path)
                                else:
                                    invalid_paths = True
                                    break
                            if invalid_paths or not paths:
                                result = {"error": "Missing or invalid tool argument: paths"}
                            else:
                                result = answer(paths, question)
                        case _:
                            result = {"error": "Missing or invalid tool argument: paths"}

                    logging.info("Tool %s returned %s", tool_name, _summarize_agent_tool_result(result))

                    tool_message: ChatCompletionToolMessageParam = {
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False),
                    }

                    messages.append(tool_message)

                elif tool_name == "answer":
                    match tool_arguments:
                        case {"result": result_value}:
                            if isinstance(result_value, str):
                                pending_answer_result = result_value
                            else:
                                pending_answer_result = json.dumps(result_value, ensure_ascii=False)
                        case _:
                            result = {"error": "Missing tool argument: result"}
                            logging.info("Tool %s returned %s", tool_name, _summarize_agent_tool_result(result))
                            missing_result_tool_message: ChatCompletionToolMessageParam = {
                                "tool_call_id": tool_id,
                                "role": "tool",
                                "content": json.dumps(result, ensure_ascii=False),
                            }
                            messages.append(missing_result_tool_message)
                            continue
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}
                    logging.info("Tool %s returned %s", tool_name, _summarize_agent_tool_result(result))
                    unknown_tool_message: ChatCompletionToolMessageParam = {
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                    messages.append(unknown_tool_message)

            if pending_answer_result is not None:
                return pending_answer_result

        if not message.tool_calls:
            _raise_agent_call_error(f"missing tool calls at step {step + 1}")

    _raise_agent_call_error(f"exceeded maximum tool-call steps ({AGENT_CALL_MAX_STEPS})")


def create_readme(project_name: str, root: Path, /, api_key: str) -> str:
    client = openai.Client(api_key=api_key)

    overview = agent_call(
        root,
        textwrap.dedent("""
             Create an overview of the repository as if you were writing a README file.
             Focus primarily on the high-level picture of the codebase, its purpose, and the main components.
             """).strip(),
        client=client,
    )

    usage = agent_call(
        root,
        textwrap.dedent("""
            Collect or create code usage examples for the repository.
            IF there are tests, use the tests to demonstrate usage.
            IF there are no tests, learn from the codebase and write examples.
            """).strip(),
        client=client,
    )

    notes = textwrap.dedent("""
     <overview>{overview}</overview>
     <usage>{usage}</usage>
     """).strip().replace("{overview}", overview).replace("{usage}", usage)

    prompt_template = _render_readme_prompt_template(
        read_text_file(repo_template_path("repo_template_prompt.txt")),
        project_id=project_name,
        notes=notes,
    )

    response = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a 10x software developer, matching in skill and experience to John Carmack.",
            },
            {"role": "user", "content": prompt_template},
        ],
        model=CHAT_MODEL,
        max_tokens=8000,
        temperature=1.0,
        top_p=0.95,
    )

    content = response.choices[0].message.content
    if content is None:
        return ""
    result = content.strip()
    if result.startswith("```") and result.endswith("```"):
        result = result[result.find("\n") + 1 : result.rfind("\n")]
    return result
