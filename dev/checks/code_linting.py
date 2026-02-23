"""
* [x] Use linters or code formatters for each language in the repo to ensure consistent
      indentation, spacing, naming conventions, etc.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from dev.checks.base import FileCheck, FileContext, IssueType
from dev.messages import error

E_KTLINT_MISSING = IssueType("E_KTLINT_MISSING", "The 'ktlint' formatter is not installed.")
E_KTFMT_MISSING = IssueType("E_KTFMT_MISSING", "The 'ktfmt' formatter is not installed.")
E_KOTLIN_NOT_FORMATTED = IssueType("E_KOTLIN_NOT_FORMATTED", "Kotlin file is not formatted with ktfmt.")


class KotlinFormattingCheck(FileCheck):
    """Check Kotlin source files with ``ktfmt``."""

    def check(self, ctx: FileContext):
        if ctx.path.suffix != ".kt" or not ctx.path.is_file():
            return

        cmd = [
            "java",
            "-jar",
            "ktfmt-0.59-with-dependencies.jar",
            "--kotlinlang-style",
            "--set-exit-if-changed",
        ]

        try:
            result = subprocess.run(
                cmd + ["--dry-run", str(ctx.path)],
                capture_output=True,
                text=True,
            )

            def fix():
                try:
                    subprocess.run(
                        cmd + [str(ctx.path)],
                        capture_output=True,
                        text=True,
                    )
                except Exception as e:
                    error(f"Failed to format {ctx.path}: {e}")

            if result.returncode != 0:
                ctx.add_issue(E_KOTLIN_NOT_FORMATTED, fix=fix)

        except FileNotFoundError:
            ctx.add_issue(E_KTFMT_MISSING)


# class KotlinFormattingCheck(FileCheck):
#     """Check Kotlin source files with ``ktlint``."""

#     def check(self, ctx: FileContext):
#         if ctx.path.suffix != ".kt" or not ctx.path.is_file():
#             return

#         try:
#             result = subprocess.run(
#                 ["ktlint", str(ctx.path)],
#                 capture_output=True,
#                 text=True,
#             )

#             def fix():
#                 try:
#                     subprocess.run(
#                         ["ktlint", "-F", str(ctx.path)],
#                         capture_output=True,
#                         text=True,
#                     )
#                 except Exception as e:
#                     error(f"Failed to format {ctx.path}: {e}")

#             if result.returncode != 0:
#                 # Print errors first then \n\n then summary
#                 # Each error looks like: path:line:col: error message (rule)
#                 raw_errors = result.stdout.strip()
#                 i = raw_errors.rfind("\n\n")
#                 if i != -1:
#                     errors = raw_errors[:i].splitlines()
#                 else:
#                     errors = raw_errors.splitlines()

#                 # 14:59:00.712 [main] WARN com.pinterest.ktlint.cli.internal.KtlintCommandLine -- Lint has found errors than can be autocorrected using 'ktlint --format'
#                 pattern = re.compile(r"^.+:(\d+):\d+: (.+) \(.+\)$")
#                 for err in errors:
#                     if (
#                         "WARN com.pinterest.ktlint.cli.internal.KtlintCommandLine -- Lint has found errors"
#                         in err
#                     ):
#                         continue
#                     match = pattern.match(err)
#                     assert match is not None, f"Unexpected ktlint error format: {err}"
#                     line = int(match.group(1))
#                     message = match.group(2)

#                     ctx.add_issue(
#                         E_KOTLIN_NOT_FORMATTED, fix=fix, details=message, line=line
#                     )

#         except FileNotFoundError:
#             ctx.add_issue(E_KTLINT_MISSING)


E_CLANG_FORMAT_MISSING = IssueType("E_CLANG_FORMAT_MISSING", "The 'clang-format' formatter is not installed.")
E_CPP_NOT_FORMATTED = IssueType("E_CPP_NOT_FORMATTED", "C/C++ file is not formatted with clang-format.")


class CppFormattingCheck(FileCheck):
    """Check C/C++ source files with ``clang-format``."""

    def check(self, ctx: FileContext):
        if ctx.path.suffix not in {".c", ".cpp", ".cc", ".h", ".hpp"} or not ctx.path.is_file():
            return

        try:
            result = subprocess.run(
                ["clang-format", "--dry-run", "--Werror", str(ctx.path)],
                capture_output=True,
                text=True,
            )

            def fix():
                try:
                    # -i edits files in-place
                    subprocess.run(
                        ["clang-format", "-i", str(ctx.path)],
                        capture_output=True,
                        text=True,
                    )
                except Exception as e:
                    error(f"Failed to format {ctx.path}: {e}")

            if result.returncode != 0:
                ctx.add_issue(E_CPP_NOT_FORMATTED, fix=fix)
        except FileNotFoundError:
            ctx.add_issue(E_CLANG_FORMAT_MISSING)

        return ctx.issues


E_PURSTIDY_MISSING = IssueType("E_PURSTIDY_MISSING", "The 'purs-tidy' formatter is not installed.")
E_PURESCRIPT_NOT_FORMATTED = IssueType("E_PURESCRIPT_NOT_FORMATTED", "Purescript file is not formatted with purs-tidy.")


class PurescriptFormattingCheck(FileCheck):
    """Check Purescript files with ``purs-tidy``."""

    def check(self, ctx: FileContext):
        if ctx.path.suffix != ".purs" or not ctx.path.is_file():
            return

        try:
            # Use the dedicated 'check' command (preferred in current CLI)
            result = subprocess.run(
                ["purs-tidy", "check", str(ctx.path)],
                capture_output=True,
                text=True,
            )

            def fix():
                try:
                    # Format in place
                    subprocess.run(
                        ["purs-tidy", "format-in-place", str(ctx.path)],
                        capture_output=True,
                        text=True,
                    )
                except Exception as e:
                    error(f"Failed to format {ctx.path}: {e}")

            if result.returncode != 0:
                ctx.add_issue(E_PURESCRIPT_NOT_FORMATTED, fix=fix)
        except FileNotFoundError:
            ctx.add_issue(E_PURSTIDY_MISSING)

        return ctx.issues


E_CSHARPIER_MISSING = IssueType("E_CSHARPIER_MISSING", "The 'csharpier' formatter is not installed.")
E_CS_NOT_FORMATTED = IssueType("E_CS_NOT_FORMATTED", "C# file is not formatted with csharpier.")


class CSharpFormattingCheck(FileCheck):
    """Check C# files with ``csharpier``."""

    def _run(self, args: Sequence[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True)

    def check(self, ctx: FileContext):
        if ctx.path.suffix not in {".cs"} or not ctx.path.is_file():
            return

        dotnet_cmd = ["dotnet", "csharpier"]
        legacy_cmd = ["csharpier"]  # legacy tool alias still used in some setups

        selected: str | None = None  # "dotnet" | "legacy"

        try:
            # Prefer modern CLI: dotnet csharpier check <file>
            try:
                result = self._run(dotnet_cmd + ["check", str(ctx.path)])
                selected = "dotnet"
            except FileNotFoundError:
                # dotnet not found; try legacy shim
                result = self._run(legacy_cmd + ["--check", str(ctx.path)])
                selected = "legacy"

            # If 'dotnet' exists but tool isn't in manifest / not installed,
            # try legacy shim as a fallback before declaring missing.
            if result.returncode != 0 and selected == "dotnet":
                try:
                    result_legacy = self._run(legacy_cmd + ["--check", str(ctx.path)])
                    if result_legacy.returncode == 0:
                        selected = "legacy"
                        result = result_legacy
                except FileNotFoundError:
                    # ignore here; handled below if needed
                    pass

            def fix():
                try:
                    if selected == "legacy":
                        # Legacy CLI formats in-place by default
                        subprocess.run(
                            legacy_cmd + [str(ctx.path)],
                            capture_output=True,
                            text=True,
                        )
                    else:
                        # Default path: modern CLI
                        subprocess.run(
                            dotnet_cmd + ["format", str(ctx.path)],
                            capture_output=True,
                            text=True,
                        )
                except Exception as e:
                    error(f"Failed to format {ctx.path}: {e}")

            if result.returncode != 0:
                ctx.add_issue(E_CS_NOT_FORMATTED, fix=fix)

        except FileNotFoundError:
            # Neither `dotnet` nor legacy `csharpier` found
            ctx.add_issue(E_CSHARPIER_MISSING)

        return ctx.issues
