from __future__ import annotations

from pathlib import Path

from dev.setup_plan import SetupPlan, SetupPlanCategory, SetupPlanKind, SetupPlanOwnership


def test_setup_plan_groups_repo_paths_and_local_only_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    plan = SetupPlan()
    plan.record(
        kind=SetupPlanKind.REPLACE_TEXT,
        repo_root=repo_root,
        path=repo_root / "kotlin-conventions.md",
        category=SetupPlanCategory.GUIDANCE,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )
    plan.record(
        kind=SetupPlanKind.REPLACE_TEXT,
        repo_root=repo_root,
        path=repo_root / "settings.local.gradle.kts",
        category=SetupPlanCategory.BUILD,
        ownership=SetupPlanOwnership.LOCAL_ONLY,
    )

    assert plan.planned_paths_for_repo(repo_root) == frozenset({"kotlin-conventions.md"})
    assert plan.planned_paths_for_repo(repo_root, include_local_only=True) == frozenset(
        {"kotlin-conventions.md", "settings.local.gradle.kts"}
    )
    assert plan.local_only_paths_for_repo(repo_root) == frozenset({"settings.local.gradle.kts"})


def test_setup_plan_only_records_optional_operations_when_they_apply(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    plan = SetupPlan()

    existing_path = repo_root / "existing.txt"
    existing_path.write_text("keep\n", encoding="utf-8")
    assert not plan.ensure_text_if_missing(
        repo_root=repo_root,
        path=existing_path,
        content="new\n",
        category=SetupPlanCategory.GUIDANCE,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )

    missing_path = repo_root / "missing.txt"
    assert plan.ensure_text_if_missing(
        repo_root=repo_root,
        path=missing_path,
        content="new\n",
        category=SetupPlanCategory.GUIDANCE,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )

    words_path = repo_root / ".codespell-ignore-words.txt"
    words_path.write_text("wabbit\n", encoding="utf-8")
    assert not plan.merge_word_list(
        repo_root=repo_root,
        path=words_path,
        words=["wabbit"],
        category=SetupPlanCategory.METADATA,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )
    assert plan.merge_word_list(
        repo_root=repo_root,
        path=words_path,
        words=["codex"],
        category=SetupPlanCategory.METADATA,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )

    absent_delete = repo_root / "absent.txt"
    plan.delete_path(
        repo_root=repo_root,
        path=absent_delete,
        category=SetupPlanCategory.GUIDANCE,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )

    present_delete = repo_root / "delete-me.txt"
    present_delete.write_text("bye\n", encoding="utf-8")
    plan.delete_path(
        repo_root=repo_root,
        path=present_delete,
        category=SetupPlanCategory.GUIDANCE,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )

    assert plan.planned_paths_for_repo(repo_root, include_local_only=True) == frozenset(
        {"missing.txt", ".codespell-ignore-words.txt", "delete-me.txt"}
    )
