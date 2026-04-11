from __future__ import annotations

import json
from pathlib import Path

import pytest
from mu.parser import parse


def _make_python_project(path: Path):
    from dev.config import OwnershipType, PythonProject

    return PythonProject(
        path=path,
        name="alpha",
        version=None,
        description="Alpha project",
        authors=["Dev"],
        license="AGPL",
        github_repo="wabbit-corp/alpha",
        requires_python=">=3.12",
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        application=None,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=False,
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
        project_id="alpha",
        docs_enabled=True,
        docs_system="mkdocs",
    )


def _make_gradle_project(path: Path):
    from dev.config import GradleProject, OwnershipType, Version

    return GradleProject(
        path=path,
        group_name="one.wabbit",
        name="alpha",
        version=Version.parse("0.1.0"),
        description="Alpha project",
        authors=["Dev"],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo="wabbit-corp/alpha",
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        project_id="alpha",
        docs_enabled=True,
        docs_system="dokka",
    )


def _write_common_docs(project_path: Path, *, readme_text: str, install_text: str = "# Install\n") -> None:
    (project_path / "README.md").write_text(readme_text, encoding="utf-8")
    (project_path / "mkdocs.yml").write_text("site_name: alpha\n", encoding="utf-8")
    (project_path / "docs").mkdir(parents=True, exist_ok=True)
    (project_path / "docs" / "index.md").write_text("# Docs\n", encoding="utf-8")
    (project_path / "docs" / "installation.md").write_text(install_text, encoding="utf-8")
    (project_path / "scripts").mkdir(parents=True, exist_ok=True)
    (project_path / "scripts" / "generate_api_docs.py").write_text("print('ok')\n", encoding="utf-8")
    (project_path / "scripts" / "check_docs_links.py").write_text("print('ok')\n", encoding="utf-8")
    (project_path / "tests").mkdir(parents=True, exist_ok=True)
    (project_path / "tests" / "test_docs_snippets.py").write_text("def test_docs():\n    pass\n", encoding="utf-8")


def test_docs_check_json_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text=(
            "# Alpha\n\n"
            "Alpha is a small developer library that exists to make alpha workflows predictable for integrations.\n\n"
            "## Status\n\n"
            "Experimental but maintained.\n\n"
            "## Installation\n\n"
            "Install it.\n\n"
            "## Quickstart\n\n"
            "[Install docs](docs/installation.md#install)\n\n"
            "[API docs](docs/index.md)\n\n"
            "[Issues](https://github.com/wabbit-corp/alpha/issues)\n\n"
            "[Changelog](CHANGELOG.md)\n\n"
            "## Examples\n\n"
            "```python\nprint('ok')\n```\n"
        ),
    )
    (project_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(docs_task, "_check_external_url", lambda url, timeout_seconds=5.0: (True, "HTTP 200"))

    result = docs_task.docs_check(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resolvedTargets"] == ["alpha"]
    assert payload["summary"]["success"] == 1
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][0]["snippetSummary"]["checked"] == 1


def test_docs_check_json_reports_broken_link_and_invalid_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text=(
            "# Alpha\n\n"
            "## Installation\n\n"
            "[Missing docs](docs/missing.md)\n\n"
            "## Quickstart\n\n"
            "```python\ndef broken(:\n    pass\n```\n"
        ),
    )
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(docs_task, "_check_external_url", lambda url, timeout_seconds=5.0: (True, "HTTP 200"))

    result = docs_task.docs_check(["alpha"], json_output=True)

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    findings = payload["results"][0]["findings"]
    codes = {finding["code"] for finding in findings}
    assert "E_DOCS_BROKEN_INTERNAL_LINK" in codes
    assert "E_DOCS_SNIPPET_INVALID_PYTHON" in codes


