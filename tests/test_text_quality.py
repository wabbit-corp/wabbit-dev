from __future__ import annotations

from pathlib import Path

from dev.checks.base import FileContext
from dev.checks.text_quality import E_BOM_AT_START, TextQualityCheck


def test_text_quality_bom_issue_is_fixable_for_valid_utf8_payload(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_bytes(b"\xef\xbb\xbfprint('ok')\n")

    ctx = FileContext(check_name="TextQualityCheck", path=path)
    TextQualityCheck().check(ctx)

    bom_issues = [issue for issue in ctx.issues if issue.issue_type.id == E_BOM_AT_START.id]
    assert len(bom_issues) == 1
    assert bom_issues[0].fix is not None

    bom_issues[0].fix()
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")

