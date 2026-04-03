import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dev.config import Config


def _load_from_temp_root(tmp_path: Path, root_clj: str) -> "Config":
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


def test_define_kotlin_plugin_accepts_group_artifact_version(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        '(define-kotlin-plugin "kotlin-jvm" "org.jetbrains.kotlin:kotlin-gradle-plugin:2.0.20")\n',
    )

    plugin = config.plugins["kotlin-jvm"]
    assert plugin.plugin_id == "org.jetbrains.kotlin:kotlin-gradle-plugin"
    assert plugin.version == "2.0.20"


def test_define_kotlin_plugin_accepts_id_version(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        '(define-kotlin-plugin "shadow" "com.gradleup.shadow:8.3.0")\n',
    )

    plugin = config.plugins["shadow"]
    assert plugin.plugin_id == "com.gradleup.shadow"
    assert plugin.version == "8.3.0"


def test_define_kotlin_plugin_accepts_local_project_reference(tmp_path: Path) -> None:
    from dev.config import (
        resolve_kotlin_compiler_plugin_id,
        resolve_kotlin_plugin_id,
        resolve_kotlin_plugin_version,
    )

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(define-kotlin-plugin "acyclic" ":kotlin-acyclic-gradle-plugin" :compilerPlugin "kotlin-acyclic-plugin" :compilerPluginId "one.wabbit.acyclic")',
                '(gradle "kotlin-acyclic-gradle-plugin" :version "0.0.1" :gradlePluginId "one.wabbit.acyclic" :features [(jvm-kotlin-library)])',
                '(gradle "kotlin-acyclic-plugin" :version "0.0.1" :features [(jvm-kotlin-library)])',
                "",
            ]
        ),
    )

    plugin = config.plugins["acyclic"]
    assert plugin.project == "kotlin-acyclic-gradle-plugin"
    assert plugin.compiler_plugin == "kotlin-acyclic-plugin"
    assert plugin.compiler_plugin_id == "one.wabbit.acyclic"
    assert resolve_kotlin_plugin_id(config, plugin) == "one.wabbit.acyclic"
    assert resolve_kotlin_compiler_plugin_id(config, plugin) == "one.wabbit.acyclic"
    assert resolve_kotlin_plugin_version(config, plugin) == "0.0.1"
