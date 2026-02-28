# pyright: reportPrivateUsage=false

import sys
from pathlib import Path
from types import SimpleNamespace
from collections.abc import Callable
from typing import cast

from git import Repo


def _resolve_tag_commit_fn() -> Callable[[Repo, str, str], object]:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.tasks.publish import _resolve_tag_commit

    return _resolve_tag_commit


def test_resolve_tag_commit_uses_existing_tag_commit() -> None:
    resolve_tag_commit = _resolve_tag_commit_fn()

    existing_commit = object()
    head_commit = object()

    class DummyRepo:
        def __init__(self) -> None:
            self.tags: list[SimpleNamespace] = [SimpleNamespace(name="1.2.3", commit=existing_commit)]
            self.head = SimpleNamespace(commit=head_commit)
            self.created: list[tuple[str, str]] = []

        def create_tag(self, name: str, message: str) -> None:
            self.created.append((name, message))

    repo = DummyRepo()
    result = resolve_tag_commit(cast(Repo, repo), "1.2.3", "demo-project")

    assert result is existing_commit
    assert repo.created == []


def test_resolve_tag_commit_creates_tag_when_missing() -> None:
    resolve_tag_commit = _resolve_tag_commit_fn()

    head_commit = object()

    class DummyRepo:
        def __init__(self) -> None:
            self.tags: list[SimpleNamespace] = []
            self.head = SimpleNamespace(commit=head_commit)
            self.created: list[tuple[str, str]] = []

        def create_tag(self, name: str, message: str) -> None:
            self.created.append((name, message))

    repo = DummyRepo()
    result = resolve_tag_commit(cast(Repo, repo), "2.0.0", "demo-project")

    assert result is head_commit
    assert repo.created == [("2.0.0", "Release 2.0.0")]
