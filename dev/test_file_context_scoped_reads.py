from __future__ import annotations

from pathlib import Path

from dev.checks.base import (
    FileContext,
    IssueType,
    ScopedFindingIgnoreRule,
    ScopedReadSuppressions,
)

E_TEST_SCOPED_READ = IssueType("E_TEST_SCOPED_READ", "scoped read")
E_TEST_SCOPED_OTHER = IssueType("E_TEST_SCOPED_OTHER", "scoped read other")


def _newline_positions(text: str) -> list[int]:
    return [i for i, ch in enumerate(text) if ch == "\n"]


def test_inline_ignore_masks_entire_line_for_matching_issue(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        'host = "10.0.0.0"  # check:ignore E_TEST_SCOPED_READ\n' 'other = "172.16.0.1"\n',
        encoding="utf-8",
    )

    ctx = FileContext(check_name="test", path=path)
    masked = ctx.read_text(E_TEST_SCOPED_READ)
    unmasked = ctx.read_text(E_TEST_SCOPED_OTHER)

    assert masked.splitlines()[0].strip() == ""
    assert 'other = "172.16.0.1"' in masked
    assert 'host = "10.0.0.0"' in unmasked


def test_inline_ignore_value_masks_only_matching_value(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        'host = "10.0.0.0"  # check:ignore E_TEST_SCOPED_READ value=10.0.0.0\n' 'other = "172.16.0.1"\n',
        encoding="utf-8",
    )

    ctx = FileContext(check_name="test", path=path)
    masked = ctx.read_text(E_TEST_SCOPED_READ)

    first_line, second_line = masked.splitlines()
    assert "10.0.0.0" not in first_line
    assert "host =" in first_line
    assert "172.16.0.1" in second_line


def test_config_scoped_mask_preserves_length_and_newlines(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    original = 'host = "10.0.0.0"\nother = "172.16.0.1"\n'
    path.write_text(original, encoding="utf-8")

    suppressions = ScopedReadSuppressions(
        config_ignores=(
            ScopedFindingIgnoreRule(
                issue_id="E_TEST_SCOPED_READ",
                value="172.16.0.1",
            ),
        )
    )
    ctx = FileContext(
        check_name="test",
        path=path,
        scoped_read_suppressions=suppressions,
    )
    masked = ctx.read_text(E_TEST_SCOPED_READ)

    assert "172.16.0.1" not in masked
    assert len(masked) == len(original)
    assert _newline_positions(masked) == _newline_positions(original)
