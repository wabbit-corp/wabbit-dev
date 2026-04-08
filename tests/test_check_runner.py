from __future__ import annotations

from pathlib import Path

import pytest

from dev.checks.base import FileCheck, FileContext, Issue, IssueType, RepoCheck, Severity
from dev.tasks import check as check_task

E_TEST_ERROR = IssueType("E_TEST_RUNNER_ERROR", "runner error")
E_TEST_WARNING = IssueType(
    "E_TEST_RUNNER_WARNING",
    "runner warning",
    severity=Severity.WARNING,
)
E_TEST_VALUE_MATCH = IssueType("E_TEST_VALUE_MATCH", "found literal: {literal}")


class RepoOrderSecond(RepoCheck):
    order = 200

    def check(self, path: Path, project: object) -> list[Issue]:
        ORDER_CALLS.append("repo_second")
        return []


class RepoOrderFirst(RepoCheck):
    order = 100

    def check(self, path: Path, project: object) -> list[Issue]:
        ORDER_CALLS.append("repo_first")
        return []


class FileOrderSecond(FileCheck):
    order = 200

    def check(self, ctx: FileContext) -> None:
        ORDER_CALLS.append("file_second")


class FileOrderFirst(FileCheck):
    order = 100

    def check(self, ctx: FileContext) -> None:
        ORDER_CALLS.append("file_first")


class RepoError(RepoCheck):
    order = 100

    def check(self, path: Path, project: object) -> list[Issue]:
        return [E_TEST_ERROR.at(path)]


class RepoWarning(RepoCheck):
    order = 100

    def check(self, path: Path, project: object) -> list[Issue]:
        return [E_TEST_WARNING.at(path)]


class RepoValueMatch(RepoCheck):
    order = 100

    def check(self, path: Path, project: object) -> list[Issue]:
        return [E_TEST_VALUE_MATCH.make(literal="10.0.0.0").at(path)]


class FileRecorder(FileCheck):
    order = 100

    def check(self, ctx: FileContext) -> None:
        FILE_CALLS.append(ctx.path.as_posix())


class ValueMatchCheck(FileCheck):
    order = 100

    def check(self, ctx: FileContext) -> None:
        if not ctx.path.is_file():
            return
        if ctx.path.suffix != ".py":
            return
        text = ctx.read_text(E_TEST_VALUE_MATCH)
        for line_number, line in enumerate(text.splitlines(), start=1):
            literal = "10.0.0.0"
            if literal in line:
                ctx.add_issue(E_TEST_VALUE_MATCH, line=line_number, literal=literal)


ORDER_CALLS: list[str] = []
FILE_CALLS: list[str] = []


@pytest.fixture(autouse=True)
def clear_calls() -> None:
    ORDER_CALLS.clear()
    FILE_CALLS.clear()


def _make_repo(root: Path) -> None:
    (root / ".git").mkdir(parents=True)


def _write_minimal_config(root: Path, root_clj: str) -> None:
    (root / "root.clj").write_text(root_clj, encoding="utf-8")
    (root / "root.private.clj").write_text('(github-token "dummy")\n', encoding="utf-8")


def test_check_main_no_config_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_task.Module, "load_modules", staticmethod(lambda: {}))
    rc = check_task.check_main(str(tmp_path))
    assert rc == 0


def test_check_ordering_by_order_and_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    (tmp_path / "sample.txt").write_text("x\n", encoding="utf-8")

    def fake_modules() -> dict[str, object]:
        return {
            "RepoOrderSecond": RepoOrderSecond(),
            "RepoOrderFirst": RepoOrderFirst(),
            "FileOrderSecond": FileOrderSecond(),
            "FileOrderFirst": FileOrderFirst(),
        }

    monkeypatch.setattr(check_task.Module, "load_modules", staticmethod(fake_modules))
    rc = check_task.check_main(str(tmp_path))
    assert rc == 0
    assert ORDER_CALLS == ["repo_first", "repo_second", "file_first", "file_second"]


def test_file_target_runs_repo_checks_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    nested = tmp_path / "src"
    nested.mkdir()
    file_path = nested / "a.py"
    file_path.write_text("print('x')\n", encoding="utf-8")

    calls = {"repo": 0}

    class RepoCounter(RepoCheck):
        order = 100

        def check(self, path: Path, project: object) -> list[Issue]:
            calls["repo"] += 1
            return []

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"RepoCounter": RepoCounter()}),
    )

    rc = check_task.check_main(str(file_path))
    assert rc == 0
    assert calls["repo"] == 1


