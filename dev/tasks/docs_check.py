from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from contextlib import nullcontext, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlparse

import openai
import requests
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses.function_tool_param import FunctionToolParam
from openai.types.responses.response_input_item_param import FunctionCallOutput
from openai.types.responses.response_input_param import ResponseInputParam

from dev.config import GradleProject, Project, PythonProject, load_config
from dev.failure_context import contextualize_failure
from dev.json_utils import as_dict, as_list
from dev.messages import accent, error, heading, info, style, success, warning
from dev.repo_resolution import inferred_project_targets, resolve_project_ids

DocsSeverity = Literal["warning", "error"]

_MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
_MARKDOWN_LINK_WITH_LABEL_RE = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\n]+)\)")
_HTML_LINK_RE = re.compile(r"""<(?:a|img)\b[^>]*\b(?:href|src)=["']([^"']+)["'][^>]*>""", re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_FENCED_CODE_RE = re.compile(r"(?ms)^```([^\n`]*)\n(.*?)^```[ \t]*$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PUNCTUATION_RE = re.compile(r"[^\w\s-]")
_EXTERNAL_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

_INSTALL_KEYWORDS = ("install", "installation")
_QUICKSTART_KEYWORDS = ("quickstart", "quick start", "getting started")
_EXAMPLE_KEYWORDS = ("example", "examples")
_USAGE_KEYWORDS = ("usage",)
_PURPOSE_KEYWORDS = ("why", "motivation", "purpose", "problem", "overview", "about", "background")
_STATUS_KEYWORDS = ("status", "stability", "maturity", "experimental", "beta", "stable", "maintained", "maintenance")
_DOCS_LINK_KEYWORDS = ("docs", "documentation", "api", "reference", "guide", "wiki")
_SUPPORT_LINK_KEYWORDS = ("support", "help", "issue", "issues", "discussion", "discussions", "community", "contact")
_CHANGELOG_KEYWORDS = ("changelog", "change log", "release notes", "releases", "history")
_SNIPPET_JVM_LANGUAGES = {"kotlin", "kt", "java", "groovy", "gradle", "kts"}
_SNIPPET_YAML_LANGUAGES = {"yaml", "yml"}
_SNIPPET_JSON_LANGUAGES = {"json"}
_SNIPPET_TOML_LANGUAGES = {"toml"}
_SNIPPET_PYTHON_LANGUAGES = {"python", "py"}
_SNIPPET_SHELL_LANGUAGES = {"bash", "sh", "zsh", "shell"}
_SEMANTIC_TOOL_MAX_FILE_CHARS = 12000
_SEMANTIC_TOOL_MAX_LIST_ENTRIES = 200
_SEMANTIC_TOOL_MAX_GREP_LINES = 200
_SEMANTIC_TOOL_TIMEOUT_SECONDS = 5


class DocsCheckError(Exception):
    pass


@dataclass(frozen=True)
class DocsFinding:
    code: str
    severity: DocsSeverity
    message: str
    path: str | None = None
    line: int | None = None
    source: Literal["deterministic", "semantic"] = "deterministic"

    def payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "source": self.source,
        }


@dataclass(frozen=True)
class MarkdownLink:
    path: Path
    target: str
    line: int
    is_image: bool = False


@dataclass(frozen=True)
class FencedCodeBlock:
    path: Path
    language: str
    code: str
    line: int


def _project_kind(project: Project) -> str:
    return type(project).__name__.removesuffix("Project").lower()


def _clean_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target:
        return target
    if " " in target and not _EXTERNAL_URL_RE.match(target):
        target = target.split(maxsplit=1)[0]
    return target


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _markdown_links(path: Path, text: str) -> list[MarkdownLink]:
    results: list[MarkdownLink] = []
    for match in _MARKDOWN_LINK_RE.finditer(text):
        raw_target = match.group(1)
        target = _clean_link_target(raw_target)
        if not target:
            continue
        snippet = match.group(0)
        results.append(
            MarkdownLink(
                path=path,
                target=target,
                line=_line_number(text, match.start()),
                is_image=snippet.startswith("!"),
            )
        )
    for match in _HTML_LINK_RE.finditer(text):
        target = _clean_link_target(match.group(1))
        if not target:
            continue
        results.append(
            MarkdownLink(
                path=path,
                target=target,
                line=_line_number(text, match.start()),
                is_image="<img" in match.group(0).lower(),
            )
        )
    return results


def _slugify_anchor(text: str) -> str:
    normalized = _HTML_TAG_RE.sub("", text)
    normalized = normalized.replace("`", "")
    normalized = normalized.strip().lower()
    normalized = _PUNCTUATION_RE.sub("", normalized)
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def _markdown_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    for match in _HEADING_RE.finditer(text):
        anchor = _slugify_anchor(match.group(2))
        if anchor:
            anchors.add(anchor)
    return anchors


def _markdown_headings(text: str) -> list[str]:
    return [_HTML_TAG_RE.sub("", match.group(2)).strip().lower() for match in _HEADING_RE.finditer(text)]


def _markdown_link_texts(text: str) -> list[str]:
    values: list[str] = []
    for match in _MARKDOWN_LINK_WITH_LABEL_RE.finditer(text):
        label = match.group(2).strip().lower()
        target = _clean_link_target(match.group(3)).lower()
        combined = " ".join(part for part in (label, target) if part)
        if combined:
            values.append(combined)
    for match in _HTML_LINK_RE.finditer(text):
        target = _clean_link_target(match.group(1)).lower()
        if target:
            values.append(target)
    return values


def _markdown_code_blocks(path: Path, text: str) -> list[FencedCodeBlock]:
    blocks: list[FencedCodeBlock] = []
    for match in _FENCED_CODE_RE.finditer(text):
        language = match.group(1).strip().lower()
        code = match.group(2)
        blocks.append(
            FencedCodeBlock(
                path=path,
                language=language,
                code=code,
                line=_line_number(text, match.start()),
            )
        )
    return blocks


def _project_code_blocks(markdown_files: Sequence[Path]) -> list[FencedCodeBlock]:
    code_blocks: list[FencedCodeBlock] = []
    for markdown_file in markdown_files:
        text = markdown_file.read_text(encoding="utf-8")
        code_blocks.extend(_markdown_code_blocks(markdown_file, text))
    return code_blocks


def _candidate_doc_paths(base: Path) -> Iterable[Path]:
    yield base
    if base.suffix == "":
        yield base.with_suffix(".md")
        yield base / "README.md"
        yield base / "index.md"
    elif base.is_dir():
        yield base / "README.md"
        yield base / "index.md"


def _resolve_internal_target(project: Project, source_path: Path, target: str) -> tuple[Path | None, str | None]:
    path_part, _, fragment = target.partition("#")
    if not path_part:
        return source_path, fragment or None

    raw_path = Path(path_part)
    if raw_path.is_absolute():
        base = raw_path
    elif path_part.startswith("/"):
        base = project.path / path_part.lstrip("/")
    else:
        base = source_path.parent / raw_path
    base = base.resolve()

    for candidate in _candidate_doc_paths(base):
        if candidate.exists():
            return candidate, fragment or None
    return None, fragment or None


def _link_type(target: str) -> Literal["external", "internal", "skip"]:
    if not target or target.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return "skip"
    if _EXTERNAL_URL_RE.match(target):
        return "external"
    return "internal"


def _check_external_url(url: str, *, timeout_seconds: float = 5.0) -> tuple[bool, str]:
    headers = {"User-Agent": "wabbit-dev docs-check"}
    try:
        head = requests.head(url, allow_redirects=True, timeout=timeout_seconds, headers=headers)
        if head.status_code < 400:
            return True, f"HTTP {head.status_code}"
        if head.status_code not in {403, 405}:
            return False, f"HTTP {head.status_code}"
        get_response = requests.get(url, allow_redirects=True, timeout=timeout_seconds, headers=headers)
        if get_response.status_code < 400:
            return True, f"HTTP {get_response.status_code}"
        return False, f"HTTP {get_response.status_code}"
    except requests.RequestException as ex:
        return False, f"{type(ex).__name__}: {ex}"


def _plain_markdown_text(text: str) -> str:
    normalized = _MARKDOWN_LINK_WITH_LABEL_RE.sub(lambda match: match.group(2), text)
    normalized = _HTML_TAG_RE.sub(" ", normalized)
    normalized = normalized.replace("`", " ")
    normalized = re.sub(r"!\[[^\]\n]*\]\([^)]+\)", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _readme_intro_text(text: str) -> str:
    lines = text.splitlines()
    intro_lines: list[str] = []
    saw_title = False
    for raw_line in lines:
        stripped = raw_line.strip()
        if not saw_title:
            if stripped.startswith("# "):
                saw_title = True
            continue
        if stripped.startswith("##"):
            break
        if not stripped:
            continue
        intro_lines.append(stripped)
    return _plain_markdown_text("\n".join(intro_lines))


def _contains_any_keyword(values: Iterable[str], keywords: Sequence[str]) -> bool:
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    return any(any(keyword in value.lower() for keyword in lowered_keywords) for value in values)


def _section_findings(readme_path: Path, text: str, code_blocks: Sequence[FencedCodeBlock]) -> list[DocsFinding]:
    headings = _markdown_headings(text)
    link_texts = _markdown_link_texts(text)
    plain_text = _plain_markdown_text(text)
    intro_text = _readme_intro_text(text)
    findings: list[DocsFinding] = []
    has_install = any(any(keyword in heading for keyword in _INSTALL_KEYWORDS) for heading in headings)
    has_quickstart = any(any(keyword in heading for keyword in _QUICKSTART_KEYWORDS) for heading in headings)
    has_usage = any(any(keyword in heading for keyword in _USAGE_KEYWORDS) for heading in headings)
    has_examples = any(any(keyword in heading for keyword in _EXAMPLE_KEYWORDS) for heading in headings) or bool(
        code_blocks
    )
    has_purpose = _contains_any_keyword(headings, _PURPOSE_KEYWORDS) or len(intro_text.split()) >= 12
    has_status = _contains_any_keyword(headings, _STATUS_KEYWORDS) or _contains_any_keyword([text], _STATUS_KEYWORDS)
    has_docs_link = _contains_any_keyword(link_texts, _DOCS_LINK_KEYWORDS)
    has_support_link = _contains_any_keyword(link_texts, _SUPPORT_LINK_KEYWORDS) or _contains_any_keyword(
        [plain_text], _SUPPORT_LINK_KEYWORDS
    )
    has_changelog_link = (
        _contains_any_keyword(headings, _CHANGELOG_KEYWORDS)
        or _contains_any_keyword(link_texts, _CHANGELOG_KEYWORDS)
        or _contains_any_keyword([plain_text], _CHANGELOG_KEYWORDS)
    )

    if not has_install:
        findings.append(
            DocsFinding(
                code="W_DOCS_MISSING_INSTALL_SECTION",
                severity="warning",
                message="README is missing an installation section.",
                path=str(readme_path),
            )
        )
    if not has_purpose:
        findings.append(
            DocsFinding(
                code="W_DOCS_MISSING_PROJECT_PURPOSE",
                severity="warning",
                message="README does not clearly explain what the project is and why it exists.",
                path=str(readme_path),
            )
        )
    if not (has_quickstart or has_usage):
        findings.append(
            DocsFinding(
                code="W_DOCS_MISSING_QUICKSTART_SECTION",
                severity="warning",
                message="README is missing a quickstart or usage section.",
                path=str(readme_path),
            )
        )
    if not has_status:
        findings.append(
            DocsFinding(
                code="W_DOCS_MISSING_PROJECT_STATUS",
                severity="warning",
                message="README is missing project status or maturity guidance.",
                path=str(readme_path),
            )
        )
    if not has_docs_link:
        findings.append(
            DocsFinding(
                code="W_DOCS_MISSING_DOCS_LINK",
                severity="warning",
                message="README is missing a docs, guide, or API reference link.",
                path=str(readme_path),
            )
        )
    if not has_support_link:
        findings.append(
            DocsFinding(
                code="W_DOCS_MISSING_SUPPORT_LINK",
                severity="warning",
                message="README is missing a support path such as issues, discussions, or contact guidance.",
                path=str(readme_path),
            )
        )
    if not has_changelog_link:
        findings.append(
            DocsFinding(
                code="W_DOCS_MISSING_CHANGELOG_LINK",
                severity="warning",
                message="README is missing a changelog or release-notes link.",
                path=str(readme_path),
            )
        )
    if not has_examples:
        findings.append(
            DocsFinding(
                code="W_DOCS_MISSING_EXAMPLES",
                severity="warning",
                message="README is missing example-oriented content or runnable code snippets.",
                path=str(readme_path),
            )
        )
    return findings


def _docs_hook_findings(project: Project) -> list[DocsFinding]:
    findings: list[DocsFinding] = []
    if not project.docs_enabled:
        return findings

    if isinstance(project, PythonProject) and project.docs_system == "mkdocs":
        expected_errors = [
            (
                project.path / "mkdocs.yml",
                "E_DOCS_MISSING_MKDOCS_CONFIG",
                "Docs are enabled but mkdocs.yml is missing.",
            ),
            (
                project.path / "docs" / "index.md",
                "E_DOCS_MISSING_INDEX",
                "Docs are enabled but docs/index.md is missing.",
            ),
        ]
        for path, code, message in expected_errors:
            if not path.is_file():
                findings.append(DocsFinding(code=code, severity="error", message=message, path=str(path)))

        expected_warnings = [
            (
                project.path / "scripts" / "generate_api_docs.py",
                "W_DOCS_MISSING_API_DOCS_HOOK",
                "Docs are enabled but scripts/generate_api_docs.py is missing.",
            ),
            (
                project.path / "scripts" / "check_docs_links.py",
                "W_DOCS_MISSING_LINK_CHECK_HOOK",
                "Docs are enabled but scripts/check_docs_links.py is missing.",
            ),
            (
                project.path / "tests" / "test_docs_snippets.py",
                "W_DOCS_MISSING_SNIPPETS_TEST",
                "Docs are enabled but tests/test_docs_snippets.py is missing.",
            ),
        ]
        for path, code, message in expected_warnings:
            if not path.is_file():
                findings.append(DocsFinding(code=code, severity="warning", message=message, path=str(path)))
        return findings

    if isinstance(project, GradleProject) and project.docs_system == "dokka":
        repo_root = project.effective_repo_root
        for path, code, message in (
            (
                repo_root / ".github" / "workflows" / "docs-quality.yml",
                "W_DOCS_MISSING_DOKKA_QUALITY_WORKFLOW",
                "Docs are enabled but the Dokka docs-quality workflow is missing.",
            ),
            (
                repo_root / ".github" / "workflows" / "docs-deploy.yml",
                "W_DOCS_MISSING_DOKKA_DEPLOY_WORKFLOW",
                "Docs are enabled but the Dokka docs-deploy workflow is missing.",
            ),
        ):
            if not path.is_file():
                findings.append(DocsFinding(code=code, severity="warning", message=message, path=str(path)))
    return findings


def _snippet_language(block: FencedCodeBlock) -> str:
    return block.language.split()[0] if block.language else ""


def _syntax_check_snippets(code_blocks: Sequence[FencedCodeBlock]) -> tuple[list[DocsFinding], dict[str, int]]:
    findings: list[DocsFinding] = []
    checked = 0
    skipped = 0
    unsupported = 0

    for block in code_blocks:
        language = _snippet_language(block)
        if language in _SNIPPET_PYTHON_LANGUAGES:
            checked += 1
            try:
                compile(block.code, str(block.path), "exec")
            except SyntaxError as ex:
                findings.append(
                    DocsFinding(
                        code="E_DOCS_SNIPPET_INVALID_PYTHON",
                        severity="error",
                        message=f"Python docs snippet does not compile: {ex.msg}.",
                        path=str(block.path),
                        line=block.line,
                    )
                )
        elif language in _SNIPPET_SHELL_LANGUAGES:
            lines: list[str] = []
            checkable = True
            for raw_line in block.code.splitlines():
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith(("$ ", "% ")):
                    lines.append(stripped[2:])
                elif stripped.startswith("... "):
                    if lines:
                        lines[-1] += stripped[3:]
                    else:
                        checkable = False
                        break
                else:
                    checkable = False
                    break
            if not checkable or not lines:
                skipped += 1
                continue
            checked += 1
            process = subprocess.run(
                ["bash", "-n"],
                input="\n".join(lines),
                text=True,
                capture_output=True,
                check=False,
            )
            if process.returncode != 0:
                findings.append(
                    DocsFinding(
                        code="E_DOCS_SNIPPET_INVALID_SHELL",
                        severity="error",
                        message="Shell docs snippet does not parse under bash -n.",
                        path=str(block.path),
                        line=block.line,
                    )
                )
        elif language in _SNIPPET_JSON_LANGUAGES:
            checked += 1
            try:
                json.loads(block.code)
            except json.JSONDecodeError as ex:
                findings.append(
                    DocsFinding(
                        code="E_DOCS_SNIPPET_INVALID_JSON",
                        severity="error",
                        message=f"JSON docs snippet does not parse: {ex.msg}.",
                        path=str(block.path),
                        line=block.line,
                    )
                )
        elif language in _SNIPPET_TOML_LANGUAGES:
            checked += 1
            try:
                tomllib.loads(block.code)
            except tomllib.TOMLDecodeError as ex:
                findings.append(
                    DocsFinding(
                        code="E_DOCS_SNIPPET_INVALID_TOML",
                        severity="error",
                        message=f"TOML docs snippet does not parse: {ex}.",
                        path=str(block.path),
                        line=block.line,
                    )
                )
        elif language in _SNIPPET_YAML_LANGUAGES:
            checked += 1
            try:
                import yaml

                yaml.safe_load(block.code)
            except ModuleNotFoundError:
                skipped += 1
            except Exception as ex:
                findings.append(
                    DocsFinding(
                        code="E_DOCS_SNIPPET_INVALID_YAML",
                        severity="error",
                        message=f"YAML docs snippet does not parse: {ex}.",
                        path=str(block.path),
                        line=block.line,
                    )
                )
        else:
            skipped += 1
            if language:
                unsupported += 1

    return findings, {"checked": checked, "skipped": skipped, "unsupported": unsupported, "total": len(code_blocks)}


def _snippet_findings(code_blocks: Sequence[FencedCodeBlock]) -> tuple[list[DocsFinding], dict[str, int]]:
    return _syntax_check_snippets(code_blocks)


def _run_python_snippet_hook(
    project: PythonProject,
    *,
    redirect_output: bool,
) -> tuple[list[DocsFinding], dict[str, object]]:
    hook_path = project.path / "tests" / "test_docs_snippets.py"
    result: dict[str, object] = {
        "status": "skipped",
        "path": str(hook_path.resolve()),
    }
    if not hook_path.is_file():
        finding = DocsFinding(
            code="W_DOCS_SNIPPETS_MISSING_PYTHON_HOOK",
            severity="warning",
            message="Python snippet execution was requested but tests/test_docs_snippets.py is missing.",
            path=str(hook_path.resolve()),
        )
        result["reason"] = "missing-hook"
        return [finding], result

    command = [sys.executable, "-m", "pytest", "-q", "tests/test_docs_snippets.py"]
    result["command"] = command
    try:
        if redirect_output:
            subprocess.run(command, cwd=project.path, check=True, stdout=sys.stderr, stderr=sys.stderr)
        else:
            subprocess.run(command, cwd=project.path, check=True)
    except subprocess.CalledProcessError as ex:
        finding = DocsFinding(
            code="E_DOCS_SNIPPETS_PYTHON_HOOK_FAILED",
            severity="error",
            message=f"Python docs snippet hook failed with exit code {ex.returncode}.",
            path=str(hook_path.resolve()),
        )
        result["status"] = "failed"
        result["returnCode"] = ex.returncode
        return [finding], result

    result["status"] = "success"
    return [], result


def _run_gradle_snippet_build(
    project: GradleProject,
    *,
    redirect_output: bool,
) -> tuple[list[DocsFinding], dict[str, object]]:
    from dev.tasks.build import build_gradle_project, gradle_command, gradle_task_name

    if project.is_kmp:
        gradle_root = project.effective_gradle_root
        command = [
            *gradle_command(gradle_root),
            "--no-daemon",
            gradle_task_name(project, "publishKotlinMultiplatformPublicationToMavenLocal"),
        ]
        try:
            if redirect_output:
                subprocess.run(command, cwd=gradle_root, check=True, stdout=sys.stderr, stderr=sys.stderr)
            else:
                subprocess.run(command, cwd=gradle_root, check=True)
        except subprocess.CalledProcessError as ex:
            failed_result: dict[str, object] = {
                "status": "failed",
                "details": {
                    "kind": "gradle",
                    "gradleRoot": str(gradle_root.resolve()),
                    "command": command,
                    "error": f"Build failed with exit code {ex.returncode}.",
                    "returnCode": ex.returncode,
                },
                "mode": "kmp-multiplatform-publication",
            }
            finding = DocsFinding(
                code="E_DOCS_SNIPPETS_GRADLE_BUILD_FAILED",
                severity="error",
                message=(
                    "Gradle snippet verification requested a coarse project build, and that build failed. "
                    "This validates the project build as a whole, not each snippet individually."
                ),
                path=str(project.path.resolve()),
            )
            return [finding], failed_result

        return (
            [],
            {
                "status": "success",
                "details": {
                    "kind": "gradle",
                    "gradleRoot": str(gradle_root.resolve()),
                    "command": command,
                },
                "mode": "kmp-multiplatform-publication",
            },
        )

    success_build, details = build_gradle_project(
        project,
        emit_messages=not redirect_output,
        redirect_output=redirect_output,
    )
    result: dict[str, object] = {
        "status": "success" if success_build else "failed",
        "details": details,
        "mode": "coarse-project-build",
    }
    if success_build:
        return [], result

    finding = DocsFinding(
        code="E_DOCS_SNIPPETS_GRADLE_BUILD_FAILED",
        severity="error",
        message=(
            "Gradle snippet verification requested a coarse project build, and that build failed. "
            "This validates the project build as a whole, not each snippet individually."
        ),
        path=str(project.path.resolve()),
    )
    return [finding], result


def _semantic_prompt(project: Project, markdown_files: Sequence[Path]) -> str:
    facts = {
        "projectId": project.project_id or project.name,
        "projectKind": _project_kind(project),
        "description": getattr(project, "description", None),
        "githubRepo": getattr(project, "github_repo", None),
        "docsEnabled": project.docs_enabled,
        "docsSystem": project.docs_system,
        "publishTarget": getattr(project, "publish_target", None),
        "buildModel": getattr(project, "build_model", None),
        "hasReadme": (project.path / "README.md").is_file(),
        "docsFiles": [path.relative_to(project.path).as_posix() for path in markdown_files],
        "path": str(project.path.resolve()),
    }
    prompt = [
        "You are reviewing project documentation quality for a developer tool.",
        "Only make high-signal semantic judgments that cannot be determined by syntax or link checks alone.",
        "Do not report broken links, missing files, or syntax errors. Those are handled elsewhere.",
        "Judge the docs as a newcomer would: can they understand what this project is for, who it is for, how mature it is, and how to get to first success?",
        "You may use the provided local tools to inspect the repo structure, grep for evidence, and read a few relevant text files such as mkdocs.yml, pyproject.toml, build.gradle.kts, or docs pages.",
        "Return strict JSON with this shape:",
        '{"summary": "string", "findings": [{"code": "string", "severity": "warning", "path": "string|null", "message": "string", "evidence": "string"}]}',
        "Use at most 7 findings.",
        (
            "Allowed codes: missing-project-why, quickstart-not-actionable, "
            "examples-not-core-or-compelling, docs-audience-mismatch, "
            "maturity-or-status-misleading, docs-journey-fragmented, "
            "support-path-unclear, readme-first-use-buried."
        ),
        "Findings must be warning severity only.",
        "Every finding must include short concrete evidence quoted or paraphrased from the provided docs files.",
        "Do not complain about writing style, tone, badges, visuals, or generic polish.",
        "Do not suggest adding sections that already exist unless their content is substantively weak or misleading.",
        (
            "For README.md specifically, prefer the landing pattern: one-sentence description, "
            "then a concrete quick start code example that shows what using the project actually "
            "looks like, then deeper material."
        ),
        (
            "Use readme-first-use-buried when the README makes a newcomer scroll through module "
            "tables, design philosophy, status sections, badges, or artifact coordinates before "
            "showing any concrete usage."
        ),
        "Base your judgment only on the facts and files provided.",
        "",
        "<project-facts>",
        json.dumps(facts, indent=2),
        "</project-facts>",
        "",
    ]

    total_chars = 0
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        if total_chars > 60000:
            break
        truncated = text[:12000]
        total_chars += len(truncated)
        prompt.extend(
            [
                f'<file path="{path.relative_to(project.path).as_posix()}">',
                truncated,
                "</file>",
                "",
            ]
        )
    return "\n".join(prompt)


def _resolve_semantic_relative_path(project: Project, relative_path: str) -> Path:
    base = project.path.resolve()
    candidate = (base / relative_path).resolve() if relative_path not in {"", "."} else base
    if not candidate.is_relative_to(base):
        raise DocsCheckError(f"Path escapes project root: {relative_path}")
    return candidate


def _clip_semantic_text(text: str, *, limit: int = _SEMANTIC_TOOL_MAX_FILE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n...[truncated]"


def _semantic_tool_list_paths(project: Project, *, relative_path: str = ".") -> dict[str, object]:
    try:
        path = _resolve_semantic_relative_path(project, relative_path)
    except DocsCheckError as ex:
        return {"ok": False, "error": str(ex)}

    if not path.exists():
        return {"ok": False, "error": f"Path does not exist: {relative_path}"}

    if path.is_file():
        return {
            "ok": True,
            "path": str(path.relative_to(project.path.resolve())),
            "entries": [{"path": str(path.relative_to(project.path.resolve())), "kind": "file"}],
            "truncated": False,
        }

    entries: list[dict[str, str]] = []
    children = sorted(path.iterdir(), key=lambda item: item.name.casefold())
    for child in children[:_SEMANTIC_TOOL_MAX_LIST_ENTRIES]:
        kind = "dir" if child.is_dir() else "file"
        entries.append({"path": child.relative_to(project.path.resolve()).as_posix(), "kind": kind})
    return {
        "ok": True,
        "path": str(path.relative_to(project.path.resolve())) if path != project.path.resolve() else ".",
        "entries": entries,
        "truncated": len(children) > _SEMANTIC_TOOL_MAX_LIST_ENTRIES,
    }


def _semantic_tool_read_file(project: Project, *, relative_path: str) -> dict[str, object]:
    try:
        path = _resolve_semantic_relative_path(project, relative_path)
    except DocsCheckError as ex:
        return {"ok": False, "error": str(ex)}

    if not path.is_file():
        return {"ok": False, "error": f"File does not exist: {relative_path}"}

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "error": f"File is not valid UTF-8 text: {relative_path}"}

    return {
        "ok": True,
        "path": path.relative_to(project.path.resolve()).as_posix(),
        "content": _clip_semantic_text(content),
        "truncated": len(content) > _SEMANTIC_TOOL_MAX_FILE_CHARS,
    }


def _semantic_tool_grep_repo(
    project: Project,
    *,
    pattern: str,
    relative_path: str = ".",
) -> dict[str, object]:
    try:
        path = _resolve_semantic_relative_path(project, relative_path)
    except DocsCheckError as ex:
        return {"ok": False, "error": str(ex)}

    if not path.exists():
        return {"ok": False, "error": f"Path does not exist: {relative_path}"}

    rg_path = shutil.which("rg")
    if rg_path is not None:
        command = [
            rg_path,
            "-n",
            "--hidden",
            "--color",
            "never",
            "--max-count",
            str(_SEMANTIC_TOOL_MAX_GREP_LINES),
            pattern,
            str(path),
        ]
    else:
        command = [
            "grep",
            "-R",
            "-n",
            "-E",
            pattern,
            str(path),
        ]

    try:
        completed = subprocess.run(
            command,
            cwd=project.path,
            capture_output=True,
            text=True,
            timeout=_SEMANTIC_TOOL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"grep timed out after {_SEMANTIC_TOOL_TIMEOUT_SECONDS}s"}
    except OSError as ex:
        return {"ok": False, "error": f"Failed to execute grep tool: {ex}"}

    if completed.returncode not in {0, 1}:
        return {"ok": False, "error": completed.stderr.strip() or f"grep failed with exit code {completed.returncode}"}

    stdout = completed.stdout.strip()
    results = stdout.splitlines() if stdout else []
    normalized_results: list[str] = []
    project_root = project.path.resolve()
    for line in results[:_SEMANTIC_TOOL_MAX_GREP_LINES]:
        if line.startswith(str(project_root)):
            normalized_results.append(line.replace(str(project_root) + "/", "", 1))
        else:
            normalized_results.append(line)

    return {
        "ok": True,
        "path": str(path.relative_to(project_root)) if path != project_root else ".",
        "pattern": pattern,
        "matches": normalized_results,
        "truncated": len(results) > _SEMANTIC_TOOL_MAX_GREP_LINES,
    }


def _semantic_tools() -> list[FunctionToolParam]:
    return [
        {
            "type": "function",
            "strict": False,
            "name": "list_paths",
            "description": "List files or directories under the project root to understand docs structure and neighboring config files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Project-relative directory or file path to inspect. Defaults to '.'.",
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "strict": False,
            "name": "read_file",
            "description": "Read one UTF-8 text file from the project, such as README.md, mkdocs.yml, pyproject.toml, build.gradle.kts, or a docs page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Project-relative file path to read.",
                    }
                },
                "required": ["relative_path"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "strict": False,
            "name": "grep_repo",
            "description": "Search project files for evidence such as quickstart commands, support paths, status language, or docs references.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Ripgrep or grep regex pattern to search for.",
                    },
                    "relative_path": {
                        "type": "string",
                        "description": "Project-relative starting path. Defaults to '.'.",
                    },
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
        },
    ]


