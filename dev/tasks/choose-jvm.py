#!/usr/bin/env python3

import argparse
import enum
import math
import os
import re
import sys
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from functools import cmp_to_key
from importlib import import_module

type VersionComponent = int | float
type VersionTuple = tuple[VersionComponent, ...]
type VersionInput = str | Sequence[VersionComponent]
type VersionRange = tuple[VersionTuple, VersionTuple]
type ParsedQuery = tuple[VersionRange, str, set[str]]


class VersionComparison(enum.Enum):
    """
    Enum for version comparison results.
    """

    LT = -1  # e.g. 8.0.1 < 8.0.2 or 8.0.1 < 8.1.0
    EQ = 0  # e.g. 8.0.1 == 8.0.1 and 8 == 8.0 but not 8.0.1 == 8.0.1.2
    GT = 1  # e.g. 8.0.2 > 8.0.1 or 8.1.0 > 8.0.2


def _normalize_version(version: VersionInput) -> list[VersionComponent]:
    if isinstance(version, str):
        return [int(x) for x in version.split(".")]
    return list(version)


def compare_versions(a: VersionInput, b: VersionInput) -> int:
    left = _normalize_version(a)
    right = _normalize_version(b)

    # remove trailing zeros
    while left and left[-1] == 0:
        left = left[:-1]
    while right and right[-1] == 0:
        right = right[:-1]

    for i in range(min(len(left), len(right))):
        if left[i] < right[i]:
            return -1
        if left[i] > right[i]:
            return 1

    if len(left) < len(right):
        return -1
    if len(left) > len(right):
        return 1
    return 0


def version_signed_distance(a: VersionInput, b: VersionInput, normalize: bool = False) -> tuple[float, ...]:
    left = _normalize_version(a)
    right = _normalize_version(b)

    # remove trailing zeros
    while left and left[-1] == 0:
        left = left[:-1]
    while right and right[-1] == 0:
        right = right[:-1]

    distance: list[float] = []
    for i in range(max(len(left), len(right))):
        av = float(left[i]) if i < len(left) else 0.0
        bv = float(right[i]) if i < len(right) else 0.0
        delta = av - bv
        if normalize:
            delta /= max(1.0, max(av, bv))
        distance.append(delta)
    return tuple(distance)


# for test_version_pair in [('8', '8.0'), ('8.0', '8.0.0'), ('8.0.1', '8.0.1'), ('8.0.1', '8.0.2'), ('8.0.2', '8.1.0'), ('9.0.1', '10')]:
#     r = compare_versions(*test_version_pair)
#     d = version_signed_distance(*test_version_pair)
#     print(test_version_pair, r, d)
#     assert compare_versions(test_version_pair[1], test_version_pair[0]) == -r
#     nd = tuple(-x for x in d)
#     assert version_signed_distance(test_version_pair[1], test_version_pair[0]) == nd
#     if r == 0:
#         assert all(x == 0 for x in d)


