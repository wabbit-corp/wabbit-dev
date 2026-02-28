import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest


def test_commit_repo_changes_handles_added_files_without_a_path(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import dev.tasks.setup as setup_module
    from dev.git_changes import ChangeType, FileDiff, FileType
    from dev.config import Project
    from git import Repo

    class DummyGit:
        def __init__(self) -> None:
            self.add_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def add(self, *args: object, **kwargs: object) -> None:
            self.add_calls.append((args, kwargs))

    class DummyIndex:
        def __init__(self) -> None:
            self.commits: list[str] = []

        def commit(self, message: str) -> None:
            self.commits.append(message)

    class DummyHead:
        def __init__(self) -> None:
            self.commit = object()

        def is_valid(self) -> bool:
            return True

    class DummyRepo:
        def __init__(self) -> None:
            self.head = DummyHead()
            self.git = DummyGit()
            self.index = DummyIndex()

    diff_calls: list[bool] = []

    def fake_compute_repo_diffs(repo: DummyRepo, include_untracked: bool = False) -> list[FileDiff]:
        diff_calls.append(include_untracked)
        return [
            FileDiff(
                old_path=None,
                new_path="new_file.py",
                change_type=ChangeType.ADDED,
                staged=False,
                unstaged=False,
                untracked=True,
                new_type=FileType.TEXT,
                unified_diff="@@ -0,0 +1 @@\n+print('hi')\n",
            )
        ]

    monkeypatch.setattr(setup_module, "compute_repo_diffs", fake_compute_repo_diffs)

    def fake_suggest_commit_name(*_args: object, **_kwargs: object) -> str:
        return "Add new file"

    def fake_semver_line(msg: str) -> str:
        return msg + "\n\nSemver Impact: NONE"

    monkeypatch.setattr(setup_module, "suggest_commit_name", fake_suggest_commit_name)
    monkeypatch.setattr(
        setup_module,
        "ensure_semver_impact_line",
        fake_semver_line,
    )

    repo = DummyRepo()
    project = SimpleNamespace(name="demo-project", quarantine=False)

    setup_module.commit_repo_changes(
        cast(Project, project),
        cast(Repo, repo),
        openai_key=None,
        interactive=False,
        add_files=False,
    )

    assert diff_calls == [False, True]
    assert repo.index.commits == ["Add new file\n\nSemver Impact: NONE"]
    assert repo.git.add_calls == [((), {"all": True})]
