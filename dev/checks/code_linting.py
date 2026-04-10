"""
* [x] Use linters or code formatters for each language in the repo to ensure consistent
      indentation, spacing, naming conventions, etc.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from dev.checks.base import FileCheck, FileContext, IssueType
from dev.messages import error
from dev.tool_paths import find_tool, workspace_root

E_KTLINT_MISSING = IssueType("E_KTLINT_MISSING", "The 'ktlint' formatter is not installed.")
E_KTFMT_MISSING = IssueType("E_KTFMT_MISSING", "The 'ktfmt' formatter is not installed.")
E_KOTLIN_NOT_FORMATTED = IssueType("E_KOTLIN_NOT_FORMATTED", "Kotlin file is not formatted with ktfmt.")
E_KTFMT_FAILED = IssueType("E_KTFMT_FAILED", "The 'ktfmt' formatter failed: {reason}.")


def _formatter_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part and part.strip())


def _default_failure_reason(result: subprocess.CompletedProcess[str]) -> str:
    output = _formatter_output(result)
    if output:
        return output
    return f"Exited with status {result.returncode}"


class KotlinFormattingCheck(FileCheck):
    """Check Kotlin source files with ``ktfmt``."""

    def check(self, ctx: FileContext) -> None:
        if ctx.path.suffix != ".kt" or not ctx.path.is_file():
            return

        cmd = [*_ktfmt_command(), "--kotlinlang-style", "--set-exit-if-changed"]

        try:
            result = subprocess.run(
                cmd + ["--dry-run", str(ctx.path)],
                capture_output=True,
                text=True,
            )

            def fix() -> None:
                try:
                    subprocess.run(
                        cmd + [str(ctx.path)],
                        capture_output=True,
                        text=True,
                    )
                except Exception as e:
                    error(f"Failed to format {ctx.path}: {e}")

            output = _formatter_output(result)
            if result.returncode == 0:
                return
            if "Unable to access jarfile" in output or "No such file or directory" in output:
                ctx.add_issue(E_KTFMT_MISSING)
            elif result.returncode == 1:
                ctx.add_issue(E_KOTLIN_NOT_FORMATTED, fix=fix)
            else:
                ctx.add_issue(E_KTFMT_FAILED, reason=_default_failure_reason(result))

        except FileNotFoundError:
            ctx.add_issue(E_KTFMT_MISSING)


def _ktfmt_command() -> list[str]:
    ktfmt = find_tool("ktfmt")
    if ktfmt is not None:
        return [str(ktfmt)]

    for root in (Path.cwd(), workspace_root()):
        jars = sorted(root.glob("ktfmt-*-with-dependencies.jar"))
        if jars:
            return ["java", "-jar", str(jars[-1])]

    return ["ktfmt"]


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
E_CLANG_FORMAT_FAILED = IssueType("E_CLANG_FORMAT_FAILED", "The 'clang-format' formatter failed: {reason}.")


class CppFormattingCheck(FileCheck):
    """Check C/C++ source files with ``clang-format``."""

    def check(self, ctx: FileContext) -> None:
        if ctx.path.suffix not in {".c", ".cpp", ".cc", ".h", ".hpp"} or not ctx.path.is_file():
            return

        clang_format = find_tool("clang-format")
        if clang_format is None:
            ctx.add_issue(E_CLANG_FORMAT_MISSING)
            return
        cmd = [str(clang_format)]

        try:
            result = subprocess.run(
                cmd + ["--dry-run", "--Werror", str(ctx.path)],
                capture_output=True,
                text=True,
            )

            def fix() -> None:
                try:
                    # -i edits files in-place
                    subprocess.run(
                        cmd + ["-i", str(ctx.path)],
                        capture_output=True,
                        text=True,
                    )
                except Exception as e:
                    error(f"Failed to format {ctx.path}: {e}")

            if result.returncode == 1:
                ctx.add_issue(E_CPP_NOT_FORMATTED, fix=fix)
            elif result.returncode != 0:
                ctx.add_issue(E_CLANG_FORMAT_FAILED, reason=_default_failure_reason(result))
        except FileNotFoundError:
            ctx.add_issue(E_CLANG_FORMAT_MISSING)


E_PURSTIDY_MISSING = IssueType("E_PURSTIDY_MISSING", "The 'purs-tidy' formatter is not installed.")
E_PURESCRIPT_NOT_FORMATTED = IssueType("E_PURESCRIPT_NOT_FORMATTED", "Purescript file is not formatted with purs-tidy.")
E_PURSTIDY_FAILED = IssueType("E_PURSTIDY_FAILED", "The 'purs-tidy' formatter failed: {reason}.")


class PurescriptFormattingCheck(FileCheck):
    """Check Purescript files with ``purs-tidy``."""

    def check(self, ctx: FileContext) -> None:
        if ctx.path.suffix != ".purs" or not ctx.path.is_file():
            return

        purs_tidy = find_tool("purs-tidy")
        if purs_tidy is None:
            ctx.add_issue(E_PURSTIDY_MISSING)
            return
        cmd = [str(purs_tidy)]

        try:
            # Use the dedicated 'check' command (preferred in current CLI)
            result = subprocess.run(
                cmd + ["check", str(ctx.path)],
                capture_output=True,
                text=True,
            )

            def fix() -> None:
                try:
                    # Format in place
                    subprocess.run(
                        cmd + ["format-in-place", str(ctx.path)],
                        capture_output=True,
                        text=True,
                    )
                except Exception as e:
                    error(f"Failed to format {ctx.path}: {e}")

            if result.returncode == 1:
                ctx.add_issue(E_PURESCRIPT_NOT_FORMATTED, fix=fix)
            elif result.returncode != 0:
                ctx.add_issue(E_PURSTIDY_FAILED, reason=_default_failure_reason(result))
        except FileNotFoundError:
            ctx.add_issue(E_PURSTIDY_MISSING)


E_CSHARPIER_MISSING = IssueType("E_CSHARPIER_MISSING", "The 'csharpier' formatter is not installed.")
E_CS_NOT_FORMATTED = IssueType("E_CS_NOT_FORMATTED", "C# file is not formatted with csharpier.")
E_CSHARPIER_FAILED = IssueType("E_CSHARPIER_FAILED", "The 'csharpier' formatter failed: {reason}.")


def _looks_like_dotnet_csharpier_missing(result: subprocess.CompletedProcess[str]) -> bool:
    output = _formatter_output(result).lower()
    missing_markers = (
        "dotnet-csharpier does not exist",
        "could not execute because the specified command or file was not found",
        "you intended to execute a .net program",
        "dotnet csharpier",
        "was not found",
    )
    return any(marker in output for marker in missing_markers)


class CSharpFormattingCheck(FileCheck):
    """Check C# files with ``csharpier``."""

    def _run(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, capture_output=True, text=True)

    def check(self, ctx: FileContext) -> None:
        if ctx.path.suffix not in {".cs"} or not ctx.path.is_file():
            return

        dotnet_cmd = ["dotnet", "csharpier"]
        managed_csharpier = find_tool("csharpier") or find_tool("dotnet-csharpier")
        legacy_cmd = [str(managed_csharpier)] if managed_csharpier is not None else ["csharpier"]

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
                dotnet_result = result
                try:
                    result_legacy = self._run(legacy_cmd + ["--check", str(ctx.path)])
                    if _looks_like_dotnet_csharpier_missing(dotnet_result) or result_legacy.returncode == 0:
                        selected = "legacy"
                        result = result_legacy
                except FileNotFoundError:
                    if _looks_like_dotnet_csharpier_missing(result):
                        ctx.add_issue(E_CSHARPIER_MISSING)
                        return

            def fix() -> None:
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

            if result.returncode == 1:
                ctx.add_issue(E_CS_NOT_FORMATTED, fix=fix)
            elif result.returncode != 0:
                if selected == "dotnet" and _looks_like_dotnet_csharpier_missing(result):
                    ctx.add_issue(E_CSHARPIER_MISSING)
                else:
                    ctx.add_issue(E_CSHARPIER_FAILED, reason=_default_failure_reason(result))

        except FileNotFoundError:
            # Neither `dotnet` nor legacy `csharpier` found
            ctx.add_issue(E_CSHARPIER_MISSING)


__all__ = [
    "E_KTLINT_MISSING",
    "E_KTFMT_MISSING",
    "E_KOTLIN_NOT_FORMATTED",
    "E_KTFMT_FAILED",
    "KotlinFormattingCheck",
    "E_CLANG_FORMAT_MISSING",
    "E_CPP_NOT_FORMATTED",
    "E_CLANG_FORMAT_FAILED",
    "CppFormattingCheck",
    "E_PURSTIDY_MISSING",
    "E_PURESCRIPT_NOT_FORMATTED",
    "E_PURSTIDY_FAILED",
    "PurescriptFormattingCheck",
    "E_CSHARPIER_MISSING",
    "E_CS_NOT_FORMATTED",
    "E_CSHARPIER_FAILED",
    "CSharpFormattingCheck",
]