def test_check_main_exit_code_nonzero_on_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"RepoError": RepoError()}),
    )
    assert check_task.check_main(str(tmp_path)) == 1


def test_check_main_exit_code_zero_for_warnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"RepoWarning": RepoWarning()}),
    )
    assert check_task.check_main(str(tmp_path)) == 0


def test_check_main_loads_config_from_parent_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_minimal_config(tmp_path, '(python "pkg" :version "0.1.0")\n')
    (tmp_path / "pkg").mkdir(parents=True)
    nested = tmp_path / "pkg" / "src"
    nested.mkdir()
    monkeypatch.chdir(nested)
    monkeypatch.setattr(check_task.Module, "load_modules", staticmethod(lambda: {}))

    assert check_task.check_main("pkg") == 0


def test_checkignore_applies_without_git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".checkignore").write_text("skip.txt\n", encoding="utf-8")
    (tmp_path / "skip.txt").write_text("skip\n", encoding="utf-8")
    (tmp_path / "keep.txt").write_text("keep\n", encoding="utf-8")

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"FileRecorder": FileRecorder()}),
    )

    assert check_task.check_main(str(tmp_path)) == 0
    joined = "\n".join(FILE_CALLS)
    assert "keep.txt" in joined
    assert "skip.txt" not in joined


def test_checkignore_overrides_gitignore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("*.py\n", encoding="utf-8")
    (tmp_path / ".checkignore").write_text("!keep.py\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("print('keep')\n", encoding="utf-8")
    (tmp_path / "drop.py").write_text("print('drop')\n", encoding="utf-8")

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"FileRecorder": FileRecorder()}),
    )

    assert check_task.check_main(str(tmp_path)) == 0
    joined = "\n".join(FILE_CALLS)
    assert "keep.py" in joined
    assert "drop.py" not in joined


def test_nested_checkignore_applies_only_to_subtree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / ".checkignore").write_text("skip.txt\n", encoding="utf-8")

    (tmp_path / "skip.txt").write_text("root\n", encoding="utf-8")
    (src / "skip.txt").write_text("nested-skip\n", encoding="utf-8")
    (src / "keep.txt").write_text("nested-keep\n", encoding="utf-8")

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"FileRecorder": FileRecorder()}),
    )

    assert check_task.check_main(str(tmp_path)) == 0
    joined = "\n".join(FILE_CALLS)
    assert "/skip.txt" in joined
    assert "/src/keep.txt" in joined
    assert "/src/skip.txt" not in joined


def test_ignore_finding_config_suppresses_matching_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    _write_minimal_config(
        tmp_path,
        '(checks/ignore-finding "E_TEST_VALUE_MATCH" "**/*.py" "10.0.0.0")\n',
    )
    monkeypatch.chdir(tmp_path)

    (tmp_path / "sample.py").write_text('HOST = "10.0.0.0"\n', encoding="utf-8")
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path)) == 0


def test_ignore_finding_config_non_matching_value_still_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_repo(tmp_path)
    _write_minimal_config(
        tmp_path,
        '(checks/ignore-finding "E_TEST_VALUE_MATCH" "**/*.py" "172.16.0.1")\n',
    )
    monkeypatch.chdir(tmp_path)

    (tmp_path / "sample.py").write_text('HOST = "10.0.0.0"\n', encoding="utf-8")
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path)) == 1


def test_ignore_finding_config_wildcard_issue_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    _write_minimal_config(
        tmp_path,
        '(checks/ignore-finding "*" "**/*.py" "10.0.0.0")\n',
    )
    monkeypatch.chdir(tmp_path)

    (tmp_path / "sample.py").write_text('HOST = "10.0.0.0"\n', encoding="utf-8")
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path)) == 0


def test_inline_check_ignore_works_without_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    (tmp_path / "sample.py").write_text(
        'HOST = "10.0.0.0"  # check:ignore E_TEST_VALUE_MATCH value=10.0.0.0\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path)) == 0


def test_ignore_finding_applies_to_repo_checks_at_report_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    _write_minimal_config(
        tmp_path,
        '(checks/ignore-finding "E_TEST_VALUE_MATCH" "**" "10.0.0.0")\n',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"RepoValueMatch": RepoValueMatch()}),
    )

    assert check_task.check_main(str(tmp_path)) == 0
