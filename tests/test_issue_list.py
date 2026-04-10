from pathlib import Path

from dev.checks.base import IssueList, IssueType

E_TEST_ISSUE_LIST_BEHAVIOR = IssueType(
    "E_TEST_ISSUE_LIST_BEHAVIOR",
    "Test issue list behavior.",
)


def test_issue_list_append_keeps_same_issue_data_on_different_paths() -> None:
    issues = IssueList()

    issues.append(E_TEST_ISSUE_LIST_BEHAVIOR.make(kind="duplicate").at(Path("src/a.py"), line=10))
    issues.append(E_TEST_ISSUE_LIST_BEHAVIOR.make(kind="duplicate").at(Path("src/b.py"), line=20))

    assert len(issues.issues) == 2
    assert issues.issues[0].location is not None
    assert issues.issues[1].location is not None
    assert issues.issues[0].location.path == Path("src/a.py")
    assert issues.issues[1].location.path == Path("src/b.py")


def test_issue_list_append_merges_same_file_without_appending_duplicate_issue() -> None:
    issues = IssueList()

    issues.append(E_TEST_ISSUE_LIST_BEHAVIOR.make(kind="duplicate").at(Path("src/a.py"), line=10))
    issues.append(E_TEST_ISSUE_LIST_BEHAVIOR.make(kind="duplicate").at(Path("src/a.py"), line=20))

    assert len(issues.issues) == 1
    location = issues.issues[0].location
    assert location is not None
    assert location.path == Path("src/a.py")
    assert list(location.lines or []) == [10, 20]


def test_issue_list_extend_routes_plain_lists_through_append_logic() -> None:
    issues = IssueList()

    issues.extend(
        [
            E_TEST_ISSUE_LIST_BEHAVIOR.make(kind="duplicate").at(Path("src/a.py"), line=10),
            E_TEST_ISSUE_LIST_BEHAVIOR.make(kind="duplicate").at(Path("src/a.py"), line=20),
            E_TEST_ISSUE_LIST_BEHAVIOR.make(kind="duplicate").at(Path("src/b.py"), line=30),
        ]
    )

    assert len(issues.issues) == 2

    first_location = issues.issues[0].location
    second_location = issues.issues[1].location
    assert first_location is not None
    assert second_location is not None
    assert first_location.path == Path("src/a.py")
    assert list(first_location.lines or []) == [10, 20]
    assert second_location.path == Path("src/b.py")
    assert list(second_location.lines or []) == [30]