def find_installed_jvms_win32() -> set[str]:
    found_jvms: set[str] = set()

    # Step 1: check PATH to find Java installations
    for path in os.environ.get("PATH", "").split(";"):
        if not os.path.isdir(path):
            continue

        has_java = os.path.exists(os.path.join(path, "java.exe"))
        has_javaw = os.path.exists(os.path.join(path, "javaw.exe"))

        if not has_java or not has_javaw:
            continue

        java_home = os.path.abspath(path + os.sep + "..")

        # print("Found Java installation in PATH: {}".format(java_home))
        found_jvms.add(java_home)

    # Step 2: check JAVA_HOME to find Java installations
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        has_java = os.path.exists(os.path.join(java_home, "bin", "java.exe"))
        has_javaw = os.path.exists(os.path.join(java_home, "bin", "javaw.exe"))

        if has_java and has_javaw:
            # print("Found Java installation in JAVA_HOME: {}".format(java_home))
            found_jvms.add(os.path.abspath(java_home))

    # Step 3: check registry to find Java installations
    try:
        winreg_module = import_module("winreg")
    except ModuleNotFoundError:
        winreg_module = None

    if winreg_module is not None:
        open_key = getattr(winreg_module, "OpenKey", None)
        hkey_local_machine = getattr(winreg_module, "HKEY_LOCAL_MACHINE", None)
        query_info_key = getattr(winreg_module, "QueryInfoKey", None)
        enum_key = getattr(winreg_module, "EnumKey", None)
        query_value_ex = getattr(winreg_module, "QueryValueEx", None)

        if (
            callable(open_key)
            and hkey_local_machine is not None
            and callable(query_info_key)
            and callable(enum_key)
            and callable(query_value_ex)
        ):
            try:
                root_key = open_key(hkey_local_machine, r"SOFTWARE\JavaSoft\JDK")
                key_count = query_info_key(root_key)[0]
            except OSError:
                key_count = 0

            for i in range(0, key_count):
                key_name = enum_key(root_key, i)
                try:
                    key = open_key(hkey_local_machine, rf"SOFTWARE\JavaSoft\JDK\\{key_name}")
                    java_home_value, _ = query_value_ex(key, "JavaHome")
                except OSError:
                    continue
                if not isinstance(java_home_value, str):
                    continue

                has_java = os.path.exists(os.path.join(java_home_value, "bin", "java.exe"))
                has_javaw = os.path.exists(os.path.join(java_home_value, "bin", "javaw.exe"))
                if has_java and has_javaw:
                    found_jvms.add(os.path.abspath(java_home_value))

    # Step 4: check common locations to find Java installations
    win32api = __import__("win32api")
    drives = win32api.GetLogicalDriveStrings()
    drives = drives.split("\000")[:-1]

    for drive in drives:
        if not os.path.isdir(drive):
            continue

        PROGRAM_FILES_DIRS = [
            "Program Files",
            "Program Files (x86)",
        ]

        JVM_KEYWORDS = [
            "java",
            "jdk",
            "jre",
            "amazon correto",
            "openjdk",
            "zulu",
            "adoptopenjdk",
            "corretto",
            "graalvm",
            "eclipse",
            "adoptium",
        ]

        for program_files_dir in PROGRAM_FILES_DIRS:
            if not os.path.isdir(os.path.join(drive, program_files_dir)):
                continue

            for test_dir in os.listdir(os.path.join(drive, program_files_dir)):
                if test_dir == "JetBrains":
                    for jetbrains_dir in os.listdir(os.path.join(drive, program_files_dir, test_dir)):
                        if os.path.exists(os.path.join(drive, program_files_dir, test_dir, jetbrains_dir, "jbr")):

                            java_home = os.path.join(drive, program_files_dir, test_dir, jetbrains_dir, "jbr")
                            has_java = os.path.exists(os.path.join(java_home, "bin", "java.exe"))
                            has_javaw = os.path.exists(os.path.join(java_home, "bin", "javaw.exe"))

                            if has_java and has_javaw:
                                # print("Found Java installation in common location: {}".format(java_home))
                                found_jvms.add(os.path.abspath(java_home))

                if any(keyword in test_dir.lower() for keyword in JVM_KEYWORDS):
                    # two options: either there are subdirectories listing versions, or there is a single directory

                    java_home = os.path.join(drive, program_files_dir, test_dir)

                    if os.path.isdir(os.path.join(java_home, "bin")):
                        has_java = os.path.exists(os.path.join(java_home, "bin", "java.exe"))
                        has_javaw = os.path.exists(os.path.join(java_home, "bin", "javaw.exe"))
                        if has_java and has_javaw:
                            print(f"Found Java installation in common location: {java_home}")
                            found_jvms.add(os.path.abspath(java_home))
                    else:
                        for version_dir in os.listdir(java_home):
                            if not os.path.isdir(os.path.join(java_home, version_dir)):
                                continue

                            java_home = os.path.join(java_home, version_dir)

                            has_java = os.path.exists(os.path.join(java_home, "bin", "java.exe"))
                            has_javaw = os.path.exists(os.path.join(java_home, "bin", "javaw.exe"))
                            if has_java and has_javaw:
                                # print("Found Java installation in common location: {}".format(java_home))
                                found_jvms.add(os.path.abspath(java_home))

    # Step 5: check home directory to find Java installations
    user_home = os.path.expanduser("~")

    if os.path.exists(os.path.join(user_home, ".gradle", "jdks")):
        for test_dir in os.listdir(os.path.join(user_home, ".gradle", "jdks")):
            java_home = os.path.join(user_home, ".gradle", "jdks", test_dir)

            if not os.path.isdir(java_home):
                continue

            has_java = os.path.exists(os.path.join(java_home, "bin", "java.exe"))
            has_javaw = os.path.exists(os.path.join(java_home, "bin", "javaw.exe"))

            if has_java and has_javaw:
                # print("Found Java installation in home directory: {}".format(java_home))
                found_jvms.add(os.path.abspath(java_home))

    return found_jvms


