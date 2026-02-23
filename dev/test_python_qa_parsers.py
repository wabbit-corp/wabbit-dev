from __future__ import annotations

from pathlib import Path

from dev.checks.python_qa_common import (
    BanditIssue,
    BlackIssue,
    CoverageReportIssue,
    CoverageXmlIssue,
    DeptryIssue,
    DiffCoverFileIssue,
    DiffCoverSummaryIssue,
    DiffCoverThresholdIssue,
    ImportLinterIssue,
    MypyIssue,
    PipAuditIssue,
    PyrightIssue,
    PytestIssue,
    RuffIssue,
    SemgrepIssue,
    UnittestIssue,
    VultureIssue,
    parse_bandit_issues,
    parse_black_issues,
    parse_coverage_report_issues,
    parse_coverage_xml_issues,
    parse_deptry_issues,
    parse_diff_cover_issues,
    parse_import_linter_issues,
    parse_mypy_issues,
    parse_pip_audit_issues,
    parse_pyright_issues,
    parse_pytest_issues,
    parse_ruff_issues,
    parse_semgrep_issues,
    parse_unittest_issues,
    parse_vulture_issues,
)


def test_parse_ruff_json() -> None:
    raw = (
        '[{"code":"F401","message":"unused import","filename":"sample.py",'
        '"location":{"row":2,"column":8},"end_location":{"row":2,"column":10},'
        '"fix":{},"url":"https://docs.astral.sh/ruff/rules/unused-import"}]'
    )
    issues = list(parse_ruff_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, RuffIssue)
    assert issue.code == "F401"
    assert issue.location.line == 2
    assert issue.fix_available is True


def test_parse_black_reformat() -> None:
    raw = "would reformat /tmp/sample.py\n\n1 file would be reformatted."
    issues = list(parse_black_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, BlackIssue)
    assert issue.path == "/tmp/sample.py"


def test_parse_mypy_text() -> None:
    raw = "sample.py:2: error: Incompatible return value type " '(got "str", expected "int")  [return-value]'
    issues = list(parse_mypy_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, MypyIssue)
    assert issue.code == "return-value"
    assert issue.location.line == 2


def test_parse_import_linter_text() -> None:
    raw = "Architecture layering BROKEN\nContracts: 1 kept, 1 broken."
    issues = list(parse_import_linter_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, ImportLinterIssue)
    assert issue.contract == "Architecture layering"


def test_parse_pyright_json() -> None:
    raw = (
        '{"generalDiagnostics":[{"file":"sample.py","severity":"warning",'
        '"message":"bad","range":{"start":{"line":1,"character":2},'
        '"end":{"line":1,"character":5}},"rule":"reportUnknown"}]}'
    )
    issues = list(parse_pyright_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, PyrightIssue)
    assert issue.location.line == 2
    assert issue.location.column == 3


def test_parse_semgrep_json() -> None:
    raw = (
        '{"results":[{"check_id":"rule.id","path":"sample.py",'
        '"start":{"line":4,"col":1},"end":{"line":4,"col":6},'
        '"extra":{"message":"avoid this","severity":"warning"}}]}'
    )
    issues = list(parse_semgrep_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, SemgrepIssue)
    assert issue.rule_id == "rule.id"
    assert issue.severity == "warning"


def test_parse_pytest_text() -> None:
    raw = "FAILED tests/test_mod.py::test_a - assert False"
    issues = list(parse_pytest_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, PytestIssue)
    assert issue.nodeid == "tests/test_mod.py::test_a"
    assert issue.location.path == "tests/test_mod.py"


def test_parse_pytest_junit(tmp_path: Path) -> None:
    junit = """<testsuite tests="1" failures="1"><testcase classname="tests.test_mod" name="test_a" file="tests/test_mod.py" line="7"><failure message="boom">Traceback</failure></testcase></testsuite>"""
    log_path = tmp_path / "pytest.log"
    log_path.write_text("", encoding="utf-8")
    junit_path = log_path.with_suffix(".junit.xml")
    junit_path.write_text(junit, encoding="utf-8")
    issues = list(parse_pytest_issues("", log_path))

    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, PytestIssue)
    assert issue.outcome == "FAILURE"


