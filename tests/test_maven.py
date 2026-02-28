import re
from collections.abc import Callable

import pytest

from dev.maven import MavenCoordinate, MavenVersion, is_valid_maven_coordinate

VersionComparator = Callable[[MavenVersion, MavenVersion], bool]


def _lt(a: MavenVersion, b: MavenVersion) -> bool:
    return a < b


def _le(a: MavenVersion, b: MavenVersion) -> bool:
    return a < b or a == b


def _eq(a: MavenVersion, b: MavenVersion) -> bool:
    return a == b


def _approx(a: MavenVersion, b: MavenVersion) -> bool:
    return a.approx_eq(b)


def _ne(a: MavenVersion, b: MavenVersion) -> bool:
    return a != b


def _not_approx(a: MavenVersion, b: MavenVersion) -> bool:
    return not a.approx_eq(b)


def _ge(a: MavenVersion, b: MavenVersion) -> bool:
    return a > b or a == b


def _gt(a: MavenVersion, b: MavenVersion) -> bool:
    return a > b


COMPARISON_OPS: dict[str, VersionComparator] = {
    "<": _lt,
    "<=": _le,
    "=": _eq,
    "~": _approx,
    "!=": _ne,
    "!~": _not_approx,
    ">=": _ge,
    ">": _gt,
}


def _assert_version_sequence(vs: str) -> None:
    ops = ["<", "~", "=", "!~", "!=", ">=", ">", "<="]
    op_regex = "|".join(re.escape(op) for op in ops)

    start = 0
    args: list[MavenVersion] = []
    found_ops: list[str] = []
    for match in re.finditer(op_regex, vs):
        op = match.group()
        found_ops.append(op)
        end = match.start()
        if end > start:
            v1_str = vs[start:end].strip()
            args.append(MavenVersion.parse(v1_str))
        start = match.end()

    args.append(MavenVersion.parse(vs[start:].strip()))

    for i, op in enumerate(found_ops):
        v1 = args[i]
        v2 = args[i + 1]
        assert COMPARISON_OPS[op](v1, v2), f"{v1} {op} {v2}"


@pytest.mark.parametrize(
    "sequence",
    [
        "1.0.0 = 1.0.0",
        "1 ~ 1.0 ~ 1.0.0 ~ 1.0.0.0",
        "1.0.0 !~ 1.0.1",
        "1.2.M01 < 1.2.M02 < 1.2.M06 < 1.2",
        "1.8.M01 < 1.8.RC1 < 1.8 < 1.8.1",
        "1.0.0-alpha < 1.0.0-beta < 1.0.0",
        "2.0.0-alpha.1 < 2.0.0-beta.1 < 2.0.0",
        "1.0-rc1 < 1.0-rc2 < 1.0 < 1.0.1",
        "2.0.08 ~ 2.0.8",
        "1.0.0-RC1 < 1.0.0-GA ~ 1.0.0.RELEASE ~ 1.0.0",
        "1.0.0.Final ~ 1.0.0-Final ~ 1.0.0",
    ],
)
def test_version_sequence(sequence: str) -> None:
    _assert_version_sequence(sequence)


@pytest.mark.parametrize(
    "coordinate,expected",
    [
        ("org.jetbrains.kotlinx:kotlinx-serialization-core:1.7.1", True),
        ("com.google.guava:guava:31.1-jre", True),
        ("io.papermc.paper:paper-api:1.21.1-R0.1-SNAPSHOT", True),
        ("invalid:coordinate", False),
    ],
)
def test_is_valid_coordinate(coordinate: str, expected: bool) -> None:
    assert is_valid_maven_coordinate(coordinate) is expected


def test_parse_coordinate_roundtrip() -> None:
    raw = "com.example:library:1.2.3"
    parsed = MavenCoordinate.parse(raw)
    assert parsed.group_id == "com.example"
    assert parsed.artifact_id == "library"
    assert parsed.version == "1.2.3"
    assert str(parsed) == raw


def test_parse_invalid_coordinate_raises() -> None:
    with pytest.raises(ValueError):
        MavenCoordinate.parse("invalid")
