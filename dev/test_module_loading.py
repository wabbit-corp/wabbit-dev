from pathlib import Path

from dev.base import Module


def test_load_modules_does_not_require_checks_directory_iteration(monkeypatch) -> None:
    def _fail_iterdir(_: Path):
        raise AssertionError("Path.iterdir should not be used by Module.load_modules")

    monkeypatch.setattr(Path, "iterdir", _fail_iterdir)
    modules = Module.load_modules()

    assert "TextQualityCheck" in modules
