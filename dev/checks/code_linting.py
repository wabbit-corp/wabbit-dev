'''
* [ ] Use linters or code formatters for each language in the repo to ensure consistent
      indentation, spacing, naming conventions, etc.
'''

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from dev.checks.base import FileCheck, IssueType, IssueList, FileContext
from dev.messages import info, error


E_BLACK_MISSING = IssueType(
    "110a3061-88e1-4ddc-8873-cb2c34657c6d",
    "The 'black' formatter is not installed.",
)

E_NOT_FORMATTED = IssueType(
    "a3c3b758-1e3c-43f6-beba-f67bbebe97df",
    "Python file is not formatted with black.",
)

E_KTLINT_MISSING = IssueType(
    "2477ce3f-41d3-4df7-8156-7e25223aa7e6",
    "The 'ktlint' formatter is not installed.",
)

E_KOTLIN_NOT_FORMATTED = IssueType(
    "d62d8b23-7409-4b82-a21e-47636d86c1e0",
    "Kotlin file is not formatted with ktlint.",
)

E_CLANG_FORMAT_MISSING = IssueType(
    "0b3167f8-69c5-4ed2-9cf9-c4646afb41cd",
    "The 'clang-format' formatter is not installed.",
)

E_CPP_NOT_FORMATTED = IssueType(
    "b8e2ee5d-c479-4d5c-b916-e45c12a9a4f7",
    "C/C++ file is not formatted with clang-format.",
)

E_PURSTIDY_MISSING = IssueType(
    "7d74afd8-2f93-4c0c-867d-d8ac33ad039d",
    "The 'purs-tidy' formatter is not installed.",
)

E_PURESCRIPT_NOT_FORMATTED = IssueType(
    "3155b955-cc4d-48a2-bcca-c04a39588721",
    "Purescript file is not formatted with purs-tidy.",
)

E_CSHARPIER_MISSING = IssueType(
    "c4f018e4-d205-4377-94c4-b3eff0f70cf0",
    "The 'csharpier' formatter is not installed.",
)

E_CS_NOT_FORMATTED = IssueType(
    "3c9e387b-55a0-4dd0-8ea3-05dc7d33409c",
    "C# file is not formatted with csharpier.",
)


class PythonFormattingCheck(FileCheck):
    """Check Python source files with ``black``."""

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List:
        if path.suffix != ".py" or not path.is_file():
            return []

        issues = IssueList()

        try:
            result = subprocess.run(
                ["black", "--check", "--quiet", str(path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                issues.append(E_NOT_FORMATTED.at(path))
        except FileNotFoundError:
            issues.append(E_BLACK_MISSING.at(path))

        return issues.issues


class KotlinFormattingCheck(FileCheck):
    """Check Kotlin source files with ``ktlint``."""

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List:
        if path.suffix != ".kt" or not path.is_file():
            return []

        issues = IssueList()
        try:
            result = subprocess.run(
                ["ktlint", str(path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                issues.append(E_KOTLIN_NOT_FORMATTED.at(path))
        except FileNotFoundError:
            issues.append(E_KTLINT_MISSING.at(path))

        return issues.issues


class CppFormattingCheck(FileCheck):
    """Check C/C++ source files with ``clang-format``."""

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List:
        if path.suffix not in {".c", ".cpp", ".cc", ".h", ".hpp"} or not path.is_file():
            return []

        issues = IssueList()
        try:
            result = subprocess.run(
                ["clang-format", "--dry-run", "--Werror", str(path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                issues.append(E_CPP_NOT_FORMATTED.at(path))
        except FileNotFoundError:
            issues.append(E_CLANG_FORMAT_MISSING.at(path))

        return issues.issues


class PurescriptFormattingCheck(FileCheck):
    """Check Purescript files with ``purs-tidy``."""

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List:
        if path.suffix != ".purs" or not path.is_file():
            return []

        issues = IssueList()
        try:
            result = subprocess.run(
                ["purs-tidy", "format", "--check", str(path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                issues.append(E_PURESCRIPT_NOT_FORMATTED.at(path))
        except FileNotFoundError:
            issues.append(E_PURSTIDY_MISSING.at(path))

        return issues.issues


class CSharpFormattingCheck(FileCheck):
    """Check C# files with ``csharpier``."""

    def check(self, path: Path, ctx: FileContext = FileContext()) -> List:
        if path.suffix not in {".cs"} or not path.is_file():
            return []

        issues = IssueList()
        try:
            result = subprocess.run(
                ["csharpier", "--check", str(path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                issues.append(E_CS_NOT_FORMATTED.at(path))
        except FileNotFoundError:
            issues.append(E_CSHARPIER_MISSING.at(path))

        return issues.issues
