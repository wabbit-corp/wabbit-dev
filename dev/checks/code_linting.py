"""
* [x] Use linters or code formatters for each language in the repo to ensure consistent
      indentation, spacing, naming conventions, etc.
"""

from __future__ import annotations

import subprocess

from dev.checks.base import FileCheck, IssueType, IssueList, FileContext
from dev.messages import info, error


E_BLACK_MISSING = IssueType(
    "E_BLACK_MISSING", "The 'black' formatter is not installed."
)
E_PYTHON_NOT_FORMATTED = IssueType(
    "E_PYTHON_NOT_FORMATTED", "Python file is not formatted with black."
)


class PythonFormattingCheck(FileCheck):
    """Check Python source files with ``black``."""

    def check(self, ctx: FileContext):
        if ctx.path.suffix != ".py" or not ctx.path.is_file():
            return

        try:
            result = subprocess.run(
                ["black", "--check", "--quiet", str(ctx.path)],
                capture_output=True,
                text=True,
            )

            def fix():
                try:
                    subprocess.run(
                        ["black", str(ctx.path)],
                        capture_output=True,
                        text=True,
                    )
                except Exception as e:
                    error(f"Failed to format {ctx.path}: {e}")

            if result.returncode != 0:
                ctx.add_issue(E_PYTHON_NOT_FORMATTED, fix=fix)
        except FileNotFoundError:
            ctx.add_issue(E_BLACK_MISSING)

        return ctx.issues


E_KTLINT_MISSING = IssueType(
    "E_KTLINT_MISSING", "The 'ktlint' formatter is not installed."
)
E_KOTLIN_NOT_FORMATTED = IssueType(
    "E_KOTLIN_NOT_FORMATTED", "Kotlin file is not formatted with ktlint."
)


class KotlinFormattingCheck(FileCheck):
    """Check Kotlin source files with ``ktlint``."""

    def check(self, ctx: FileContext):
        if ctx.path.suffix != ".kt" or not ctx.path.is_file():
            return

        try:
            result = subprocess.run(
                ["ktlint", str(ctx.path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                ctx.add_issue(E_KOTLIN_NOT_FORMATTED)
        except FileNotFoundError:
            ctx.add_issue(E_KTLINT_MISSING)


E_CLANG_FORMAT_MISSING = IssueType(
    "E_CLANG_FORMAT_MISSING", "The 'clang-format' formatter is not installed."
)
E_CPP_NOT_FORMATTED = IssueType(
    "E_CPP_NOT_FORMATTED", "C/C++ file is not formatted with clang-format."
)


class CppFormattingCheck(FileCheck):
    """Check C/C++ source files with ``clang-format``."""

    def check(self, ctx: FileContext):
        if (
            ctx.path.suffix not in {".c", ".cpp", ".cc", ".h", ".hpp"}
            or not ctx.path.is_file()
        ):
            return

        try:
            result = subprocess.run(
                ["clang-format", "--dry-run", "--Werror", str(ctx.path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                ctx.add_issue(E_CPP_NOT_FORMATTED)
        except FileNotFoundError:
            ctx.add_issue(E_CLANG_FORMAT_MISSING)


E_PURSTIDY_MISSING = IssueType(
    "E_PURSTIDY_MISSING", "The 'purs-tidy' formatter is not installed."
)
E_PURESCRIPT_NOT_FORMATTED = IssueType(
    "E_PURESCRIPT_NOT_FORMATTED", "Purescript file is not formatted with purs-tidy."
)


class PurescriptFormattingCheck(FileCheck):
    """Check Purescript files with ``purs-tidy``."""

    def check(self, ctx: FileContext):
        if ctx.path.suffix != ".purs" or not ctx.path.is_file():
            return

        try:
            result = subprocess.run(
                ["purs-tidy", "format", "--check", str(ctx.path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                ctx.add_issue(E_PURESCRIPT_NOT_FORMATTED)
        except FileNotFoundError:
            ctx.add_issue(E_PURSTIDY_MISSING)


E_CSHARPIER_MISSING = IssueType(
    "E_CSHARPIER_MISSING", "The 'csharpier' formatter is not installed."
)
E_CS_NOT_FORMATTED = IssueType(
    "E_CS_NOT_FORMATTED", "C# file is not formatted with csharpier."
)


class CSharpFormattingCheck(FileCheck):
    """Check C# files with ``csharpier``."""

    def check(self, ctx: FileContext):
        if ctx.path.suffix not in {".cs"} or not ctx.path.is_file():
            return

        try:
            result = subprocess.run(
                ["csharpier", "--check", str(ctx.path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                ctx.add_issue(E_CS_NOT_FORMATTED)
        except FileNotFoundError:
            ctx.add_issue(E_CSHARPIER_MISSING)
