from pathlib import Path

from dev.ignore_files import (
    CheckIgnoreIssueDirective,
    CheckIgnoreIssueMatcher,
    IgnoreMatcher,
    parse_checkignore_issue_directive,
    read_checkignore_issue_directives,
    read_ignore_patterns,
)


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


def test_ignore_matcher_supports_extra_metadata_predicates(tmp_path: Path) -> None:
    generated_file = tmp_path / "generated.txt"
    generated_file.write_text("generated\n", encoding="utf-8")

    matcher = IgnoreMatcher(
        tmp_path,
        extra_predicates=(lambda path, is_dir: not is_dir and path == generated_file.resolve(),),
    )

    assert matcher.matches(generated_file, is_dir=False) is True


def test_read_ignore_patterns_skips_issue_directives(tmp_path: Path) -> None:
    checkignore = tmp_path / ".checkignore"
    checkignore.write_text(
        "build/\n" "check:ignore E_TEST_VALUE_MATCH sample.py\n" "# comment\n",
        encoding="utf-8",
    )

    assert read_ignore_patterns(checkignore) == ["build/"]


def test_parse_checkignore_issue_directive_supports_optional_value() -> None:
    assert parse_checkignore_issue_directive("check:ignore E_TEST_VALUE_MATCH sample.py") == (
        CheckIgnoreIssueDirective(
            issue_id="E_TEST_VALUE_MATCH",
            pathspec="sample.py",
            matcher=None,
        )
    )
    assert parse_checkignore_issue_directive("check:ignore * src/*.py value=10.0.0.0") == CheckIgnoreIssueDirective(
        issue_id="*",
        pathspec="src/*.py",
        matcher=CheckIgnoreIssueMatcher(value="10.0.0.0"),
    )
    assert parse_checkignore_issue_directive(
        "check:ignore E_HARDCODED_URL config/items/head-items.rkt url_found~http://textures.minecraft.net/texture/.+"
    ) == CheckIgnoreIssueDirective(
        issue_id="E_HARDCODED_URL",
        pathspec="config/items/head-items.rkt",
        matcher=CheckIgnoreIssueMatcher(
            field_name="url_found",
            field_regex=r"http://textures.minecraft.net/texture/.+",
        ),
    )
    assert parse_checkignore_issue_directive(
        "check:ignore E_HARDCODED_URL config/codex/voting.rkt url_found=https://example.com"
    ) == CheckIgnoreIssueDirective(
        issue_id="E_HARDCODED_URL",
        pathspec="config/codex/voting.rkt",
        matcher=CheckIgnoreIssueMatcher(
            field_name="url_found",
            field_value="https://example.com",
        ),
    )


def test_read_checkignore_issue_directives_reads_only_directive_lines(tmp_path: Path) -> None:
    checkignore = tmp_path / ".checkignore"
    checkignore.write_text(
        "\n".join(
            [
                "build/",
                "check:ignore E_TEST_VALUE_MATCH sample.py",
                "check:ignore * src/*.py value=10.0.0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert read_checkignore_issue_directives(checkignore) == [
        CheckIgnoreIssueDirective(
            issue_id="E_TEST_VALUE_MATCH",
            pathspec="sample.py",
            matcher=None,
        ),
        CheckIgnoreIssueDirective(
            issue_id="*",
            pathspec="src/*.py",
            matcher=CheckIgnoreIssueMatcher(value="10.0.0.0"),
        ),
    ]
