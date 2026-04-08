"""
Checks for oversized files and checked-in binary dependency artifacts.
"""

from __future__ import annotations

from pathlib import Path

from dev.checks.base import FileCheck, FileContext, IssueType

DEFAULT_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
DEFAULT_BINARY_DEPENDENCY_DIR_NAMES = frozenset(
    {
        "deps",
        "external",
        "lib",
        "libs",
        "third-party",
        "third_party",
        "vendor",
    }
)
DEFAULT_BINARY_DEPENDENCY_SUFFIXES = frozenset(
    {
        ".a",
        ".aar",
        ".class",
        ".dll",
        ".dylib",
        ".ear",
        ".exe",
        ".jar",
        ".lib",
        ".nar",
        ".o",
        ".obj",
        ".so",
        ".war",
    }
)

E_LARGE_FILE = IssueType(
    "E_LARGE_FILE",
    "File is too large ({size_bytes} bytes; limit: {max_size_bytes} bytes).",
)
E_CHECKED_IN_BINARY_DEPENDENCY = IssueType(
    "E_CHECKED_IN_BINARY_DEPENDENCY",
    "Binary dependency artifact should not be checked into the repository.",
)


class LargeFileCheck(FileCheck):
    """Flags files that exceed a configurable size threshold."""

    def __init__(self, max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES):
        self.max_size_bytes = max_size_bytes

    def check(self, ctx: FileContext) -> None:
        if not ctx.is_file or ctx.path.is_symlink():
            return

        size_bytes = ctx.path.stat().st_size
        if size_bytes <= self.max_size_bytes:
            return

        ctx.add_issue(
            E_LARGE_FILE,
            size_bytes=size_bytes,
            max_size_bytes=self.max_size_bytes,
        )


class CheckedInBinaryDependencyCheck(FileCheck):
    """Flags common packaged binary dependencies checked into vendor-style directories."""

    def __init__(
        self,
        dependency_dir_names: frozenset[str] = DEFAULT_BINARY_DEPENDENCY_DIR_NAMES,
        binary_suffixes: frozenset[str] = DEFAULT_BINARY_DEPENDENCY_SUFFIXES,
    ):
        self.dependency_dir_names = {name.lower() for name in dependency_dir_names}
        self.binary_suffixes = {suffix.lower() for suffix in binary_suffixes}

    def check(self, ctx: FileContext) -> None:
        if not ctx.is_file or ctx.path.is_symlink():
            return

        if ctx.path.suffix.lower() not in self.binary_suffixes:
            return

        parent_dir_names = {parent.name.lower() for parent in ctx.path.parents}
        if self.dependency_dir_names.isdisjoint(parent_dir_names):
            return

        ctx.add_issue(E_CHECKED_IN_BINARY_DEPENDENCY)


__all__ = [
    "CheckedInBinaryDependencyCheck",
    "DEFAULT_BINARY_DEPENDENCY_DIR_NAMES",
    "DEFAULT_BINARY_DEPENDENCY_SUFFIXES",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "E_CHECKED_IN_BINARY_DEPENDENCY",
    "E_LARGE_FILE",
    "LargeFileCheck",
]
