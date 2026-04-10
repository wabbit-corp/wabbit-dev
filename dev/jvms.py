from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

type VersionTuple = tuple[int, ...]
type JvmOrder = Literal["latest", "earliest"]

_MACOS_JAVA_HOME_LINE_RE = re.compile(
    r'^\s*(?P<version>[0-9][0-9._+-]*)\s+\((?P<arch>[^)]+)\)\s+"(?P<implementor>[^"]+)"'
    r'(?:\s+-\s+"[^"]*")?\s+(?P<path>/.*)$'
)


@dataclass(frozen=True)
class InstalledJvm:
    home: Path
    version: VersionTuple
    implementor: str | None
    architecture: str | None = None
    source: str = "unknown"


@dataclass(frozen=True)
class JvmSelectionCriteria:
    min_version: VersionTuple | None = None
    max_version_exclusive: VersionTuple | None = None
    preferred_keywords: tuple[str, ...] = ()
    avoided_keywords: tuple[str, ...] = ()
    order: JvmOrder = "latest"


class JvmPolicyProject(Protocol):
    @property
    def jvm_policy(self) -> str | None: ...

    @property
    def jvm_task_policies(self) -> Mapping[str, str]: ...


def _trim_version(version: Sequence[int]) -> VersionTuple:
    normalized = list(version)
    while normalized and normalized[-1] == 0:
        normalized.pop()
    return tuple(normalized)


def _pad_version(version: Sequence[int], size: int = 6) -> VersionTuple:
    trimmed = _trim_version(version)
    if len(trimmed) >= size:
        return tuple(trimmed[:size])
    return tuple(trimmed) + (0,) * (size - len(trimmed))


def compare_versions(left: Sequence[int], right: Sequence[int]) -> int:
    left_key = _pad_version(left)
    right_key = _pad_version(right)
    if left_key < right_key:
        return -1
    if left_key > right_key:
        return 1
    return 0


def _version_distance(left: Sequence[int], right: Sequence[int]) -> VersionTuple:
    left_key = _pad_version(left)
    right_key = _pad_version(right)
    return tuple(abs(a - b) for a, b in zip(left_key, right_key, strict=False))


def _parse_version_text(version_text: str) -> VersionTuple:
    normalized = version_text.strip().strip('"')
    normalized = normalized.split("+", 1)[0]
    normalized = normalized.split("-", 1)[0]
    if normalized.startswith("1."):
        normalized = normalized[2:]
    normalized = normalized.replace("_", ".")
    return tuple(int(part) for part in normalized.split(".") if part)


def _java_binary_names() -> tuple[str, ...]:
    if os.name == "nt":
        return ("java.exe", "javaw.exe")
    return ("java",)


def is_java_home(path: Path) -> bool:
    if not path.is_dir():
        return False
    return all((path / "bin" / binary_name).exists() for binary_name in _java_binary_names())


def read_release_metadata(java_home: Path) -> InstalledJvm | None:
    release_path = java_home / "release"
    if not release_path.is_file():
        return None

    version: VersionTuple | None = None
    implementor: str | None = None
    with release_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line.startswith("JAVA_VERSION="):
                version = _parse_version_text(line.split("=", 1)[1])
            elif line.startswith("IMPLEMENTOR="):
                implementor = line.split("=", 1)[1].strip().strip('"')

    if version is None:
        return None

    return InstalledJvm(
        home=java_home,
        version=version,
        implementor=implementor,
        source="release",
    )


def parse_macos_java_home_listing(text: str) -> list[InstalledJvm]:
    jvms: list[InstalledJvm] = []
    for raw_line in text.splitlines():
        match = _MACOS_JAVA_HOME_LINE_RE.match(raw_line)
        if match is None:
            continue
        jvms.append(
            InstalledJvm(
                home=Path(match.group("path").strip()),
                version=_parse_version_text(match.group("version")),
                implementor=match.group("implementor").strip(),
                architecture=match.group("arch").strip(),
                source="macos-java-home",
            )
        )
    return jvms


