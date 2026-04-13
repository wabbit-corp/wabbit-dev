from __future__ import annotations

import pytest


def test_list_checks_includes_spdx_and_fixability(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.list_checks()

    assert result == 0
    output = capsys.readouterr().out
    assert "spdx-header" in output
    assert "SpdxHeaderCheck" in output
    assert "ManagedGeneratedFileIntegrityCheck" in output
    assert "RepoLegalLayoutMigrationCheck" in output
    assert "GitignoreWithoutRepoCheck" in output
    assert "KmpTargetExpansionCheck" in output
    assert "fix:yes" in output
    assert "Run `check show <check-id-or-issue-id>`" in output


def test_show_check_includes_issue_ids_and_suppressions(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.show_check("spdx-header")

    assert result == 0
    output = capsys.readouterr().out
    assert "Check: spdx-header" in output
    assert "Legacy name: SpdxHeaderCheck" in output
    assert "Issue types:" in output
    assert "E_INCORRECT_SPDX_HEADER" in output
    assert '(checks/disable "E_INCORRECT_SPDX_HEADER" "**/*")' in output
    assert "# check:ignore E_INCORRECT_SPDX_HEADER" in output


def test_describe_generated_file_integrity_check_mentions_edit_issue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.tasks import check as check_task

    result = check_task.show_check("managed-generated-file-integrity")

    assert result == 0
    output = capsys.readouterr().out
    assert "E_MANAGED_GENERATED_FILE_EDITED" in output


def test_describe_gitignore_without_repo_check_mentions_root_issue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.tasks import check as check_task

    result = check_task.show_check("gitignore-without-repo")

    assert result == 0
    output = capsys.readouterr().out
    assert "E_GITIGNORE_WITHOUT_REPO" in output


def test_describe_repo_legal_layout_migration_check_mentions_misplaced_legal_issue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.tasks import check as check_task

    result = check_task.show_check("repo-legal-layout-migration")

    assert result == 0
    output = capsys.readouterr().out
    assert "E_MISPLACED_LEGAL_FILE" in output


def test_describe_kmp_target_expansion_check_mentions_possible_target_issue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.tasks import check as check_task

    result = check_task.show_check("kmp-target-expansion")

    assert result == 0
    output = capsys.readouterr().out
    assert "E_KMP_POSSIBLE_MISSING_TARGET" in output


def test_show_check_accepts_issue_id(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.show_check("E_DUPLICATE_FILE")

    assert result == 0
    output = capsys.readouterr().out
    assert "Issue: E_DUPLICATE_FILE" in output
    assert "Matching checks: 1" in output
    assert "duplicate-files" in output
    assert "DuplicateFilesCheck" in output
    assert "E_DUPLICATE_FILE" in output


def test_issue_id_can_resolve_to_multiple_checks() -> None:
    from dev.checks.base import IssueType
    from dev.tasks import check as check_task

    shared_issue = IssueType("E_SHARED_TEST_MULTI_OWNER", "Shared issue for selector resolution.")
    catalog = {
        "alpha": check_task.CheckCatalogEntry(
            id="alpha",
            name="AlphaCheck",
            kind="repo",
            summary="Alpha.",
            fixable="no",
            issue_types=(shared_issue,),
            bundles=("default",),
            legacy_names=("AlphaCheck",),
            config_commands=(),
        ),
        "beta": check_task.CheckCatalogEntry(
            id="beta",
            name="BetaCheck",
            kind="repo",
            summary="Beta.",
            fixable="no",
            issue_types=(shared_issue,),
            bundles=("default",),
            legacy_names=("BetaCheck",),
            config_commands=(),
        ),
    }

    resolved = check_task._resolve_check_names(catalog, ["E_SHARED_TEST_MULTI_OWNER"])

    assert resolved == ("AlphaCheck", "BetaCheck")


def test_python_qa_checks_declare_issue_types() -> None:
    from dev.tasks import check as check_task

    catalog = check_task.load_check_catalog()

    assert catalog["PythonRuffCheck"].issue_types
    assert catalog["PythonBlackCheck"].issue_types
    assert catalog["PythonImportLinterCheck"].issue_types
    assert catalog["PythonMypyCheck"].issue_types
    assert catalog["PythonPyrightCheck"].issue_types
    assert catalog["PythonPytestCheck"].issue_types
    assert catalog["PythonCoverageReportCheck"].issue_types
    assert catalog["PythonCoverageXmlCheck"].issue_types
    assert catalog["PythonDiffCoverCheck"].issue_types
    assert catalog["PythonUnittestCheck"].issue_types
    assert catalog["PythonDeptryCheck"].issue_types
    assert catalog["PythonVultureCheck"].issue_types
    assert catalog["PythonSemgrepCheck"].issue_types
    assert catalog["PythonBanditCheck"].issue_types
    assert catalog["PythonPipAuditCheck"].issue_types


def test_show_check_accepts_shared_python_issue_id(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.show_check("E_PYQA_TOOL_MISSING")

    assert result == 0
    output = capsys.readouterr().out
    assert "Issue: E_PYQA_TOOL_MISSING" in output
    assert "PythonRuffCheck" in output
    assert "PythonBlackCheck" in output
    assert "PythonPipAuditCheck" in output


def test_describe_check_unknown_name_suggests_close_match() -> None:
    from dev.tasks import check as check_task

    with pytest.raises(ValueError, match=r"Did you mean 'spdx-header'"):
        check_task.show_check("spdx-heade")


def test_list_checks_json_output_is_structured(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.list_checks(json_output=True)

    assert result == 0
    output = capsys.readouterr().out
    assert '"bundles"' in output
    assert '"id": "spdx-header"' in output
    assert '"checks"' in output
    assert '"name": "SpdxHeaderCheck"' in output
    assert '"fixable": "yes"' in output


def test_show_check_json_output_is_structured(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.show_check("spdx-header", json_output=True)

    assert result == 0
    output = capsys.readouterr().out
    assert '"check"' in output
    assert '"id": "spdx-header"' in output
    assert '"name": "SpdxHeaderCheck"' in output
    assert '"suppressionExamples"' in output
    assert '"rootCljDisable"' in output
