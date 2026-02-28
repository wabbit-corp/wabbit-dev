import sys
from collections.abc import Callable
from pathlib import Path


def _target_version_fn() -> Callable[[str | None], str]:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.tasks.setup_python import python_target_version

    return python_target_version


def test_python_target_version_uses_minimum_supported_version() -> None:
    python_target_version = _target_version_fn()
    assert python_target_version(">=3.10,<3.12") == "py310"
    assert python_target_version(">=3.11,<4.0") == "py311"


def test_python_target_version_defaults_when_unbounded_or_invalid() -> None:
    python_target_version = _target_version_fn()
    assert python_target_version(None) == "py310"
    assert python_target_version("not-a-specifier") == "py310"
