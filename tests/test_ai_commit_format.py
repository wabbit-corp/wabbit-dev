from dev.ai import ensure_semver_impact_line


def test_ensure_semver_impact_line_preserves_explicit_value() -> None:
    msg = "feat: add parser improvements\n\nSemver Impact: MINOR"
    assert ensure_semver_impact_line(msg) == msg


def test_ensure_semver_impact_line_appends_none_if_missing() -> None:
    msg = "chore: update docs"
    assert ensure_semver_impact_line(msg) == "chore: update docs\n\nSemver Impact: NONE"


def test_ensure_semver_impact_line_defaults_empty_messages() -> None:
    assert ensure_semver_impact_line("") == "chore: update repository\n\nSemver Impact: NONE"
