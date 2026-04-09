from pathlib import Path
from types import ModuleType
import sys

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
    assert "RepoMetadataHygieneCheck" in modules
    assert "SuspiciousExecutableFileModeCheck" in modules
    assert "TextQualityCheck" in modules


def test_load_modules_skips_classes_that_require_constructor_args(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "tests.fake_module_loading_required_args"
    fake_module = ModuleType(module_name)

    class NeedsArgsModule(Module):
        def __init__(self, required: str) -> None:
            self.required = required

    fake_module.NeedsArgsModule = NeedsArgsModule
    sys.modules[module_name] = fake_module
    monkeypatch.setattr("dev.base.CHECK_MODULE_IMPORTS", (module_name,))

    try:
        modules = Module.load_modules()
    finally:
        sys.modules.pop(module_name, None)

    assert "NeedsArgsModule" not in modules


def test_load_modules_propagates_type_error_from_constructor(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "tests.fake_module_loading_broken_init"
    fake_module = ModuleType(module_name)

    class BrokenModule(Module):
        def __init__(self) -> None:
            raise TypeError("broken init")

    fake_module.BrokenModule = BrokenModule
    sys.modules[module_name] = fake_module
    monkeypatch.setattr("dev.base.CHECK_MODULE_IMPORTS", (module_name,))

    try:
        with pytest.raises(TypeError, match="broken init"):
            Module.load_modules()
    finally:
        sys.modules.pop(module_name, None)