def test_docs_check_accepts_plain_text_support_and_changelog_mentions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text=(
            "# Alpha\n\n"
            "Alpha is a small developer library that exists to make alpha workflows predictable for integrations.\n\n"
            "## Status\n\n"
            "Experimental but maintained.\n\n"
            "## Installation\n\n"
            "Install it.\n\n"
            "## Quickstart\n\n"
            "[API docs](docs/index.md)\n\n"
            "## Documentation\n\n"
            "- Changelog and release notes: `CHANGELOG.md`\n"
            "- Support and bug reports: https://github.com/wabbit-corp/alpha/issues\n"
            "- Security-sensitive questions: support@wabbit.one\n\n"
            "## Examples\n\n"
            "```python\nprint('ok')\n```\n"
        ),
    )
    (project_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(docs_task, "_check_external_url", lambda url, timeout_seconds=5.0: (True, "HTTP 200"))

    result = docs_task.docs_check(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    codes = {finding["code"] for finding in payload["results"][0]["findings"]}
    assert "W_DOCS_MISSING_SUPPORT_LINK" not in codes
    assert "W_DOCS_MISSING_CHANGELOG_LINK" not in codes


def test_docs_check_semantic_requires_openai_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text=(
            "# Alpha\n\n"
            "Alpha is a small developer library that exists to make alpha workflows predictable for integrations.\n\n"
            "## Status\n\n"
            "Experimental but maintained.\n\n"
            "## Installation\n\n"
            "## Quickstart\n\n"
            "[API docs](docs/index.md)\n\n"
            "[Issues](https://github.com/wabbit-corp/alpha/issues)\n\n"
            "[Changelog](CHANGELOG.md)\n\n"
            "## Examples\n\n"
            "```python\nprint('ok')\n```\n"
        ),
    )
    (project_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project
    config.openai_key = None

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(docs_task, "_check_external_url", lambda url, timeout_seconds=5.0: (True, "HTTP 200"))

    result = docs_task.docs_check(["alpha"], semantic=True, json_output=True)

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert "OpenAI key" in payload["error"]


def test_docs_check_semantic_adds_advisory_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text=(
            "# Alpha\n\n"
            "Alpha is a small developer library that exists to make alpha workflows predictable for integrations.\n\n"
            "## Status\n\n"
            "Experimental but maintained.\n\n"
            "## Installation\n\n"
            "## Quickstart\n\n"
            "[API docs](docs/index.md)\n\n"
            "[Issues](https://github.com/wabbit-corp/alpha/issues)\n\n"
            "[Changelog](CHANGELOG.md)\n\n"
            "## Examples\n\n"
            "```python\nprint('ok')\n```\n"
        ),
    )
    (project_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project
    config.openai_key = "test-key"

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(docs_task, "_check_external_url", lambda url, timeout_seconds=5.0: (True, "HTTP 200"))
    monkeypatch.setattr(
        docs_task,
        "_semantic_findings",
        lambda project, markdown_files, api_key: [
            docs_task.DocsFinding(
                code="W_DOCS_WEAK_QUICKSTART",
                severity="warning",
                message="Quickstart is too abstract for a first-time user.",
                path=str((project.path / "README.md").resolve()),
                source="semantic",
            )
        ],
    )

    result = docs_task.docs_check(["alpha"], semantic=True, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["warning"] == 1
    findings = payload["results"][0]["findings"]
    assert findings[0]["source"] == "semantic"


def test_docs_check_json_suppresses_summary_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text=(
            "# Alpha\n\n"
            "Alpha is a small developer library that exists to make alpha workflows predictable.\n\n"
            "## Status\n\nExperimental.\n\n"
            "## Installation\n\n"
            "## Quickstart\n\n"
            "[API docs](docs/index.md)\n\n"
            "[Issues](https://github.com/wabbit-corp/alpha/issues)\n\n"
            "[Changelog](CHANGELOG.md)\n\n"
            "## Examples\n\n```python\nprint('ok')\n```\n"
        ),
    )
    (project_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project
    config.openai_key = "test-key"

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(docs_task, "_check_external_url", lambda url, timeout_seconds=5.0: (True, "HTTP 200"))
    monkeypatch.setattr(docs_task, "_semantic_findings", lambda project, markdown_files, api_key: [])

    result = docs_task.docs_check(["alpha"], semantic=True, json_output=True)

    assert result == 0
    output = capsys.readouterr().out
    assert output.lstrip().startswith("{")


def test_semantic_prompt_includes_new_semantic_categories_and_project_facts(tmp_path: Path) -> None:
    import dev.tasks.docs_check as docs_task

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    readme_path = project_path / "README.md"
    readme_path.write_text("# Alpha\n\nAlpha docs.\n", encoding="utf-8")
    project = _make_python_project(project_path)
    project.description = "Alpha project"
    project.publish_target = "pypi"

    prompt = docs_task._semantic_prompt(project, [readme_path])

    assert '"projectKind": "python"' in prompt
    assert '"githubRepo": "wabbit-corp/alpha"' in prompt
    assert '"publishTarget": "pypi"' in prompt
    assert '"docsFiles": [' in prompt
    assert "missing-project-why" in prompt
    assert "quickstart-not-actionable" in prompt
    assert "examples-not-core-or-compelling" in prompt
    assert "docs-audience-mismatch" in prompt
    assert "maturity-or-status-misleading" in prompt
    assert "docs-journey-fragmented" in prompt
    assert "support-path-unclear" in prompt
    assert "readme-first-use-buried" in prompt
    assert "one-sentence description" in prompt
    assert "concrete quick start code example" in prompt
    assert "You may use the provided local tools" in prompt


def test_semantic_coercion_preserves_readme_first_use_buried_code(tmp_path: Path) -> None:
    import dev.tasks.docs_check as docs_task

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    project = _make_python_project(project_path)

    findings = docs_task._coerce_semantic_findings(
        project,
        {
            "findings": [
                {
                    "code": "readme-first-use-buried",
                    "severity": "warning",
                    "path": "README.md",
                    "message": "README postpones concrete usage until after topology and philosophy sections.",
                    "evidence": "The first code example appears only after module tables and artifact coordinates.",
                }
            ]
        },
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "W_DOCS_README_FIRST_USE_BURIED"
    assert finding.source == "semantic"
    assert finding.path == str((project_path / "README.md").resolve())
    assert "Evidence:" in finding.message


def test_semantic_tools_can_list_read_and_grep_project_files(tmp_path: Path) -> None:
    import dev.tasks.docs_check as docs_task

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    (project_path / "README.md").write_text("# Alpha\n\nQuickstart here.\n", encoding="utf-8")
    (project_path / "docs").mkdir()
    (project_path / "docs" / "index.md").write_text("# Docs\n\nSupport via issues.\n", encoding="utf-8")
    (project_path / "mkdocs.yml").write_text("site_name: Alpha\n", encoding="utf-8")
    project = _make_python_project(project_path)

    listed = docs_task._semantic_tool_list_paths(project, relative_path=".")
    assert listed["ok"] is True
    listed_paths = {entry["path"] for entry in listed["entries"]}
    assert "README.md" in listed_paths
    assert "docs" in listed_paths
    assert "mkdocs.yml" in listed_paths

    read = docs_task._semantic_tool_read_file(project, relative_path="mkdocs.yml")
    assert read["ok"] is True
    assert "site_name: Alpha" in str(read["content"])

    grep = docs_task._semantic_tool_grep_repo(project, pattern="Quickstart|Support", relative_path=".")
    assert grep["ok"] is True
    matches = grep["matches"]
    assert isinstance(matches, list)
    joined = "\n".join(matches)
    assert "README.md" in joined or "docs/index.md" in joined


def test_docs_check_reports_missing_readme_quality_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text=(
            "# Alpha\n\n" "## Installation\n\n" "Install it.\n\n" "## Quickstart\n\n" "```python\nprint('ok')\n```\n"
        ),
    )
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(docs_task, "_check_external_url", lambda url, timeout_seconds=5.0: (True, "HTTP 200"))

    result = docs_task.docs_check(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    codes = {finding["code"] for finding in payload["results"][0]["findings"]}
    assert "W_DOCS_MISSING_PROJECT_PURPOSE" in codes
    assert "W_DOCS_MISSING_PROJECT_STATUS" in codes
    assert "W_DOCS_MISSING_DOCS_LINK" in codes
    assert "W_DOCS_MISSING_SUPPORT_LINK" in codes
    assert "W_DOCS_MISSING_CHANGELOG_LINK" in codes


def test_docs_snippets_json_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text=(
            "# Alpha\n\n"
            "Alpha is a small developer library that exists to make alpha workflows predictable for integrations.\n\n"
            "## Examples\n\n"
            "```python\nprint('ok')\n```\n\n"
            '```json\n{"ok": true}\n```\n'
        ),
    )
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))

    result = docs_task.docs_snippets(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["success"] == 1
    assert payload["results"][0]["snippetSummary"]["checked"] == 2
    assert payload["results"][0]["status"] == "success"


def test_docs_snippets_runs_python_hook_when_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text="# Alpha\n\n## Examples\n\n```python\nprint('ok')\n```\n",
    )
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    commands: list[list[str]] = []

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(
        docs_task.subprocess,
        "run",
        lambda command, cwd, check, **kwargs: commands.append(command) or None,
    )

    result = docs_task.docs_snippets(["alpha"], verify=True, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["verification"]["status"] == "success"
    assert commands == [[docs_task.sys.executable, "-m", "pytest", "-q", "tests/test_docs_snippets.py"]]


def test_docs_snippets_warns_when_python_hook_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    _write_common_docs(
        project_path,
        readme_text="# Alpha\n\n## Examples\n\n```python\nprint('ok')\n```\n",
    )
    (project_path / "tests" / "test_docs_snippets.py").unlink()
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))

    result = docs_task.docs_snippets(["alpha"], verify=True, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["success"] == 1
    assert payload["results"][0]["verification"]["status"] == "skipped"


def test_docs_snippets_runs_gradle_build_when_verify_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    (project_path / "README.md").write_text(
        '# Alpha\n\n## Examples\n\n```kotlin\nprintln("ok")\n```\n',
        encoding="utf-8",
    )
    project = _make_gradle_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(
        docs_task,
        "_run_gradle_snippet_build",
        lambda project, redirect_output: ([], {"status": "success", "mode": "coarse-project-build"}),
    )

    result = docs_task.docs_snippets(["alpha"], verify=True, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["verification"]["status"] == "success"


def test_docs_snippets_kmp_gradle_build_uses_multiplatform_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.docs_check as docs_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    (project_path / "README.md").write_text(
        '# Alpha\n\n## Examples\n\n```kotlin\nprintln("ok")\n```\n',
        encoding="utf-8",
    )
    (project_path / "gradlew").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    project = _make_gradle_project(project_path)
    project.build_model = "kmp"
    project.platforms = ["jvm", "linuxX64", "mingwX64"]

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    commands: list[list[str]] = []

    monkeypatch.setattr(docs_task, "load_config", lambda: config)
    monkeypatch.setattr(docs_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(
        docs_task.subprocess,
        "run",
        lambda command, cwd, check, **kwargs: commands.append(command) or None,
    )

    result = docs_task.docs_snippets(["alpha"], verify=True, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["verification"]["status"] == "success"
    assert payload["results"][0]["verification"]["mode"] == "kmp-multiplatform-publication"
    assert commands == [["./gradlew", "--no-daemon", "publishKotlinMultiplatformPublicationToMavenLocal"]]
