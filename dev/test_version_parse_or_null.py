import sys
from pathlib import Path


def _version_cls():
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

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