def get_jvm_version(java_home: str) -> tuple[tuple[int, ...], str | None] | None:
    # Step 6: find out the versions
    release_path = os.path.join(java_home, "release")
    if not os.path.exists(release_path):
        print(f"No release file found in {java_home}")
        return None

    with open(release_path, encoding="utf-8") as f:
        java_version = None
        java_implementor = None

        for line in f:
            if line.startswith("JAVA_VERSION="):
                version_text = line.split("=")[1].strip().strip('"')
                if version_text.startswith("1."):
                    version_text = version_text[2:].replace("_", ".")

                parsed_version = tuple(int(x) for x in version_text.split("."))

                # print("Found version {} in {}".format(version, java_home))
                java_version = parsed_version
            elif line.startswith("IMPLEMENTOR="):
                implementor = line.split("=")[1].strip().strip('"')
                # print("Found implementor {} in {}".format(implementor, java_home))
                java_implementor = implementor

        if java_version is not None:
            return java_version, java_implementor
    return None


def parse_query(query: str) -> ParsedQuery:
    query_parts = query.strip().lower().split(" ")
    query_version = query_parts.pop(0)

    assert re.match(r"^\d+(\.\d+)*\+?$", query_version), f"Invalid version: {query_version}"

    if "+" in query_version:
        query_version = query_version[:-1]
        query_version_range_lower: list[VersionComponent] = [int(x) for x in query_version.split(".")]
        query_version_range_upper: list[VersionComponent] = query_version_range_lower[:-1] + [math.inf]
    else:
        query_version_range_lower = [int(x) for x in query_version.split(".")]
        query_version_range_upper = query_version_range_lower + [math.inf]

    query_version_range = (
        tuple(query_version_range_lower),
        tuple(query_version_range_upper),
    )

    query_order = "earliest"
    while "latest" in query_parts:
        query_order = "latest"
        query_parts.remove("latest")
    while "earliest" in query_parts:
        query_order = "earliest"
        query_parts.remove("earliest")

    query_keywords = set(query_parts)

    return query_version_range, query_order, query_keywords


# for test_query in ['8 earliest', '8+ adopt latest', '8.1+', '8.2.3', '8.2.3.4+']:
#     print(parse_query(test_query))


def rank_remapping[T: Hashable](
    values: Sequence[T],
    zero: T,
    cmp: Callable[[T, T], int] | None = None,
    reverse: bool = False,
) -> list[float]:
    mapping = [x for x in values if x != zero]
    if len(mapping) == 0:
        return [0.0 for _ in values]
    if cmp is None:
        mapping.sort(reverse=reverse, key=repr)
    else:
        mapping.sort(reverse=reverse, key=cmp_to_key(cmp))

    # remove consecutive duplicates
    unique_mapping = [x for i, x in enumerate(mapping) if i == 0 or x != mapping[i - 1]]

    score_to_rank = {score: (i + 1) / len(unique_mapping) for i, score in enumerate(unique_mapping)}

    return [score_to_rank[score] if score != zero else 0.0 for score in values]