def _discover_macos_java_home_listing() -> str:
    process = subprocess.run(
        ["/usr/libexec/java_home", "-V"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "\n".join(part for part in (process.stdout, process.stderr) if part)


def _discover_path_homes(env: Mapping[str, str]) -> list[Path]:
    delimiter = ";" if os.name == "nt" else ":"
    java_names = _java_binary_names()
    homes: list[Path] = []
    for path_entry in env.get("PATH", "").split(delimiter):
        if not path_entry:
            continue
        bin_dir = Path(path_entry)
        if not bin_dir.is_dir():
            continue
        if any((bin_dir / binary_name).exists() for binary_name in java_names):
            homes.append(bin_dir.parent)
    return homes


def _discover_standard_homes(home_dir: Path, platform_name: str) -> list[Path]:
    candidates: list[Path] = []
    if platform_name == "darwin":
        for base_dir in (
            Path("/Library/Java/JavaVirtualMachines"),
            home_dir / "Library" / "Java" / "JavaVirtualMachines",
        ):
            if not base_dir.is_dir():
                continue
            for child in sorted(base_dir.iterdir()):
                home = child / "Contents" / "Home"
                if home.is_dir():
                    candidates.append(home)

    for base_dir in (
        Path("/usr/lib/jvm"),
        home_dir / ".sdkman" / "candidates" / "java",
        home_dir / ".gradle" / "jdks",
    ):
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir()):
            if child.name == "current" and child.is_symlink():
                candidates.append(child.resolve())
                continue
            candidates.append(child)

    return candidates


def _merge_candidate(result: dict[Path, InstalledJvm], jvm: InstalledJvm) -> None:
    existing = result.get(jvm.home)
    if existing is None:
        result[jvm.home] = jvm
        return
    if existing.implementor is None and jvm.implementor is not None:
        result[jvm.home] = jvm


def discover_installed_jvms(
    *,
    env: Mapping[str, str] | None = None,
    home_dir: Path | None = None,
    platform_name: str | None = None,
    macos_java_home_listing: str | None = None,
) -> list[InstalledJvm]:
    effective_env = env if env is not None else os.environ
    effective_home_dir = home_dir if home_dir is not None else Path.home()
    effective_platform = platform_name if platform_name is not None else sys.platform
    found: dict[Path, InstalledJvm] = {}

    if effective_platform == "darwin":
        listing = macos_java_home_listing
        if listing is None:
            listing = _discover_macos_java_home_listing()
        for jvm in parse_macos_java_home_listing(listing):
            _merge_candidate(found, jvm)

    java_home_text = effective_env.get("JAVA_HOME")
    if java_home_text:
        java_home = Path(java_home_text).expanduser()
        metadata = read_release_metadata(java_home)
        if metadata is not None:
            _merge_candidate(found, metadata)

    for java_home in _discover_path_homes(effective_env):
        metadata = read_release_metadata(java_home)
        if metadata is not None:
            _merge_candidate(found, metadata)

    for java_home in _discover_standard_homes(effective_home_dir, effective_platform):
        metadata = read_release_metadata(java_home)
        if metadata is not None:
            _merge_candidate(found, metadata)

    return sorted(found.values(), key=lambda item: (item.home.as_posix(), item.version))


def parse_legacy_query(query: str) -> JvmSelectionCriteria:
    tokens = [token.strip().lower() for token in query.split() if token.strip()]
    if not tokens:
        raise ValueError("Legacy JVM query must not be empty")

    version_token = tokens.pop(0)
    exact_match = not version_token.endswith("+")
    if not re.fullmatch(r"\d+(?:\.\d+)*(?:\+)?", version_token):
        raise ValueError(f"Invalid JVM query version {version_token!r}")

    base_version_text = version_token[:-1] if version_token.endswith("+") else version_token
    min_version = _parse_version_text(base_version_text)
    max_version_exclusive: VersionTuple | None = None
    if exact_match:
        major = min_version[0]
        max_version_exclusive = (major + 1,)

    order: JvmOrder = "earliest"
    if "latest" in tokens:
        order = "latest"
        tokens = [token for token in tokens if token != "latest"]
    elif "earliest" in tokens:
        order = "earliest"
        tokens = [token for token in tokens if token != "earliest"]

    return JvmSelectionCriteria(
        min_version=min_version,
        max_version_exclusive=max_version_exclusive,
        preferred_keywords=tuple(tokens),
        order=order,
    )


def criteria_from_policy_name(policy_name: str) -> JvmSelectionCriteria:
    normalized = policy_name.strip().lower()
    if not normalized or normalized == "auto":
        return JvmSelectionCriteria(order="latest")

    if normalized == "android-agp-21":
        return JvmSelectionCriteria(
            min_version=(21,),
            max_version_exclusive=(22,),
            preferred_keywords=("corretto", "amazon"),
            avoided_keywords=("graalvm",),
            order="latest",
        )

    match = re.fullmatch(r"jvm-(\d+)(\+)?", normalized)
    if match is not None:
        major = int(match.group(1))
        if match.group(2):
            return JvmSelectionCriteria(min_version=(major,), order="latest")
        return JvmSelectionCriteria(
            min_version=(major,),
            max_version_exclusive=(major + 1,),
            order="latest",
        )

    raise ValueError(f"Unknown JVM policy {policy_name!r}")


def resolve_project_jvm_policy(
    project: JvmPolicyProject,
    *,
    task_name: str | None,
    repo_policy: str | None,
    global_jvm_version: int | None,
) -> str:
    if task_name:
        exact_policy = project.jvm_task_policies.get(task_name)
        if exact_policy is not None:
            return exact_policy
        for pattern, policy in project.jvm_task_policies.items():
            if any(char in pattern for char in "*?[]") and fnmatch.fnmatch(task_name, pattern):
                return policy

    if project.jvm_policy is not None:
        return project.jvm_policy
    if repo_policy is not None:
        return repo_policy
    if global_jvm_version is not None:
        return f"jvm-{global_jvm_version}"
    return "auto"


def _version_in_range(version: VersionTuple, criteria: JvmSelectionCriteria) -> bool:
    if criteria.min_version is not None and compare_versions(version, criteria.min_version) < 0:
        return False
    if criteria.max_version_exclusive is not None and compare_versions(version, criteria.max_version_exclusive) >= 0:
        return False
    return True


def _distance_to_range(version: VersionTuple, criteria: JvmSelectionCriteria) -> VersionTuple:
    if criteria.min_version is not None and compare_versions(version, criteria.min_version) < 0:
        return _version_distance(criteria.min_version, version)
    if criteria.max_version_exclusive is not None and compare_versions(version, criteria.max_version_exclusive) >= 0:
        return _version_distance(version, criteria.max_version_exclusive)
    return (0, 0, 0, 0, 0, 0)


def _implementor_text(jvm: InstalledJvm) -> str:
    implementor = jvm.implementor
    if implementor is None:
        return ""
    return implementor.lower()


def _preferred_keyword_rank(jvm: InstalledJvm, preferred_keywords: Sequence[str]) -> int:
    if not preferred_keywords:
        return 0
    implementor_text = _implementor_text(jvm)
    for index, keyword in enumerate(preferred_keywords):
        if keyword in implementor_text:
            return index
    return len(preferred_keywords) + 1


def _avoided_keyword_penalty(jvm: InstalledJvm, avoided_keywords: Sequence[str]) -> int:
    implementor_text = _implementor_text(jvm)
    if any(keyword in implementor_text for keyword in avoided_keywords):
        return 1
    return 0


def _order_key(version: VersionTuple, order: JvmOrder) -> VersionTuple:
    padded = _pad_version(version)
    if order == "latest":
        return tuple(-item for item in padded)
    return padded


def rank_jvms(
    installed_jvms: Sequence[InstalledJvm],
    criteria: JvmSelectionCriteria,
) -> list[InstalledJvm]:
    return sorted(
        installed_jvms,
        key=lambda jvm: (
            0 if _version_in_range(jvm.version, criteria) else 1,
            _avoided_keyword_penalty(jvm, criteria.avoided_keywords),
            _preferred_keyword_rank(jvm, criteria.preferred_keywords),
            _distance_to_range(jvm.version, criteria),
            _order_key(jvm.version, criteria.order),
            jvm.home.as_posix(),
        ),
    )


def select_jvm(
    installed_jvms: Sequence[InstalledJvm],
    *,
    policy_name: str | None = None,
    legacy_query: str | None = None,
) -> InstalledJvm | None:
    if policy_name is not None and legacy_query is not None:
        raise ValueError("Specify either policy_name or legacy_query, not both")
    if not installed_jvms:
        return None

    if policy_name is not None:
        criteria = criteria_from_policy_name(policy_name)
    elif legacy_query is not None:
        criteria = parse_legacy_query(legacy_query)
    else:
        criteria = JvmSelectionCriteria(order="latest")

    ranked = rank_jvms(installed_jvms, criteria)
    if not ranked:
        return None
    return ranked[0]


__all__ = [
    "InstalledJvm",
    "JvmPolicyProject",
    "JvmSelectionCriteria",
    "compare_versions",
    "criteria_from_policy_name",
    "discover_installed_jvms",
    "is_java_home",
    "parse_legacy_query",
    "parse_macos_java_home_listing",
    "rank_jvms",
    "read_release_metadata",
    "resolve_project_jvm_policy",
    "select_jvm",
]