def test_parse_pytest_junit_collection_failure_uses_detailed_text(tmp_path: Path) -> None:
    junit = """<testsuite tests="1" errors="1"><testcase classname="tests.test_mod" name="test_collect"><error message="collection failure">ImportError while importing test module '/tmp/tests/test_mod.py'\nTraceback (most recent call last):\n...</error></testcase></testsuite>"""
    log_path = tmp_path / "pytest.log"
    log_path.write_text("", encoding="utf-8")
    junit_path = log_path.with_suffix(".junit.xml")
    junit_path.write_text(junit, encoding="utf-8")

    issues = list(parse_pytest_issues("", log_path))

    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, PytestIssue)
    assert issue.outcome == "ERROR"
    assert "ImportError while importing test module" in issue.message


def test_parse_bandit_json() -> None:
    raw = (
        '{"results":[{"test_id":"B602","issue_text":"shell=True",'
        '"issue_severity":"LOW","issue_confidence":"HIGH",'
        '"filename":"sample.py","line_number":3,"col_offset":0,"end_col_offset":12}]}'
    )
    issues = list(parse_bandit_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, BanditIssue)
    assert issue.test_id == "B602"
    assert issue.location.line == 3


def test_parse_pip_audit_json() -> None:
    raw = (
        '{"dependencies":[{"name":"urllib3","version":"1.26.0",'
        '"vulns":[{"id":"PYSEC-1","fix_versions":["2.0.0"],'
        '"aliases":["CVE-2023-0001"],"description":"desc"}]}]}'
    )
    issues = list(parse_pip_audit_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, PipAuditIssue)
    assert issue.package == "urllib3"
    assert issue.vulnerability_id == "PYSEC-1"


def test_parse_deptry_text() -> None:
    raw = "sample.py:12:1: DEP001 Dependency issue"
    issues = list(parse_deptry_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, DeptryIssue)
    assert issue.code == "DEP001"
    assert issue.location.line == 12


def test_parse_deptry_text_with_ansi_codes() -> None:
    raw = "\x1b[1mdev/sample.py\x1b[m\x1b[36m:\x1b[m12\x1b[36m:\x1b[m1\x1b[36m:\x1b[m \x1b[1m\x1b[31mDEP001\x1b[m Dependency issue"
    issues = list(parse_deptry_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, DeptryIssue)
    assert issue.code == "DEP001"
    assert issue.location.path == "dev/sample.py"


def test_parse_unittest_text() -> None:
    raw = "FAIL: test_add (tests.test_math.TestMath)"
    issues = list(parse_unittest_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, UnittestIssue)
    assert issue.outcome == "FAIL"


def test_parse_unittest_text_includes_reason_from_block() -> None:
    raw = (
        "ERROR: dev.test_mod (unittest.loader._FailedTest.dev.test_mod)\n"
        "----------------------------------------------------------------------\n"
        "ImportError: Failed to import test module: dev.test_mod\n"
        "Traceback (most recent call last):\n"
        "  ...\n"
        "ModuleNotFoundError: No module named 'missing_dep'\n"
    )
    issues = list(parse_unittest_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, UnittestIssue)
    assert issue.outcome == "ERROR"
    assert "ModuleNotFoundError: No module named 'missing_dep'" == issue.message


def test_parse_vulture_text() -> None:
    raw = "pkg/module.py:4: unused function 'x'"
    issues = list(parse_vulture_issues(raw))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, VultureIssue)
    assert issue.location.path == "pkg/module.py"
    assert issue.location.line == 4


def test_parse_diff_cover_snippet() -> None:
    raw = (
        "Failure. Coverage is below 80%.\n"
        "pkg/module.py (10.0%): Missing lines 1,4-6\n"
        "Missing: 5 lines\nCoverage: 10%"
    )
    issues = list(parse_diff_cover_issues(raw))
    assert any(isinstance(issue, DiffCoverFileIssue) for issue in issues)
    assert any(isinstance(issue, DiffCoverSummaryIssue) for issue in issues)
    assert any(isinstance(issue, DiffCoverThresholdIssue) for issue in issues)


def test_parse_coverage_report_fail() -> None:
    raw = "Coverage failure: total of 24 is less than fail-under=80"
    issues = list(parse_coverage_report_issues(raw, 80))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, CoverageReportIssue)
    assert issue.total == 24.0


def test_parse_coverage_xml_from_file(tmp_path: Path) -> None:
    log_path = tmp_path / "coverage_xml.log"
    log_path.write_text("Wrote XML report to coverage.xml\n", encoding="utf-8")
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text(
        '<coverage line-rate="0.8" branch-rate="0.2" lines-covered="8" '
        'lines-valid="10" branches-covered="2" branches-valid="10"/>',
        encoding="utf-8",
    )

    issues = list(parse_coverage_xml_issues(log_path.read_text(), 80, log_path))
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, CoverageXmlIssue)
    assert issue.total == 20.0