if __name__ == "__main__":
    # choose-jvm.py 17+
    # choose-jvm.py 8

    parser = argparse.ArgumentParser()
    parser.add_argument("version", type=str, help="Java version", nargs="+")
    args = parser.parse_args()

    query = " ".join(args.version)
    try:
        version_range, version_order, version_keywords = parse_query(query)
    except AssertionError as e:
        print(e)
        sys.exit(1)

    print("Version range:", version_range, file=sys.stderr)
    print("Version order:", version_order, file=sys.stderr)
    print("Version keywords:", version_keywords, file=sys.stderr)

    # if not re.match(r'^\d+\+?$', args.version):
    #     print(f"Invalid version: {args.version}")
    #     sys.exit(1)

    jvm_homes = find_installed_jvms_win32()

    jvms: list[tuple[str, tuple[int, ...], str | None]] = []
    for jvm_home in jvm_homes:
        jvm_info = get_jvm_version(jvm_home)
        if jvm_info is None:
            continue
        jvm_version, java_implementor = jvm_info
        jvms.append((jvm_home, jvm_version, java_implementor))

    @dataclass
    class Scores:
        version: tuple[float, ...] | None
        keywords: int
        order: tuple[float, ...] | None

    @dataclass
    class ScoreRanks:
        version: float
        keywords: float
        order: float

    @dataclass
    class QueryResult:
        jvm_path: str
        java_version: tuple[int, ...]
        java_implementor: str | None
        scores: Scores
        score_ranks: ScoreRanks

    # query = '16+' # or '8 adopt' or '8+ adopt latest' or '8+ jetbrains earliest' or '8+ jetbrains latest' ...
    if query:
        # for query in ['16+', '8 adopt', '8+ adopt latest', '8+ jetbrains earliest', '8+ jetbrains latest', '18+ adopt']:
        # print(repr(query), parse_query(query))
        version_range, version_order, version_keywords = parse_query(query)

        scored_jvms: list[QueryResult] = []
        for jvm_home, java_version, java_implementor in jvms:
            min_version = version_range[0]
            max_version = version_range[1]

            min_cmp = compare_versions(min_version, java_version)
            max_cmp = compare_versions(max_version, java_version)

            # print(f'{min_version} cmp {java_version} = {min_cmp}')
            # print(f'{max_version} cmp {java_version} = {max_cmp}')

            version_distance: tuple[float, ...] | None
            if min_cmp <= 0 and max_cmp >= 0:
                version_distance = None
                # print("Found exact version range match")
            else:
                if min_cmp > 0:
                    # The closest version to the minimum is the best
                    version_distance = version_signed_distance(min_version, java_version)
                else:
                    version_distance = version_signed_distance(java_version, max_version)

            # print("Distance score: {}".format(distance_score))

            sd0 = version_signed_distance("0.0.0", java_version)
            order_score: tuple[float, ...] | None
            if version_order == "earliest":
                order_score = tuple(-x for x in sd0)
            elif version_order == "latest":
                order_score = sd0
            else:
                order_score = None

            # print("Order score: {}".format(order_score))

            keyword_score = sum(
                1
                for keyword in version_keywords
                if java_implementor is not None and keyword in java_implementor.lower()
            )
            keyword_score = len(version_keywords) - keyword_score

            # print("Keyword score: {}".format(keyword_score))

            all_scores = Scores(version_distance, keyword_score, order_score)

            scored_jvms.append(
                QueryResult(jvm_home, java_version, java_implementor, all_scores, ScoreRanks(0.0, 0.0, 0.0))
            )

        # print(f"JVM Versions: {[qr.java_version for qr in scored_jvms]}")
        distance_scores = [qr.scores.version for qr in scored_jvms]

        def _compare_optional_tuples(
            left: tuple[float, ...] | None,
            right: tuple[float, ...] | None,
        ) -> int:
            if left is None and right is None:
                return 0
            if left is None:
                return -1
            if right is None:
                return 1
            return compare_versions(left, right)

        # print(f"Distance scores: {distance_scores}")
        distance_rank_scores = rank_remapping(distance_scores, None, cmp=_compare_optional_tuples)
        # print(f"Distance scores: {distance_scores}")
        order_scores = [qr.scores.order for qr in scored_jvms]
        # print(f"Order scores: {order_scores}")
        order_rank_scores = rank_remapping(order_scores, None, cmp=_compare_optional_tuples)
        # print(f"Order scores: {order_scores}")
        keyword_scores = [qr.scores.keywords for qr in scored_jvms]
        # print(f"Keyword scores: {keyword_scores}")
        keyword_rank_scores = rank_remapping(keyword_scores, 0, cmp=lambda x, y: x - y)
        # print(f"Keyword scores: {keyword_scores}")

        for i, qr in enumerate(scored_jvms):
            qr.score_ranks = ScoreRanks(
                distance_rank_scores[i],
                keyword_rank_scores[i],
                order_rank_scores[i],
            )

        perfect_matches = [qr for qr in scored_jvms if qr.scores.version is None and qr.scores.keywords == 0]

        if len(perfect_matches) != 0:
            perfect_matches.sort(key=lambda qr: qr.score_ranks.order)
            print("Perfect matches:", file=sys.stderr)
            for qr in perfect_matches:
                print(
                    f"  {'.'.join(str(x) for x in qr.java_version)} {repr(qr.java_implementor)} {qr.jvm_path}",
                    file=sys.stderr,
                )

            best = perfect_matches[0]
            print(
                f"Best match: {'.'.join(str(x) for x in best.java_version)} {repr(best.java_implementor)} {best.jvm_path}",
                file=sys.stderr,
            )

            print(f'export JAVA_HOME="{best.jvm_path}"')
            print(f'export PATH="{best.jvm_path}/bin:$PATH"')

            # You can run it like this:
            # python3 choose-jvm.py 16+ latest amazon 2>/dev/null | source
            # or like this:
            # eval $(python3 choose-jvm.py 16+ latest amazon 2>/dev/null)
        else:
            scored_jvms.sort(
                key=lambda qr: (
                    qr.score_ranks.version,
                    qr.score_ranks.keywords,
                    qr.score_ranks.order,
                )
            )
            print("Best matches:", file=sys.stderr)
            for qr in scored_jvms:
                print(
                    f"  {'.'.join(str(x) for x in qr.java_version)} {repr(qr.java_implementor)} {qr.jvm_path}",
                    file=sys.stderr,
                )  #  {qr.scores} {qr.score_ranks}
