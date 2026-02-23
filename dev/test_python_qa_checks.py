from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import dev.checks.python_qa_common as qa


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    qa.reset_all_python_qa_state()


def _make_executable(path: Path, content: str = "#!/bin/sh\nexit 0\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def test_target_first_fallback_configs(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "mypy.ini").write_text("[mypy]\n", encoding="utf-8")
    (tmp_path / "pyrightconfig.json").write_text("{}\n", encoding="utf-8")

    state = qa._get_state(tmp_path)
    assert state.pyproject_config == tmp_path / "pyproject.toml"
    assert state.mypy_config == tmp_path / "mypy.ini"
    assert state.pyright_config == tmp_path / "pyrightconfig.json"

    qa.reset_all_python_qa_state()
    other = tmp_path / "other"
    other.mkdir()
    state_fallback = qa._get_state(other)
    assert state_fallback.pyproject_config == qa.LEGACY_FALLBACK_PYPROJECT
    assert state_fallback.mypy_config == qa.LEGACY_FALLBACK_MYPY
    assert state_fallback.pyright_config == qa.LEGACY_FALLBACK_PYRIGHT


def test_coverage_report_skips_when_pytest_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    python_bin = tmp_path / ".venv" / "bin" / "python"
    _make_executable(python_bin)

    calls: list[str] = []

    def fake_tool_executable(state: qa.PythonQaRepoState, name: str) -> Path | None:
        if name == "pytest":
            path = state.bin_dir / "pytest"
            _make_executable(path)
            return path
        return None

    def fake_run_subprocess(
        state: qa.PythonQaRepoState,
        label: str,
        cmd: list[str] | tuple[str, ...],
    ) -> qa.ToolRunResult:
        calls.append(label)
        if label == "coverage run (pytest)":
            return qa.ToolRunResult(rc=1, issues=[])
        if label == "coverage report":
            return qa.ToolRunResult(rc=0, issues=[qa._failed_issue("coverage report", "unexpected", state.root)])
        return qa.ToolRunResult(rc=0, issues=[])

    monkeypatch.setattr(qa, "_coverage_available", lambda state: True)
    monkeypatch.setattr(qa, "_tool_executable", fake_tool_executable)
    monkeypatch.setattr(qa, "_run_subprocess", fake_run_subprocess)

    issues = qa.run_coverage_report(tmp_path, None)
    assert issues == []
    assert calls == ["coverage run (pytest)"]


def test_unittest_enabled_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    python_bin = tmp_path / ".venv" / "bin" / "python"
    _make_executable(python_bin)

    called: list[str] = []

    def fake_run_subprocess(
        state: qa.PythonQaRepoState,
        label: str,
        cmd: list[str] | tuple[str, ...],
    ) -> qa.ToolRunResult:
        called.append(label)
        return qa.ToolRunResult(rc=0, issues=[])

    monkeypatch.setattr(qa, "_run_subprocess", fake_run_subprocess)

    issues = qa.run_unittest(tmp_path, None)
    assert issues == []
    assert called == ["unittest"]


def test_pytest_and_unittest_both_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    python_bin = tmp_path / ".venv" / "bin" / "python"
    _make_executable(python_bin)

    labels: list[str] = []

    def fake_tool_executable(state: qa.PythonQaRepoState, name: str) -> Path | None:
        path = state.bin_dir / name
        _make_executable(path)
        return path

    def fake_run_subprocess(
        state: qa.PythonQaRepoState,
        label: str,
        cmd: list[str] | tuple[str, ...],
    ) -> qa.ToolRunResult:
        labels.append(label)
        return qa.ToolRunResult(rc=0, issues=[])

    monkeypatch.setattr(qa, "_tool_executable", fake_tool_executable)
    monkeypatch.setattr(qa, "_coverage_available", lambda state: False)
    monkeypatch.setattr(qa, "_run_subprocess", fake_run_subprocess)

    assert qa.run_pytest(tmp_path, None) == []
    assert qa.run_unittest(tmp_path, None) == []
    assert labels == ["pytest", "unittest"]


def test_subprocess_launch_failure_reports_tool_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    python_bin = tmp_path / ".venv" / "bin" / "python"
    _make_executable(python_bin)

    def fake_run(*args: object, **kwargs: object) -> object:
        raise OSError("boom")

    monkeypatch.setattr(qa.subprocess, "run", fake_run)

    issues = qa.run_unittest(tmp_path, None)
    assert len(issues) == 1
    assert issues[0].issue_type.id == "E_PYQA_TOOL_FAILED"


def test_run_subprocess_dedupes_identical_parsed_issues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    state = qa._get_state(tmp_path)

    monkeypatch.setattr(
        qa.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )

    duplicate = qa.PytestIssue(
        outcome="ERROR",
        nodeid="",
        message="collection failure",
        location=qa.issue_location(None),
    )
    monkeypatch.setattr(
        qa,
        "parse_issues",
        lambda label, log_path, fail_under: [duplicate, duplicate],
    )

    result = qa._run_subprocess(state, "pytest", ["pytest"])
    assert len(result.issues) == 1


def test_run_subprocess_merges_pytest_issues_with_same_root_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    state = qa._get_state(tmp_path)

    monkeypatch.setattr(
        qa.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )

    monkeypatch.setattr(
        qa,
        "parse_issues",
        lambda label, log_path, fail_under: [
            qa.PytestIssue(
                outcome="ERROR",
                nodeid="dev.test_a",
                message="ImportError while importing test module",
                location=qa.issue_location(None),
            ),
            qa.PytestIssue(
                outcome="ERROR",
                nodeid="dev.test_b",
                message="ImportError while importing test module",
                location=qa.issue_location(None),
            ),
        ],
    )

    result = qa._run_subprocess(state, "pytest", ["pytest"])
    assert len(result.issues) == 1
    assert "dev.test_a" in (result.issues[0].data or {}).get("message", "")
    assert "dev.test_b" in (result.issues[0].data or {}).get("message", "")


def test_run_subprocess_merges_unittest_issues_with_same_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    state = qa._get_state(tmp_path)

    monkeypatch.setattr(
        qa.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )

    monkeypatch.setattr(
        qa,
        "parse_issues",
        lambda label, log_path, fail_under: [
            qa.UnittestIssue(
                outcome="ERROR",
                test="dev.test_a (unittest.loader._FailedTest.dev.test_a)",
                message="ModuleNotFoundError: No module named 'dateparser'",
            ),
            qa.UnittestIssue(
                outcome="ERROR",
                test="dev.test_b (unittest.loader._FailedTest.dev.test_b)",
                message="ModuleNotFoundError: No module named 'dateparser'",
            ),
        ],
    )

    result = qa._run_subprocess(state, "unittest", ["python", "-m", "unittest"])
    assert len(result.issues) == 1
    assert "dev.test_a" in (result.issues[0].data or {}).get("message", "")
    assert "dev.test_b" in (result.issues[0].data or {}).get("message", "")


def test_pytest_issue_message_includes_nodeid() -> None:
    code, message = qa._issue_code_and_message(
        qa.PytestIssue(
            outcome="ERROR",
            nodeid="tests/test_mod.py::test_collect",
            message="collection failure",
            location=qa.issue_location("tests/test_mod.py"),
        )
    )
    assert code == "ERROR"
    assert "tests/test_mod.py::test_collect" in message


def test_unittest_issue_message_includes_test_name() -> None:
    code, message = qa._issue_code_and_message(
        qa.UnittestIssue(
            outcome="ERROR",
            test="test_add (tests.test_math.TestMath)",
            message="Unittest failure",
        )
    )
    assert code == "ERROR"
    assert "test_add (tests.test_math.TestMath)" in message


def test_failure_issue_includes_detail_line_for_deptry() -> None:
    issue = qa.failure_issue(
        "deptry",
        "Traceback (most recent call last):\nerror: Could not parse pyproject.toml\n",
        rc=1,
    )
    assert isinstance(issue, qa.DeptryFailure)
    assert "Could not parse pyproject.toml" in issue.message
    assert "exit code 1" in issue.message


def test_run_subprocess_failure_with_empty_output_includes_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    state = qa._get_state(tmp_path)

    monkeypatch.setattr(
        qa.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )
    monkeypatch.setattr(qa, "parse_issues", lambda label, log_path, fail_under: [])

    result = qa._run_subprocess(state, "deptry", ["deptry", ".", "--config", "pyproject.toml"])
    assert len(result.issues) == 1
    issue_message = (result.issues[0].data or {}).get("message", "")
    assert "no output" in issue_message
    assert "--config pyproject.toml" in issue_message
