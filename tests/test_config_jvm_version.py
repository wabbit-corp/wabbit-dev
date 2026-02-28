import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from dev.config import Config


def _load_from_temp_root(tmp_path: Path, root_clj: str) -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

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


def test_jvm_version_command_sets_java_and_kotlin_targets(tmp_path: Path) -> None:
    config = _load_from_temp_root(tmp_path, '(jvm-version "17")\n')

    assert config.jvm_version == 17
    assert config.java_version == 17
    assert config.kotlin_jvm_target == "JVM_17"


def test_jvm_defaults_accepts_legacy_java_style_values(tmp_path: Path) -> None:
    config = _load_from_temp_root(tmp_path, '(jvm-defaults :version "1.8")\n')

    assert config.jvm_version == 8
    assert config.java_version == 8
    assert config.kotlin_jvm_target == "JVM_1_8"


def test_python_keywords_require_kebab_case(tmp_path: Path) -> None:
    from dev.config import PythonProject

    kebab_case = _load_from_temp_root(
        tmp_path / "kebab",
        "\n".join(
            [
                '(python-defaults :line-length "100" :coverage-fail-under "90")',
                '(python "pkg" :version "0.1.0" :requires-python ">=3.11")',
                "",
            ]
        ),
    )
    assert kebab_case.python_defaults.line_length == "100"
    assert kebab_case.python_defaults.coverage_fail_under == "90"
    pkg = kebab_case.defined_projects["pkg"]
    assert isinstance(pkg, PythonProject)
    assert pkg.requires_python == ">=3.11"

    with pytest.raises(ValueError):
        _load_from_temp_root(
            tmp_path / "legacy",
            '(python "pkg" :version "0.1.0" :python-version ">=3.10")\n',
        )
