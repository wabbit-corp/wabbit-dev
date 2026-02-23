from __future__ import annotations

from pathlib import Path

from dev.checks.base import FileContext, ScopedFindingIgnoreRule, ScopedReadSuppressions
from dev.checks.hardcoded import (
    E_HARDCODED_INTERNAL_HOSTNAME_IP,
    HardcodedInternalHostnameIpCheck,
)


def _issue_values(ctx: FileContext) -> set[str]:
    values: set[str] = set()
    for issue in ctx.issues:
        if issue.issue_type.id != E_HARDCODED_INTERNAL_HOSTNAME_IP.id:
            continue
        if issue.data is None:
            continue
        value = issue.data.get("host_or_ip")
        if isinstance(value, str):
            values.add(value)
    return values


def test_hardcoded_internal_host_ip_inline_suppression(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        'first = "10.0.0.0"  # check:ignore E_HARDCODED_INTERNAL_HOSTNAME_IP value=10.0.0.0\n'
        'second = "172.16.0.1"\n',
        encoding="utf-8",
    )

    ctx = FileContext(check_name="HardcodedInternalHostnameIpCheck", path=path)
    HardcodedInternalHostnameIpCheck().check(ctx)

    values = _issue_values(ctx)
    assert "10.0.0.0" not in values
    assert "172.16.0.1" in values


def test_hardcoded_internal_host_ip_config_suppression(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        'first = "10.0.0.0"\n'
        'second = "172.16.0.1"\n',
        encoding="utf-8",
    )

    suppressions = ScopedReadSuppressions(
        config_ignores=(
            ScopedFindingIgnoreRule(
                issue_id=E_HARDCODED_INTERNAL_HOSTNAME_IP.id,
                value="10.0.0.0",
            ),
        )
    )
    ctx = FileContext(
        check_name="HardcodedInternalHostnameIpCheck",
        path=path,
        scoped_read_suppressions=suppressions,
    )
    HardcodedInternalHostnameIpCheck().check(ctx)

    values = _issue_values(ctx)
    assert "10.0.0.0" not in values
    assert "172.16.0.1" in values
