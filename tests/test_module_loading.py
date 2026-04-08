from pathlib import Path

import pytest

from dev.base import Module


def test_load_modules_does_not_require_checks_directory_iteration(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_iterdir(_: Path) -> None:
        raise AssertionError("Path.iterdir should not be used by Module.load_modules")

    monkeypatch.setattr(Path, "iterdir", _fail_iterdir)
    modules = Module.load_modules()

    assert "DuplicateFilesCheck" in modules
    assert "LargeFileCheck" in modules
    assert "CheckedInBinaryDependencyCheck" in modules
    assert "RepoContributorIdentityCheck" in modules
    assert "TextQualityCheck" in modules
