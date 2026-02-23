import os
from pathlib import Path
import sys

import pytest


def _load_from_temp_root(tmp_path: Path, root_clj: str):
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    from dev.config import load_config

    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "root.clj").write_text(root_clj, encoding="utf-8")
    (tmp_path / "root.private.clj").write_text('(github-token "dummy")\n', encoding="utf-8")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return load_config()
    finally:
        os.chdir(cwd)


def test_library_group_rejects_unknown_string_child(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown library/group in group bad-group: unknown-lib"):
        _load_from_temp_root(
            tmp_path,
            '(define-maven-library-group "bad-group" ["unknown-lib"])\n',
        )


def test_library_group_rejects_invalid_child_type(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="Invalid group child in bad-group"):
        _load_from_temp_root(
            tmp_path,
            '(define-maven-library-group "bad-group" [true])\n',
        )


def test_library_group_accepts_valid_children(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(define-maven-library "kotlin-stdlib" "org.jetbrains.kotlin:kotlin-stdlib:1.9.0")',
                '(define-maven-library-group "base-group" ["kotlin-stdlib" "org.slf4j:slf4j-api:2.0.13" "./libs/local.jar" ":some-project"])',
                '(define-maven-library-group "combo-group" ["base-group" (dep "kotlin-stdlib")])',
                "",
            ]
        ),
    )

    assert "base-group" in config.library_groups
    assert "combo-group" in config.library_groups
    dep_children = config.library_groups["combo-group"][1]
    assert isinstance(dep_children, list)
    assert dep_children
