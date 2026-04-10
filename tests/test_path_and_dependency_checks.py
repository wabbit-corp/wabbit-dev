from pathlib import Path

from dev.checks.base import FileContext
from dev.checks.dependencies import E_UNPINNED_DEPENDENCY, PythonRequirementsPinnedCheck
from dev.checks.file_paths import (
    E_FILE_NAMING_CONVENTION,
    E_LEADING_TRAILING_SPACES_OR_DOTS,
    E_SYMLINK,
    E_SYMLINK_BROKEN,
    E_SYMLINK_ESCAPES_REPO,
    E_SYMLINK_POINTS_ABSOLUTE,
    FilenamePropertiesCheck,
    NamingConventionCheck,
    SymlinkTargetCheck,
)


def test_python_requirements_pinned_check_sets_structured_issue_location(tmp_path: Path) -> None:
    path = tmp_path / "requirements.txt"
    path.write_text("requests\n", encoding="utf-8")
    ctx = FileContext(check_name="PythonRequirementsPinnedCheck", path=path)

    PythonRequirementsPinnedCheck().check(ctx)

    assert len(ctx.issues.issues) == 1
    issue = ctx.issues.issues[0]
    assert issue.issue_type == E_UNPINNED_DEPENDENCY
    assert issue.location is not None
    assert issue.location.path == path
    assert list(issue.location.lines or []) == [1]
    assert issue.data is not None
    assert "line_number" not in issue.data


def test_python_requirements_pinned_check_allows_exact_and_major_pins(tmp_path: Path) -> None:
    path = tmp_path / "requirements.txt"
    path.write_text(
        "requests==2.31.0\n" "urllib3>=2.2.1,<3.0.0\n" "demo===1.0\n",
        encoding="utf-8",
    )
    ctx = FileContext(check_name="PythonRequirementsPinnedCheck", path=path)

    PythonRequirementsPinnedCheck().check(ctx)

    assert list(ctx.issues) == []


def test_python_requirements_pinned_check_rejects_broad_or_non_major_ranges(tmp_path: Path) -> None:
    path = tmp_path / "requirements.txt"
    path.write_text(
        "requests>=2.31.0\n" "urllib3~=2.2\n" "idna>=2.0,<4.0\n",
        encoding="utf-8",
    )
    ctx = FileContext(check_name="PythonRequirementsPinnedCheck", path=path)

    PythonRequirementsPinnedCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues.issues] == [
        E_UNPINNED_DEPENDENCY,
        E_UNPINNED_DEPENDENCY,
        E_UNPINNED_DEPENDENCY,
    ]
    assert [list(issue.location.lines or []) for issue in ctx.issues.issues] == [[1], [2], [3]]


def test_filename_properties_check_reports_leading_space(tmp_path: Path) -> None:
    path = tmp_path / " bad.txt"
    path.write_text("hello\n", encoding="utf-8")
    ctx = FileContext(check_name="FilenamePropertiesCheck", path=path)

    FilenamePropertiesCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues.issues] == [E_LEADING_TRAILING_SPACES_OR_DOTS]


def test_filename_properties_check_allows_hidden_dotfiles(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    path.write_text("build/\n", encoding="utf-8")
    ctx = FileContext(check_name="FilenamePropertiesCheck", path=path)

    FilenamePropertiesCheck().check(ctx)

    assert ctx.issues.issues == []


def test_symlink_target_check_always_reports_symlink_issue(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("hello\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target.name)
    ctx = FileContext(check_name="SymlinkTargetCheck", path=link)

    SymlinkTargetCheck().check(ctx)

    issue_types = [issue.issue_type for issue in ctx.issues.issues]
    assert E_SYMLINK in issue_types
    assert E_SYMLINK_POINTS_ABSOLUTE not in issue_types
    assert E_SYMLINK_BROKEN not in issue_types


def test_symlink_target_check_reports_relative_escape_from_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    nested = repo_root / "nested"
    nested.mkdir()

    outside_target = tmp_path / "outside.txt"
    outside_target.write_text("hello\n", encoding="utf-8")

    link = nested / "escape.txt"
    link.symlink_to("../../outside.txt")
    ctx = FileContext(check_name="SymlinkTargetCheck", path=link)

    SymlinkTargetCheck().check(ctx)

    issue_types = [issue.issue_type for issue in ctx.issues.issues]
    assert E_SYMLINK in issue_types
    assert E_SYMLINK_ESCAPES_REPO in issue_types
    assert E_SYMLINK_BROKEN not in issue_types


def test_naming_convention_check_uses_default_conventions(tmp_path: Path) -> None:
    path = tmp_path / "BadName.py"
    path.write_text("print('hello')\n", encoding="utf-8")
    ctx = FileContext(check_name="NamingConventionCheck", path=path)

    NamingConventionCheck().check(ctx)

    assert [issue.issue_type for issue in ctx.issues.issues] == [E_FILE_NAMING_CONVENTION]
