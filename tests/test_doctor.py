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

    monkeypatch.setattr(
        doctor_task, "load_config", lambda start=None: SimpleNamespace(openai_key=None, defined_projects={})
    )

    findings = collect_doctor_findings(check_ids=("commit-openai",), ctx=DoctorContext(cwd=tmp_path))

    assert len(findings) == 1
    assert findings[0].status == DoctorStatus.FAIL
    assert "OpenAI key" in findings[0].detail


def test_workspace_root_finding_passes_for_nested_subdirectory(tmp_path) -> None:
    from dev.tasks.doctor import DoctorContext, DoctorStatus, collect_doctor_findings

    workspace_root = tmp_path / "workspace"
    nested = workspace_root / "apps" / "demo"
    nested.mkdir(parents=True, exist_ok=True)
    (workspace_root / "root.clj").write_text("()", encoding="utf-8")

    findings = collect_doctor_findings(check_ids=("workspace-root",), ctx=DoctorContext(cwd=nested))

    assert len(findings) == 1
    assert findings[0].status == DoctorStatus.PASS
    assert str(workspace_root) in findings[0].detail


def test_preflight_for_command_prints_doctor_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
                fix="Run `dev check config` after fixing root.clj.",
            )
        ],
    )

    ok = doctor_task.preflight_for_command("build", prog="dev")

    assert ok is False
    output = capsys.readouterr().out
    assert "Preflight checks failed for `build`." in output
    assert "Run `dev doctor --only build` for targeted diagnostics" in output


def test_resolve_doctor_check_ids_expands_command_groups() -> None:
    from dev.tasks.doctor import resolve_doctor_check_ids

    check_ids = resolve_doctor_check_ids(["publish", "gradle"])

    assert "gradle" in check_ids
    assert "publish-pypi" in check_ids
    assert "publish-maven-central" in check_ids
    assert "publish-intellij" in check_ids
    assert "publish-jitpack" in check_ids


def test_doctor_json_output_includes_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import dev.tasks.doctor as doctor_task
    from dev.tasks.doctor import DoctorFinding, DoctorStatus

    monkeypatch.setattr(
        doctor_task,
        "collect_doctor_findings",
        lambda check_ids=doctor_task.FULL_CHECK_ORDER, ctx=None: [
            DoctorFinding(
                key="git",
                label="git",
                status=DoctorStatus.PASS,
                detail="Found git.",
            ),
            DoctorFinding(
                key="config",
                label="Config load",
                status=DoctorStatus.WARN,
                detail="Config warning.",
            ),
        ],
    )

    result = doctor_task.doctor(json_output=True)

    assert result == 0
    output = capsys.readouterr().out
    assert '"selectedTargets": []' in output
    assert '"resolvedChecks"' in output
    assert '"summary"' in output
    assert '"pass": 1' in output
    assert '"warn": 1' in output
    assert '"findings"' in output


def test_doctor_json_output_includes_only_and_targets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.doctor as doctor_task
    from dev.tasks.doctor import DoctorFinding, DoctorStatus

    monkeypatch.setattr(
        doctor_task,
        "collect_doctor_findings",
        lambda *, check_ids, ctx=None: [
            DoctorFinding(
                key=check_ids[0],
                label="Gradle",
                status=DoctorStatus.PASS,
                detail="Found Gradle.",
            )
        ],
    )

    result = doctor_task.doctor(json_output=True, only=["build"], targets=["app-wabbit-dev"])

    assert result == 0
    output = capsys.readouterr().out
    assert '"requestedOnly": [' in output
    assert '"build"' in output
    assert '"selectedTargets": [' in output
    assert '"app-wabbit-dev"' in output


def test_publish_pypi_doctor_is_advisory_by_default(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dev.tasks.doctor as doctor_task
    from dev.tasks.doctor import DoctorContext, DoctorStatus, collect_doctor_findings

    project = SimpleNamespace(project_id="python-easytime", name="python-easytime")
    monkeypatch.setattr(
        doctor_task,
        "load_config",
        lambda start=None: SimpleNamespace(
            pypi_token=None,
            maven_username=None,
            maven_password=None,
            maven_gpg_private_key=None,
            maven_gpg_passphrase=None,
            jetbrains_marketplace_token=None,
            openai_key=None,
            defined_projects={},
        ),
    )
    monkeypatch.setattr(doctor_task, "_publish_target_projects", lambda config, target_name, ctx: [project])
    monkeypatch.delenv("TWINE_PASSWORD", raising=False)

    findings = collect_doctor_findings(check_ids=("publish-pypi",), ctx=DoctorContext(cwd=tmp_path))

    assert len(findings) == 1
    assert findings[0].status == DoctorStatus.PASS
    assert "GitHub Actions" in findings[0].detail
    assert "local PyPI credentials" in findings[0].detail


def test_publish_pypi_preflight_stays_strict(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dev.tasks.doctor as doctor_task
    from dev.tasks.doctor import DoctorContext, DoctorStatus, collect_doctor_findings

    project = SimpleNamespace(project_id="python-easytime", name="python-easytime")
    monkeypatch.setattr(
        doctor_task,
        "load_config",
        lambda start=None: SimpleNamespace(
            pypi_token=None,
            maven_username=None,
            maven_password=None,
            maven_gpg_private_key=None,
            maven_gpg_passphrase=None,
            jetbrains_marketplace_token=None,
            openai_key=None,
            defined_projects={},
        ),
    )
    monkeypatch.setattr(doctor_task, "_publish_target_projects", lambda config, target_name, ctx: [project])
    monkeypatch.delenv("TWINE_PASSWORD", raising=False)

    findings = collect_doctor_findings(
        check_ids=("publish-pypi",),
        ctx=DoctorContext(
            cwd=tmp_path,
            publish_credential_mode=doctor_task.PublishCredentialMode.STRICT,
        ),
    )

    assert len(findings) == 1
    assert findings[0].status == DoctorStatus.FAIL
    assert "Missing PyPI credentials" in findings[0].detail
