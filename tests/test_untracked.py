from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

import pytest


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _config(workspace_root: Path) -> SimpleNamespace:
    alpha = workspace_root / "alpha"
    nested_repo = workspace_root / "nested" / "repo"
    return SimpleNamespace(
        workspace_root=workspace_root,
        defined_repos=OrderedDict(
            {
                "alpha": SimpleNamespace(path=alpha),
            }
        ),
        defined_projects=OrderedDict(
            {
                "nested-project": SimpleNamespace(
                    path=nested_repo / "src",
                    repo_root=nested_repo,
                ),
            }
        ),
    )


def test_find_untracked_workspace_paths_reports_uncovered_top_level_and_nested_paths(tmp_path: Path) -> None:
    from dev.tasks.untracked import find_untracked_workspace_paths

    workspace_root = tmp_path
    (workspace_root / "alpha").mkdir()
    (workspace_root / "nested" / "repo" / "src").mkdir(parents=True)
    (workspace_root / "nested" / "loose").mkdir()
    (workspace_root / "scratch").mkdir()
    (workspace_root / ".venv").mkdir()
    _touch(workspace_root / "root.clj")
    _touch(workspace_root / "root.private.clj")

    paths = find_untracked_workspace_paths(_config(workspace_root))

    assert [(path.relative_path, path.kind) for path in paths] == [
        ("nested/loose", "dir"),
        ("scratch", "dir"),
    ]


def test_find_untracked_workspace_paths_can_include_ignored_workspace_metadata(tmp_path: Path) -> None:
    from dev.tasks.untracked import find_untracked_workspace_paths

    workspace_root = tmp_path
    (workspace_root / "alpha").mkdir()
    (workspace_root / "nested" / "repo" / "src").mkdir(parents=True)
    (workspace_root / ".venv").mkdir()
    _touch(workspace_root / "root.clj")
    _touch(workspace_root / "root.private.clj")

    paths = find_untracked_workspace_paths(_config(workspace_root), include_ignored=True)

    relative_paths = {path.relative_path for path in paths}
    assert ".venv" in relative_paths
    assert "root.clj" in relative_paths
    assert "root.private.clj" in relative_paths


def test_untracked_prints_json_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from dev.tasks import untracked as untracked_task

    workspace_root = tmp_path
    (workspace_root / "alpha").mkdir()
    (workspace_root / "nested" / "repo" / "src").mkdir(parents=True)
    (workspace_root / "scratch").mkdir()

    monkeypatch.setattr(untracked_task, "load_config", lambda: _config(workspace_root))

    result = untracked_task.untracked(json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workspaceRoot"] == str(workspace_root.resolve())
    assert payload["includeIgnored"] is False
    assert {"path": "scratch", "absolutePath": str((workspace_root / "scratch").resolve()), "kind": "dir"} in payload[
        "paths"
    ]
