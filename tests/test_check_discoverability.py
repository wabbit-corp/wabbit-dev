from __future__ import annotations

import pytest


def test_list_checks_includes_spdx_and_fixability(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.list_checks()

    assert result == 0
    output = capsys.readouterr().out
    assert "SpdxHeaderCheck" in output
    assert "ManagedGeneratedFileIntegrityCheck" in output
    assert "RepoLegalLayoutMigrationCheck" in output
    assert "GitignoreWithoutRepoCheck" in output
    assert "KmpTargetExpansionCheck" in output
    assert "fix:yes" in output
    assert "Run `check describe <check>`" in output


def test_describe_check_includes_issue_ids_and_suppressions(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.describe_check("SpdxHeaderCheck")

    assert result == 0
    output = capsys.readouterr().out
    assert "Check: SpdxHeaderCheck" in output
    assert "Issue types:" in output
    assert "E_INCORRECT_SPDX_HEADER" in output
    assert '(checks/disable "E_INCORRECT_SPDX_HEADER" "**/*")' in output
    assert "# check:ignore E_INCORRECT_SPDX_HEADER" in output


def test_describe_generated_file_integrity_check_mentions_edit_issue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.tasks import check as check_task

    result = check_task.describe_check("ManagedGeneratedFileIntegrityCheck")

    assert result == 0
    output = capsys.readouterr().out
    assert "E_MANAGED_GENERATED_FILE_EDITED" in output


def test_describe_gitignore_without_repo_check_mentions_root_issue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.tasks import check as check_task

    result = check_task.describe_check("GitignoreWithoutRepoCheck")

    assert result == 0
    output = capsys.readouterr().out
    assert "E_GITIGNORE_WITHOUT_REPO" in output


def test_describe_repo_legal_layout_migration_check_mentions_misplaced_legal_issue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.tasks import check as check_task

    result = check_task.describe_check("RepoLegalLayoutMigrationCheck")

    assert result == 0
    output = capsys.readouterr().out
    assert "E_MISPLACED_LEGAL_FILE" in output


def test_describe_kmp_target_expansion_check_mentions_possible_target_issue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.tasks import check as check_task

    result = check_task.describe_check("KmpTargetExpansionCheck")

    assert result == 0
    output = capsys.readouterr().out
    assert "E_KMP_POSSIBLE_MISSING_TARGET" in output


def test_describe_check_unknown_name_suggests_close_match() -> None:
    from dev.tasks import check as check_task

    with pytest.raises(ValueError, match=r"Did you mean 'SpdxHeaderCheck'"):
        check_task.describe_check("SpdxHeaderChek")


def test_list_checks_json_output_is_structured(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.list_checks(json_output=True)

    assert result == 0
    output = capsys.readouterr().out
    assert '"checks"' in output
    assert '"name": "SpdxHeaderCheck"' in output
    assert '"fixable": "yes"' in output


def test_describe_check_json_output_is_structured(capsys: pytest.CaptureFixture[str]) -> None:
    from dev.tasks import check as check_task

    result = check_task.describe_check("SpdxHeaderCheck", json_output=True)

    assert result == 0
    output = capsys.readouterr().out
    assert '"check"' in output
    assert '"name": "SpdxHeaderCheck"' in output
    assert '"suppressionExamples"' in output
    assert '"rootCljDisable"' in output
