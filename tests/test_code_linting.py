from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dev.checks.base import FileContext
from dev.checks.code_linting import (
    E_CSHARPIER_FAILED,
    E_CSHARPIER_MISSING,
    E_CS_NOT_FORMATTED,
    E_KTFMT_FAILED,
    E_KTFMT_MISSING,
    E_KOTLIN_NOT_FORMATTED,
    CSharpFormattingCheck,
    KotlinFormattingCheck,
)


def test_kotlin_formatting_check_reports_missing_when_ktfmt_jar_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "Sample.kt"
    path.write_text("fun main() = Unit\n", encoding="utf-8")
    ctx = FileContext(check_name="KotlinFormattingCheck", path=path)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="Error: Unable to access jarfile ktfmt-0.59-with-dependencies.jar",
        )

    monkeypatch.setattr("dev.checks.code_linting.subprocess.run", fake_run)

    KotlinFormattingCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues.issues] == [E_KTFMT_MISSING]


def test_kotlin_formatting_check_reports_failure_for_formatter_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "Sample.kt"
    path.write_text("fun main() = Unit\n", encoding="utf-8")
    ctx = FileContext(check_name="KotlinFormattingCheck", path=path)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout="",
            stderr="Exception in thread 'main' java.lang.IllegalStateException: boom",
        )

    monkeypatch.setattr("dev.checks.code_linting.subprocess.run", fake_run)

    KotlinFormattingCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues.issues] == [E_KTFMT_FAILED]


def test_kotlin_formatting_check_reports_unformatted_for_style_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "Sample.kt"
    path.write_text("fun main(){println(\"x\")}\n", encoding="utf-8")
    ctx = FileContext(check_name="KotlinFormattingCheck", path=path)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="Sample.kt would be reformatted\n",
            stderr="",
        )

    monkeypatch.setattr("dev.checks.code_linting.subprocess.run", fake_run)

    KotlinFormattingCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues.issues] == [E_KOTLIN_NOT_FORMATTED]


def test_csharp_formatting_check_reports_missing_when_dotnet_tool_missing_and_no_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "Sample.cs"
    path.write_text("class C {}\n", encoding="utf-8")
    ctx = FileContext(check_name="CSharpFormattingCheck", path=path)

    calls = {"count": 0}

    def fake_run(_self: CSharpFormattingCheck, args: list[str]) -> subprocess.CompletedProcess[str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(
                args=args,
                returncode=1,
                stdout="",
                stderr="Could not execute because the specified command or file was not found.",
            )
        raise FileNotFoundError("csharpier")

    monkeypatch.setattr(CSharpFormattingCheck, "_run", fake_run)

    CSharpFormattingCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues.issues] == [E_CSHARPIER_MISSING]


def test_csharp_formatting_check_reports_failure_for_formatter_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "Sample.cs"
    path.write_text("class C {}\n", encoding="utf-8")
    ctx = FileContext(check_name="CSharpFormattingCheck", path=path)

    calls = {"count": 0}

    def fake_run(_self: CSharpFormattingCheck, args: list[str]) -> subprocess.CompletedProcess[str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(
                args=args,
                returncode=2,
                stdout="",
                stderr="Unhandled exception: parser crashed",
            )
        return subprocess.CompletedProcess(
            args=args,
            returncode=2,
            stdout="",
            stderr="legacy formatter crashed",
        )

    monkeypatch.setattr(CSharpFormattingCheck, "_run", fake_run)

    CSharpFormattingCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues.issues] == [E_CSHARPIER_FAILED]


def test_csharp_formatting_check_reports_unformatted_for_style_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "Sample.cs"
    path.write_text("class C{}\n", encoding="utf-8")
    ctx = FileContext(check_name="CSharpFormattingCheck", path=path)

    calls = {"count": 0}

    def fake_run(_self: CSharpFormattingCheck, args: list[str]) -> subprocess.CompletedProcess[str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(
                args=args,
                returncode=1,
                stdout="Needs formatting",
                stderr="",
            )
        raise FileNotFoundError("csharpier")

    monkeypatch.setattr(CSharpFormattingCheck, "_run", fake_run)

    CSharpFormattingCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues.issues] == [E_CS_NOT_FORMATTED]


def test_csharp_formatting_check_fix_uses_legacy_runner_when_dotnet_tool_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "Sample.cs"
    path.write_text("class C{}\n", encoding="utf-8")
    ctx = FileContext(check_name="CSharpFormattingCheck", path=path)

    calls = {"count": 0}

    def fake_run(_self: CSharpFormattingCheck, args: list[str]) -> subprocess.CompletedProcess[str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(
                args=args,
                returncode=1,
                stdout="",
                stderr="Could not execute because the specified command or file was not found.",
            )
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="Needs formatting",
            stderr="",
        )

    fix_invocations: list[list[str]] = []

    def fake_subprocess_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        fix_invocations.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(CSharpFormattingCheck, "_run", fake_run)
    monkeypatch.setattr("dev.checks.code_linting.subprocess.run", fake_subprocess_run)

    CSharpFormattingCheck().check(ctx)

    issues = ctx.issues.issues
    assert [issue.issue_type for issue in issues] == [E_CS_NOT_FORMATTED]
    assert issues[0].fix is not None

    issues[0].fix()

    assert fix_invocations == [["csharpier", str(path)]]
