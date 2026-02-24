import os
import sys
from pathlib import Path

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


def test_maven_version_variable_is_resolved_from_define(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(define ktor-version "3.3.0")',
                "(" 'define-maven-library "ktor-client-core" ' '"io.ktor:ktor-client-core:${ktor-version}")',
                "",
            ]
        ),
    )

    library = config.libraries["ktor-client-core"]
    assert library.maven_urn.group_id == "io.ktor"
    assert library.maven_urn.artifact_id == "ktor-client-core"
    assert library.maven_urn.version == "3.3.0"


def test_undefined_maven_version_variable_fails_with_path_and_span(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError) as exc:
        _load_from_temp_root(
            tmp_path,
            "(" 'define-maven-library "ktor-client-core" ' '"io.ktor:ktor-client-core:${ktor-version}")\n',
        )

    assert exc.value.path == "root[0]"
    assert exc.value.span is not None
    assert "Undefined variable referenced in maven version" in str(exc.value)


def test_forward_maven_version_variable_reference_is_rejected(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError) as exc:
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    "(" 'define-maven-library "ktor-client-core" ' '"io.ktor:ktor-client-core:${ktor-version}")',
                    '(define ktor-version "3.3.0")',
                    "",
                ]
            ),
        )

    assert exc.value.path == "root[0]"


def test_module_typed_commands_are_loaded_and_applied(tmp_path: Path) -> None:
    from dev.checks.code_stale import StaleCodeCheck

    config = _load_from_temp_root(
        tmp_path,
        "(checks/stale-todo/age-days 30)\n",
    )

    stale_check = next(module for module in config.modules.values() if isinstance(module, StaleCodeCheck))
    assert stale_check.todo_age_days == 30


def test_dep_call_in_gradle_dependencies_is_resolved(tmp_path: Path) -> None:
    from dev.config import MavenDependencyTarget

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(define-maven-library "kotlin-stdlib" "org.jetbrains.kotlin:kotlin-stdlib:2.0.0")',
                "("
                'gradle "demo" '
                ':version "0.1.0" '
                ":features [(jvm-kotlin-library)] "
                ':dependencies [(dep "kotlin-stdlib" "api")])',
                "",
            ]
        ),
    )

    project = config.defined_projects["demo"]
    assert any(
        dep.scope == "api"
        and isinstance(dep.target, MavenDependencyTarget)
        and dep.target.artifact == "org.jetbrains.kotlin:kotlin-stdlib:2.0.0"
        for dep in project.resolved_dependencies
    )


def test_unknown_top_level_tag_fails_decode(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError):
        _load_from_temp_root(tmp_path, '(unknown-cmd "x")\n')


def test_strict_kebab_case_rejects_legacy_python_keyword_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    "(" 'python "pkg" ' ':version "0.1.0" ' ':python_version ">=3.10" ' ':dev_dependencies ["pytest"])',
                    "",
                ]
            ),
        )


def test_checks_ignore_finding_is_loaded(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        '(checks/ignore-finding "E_HARDCODED_INTERNAL_HOSTNAME_IP" "**/*.py" "10.0.0.0")\n',
    )

    assert (
        "E_HARDCODED_INTERNAL_HOSTNAME_IP",
        "**/*.py",
        "10.0.0.0",
    ) in config.ignored_findings


def test_checks_ignore_finding_rejects_invalid_issue_id(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError):
        _load_from_temp_root(
            tmp_path,
            '(checks/ignore-finding "bad_issue" "**/*.py" "10.0.0.0")\n',
        )


def test_checks_ignore_finding_rejects_missing_args(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError):
        _load_from_temp_root(
            tmp_path,
            '(checks/ignore-finding "E_HARDCODED_INTERNAL_HOSTNAME_IP" "**/*.py")\n',
        )
