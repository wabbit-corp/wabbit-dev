from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_root_private_finding_fails_when_missing(tmp_path) -> None:
    from dev.tasks.doctor import DoctorContext, DoctorStatus, collect_doctor_findings

    (tmp_path / "root.clj").write_text("()", encoding="utf-8")

    findings = collect_doctor_findings(check_ids=("root-private-clj",), ctx=DoctorContext(cwd=tmp_path))

    assert len(findings) == 1
    assert findings[0].status == DoctorStatus.FAIL
    assert "root.private.clj" in findings[0].detail


def test_commit_openai_finding_requires_configured_key(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dev.tasks.doctor as doctor_task
    from dev.tasks.doctor import DoctorContext, DoctorStatus, collect_doctor_findings

    (tmp_path / "root.clj").write_text("()", encoding="utf-8")
    (tmp_path / "root.private.clj").write_text("()", encoding="utf-8")

    monkeypatch.setattr(doctor_task, "load_config", lambda: SimpleNamespace(openai_key=None, defined_projects={}))

    findings = collect_doctor_findings(check_ids=("commit-openai",), ctx=DoctorContext(cwd=tmp_path))

    assert len(findings) == 1
    assert findings[0].status == DoctorStatus.FAIL
    assert "OpenAI key" in findings[0].detail


def test_preflight_for_command_prints_doctor_hint(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import dev.tasks.doctor as doctor_task
    from dev.tasks.doctor import DoctorFinding, DoctorStatus

    monkeypatch.setattr(
        doctor_task,
        "collect_doctor_findings",
        lambda *, check_ids, ctx=None: [
            DoctorFinding(
                key="config",
                label="Config load",
                status=DoctorStatus.FAIL,
                detail="Failed to parse workspace config.",
                fix="Run `wabbit-dev config check` after fixing root.clj.",
            )
        ],
    )

    ok = doctor_task.preflight_for_command("build", prog="dev.py")

    assert ok is False
    output = capsys.readouterr().out
    assert "Preflight checks failed for `build`." in output
    assert "Run `dev.py doctor` for a full environment check." in output
