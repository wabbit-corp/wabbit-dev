from __future__ import annotations

from pathlib import Path

import pytest

from dev.checks.base import FileCheck, FileContext, Issue, IssueType, RepoCheck, RootCheck, Severity
from dev.checks.file_duplicates import DuplicateFilesCheck
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


class RepoFixableError(RepoCheck):
    order = 100

    def __init__(self) -> None:
        self.fixed = False

    def check(self, path: Path, project: object) -> list[Issue]:
        del project
        if self.fixed:
            return []
        return [E_TEST_ERROR.at(path).fixable(self._fix)]

    def _fix(self) -> None:
        self.fixed = True


class ProjectRecorder(check_task.ProjectCheck):
    order = 100

    def check(self, path: Path, project: object) -> list[Issue]:
        ORDER_CALLS.append(path.as_posix())
        return []


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
ROOT_CALLS: list[str] = []


@pytest.fixture(autouse=True)
def clear_calls() -> None:
    ORDER_CALLS.clear()
    FILE_CALLS.clear()
    ROOT_CALLS.clear()


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


def test_check_main_fix_mode_returns_zero_when_error_is_fixed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_repo(tmp_path)
    fixable_check = RepoFixableError()
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"RepoFixableError": fixable_check}),
    )

    assert check_task.check_main(str(tmp_path), fix=True) == 0
    assert fixable_check.fixed is True


def test_check_main_renders_warning_and_error_prefixes_by_severity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_repo(tmp_path)
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"RepoWarning": RepoWarning(), "RepoError": RepoError()}),
    )

    assert check_task.check_main(str(tmp_path)) == 1
    output = capsys.readouterr().out
    assert "[?] [E_TEST_RUNNER_WARNING]" in output
    assert "[✗] [E_TEST_RUNNER_ERROR]" in output


def test_check_main_renders_issue_data_as_named_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample = tmp_path / "demo.py"
    sample.write_text("HOST = '10.0.0.0'\n", encoding="utf-8")
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path), ["ValueMatchCheck"]) == 1
    output = capsys.readouterr().out
    assert 'literal:"10.0.0.0"' in output


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


def test_project_only_checks_skip_recursive_directory_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_minimal_config(tmp_path, '(python "pkg" :version "0.1.0")\n')
    project_path = tmp_path / "pkg"
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "nested").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ProjectRecorder": ProjectRecorder()}),
    )

    original_iterdir = Path.iterdir

    def guarded_iterdir(path: Path):
        if path.resolve() == project_path.resolve():
            raise AssertionError("project-only checks should not recurse into child directories")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)

    assert check_task.check_main("pkg", ["ProjectRecorder"]) == 0
    assert ORDER_CALLS == [project_path.as_posix()]


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


def test_explicit_checks_do_not_report_unselected_root_issues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".gitignore").write_text("skip.txt\n", encoding="utf-8")
    (tmp_path / "keep.txt").write_text("keep\n", encoding="utf-8")

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"FileRecorder": FileRecorder()}),
    )

    assert check_task.check_main(str(tmp_path), ["FileRecorder"]) == 0
    assert "E_GITIGNORE_WITHOUT_REPO" not in capsys.readouterr().out


def test_root_checks_run_once_per_selected_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class RootRecorder(RootCheck):
        order = 100

        def check(self, path: Path, project: object) -> list[Issue]:
            del project
            ROOT_CALLS.append(path.as_posix())
            return []

    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "sample.txt").write_text("x\n", encoding="utf-8")
    (nested / "sample.txt").write_text("x\n", encoding="utf-8")

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"RootRecorder": RootRecorder(), "FileRecorder": FileRecorder()}),
    )

    assert check_task.check_main(str(tmp_path)) == 0
    assert ROOT_CALLS == [tmp_path.as_posix()]


def test_gitignore_without_repo_check_uses_selected_root_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.checks.root_paths import GitignoreWithoutRepoCheck

    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"GitignoreWithoutRepoCheck": GitignoreWithoutRepoCheck()}),
    )

    assert check_task.check_main(str(tmp_path), ["GitignoreWithoutRepoCheck"]) == 1
    assert "E_GITIGNORE_WITHOUT_REPO" in capsys.readouterr().out


