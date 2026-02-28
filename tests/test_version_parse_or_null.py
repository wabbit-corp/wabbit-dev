import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dev.config import Version


def _version_cls() -> type["Version"]:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.config import Version

    return Version


def test_parse_or_null_rejects_suffix_versions() -> None:
    Version = _version_cls()

    assert Version.parse_or_null("1.2.3-alpha") is None
    assert Version.parse_or_null("1.2.3+dev-SNAPSHOT-extra") is None


def test_parse_or_null_accepts_whitespace_wrapped_versions() -> None:
    Version = _version_cls()

    parsed = Version.parse_or_null("  1.2.3  ")
    assert parsed is not None
    assert str(parsed) == "1.2.3"


def test_parse_or_null_accepts_dev_snapshot_suffix() -> None:
    Version = _version_cls()

    parsed = Version.parse_or_null("1.2.3+dev-SNAPSHOT")
    assert parsed is not None
    assert str(parsed) == "1.2.3+dev-SNAPSHOT"
