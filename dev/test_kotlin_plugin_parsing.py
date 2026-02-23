import os
from pathlib import Path
import sys


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


def test_define_kotlin_plugin_accepts_group_artifact_version(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        '(define-kotlin-plugin "kotlin-jvm" "org.jetbrains.kotlin:kotlin-gradle-plugin:2.0.20")\n',
    )

    plugin = config.plugins["kotlin-jvm"]
    assert plugin.name == "org.jetbrains.kotlin:kotlin-gradle-plugin"
    assert plugin.version == "2.0.20"


def test_define_kotlin_plugin_accepts_id_version(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        '(define-kotlin-plugin "shadow" "com.gradleup.shadow:8.3.0")\n',
    )

    plugin = config.plugins["shadow"]
    assert plugin.name == "com.gradleup.shadow"
    assert plugin.version == "8.3.0"
