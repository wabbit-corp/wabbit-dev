from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def _load_from_temp_root(
    tmp_path: Path,
    root_clj: str,
    root_private_clj: str = '(github-token "dummy")\n',
):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.config import load_config

    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "root.clj").write_text(root_clj, encoding="utf-8")
    (tmp_path / "root.private.clj").write_text(root_private_clj, encoding="utf-8")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return load_config()
    finally:
        os.chdir(cwd)


def _load_kmp_target_gap_config(tmp_path: Path):
    return _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "provider" '
                ':version "0.1.0" '
                ':buildModel "kmp" '
                ':targets [{"kind": "jvm"} {"kind": "iosArm64"} {"kind": "linuxX64"}])',
                "("
                'gradle "consumer" '
                ':version "0.1.0" '
                ':buildModel "kmp" '
                ':targets [{"kind": "jvm"} {"kind": "iosArm64"}] '
                ':sourceSetDependencies {"commonMain": [":provider"]})',
                "",
            ]
        ),
    )


def test_find_kmp_target_expansion_suggests_missing_target_when_dependency_is_a_superset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev.kmp_target_suggestions import find_kmp_target_expansion_suggestions

    config = _load_kmp_target_gap_config(tmp_path)
    consumer = config.defined_projects["consumer"]
    (tmp_path / consumer.path).mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)

    suggestions = find_kmp_target_expansion_suggestions(consumer, config)

    assert [(suggestion.platform, suggestion.supporting_dependencies) for suggestion in suggestions] == [
        ("linuxX64", ("provider",))
    ]
    assert suggestions[0].newly_activated_source_sets == ("linuxX64Main", "linuxX64Test")


def test_find_kmp_target_expansion_skips_target_with_new_platform_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev.kmp_target_suggestions import find_kmp_target_expansion_suggestions

    config = _load_kmp_target_gap_config(tmp_path)
    consumer = config.defined_projects["consumer"]
    source_dir = tmp_path / consumer.path / "src" / "linuxX64Main" / "kotlin"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "Consumer.kt").write_text("class Consumer\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    suggestions = find_kmp_target_expansion_suggestions(consumer, config)

    assert suggestions == []


def test_check_main_reports_kmp_target_expansion_as_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.tasks import check as check_task

    _load_kmp_target_gap_config(tmp_path)
    (tmp_path / "consumer").mkdir(parents=True, exist_ok=True)
    (tmp_path / "provider").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)

    result = check_task.check_main("consumer", ["KmpTargetExpansionCheck"])

    assert result == 0
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "E_KMP_POSSIBLE_MISSING_TARGET" in output
    assert "linuxX64" in output
