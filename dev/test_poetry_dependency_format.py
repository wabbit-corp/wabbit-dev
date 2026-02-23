import sys
import tomllib
from pathlib import Path

import pytest


def _format_dependency_fn():
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    from dev.tasks.setup import _format_poetry_dependency

    return _format_poetry_dependency


def _parse_dependency_entry(key: str, value: str) -> object:
    data = tomllib.loads(
        "\n".join(
            [
                "[tool.poetry.dependencies]",
                'python = ">=3.10"',
                f"{key} = {value}",
                "",
            ]
        )
    )
    return data["tool"]["poetry"]["dependencies"][key]


def test_format_poetry_dependency_simple_specifier() -> None:
    format_dependency = _format_dependency_fn()

    key, value = format_dependency("requests>=2,<3")

    assert key == "requests"
    assert _parse_dependency_entry(key, value) == ">=2,<3"


def test_format_poetry_dependency_with_extras_and_marker() -> None:
    format_dependency = _format_dependency_fn()

    key, value = format_dependency('uvicorn[standard]>=0.30; python_version < "3.13"')

    assert key == "uvicorn"
    parsed = _parse_dependency_entry(key, value)
    assert isinstance(parsed, dict)
    assert parsed["version"] == ">=0.30"
    assert parsed["extras"] == ["standard"]
    assert parsed["markers"] == 'python_version < "3.13"'


def test_format_poetry_dependency_with_url_and_marker() -> None:
    format_dependency = _format_dependency_fn()

    key, value = format_dependency('mypkg[feature] @ https://example.com/pkg.whl ; python_version >= "3.10"')

    assert key == "mypkg"
    parsed = _parse_dependency_entry(key, value)
    assert isinstance(parsed, dict)
    assert parsed["url"] == "https://example.com/pkg.whl"
    assert parsed["extras"] == ["feature"]
    assert parsed["markers"] == 'python_version >= "3.10"'


def test_format_poetry_dependency_rejects_invalid_requirement() -> None:
    format_dependency = _format_dependency_fn()

    with pytest.raises(ValueError, match="Invalid dependency requirement"):
        format_dependency("not a valid requirement ; ;")
