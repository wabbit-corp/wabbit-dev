from pathlib import Path

from dev.ignore_files import IgnoreMatcher


def test_ignore_matcher_respects_root_gitignore_directory_patterns(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    matcher = IgnoreMatcher(tmp_path)

    ignored_dir = tmp_path / ".venv"
    kept_dir = tmp_path / "src"
    ignored_dir.mkdir()
    kept_dir.mkdir()

    assert matcher.matches(ignored_dir, is_dir=True) is True
    assert matcher.matches(kept_dir, is_dir=True) is False


def test_ignore_matcher_respects_nested_gitignore_patterns_and_negation(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / ".gitignore").write_text("*.generated.md\n!keep.generated.md\n", encoding="utf-8")

    matcher = IgnoreMatcher(tmp_path)

    ignored_file = docs_dir / "api.generated.md"
    kept_file = docs_dir / "keep.generated.md"

    assert matcher.matches(ignored_file, is_dir=False) is True
    assert matcher.matches(kept_file, is_dir=False) is False


def test_ignore_matcher_respects_nested_checkignore_directory_patterns(tmp_path: Path) -> None:
    generated_dir = tmp_path / "docs" / "generated"
    generated_dir.mkdir(parents=True)
    (tmp_path / "docs" / ".checkignore").write_text("generated/\n", encoding="utf-8")

    matcher = IgnoreMatcher(tmp_path)

    assert matcher.matches(generated_dir, is_dir=True) is True
