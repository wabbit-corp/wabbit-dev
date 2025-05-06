from typing import List

import openai
import anthropic
import hashlib
import json
import os
from pathlib import Path
import textwrap
import logging

from dev.caching import cache
from dev.io import read_text_file, read_ignore_file, walk_files

SUGGEST_COMMIT_PROMPT = textwrap.dedent(
"""
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
   - If the diff only changes test or dev dependencies (e.g., `testImplementation`, `devDependencies`, build config, docs, comments, etc.), assume **NONE** impact because it does not affect the public API.
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
"""
).strip()

@cache(path=".dev.cache.db", ttl=7 * 24 * 3600)
def suggest_commit_name(modified: str, /, api_key: str) -> str:
    assert modified.strip(), "No modified files"
    client = openai.Client(api_key=api_key)

    h = hashlib.sha256()
    h.update(json.dumps({
        'modified': modified,
        'prompt': SUGGEST_COMMIT_PROMPT
    }, sort_keys=True).encode('utf-8'))
    key = h.hexdigest()

    response = client.chat.completions.create(
        messages=[
            { "role": "user", "content": SUGGEST_COMMIT_PROMPT.replace("{modified}", modified) }
        ],
        model="o3-mini",
        reasoning_effort="high",
        # max_tokens=8192,
        # temperature=1.0,
        # top_p=0.90,
        response_format={"type": "json_object"}
    )

    # we are going to save a log of the response
    os.makedirs(".llm/logs/suggest_commit_name", exist_ok=True)
    with open(f".llm/logs/suggest_commit_name/{key}.json", "w") as f:
        json.dump({
            "prompt": SUGGEST_COMMIT_PROMPT,
            "modified": modified,
            "response": response.choices[0].message.content
        }, f, indent=2)

    obj = json.loads(response.choices[0].message.content)
    if isinstance(obj, dict) and "full_commit_message" in obj:
        return obj["full_commit_message"]
    else:
        return "Unknown"

