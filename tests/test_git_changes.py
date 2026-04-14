import logging
import sys
from pathlib import Path

from git import Repo


def test_compute_repo_diffs_does_not_warn_for_normal_working_tree_deletion(
    tmp_path: Path,
    caplog,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.git_changes import ChangeType, compute_repo_diffs

    repo = Repo.init(tmp_path)
    repo.git.config("user.email", "test@example.com")
    repo.git.config("user.name", "Test User")

    deleted_path = tmp_path / "delete_me.txt"
    deleted_path.write_text("hello\n", encoding="utf-8")
    repo.git.add("delete_me.txt")
    repo.index.commit("init")

    deleted_path.unlink()

    with caplog.at_level(logging.WARNING):
        diffs = compute_repo_diffs(repo)

    assert "Cannot hash WT path delete_me.txt" not in caplog.text
    deleted_diff = next(diff for diff in diffs if diff.path == "delete_me.txt")
    assert deleted_diff.change_type == ChangeType.DELETED
    assert deleted_diff.unstaged is True