def test_checkignore_issue_directive_suppresses_matching_file_issue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "demo.py"
    sample.write_text("HOST = '10.0.0.0'\n", encoding="utf-8")
    (tmp_path / ".checkignore").write_text(
        "check:ignore E_TEST_VALUE_MATCH demo.py\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path), ["ValueMatchCheck"]) == 0


def test_nested_checkignore_issue_directive_applies_relative_to_its_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root_file = tmp_path / "demo.py"
    root_file.write_text("HOST = '10.0.0.0'\n", encoding="utf-8")
    nested_dir = tmp_path / "src"
    nested_dir.mkdir()
    nested_file = nested_dir / "demo.py"
    nested_file.write_text("HOST = '10.0.0.0'\n", encoding="utf-8")
    (nested_dir / ".checkignore").write_text(
        "check:ignore E_TEST_VALUE_MATCH demo.py\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path), ["ValueMatchCheck"]) == 1
    output = capsys.readouterr().out
    assert str(root_file) in output
    assert str(nested_file) not in output


def test_checkignore_issue_directive_supports_value_matching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "demo.py"
    sample.write_text("HOST = '10.0.0.0'\n", encoding="utf-8")
    (tmp_path / ".checkignore").write_text(
        "check:ignore E_TEST_VALUE_MATCH demo.py value=10.0.0.0\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path), ["ValueMatchCheck"]) == 0


def test_checkignore_issue_directive_supports_wildcard_issue_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "demo.py"
    sample.write_text("HOST = '10.0.0.0'\n", encoding="utf-8")
    (tmp_path / ".checkignore").write_text(
        "check:ignore * demo.py\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path), ["ValueMatchCheck"]) == 0


def test_checkignore_issue_directive_supports_field_regex_matching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "demo.py"
    sample.write_text("HOST = '10.0.0.0'\n", encoding="utf-8")
    (tmp_path / ".checkignore").write_text(
        r"check:ignore E_TEST_VALUE_MATCH demo.py literal~10\.0\..+"
        "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path), ["ValueMatchCheck"]) == 0


def test_checkignore_issue_directive_supports_exact_field_matching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "demo.py"
    sample.write_text("HOST = '10.0.0.0'\n", encoding="utf-8")
    (tmp_path / ".checkignore").write_text(
        "check:ignore E_TEST_VALUE_MATCH demo.py literal=10.0.0.0\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"ValueMatchCheck": ValueMatchCheck()}),
    )

    assert check_task.check_main(str(tmp_path), ["ValueMatchCheck"]) == 0


def test_gitignore_without_repo_check_does_not_fire_inside_enclosing_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev.checks.root_paths import GitignoreWithoutRepoCheck

    _make_repo(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"GitignoreWithoutRepoCheck": GitignoreWithoutRepoCheck()}),
    )

    assert check_task.check_main(str(nested), ["GitignoreWithoutRepoCheck"]) == 0
    assert "E_GITIGNORE_WITHOUT_REPO" not in capsys.readouterr().out


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


def test_gitignore_directory_pattern_skips_entire_directory_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_repo(tmp_path)
    (tmp_path / ".gitignore").write_text(".venv/\nsite/\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("print('keep')\n", encoding="utf-8")
    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "generated.py").write_text("print('generated')\n", encoding="utf-8")

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"FileRecorder": FileRecorder()}),
    )

    assert check_task.check_main(str(tmp_path)) == 0
    joined = "\n".join(FILE_CALLS)
    assert "keep.py" in joined
    assert "ignored.py" not in joined
    assert "generated.py" not in joined


def test_duplicate_files_check_respects_repo_gitignore_and_checkignore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_repo(tmp_path)
    (tmp_path / ".gitignore").write_text(".venv/\nsite/\n", encoding="utf-8")
    (tmp_path / ".checkignore").write_text("/tmp-test/\n", encoding="utf-8")

    keep_a = tmp_path / "src-a"
    keep_b = tmp_path / "src-b"
    keep_a.mkdir()
    keep_b.mkdir()
    (keep_a / "same.txt").write_text("same\n", encoding="utf-8")
    (keep_b / "same.txt").write_text("same\n", encoding="utf-8")

    ignored_dir = tmp_path / ".venv" / "lib"
    ignored_dir.mkdir(parents=True)
    (ignored_dir / "same.txt").write_text("same\n", encoding="utf-8")

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "same.txt").write_text("same\n", encoding="utf-8")

    tmp_test_dir = tmp_path / "tmp-test"
    tmp_test_dir.mkdir()
    (tmp_test_dir / "same.txt").write_text("same\n", encoding="utf-8")

    monkeypatch.setattr(
        check_task.Module,
        "load_modules",
        staticmethod(lambda: {"DuplicateFilesCheck": DuplicateFilesCheck()}),
    )

    assert check_task.check_main(str(tmp_path), enabled_checks=["DuplicateFilesCheck"]) == 1
    output = capsys.readouterr().out
    assert "src-a" in output
    assert "src-b" in output
    assert ".venv" not in output
    assert "site/" not in output
    assert "tmp-test" not in output



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
