from pathlib import Path

from dev.checks.base import FileContext
from dev.checks.chinese_firewall import E_CENSORED_KEYWORD, CensoredKeywords
from dev.checks.trufflehog import E_HIGH_ENTROPY_STRING, HighEntropyStringCheck


def test_chinese_firewall_reports_first_line_as_line_one(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("forbidden\nok\n", encoding="utf-8")
    ctx = FileContext(check_name="CensoredKeywords", path=path)

    CensoredKeywords(error_on={"forbidden"}).check(ctx)

    assert len(ctx.issues.issues) == 1
    issue = ctx.issues.issues[0]
    assert issue.issue_type == E_CENSORED_KEYWORD
    assert issue.location is not None
    assert list(issue.location.lines or []) == [1]


def test_trufflehog_reports_second_line_as_line_two(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        "safe = 'hello'\nsecret = 'QWxhZGRpbjpPcGVuU2VzYW1lQmFzZTY0S2V5'\n",
        encoding="utf-8",
    )
    ctx = FileContext(check_name="HighEntropyStringCheck", path=path)

    HighEntropyStringCheck().check(ctx)

    assert len(ctx.issues.issues) >= 1
    issue = ctx.issues.issues[0]
    assert issue.issue_type == E_HIGH_ENTROPY_STRING
    assert issue.location is not None
    assert list(issue.location.lines or []) == [2]