SUGGEST_VERSION_NUMBER = textwrap.dedent(
"""
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

@cache(path=".dev.cache.db", ttl=7 * 24 * 3600)
def suggest_version_number(commits: List[str], last_version: str, /, api_key: str) -> tuple[str, str, List[str]]:
    assert commits, "No commits"
    client = openai.Client(api_key=api_key)

    commits_str = "\n\n".join('```\n' + commit + '\n```' for commit in commits)

    h = hashlib.sha256()
    h.update(json.dumps({
        'prompt': SUGGEST_VERSION_NUMBER,
        'commits': commits,
        'last_version': last_version
    }, sort_keys=True).encode('utf-8'))
    key = h.hexdigest()

    response = client.chat.completions.create(
        messages=[
            {
                "role": "user", "content": SUGGEST_VERSION_NUMBER.replace("{commits}", commits_str).replace("{last_version}", str(last_version))
            }
        ],
        model="o1",
        # max_tokens=1024,
        # temperature=1.0,
        # top_p=0.90,
        response_format={"type": "json_object"}
    )

    obj = json.loads(response.choices[0].message.content)
    assert isinstance(obj, dict), "Response is not a JSON object"
    assert "version" in obj, "Version number is missing"
    assert "rationale" in obj, "Rationale is missing"
    assert "commit_rationales" in obj, "Commit rationales are missing"

    os.makedirs(".llm/logs/suggest_version_number", exist_ok=True)
    with open(f".llm/logs/suggest_version_number/{key}.json", "w") as f:
        json.dump({
            "prompt": SUGGEST_VERSION_NUMBER,
            "last_version": last_version,
            "commits": commits,
            "response": response.choices[0].message.content
        }, f, indent=2)

    return obj["version"], obj["rationale"], obj["commit_rationales"]


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



def answer_about_file(paths: List[Path], question: str, /, api_key: str | None = None, client: openai.Client | None = None) -> str:
    if client is None:
        assert api_key is not None, "API key is required"
        client = openai.Client(api_key=api_key)

    prompt = ''
    for path in paths:
        assert os.path.isfile(path), f"File {path} does not exist"
        prompt += f"<file path='{path}'>\n"
        prompt += f"```\n{read_text_file(path)}\n```\n"
        prompt += "</file>\n\n"

    prompt += "Answer the following question based on the context of the files:\n"
    prompt += f"<question>{question}</question>\n"

    response = client.chat.completions.create(
        messages=[
            { "role": "system", "content":
                "You are a 10x software developer, matching in skill and experience to John Carmack." },
            { "role": "user", "content": prompt } ],
        model="gpt-4o",
        max_tokens=8000,
        temperature=1.0,
        top_p=0.90,
    )

    return response.choices[0].message.content

def agent_call(root: Path, task: str, /, api_key: str | None = None, client: openai.Client | None = None) -> str:
    if client is None:
        assert api_key is not None, "API key is required"
        client = openai.Client(api_key=api_key)

    tools = [
        {
            'type': 'function',
            'function': {
                'name': 'request_to_developer',
                'description': 'Request your subordinate software developer to perform an analysis a set of files in the repository.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'paths': {
                            'type': 'array',
                            'items': {
                                'type': 'string'
                            },
                            'description': 'A short list of file paths to ask questions about.'
                        },
                        'task_or_question': {
                            'type': 'string',
                            'description': 'What has to be done. Has to be extremely detailed: provide ALL the context you have.'
                        }
                    },
                    'required': ['paths', 'question']
                }
            }
        },
        {
            'type': 'function',
            'function': {
                'name': 'answer',
                'description': 'Once you are ready, provide the final result of the task.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'result': {
                            'type': 'string',
                            'description': 'A complete and detailed answer to the originally posed task.'
                        }
                    },
                    'required': ['result']
                }
            }
        }
    ]

    def list_files(root: Path) -> List[str]:
        if not root.is_dir():
            return []
        ignore = read_ignore_file(root / '.gitignore', extra_positive=[
            '.git', '*.jar',
            '/gradle/', '/gradlew.bat', '/gradlew',
            '.gitignore', 'LICENSE.md', 'gradle.properties'])
        files = []
        for path in walk_files(root, predicate=lambda t: not ignore(t)):
            files.append(path.relative_to(root).as_posix())
        return files

    known_files = list_files(root)

    def answer(paths: List[str], question: str) -> str:
        paths = [path for path in paths if path]
        if not paths:
            return { "error": "No file were provided" }

        non_existent_files = [path for path in paths if not (root / path).exists()]
        if non_existent_files:
            return {
                "error": f"Files do not exist: {non_existent_files}. Known files: {known_files}"
            }

        non_file_paths = [path for path in paths if not os.path.isfile(root / path)]
        if non_file_paths:
            return {
                "error": f"Paths are directories: {non_file_paths}. Please provide paths to files, not directories."
            }

        return answer_about_file([root / path for path in paths], question, api_key=api_key, client=client)

    initial_prompt = ''
    initial_prompt += "You are given a repository with the following files:\n"
    initial_prompt += f"<existing-files>{json.dumps(known_files)}</existing-files>\n\n"
    initial_prompt += "Solve the task by asking questions about the files in the repository.\n"
    initial_prompt += "There is no limit to the number of questions you can ask, so make sure to "
    initial_prompt += "ask as many questions as you need to clarify everything.\n\n"
    initial_prompt += f"<task>{task}</task>\n\n"

    logging.info(f"Initial prompt: {initial_prompt}")

    messages = [
        { "role": "system", "content":
            "You are a 10x software developer, matching in skill and experience to John Carmack." },
        { "role": "user", "content": initial_prompt }
    ]

    while True:
        response = client.chat.completions.create(
            messages=messages,
            model="gpt-4o",
            max_tokens=4000,
            temperature=1.0,
            top_p=0.95,
            tools=tools,
            tool_choice='required'
        )

        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        assert finish_reason == 'tool_calls'
        messages.append(message)

        if message.tool_calls:
            for tool_call in message.tool_calls:
                assert tool_call.type == 'function', f"Unknown tool call type: {tool_call.type}"
                tool_id = tool_call.id
                tool_function = tool_call.function

                tool_name = tool_function.name
                tool_arguments = json.loads(tool_function.arguments)

                logging.info(f"Calling tool {tool_name} with arguments {tool_arguments}")

                if tool_name == 'request_to_developer':
                    paths = tool_arguments['paths']
                    question = tool_arguments['task_or_question']

                    result = answer(paths, question)

                    logging.info(f"Answered question: {result}")

                    msg = {
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(result, ensure_ascii=False)
                    }

                    messages.append(msg)

                elif tool_name == 'answer':
                    result = tool_arguments['result']
                    return result

def create_readme(project_name: str, root: Path, /, api_key: str) -> str:
    client = openai.Client(api_key=api_key)

    overview = agent_call(root,
        textwrap.dedent(
             """
             Create an overview of the repository as if you were writing a README file.
             Focus primarily on the high-level picture of the codebase, its purpose, and the main components.
             """).strip(),
        client=client)

    usage = agent_call(root,
        textwrap.dedent(
            """
            Collect or create code usage examples for the repository.
            IF there are tests, use the tests to demonstrate usage.
            IF there are no tests, learn from the codebase and write examples.
            """).strip(),
        client=client)

    notes = textwrap.dedent('''
     <overview>{overview}</overview>
     <usage>{usage}</usage>
     ''').strip().replace("{overview}", overview).replace("{usage}", usage)

    prompt_template = read_text_file(Path("data-repo-template/repo_template_prompt.txt"))
    prompt_template = prompt_template.replace('{{project-id}}', project_name)
    prompt_template = prompt_template.replace('{{notes}}', notes)

    response = client.chat.completions.create(
        messages=[
            { "role": "system", "content":
                "You are a 10x software developer, matching in skill and experience to John Carmack." },
            { "role": "user", "content": prompt_template } ],
        model="gpt-4o",
        max_tokens=8000,
        temperature=1.0,
        top_p=0.95,
    )

    result = response.choices[0].message.content.strip()
    if result.startswith('```') and result.endswith('```'):
        result = result[result.find('\n') + 1:
                        result.rfind('\n')]
    return result
