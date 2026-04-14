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