def _parse_semantic_response(raw: str) -> dict[str, object]:
    stripped = raw.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[stripped.find("\n") + 1 : stripped.rfind("\n")].strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise DocsCheckError("Semantic docs check returned a non-object response.")
    return cast(dict[str, object], parsed)


def _semantic_log_path(key: str) -> Path:
    return Path(".llm") / "logs" / "docs_semantic_check" / f"{key}.json"


def _semantic_findings(
    project: Project,
    markdown_files: Sequence[Path],
    *,
    api_key: str,
) -> list[DocsFinding]:
    prompt = _semantic_prompt(project, markdown_files)
    key = hashlib.sha256(json.dumps({"prompt": prompt}, sort_keys=True).encode("utf-8")).hexdigest()
    log_path = _semantic_log_path(key)
    if log_path.is_file():
        payload = json.loads(log_path.read_text(encoding="utf-8"))
        response_text = payload.get("response")
        if isinstance(response_text, str):
            parsed = _parse_semantic_response(response_text)
            return _coerce_semantic_findings(project, parsed)

    client = openai.Client(api_key=api_key)
    response = client.responses.create(
        model="gpt-5-chat-latest",
        input=[
            {
                "role": "system",
                "content": "You are a strict documentation reviewer. Output JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        tools=_semantic_tools(),
        tool_choice="auto",
    )

    tool_calls_log: list[dict[str, object]] = []
    content: str | None = None
    for _ in range(8):
        function_calls: list[ResponseFunctionToolCall] = [
            item for item in response.output if isinstance(item, ResponseFunctionToolCall)
        ]
        if not function_calls:
            content = response.output_text
            break

        tool_outputs: ResponseInputParam = []
        for tool_call in function_calls:
            tool_name = tool_call.name
            try:
                tool_arguments_raw = json.loads(tool_call.arguments)
            except json.JSONDecodeError:
                tool_arguments_raw = {}
            tool_arguments = cast(dict[str, object], tool_arguments_raw if isinstance(tool_arguments_raw, dict) else {})

            if tool_name == "list_paths":
                relative_path = tool_arguments.get("relative_path")
                tool_result = _semantic_tool_list_paths(
                    project,
                    relative_path=relative_path if isinstance(relative_path, str) else ".",
                )
            elif tool_name == "read_file":
                relative_path = tool_arguments.get("relative_path")
                if not isinstance(relative_path, str):
                    tool_result = {"ok": False, "error": "Missing or invalid relative_path"}
                else:
                    tool_result = _semantic_tool_read_file(project, relative_path=relative_path)
            elif tool_name == "grep_repo":
                pattern = tool_arguments.get("pattern")
                relative_path = tool_arguments.get("relative_path")
                if not isinstance(pattern, str):
                    tool_result = {"ok": False, "error": "Missing or invalid pattern"}
                else:
                    tool_result = _semantic_tool_grep_repo(
                        project,
                        pattern=pattern,
                        relative_path=relative_path if isinstance(relative_path, str) else ".",
                    )
            else:
                tool_result = {"ok": False, "error": f"Unknown tool: {tool_name}"}

            tool_calls_log.append(
                {
                    "name": tool_name,
                    "arguments": tool_arguments,
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
            model="gpt-5-chat-latest",
            previous_response_id=response.id,
            input=tool_outputs,
        )

    if content is None:
        raise DocsCheckError("Semantic docs check returned no content.")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(
            {
                "prompt": prompt,
                "response": content,
                "projectId": project.project_id or project.name,
                "tool_calls": tool_calls_log,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    parsed = _parse_semantic_response(content)
    return _coerce_semantic_findings(project, parsed)


def _coerce_semantic_findings(project: Project, payload: dict[str, object]) -> list[DocsFinding]:
    findings_raw = as_list(payload.get("findings"))
    if findings_raw is None:
        return []
    findings: list[DocsFinding] = []
    for item in findings_raw[:7]:
        item_dict = as_dict(item)
        if item_dict is None:
            continue
        code = item_dict.get("code")
        message = item_dict.get("message")
        evidence = item_dict.get("evidence")
        if not isinstance(code, str) or not isinstance(message, str):
            continue
        path_value = item_dict.get("path")
        path_text = None
        if isinstance(path_value, str) and path_value.strip():
            path_text = str((project.path / path_value).resolve()) if not Path(path_value).is_absolute() else path_value
        combined_message = message.strip()
        if isinstance(evidence, str) and evidence.strip():
            combined_message += f" Evidence: {evidence.strip()}"
        findings.append(
            DocsFinding(
                code=f"W_DOCS_{code.upper().replace('-', '_')}",
                severity="warning",
                message=combined_message,
                path=path_text,
                source="semantic",
            )
        )
    return findings


def _project_markdown_files(project: Project) -> list[Path]:
    files: list[Path] = []
    readme_path = project.path / "README.md"
    if readme_path.is_file():
        files.append(readme_path)
    docs_path = project.path / "docs"
    if docs_path.is_dir():
        files.extend(sorted(path for path in docs_path.rglob("*.md") if path.is_file()))
    return files


def _url_label(url: str, is_image: bool) -> str:
    host = urlparse(url).netloc.lower()
    if "img.shields.io" in host or is_image:
        return "badge"
    return "link"


def _project_docs_result(
    project: Project,
    *,
    semantic: bool,
    external_url_cache: dict[str, tuple[bool, str]],
    api_key: str | None,
) -> dict[str, object]:
    markdown_files = _project_markdown_files(project)
    result: dict[str, object] = {
        "projectId": project.project_id or project.name,
        "kind": _project_kind(project),
        "path": str(project.path.resolve()),
        "docsEnabled": project.docs_enabled,
        "docsSystem": project.docs_system,
        "filesChecked": [str(path.resolve()) for path in markdown_files],
        "findings": [],
        "snippetSummary": {"checked": 0, "skipped": 0},
        "externalLinksChecked": 0,
    }

    if not markdown_files and not project.docs_enabled:
        result["status"] = "skipped"
        result["reason"] = "no-docs-surface"
        return result

    findings: list[DocsFinding] = []
    findings.extend(_docs_hook_findings(project))
    if not (project.path / "README.md").is_file():
        findings.append(
            DocsFinding(
                code="E_DOCS_MISSING_README",
                severity="error",
                message="Project is missing README.md.",
                path=str((project.path / "README.md").resolve()),
            )
        )

    anchor_cache: dict[Path, set[str]] = {}
    code_blocks: list[FencedCodeBlock] = []

    for markdown_file in markdown_files:
        text = markdown_file.read_text(encoding="utf-8")
        if markdown_file.name == "README.md":
            readme_code_blocks = _markdown_code_blocks(markdown_file, text)
            code_blocks.extend(readme_code_blocks)
            findings.extend(_section_findings(markdown_file, text, readme_code_blocks))
        else:
            code_blocks.extend(_markdown_code_blocks(markdown_file, text))

        links = _markdown_links(markdown_file, text)
        for link in links:
            kind = _link_type(link.target)
            if kind == "skip":
                continue
            if kind == "external":
                if link.target not in external_url_cache:
                    external_url_cache[link.target] = _check_external_url(link.target)
                ok, detail = external_url_cache[link.target]
                external_links_checked = cast(int, result["externalLinksChecked"])
                result["externalLinksChecked"] = external_links_checked + 1
                if not ok:
                    label = _url_label(link.target, link.is_image)
                    findings.append(
                        DocsFinding(
                            code=(
                                "W_DOCS_UNREACHABLE_BADGE_URL"
                                if label == "badge"
                                else "W_DOCS_UNREACHABLE_EXTERNAL_URL"
                            ),
                            severity="warning",
                            message=f"External {label} URL is unreachable: {link.target} ({detail}).",
                            path=str(link.path),
                            line=link.line,
                        )
                    )
                continue

            target_path, fragment = _resolve_internal_target(project, link.path, link.target)
            if target_path is None:
                findings.append(
                    DocsFinding(
                        code="E_DOCS_BROKEN_INTERNAL_LINK",
                        severity="error",
                        message=f"Internal docs link target does not exist: {link.target}.",
                        path=str(link.path),
                        line=link.line,
                    )
                )
                continue
            if fragment:
                if target_path not in anchor_cache:
                    anchor_cache[target_path] = _markdown_anchors(target_path.read_text(encoding="utf-8"))
                if fragment not in anchor_cache[target_path]:
                    findings.append(
                        DocsFinding(
                            code="E_DOCS_BROKEN_ANCHOR",
                            severity="error",
                            message=f"Docs link points to missing anchor #{fragment}: {link.target}.",
                            path=str(link.path),
                            line=link.line,
                        )
                    )

    snippet_findings, snippet_summary = _snippet_findings(code_blocks)
    findings.extend(snippet_findings)
    result["snippetSummary"] = snippet_summary

    if semantic:
        if api_key is None:
            raise DocsCheckError(
                'Semantic docs checking requires an OpenAI key. Add `(openai-key "...")` to root.private.clj '
                "or export OPENAI_API_KEY."
            )
        if markdown_files:
            findings.extend(_semantic_findings(project, markdown_files, api_key=api_key))
            result["semantic"] = {"status": "checked"}
        else:
            result["semantic"] = {"status": "skipped", "reason": "no-markdown-files"}

    result["findings"] = [finding.payload() for finding in findings]
    has_errors = any(finding.severity == "error" for finding in findings)
    has_warnings = any(finding.severity == "warning" for finding in findings)
    if has_errors:
        result["status"] = "error"
    elif has_warnings:
        result["status"] = "warning"
    else:
        result["status"] = "success"
    return result


def _project_snippets_result(
    project: Project,
    *,
    verify: bool,
    redirect_output: bool,
) -> dict[str, object]:
    markdown_files = _project_markdown_files(project)
    code_blocks = _project_code_blocks(markdown_files)
    result: dict[str, object] = {
        "projectId": project.project_id or project.name,
        "kind": _project_kind(project),
        "path": str(project.path.resolve()),
        "filesChecked": [str(path.resolve()) for path in markdown_files],
        "snippetSummary": {"checked": 0, "skipped": 0, "unsupported": 0, "total": 0},
        "findings": [],
    }

    if not code_blocks:
        result["status"] = "skipped"
        result["reason"] = "no-snippets"
        return result

    findings, snippet_summary = _syntax_check_snippets(code_blocks)
    result["snippetSummary"] = snippet_summary

    if verify and isinstance(project, PythonProject):
        hook_path = project.path / "tests" / "test_docs_snippets.py"
        if hook_path.is_file():
            hook_findings, hook_result = _run_python_snippet_hook(project, redirect_output=redirect_output)
            findings.extend(hook_findings)
            result["verification"] = hook_result | {"mode": "python-hook"}
        else:
            result["verification"] = {
                "status": "skipped",
                "reason": "no-project-specific-verifier",
                "mode": "python-hook",
            }

    if verify and isinstance(project, GradleProject):
        has_jvm_snippets = any(_snippet_language(block) in _SNIPPET_JVM_LANGUAGES for block in code_blocks)
        if has_jvm_snippets:
            gradle_findings, gradle_result = _run_gradle_snippet_build(project, redirect_output=redirect_output)
            findings.extend(gradle_findings)
            result["verification"] = gradle_result
        else:
            result["verification"] = {"status": "skipped", "reason": "no-jvm-snippets", "mode": "gradle"}

    if verify and "verification" not in result and not isinstance(project, (PythonProject, GradleProject)):
        result["verification"] = {"status": "skipped", "reason": "unsupported-project-kind"}

    result["findings"] = [finding.payload() for finding in findings]
    has_errors = any(finding.severity == "error" for finding in findings)
    has_warnings = any(finding.severity == "warning" for finding in findings)
    if has_errors:
        result["status"] = "error"
    elif has_warnings:
        result["status"] = "warning"
    else:
        result["status"] = "success"
    return result


def _print_project_result(result: dict[str, object]) -> None:
    project_id = str(result["projectId"])
    status = str(result["status"])
    if status == "skipped":
        info(f"{accent(project_id)}: skipped ({result.get('reason', 'no checks')})")
        return

    header_color = "red" if status == "error" else "yellow" if status == "warning" else "green"
    print(f"{heading(project_id)} [{style(status, header_color, attrs=('bold',))}]")
    findings = cast(list[dict[str, object]], result["findings"])
    if not findings:
        success("  No docs issues found.")
        return
    for finding in findings:
        reporter = error if finding["severity"] == "error" else warning
        location = ""
        if isinstance(finding.get("path"), str):
            location = f" ({finding['path']}"
            if isinstance(finding.get("line"), int):
                location += f":{finding['line']}"
            location += ")"
        reporter(f"  [{finding['code']}] {finding['message']}{location}")


def _print_snippets_result(result: dict[str, object]) -> None:
    project_id = str(result["projectId"])
    status = str(result["status"])
    if status == "skipped":
        info(f"{accent(project_id)}: skipped ({result.get('reason', 'no snippet checks')})")
        return

    header_color = "red" if status == "error" else "yellow" if status == "warning" else "green"
    print(f"{heading(project_id)} [{style(status, header_color, attrs=('bold',))}]")
    findings = cast(list[dict[str, object]], result["findings"])
    if not findings:
        success("  No snippet issues found.")
        return
    for finding in findings:
        reporter = error if finding["severity"] == "error" else warning
        location = ""
        if isinstance(finding.get("path"), str):
            location = f" ({finding['path']}"
            if isinstance(finding.get("line"), int):
                location += f":{finding['line']}"
            location += ")"
        reporter(f"  [{finding['code']}] {finding['message']}{location}")


def _update_summary(payload: dict[str, object]) -> None:
    results = cast(list[dict[str, object]], payload["results"])
    payload["summary"] = {
        "total": len(results),
        "success": sum(1 for result in results if result.get("status") == "success"),
        "warning": sum(1 for result in results if result.get("status") == "warning"),
        "error": sum(1 for result in results if result.get("status") == "error"),
        "skipped": sum(1 for result in results if result.get("status") == "skipped"),
    }


def _update_snippet_summary(payload: dict[str, object]) -> None:
    results = cast(list[dict[str, object]], payload["results"])
    payload["summary"] = {
        "total": len(results),
        "success": sum(1 for result in results if result.get("status") == "success"),
        "warning": sum(1 for result in results if result.get("status") == "warning"),
        "error": sum(1 for result in results if result.get("status") == "error"),
        "skipped": sum(1 for result in results if result.get("status") == "skipped"),
    }


def docs_check(
    projects: str | list[str] | None = None,
    *,
    semantic: bool = False,
    json_output: bool = False,
) -> int:
    requested_projects = [projects] if isinstance(projects, str) else projects
    payload: dict[str, object] = {
        "requestedTargets": list(requested_projects or []),
        "inferredTargets": [],
        "resolvedTargets": [],
        "results": [],
        "semantic": semantic,
    }
    results_payload: list[dict[str, object]] = []
    payload["results"] = results_payload

    def run() -> int:
        config = load_config()
        effective_requested = inferred_project_targets(config, requested_projects)
        if requested_projects is None and effective_requested is not None:
            payload["inferredTargets"] = list(effective_requested)

        selected_project_ids: list[str] | None = None
        if effective_requested:
            try:
                selected_project_ids = resolve_project_ids(config, effective_requested)
            except ValueError as ex:
                payload["error"] = str(ex)
                if not json_output:
                    error(contextualize_failure(str(ex), ["docs", "check", *effective_requested]))
                _update_summary(payload)
                return 1
        if selected_project_ids is None:
            selected_project_ids = list(config.defined_projects.keys())
        payload["resolvedTargets"] = list(selected_project_ids)

        openai_key = getattr(config, "openai_key", None) or os.environ.get("OPENAI_API_KEY")
        external_url_cache: dict[str, tuple[bool, str]] = {}
        for project_id in selected_project_ids:
            project = config.defined_projects[project_id]
            result = _project_docs_result(
                project,
                semantic=semantic,
                external_url_cache=external_url_cache,
                api_key=openai_key,
            )
            results_payload.append(result)
            if not json_output:
                _print_project_result(result)
                print()

        _update_summary(payload)
        summary = cast(dict[str, int], payload["summary"])
        if summary["error"]:
            if not json_output:
                error(
                    f"{heading('Docs summary')}: {summary['error']} error project(s), {summary['warning']} warning project(s)."
                )
            return 1
        if summary["warning"]:
            if not json_output:
                warning(f"{heading('Docs summary')}: {summary['warning']} warning project(s), no blocking docs errors.")
            return 0
        if not json_output:
            success(f"{heading('Docs summary')}: no docs problems found.")
        return 0

    output_context = redirect_stdout(sys.stderr) if json_output else nullcontext()
    with output_context:
        try:
            exit_code = run()
        except DocsCheckError as ex:
            payload["error"] = str(ex)
            _update_summary(payload)
            if not json_output:
                error(str(ex))
            exit_code = 1

    if json_output:
        print(json.dumps(payload, indent=2))
    return exit_code


def docs_snippets(
    projects: str | list[str] | None = None,
    *,
    verify: bool = False,
    json_output: bool = False,
) -> int:
    requested_projects = [projects] if isinstance(projects, str) else projects
    payload: dict[str, object] = {
        "requestedTargets": list(requested_projects or []),
        "inferredTargets": [],
        "resolvedTargets": [],
        "results": [],
        "verify": verify,
    }
    snippet_results_payload: list[dict[str, object]] = []
    payload["results"] = snippet_results_payload

    def run() -> int:
        config = load_config()
        effective_requested = inferred_project_targets(config, requested_projects)
        if requested_projects is None and effective_requested is not None:
            payload["inferredTargets"] = list(effective_requested)

        selected_project_ids: list[str] | None = None
        if effective_requested:
            try:
                selected_project_ids = resolve_project_ids(config, effective_requested)
            except ValueError as ex:
                payload["error"] = str(ex)
                error(contextualize_failure(str(ex), ["docs", "snippets", *effective_requested]))
                _update_snippet_summary(payload)
                return 1
        if selected_project_ids is None:
            selected_project_ids = list(config.defined_projects.keys())
        payload["resolvedTargets"] = list(selected_project_ids)

        for project_id in selected_project_ids:
            project = config.defined_projects[project_id]
            result = _project_snippets_result(
                project,
                verify=verify,
                redirect_output=json_output,
            )
            snippet_results_payload.append(result)
            if not json_output:
                _print_snippets_result(result)
                print()

        _update_snippet_summary(payload)
        summary = cast(dict[str, int], payload["summary"])
        if summary["error"]:
            if not json_output:
                error(
                    f"{heading('Docs snippets summary')}: {summary['error']} error project(s), "
                    f"{summary['warning']} warning project(s)."
                )
            return 1
        if summary["warning"]:
            if not json_output:
                warning(
                    f"{heading('Docs snippets summary')}: {summary['warning']} warning project(s), "
                    "no blocking snippet errors."
                )
            return 0
        if not json_output:
            success(f"{heading('Docs snippets summary')}: no snippet problems found.")
        return 0

    output_context = redirect_stdout(sys.stderr) if json_output else nullcontext()
    with output_context:
        try:
            exit_code = run()
        except DocsCheckError as ex:
            payload["error"] = str(ex)
            _update_snippet_summary(payload)
            if not json_output:
                error(str(ex))
            exit_code = 1

    if json_output:
        print(json.dumps(payload, indent=2))
    return exit_code


__all__ = ["docs_check", "docs_snippets"]
