from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from dev.bootstrap import canonical_rerun_command, maybe_reexec_to_workspace_venv
from dev.messages import command_text, heading


class SuggestingArgumentParser(argparse.ArgumentParser):
    """
    Compatibility shim for tests and any remaining imports.

    The runtime no longer dispatches through argparse; python-wabbit-cli is the
    authoritative command grammar.
    """


def _configure_logging() -> None:
    level_name = os.environ.get("WABBIT_DEV_LOG_LEVEL", "WARNING").upper()
    level = logging.getLevelNamesMapping().get(level_name, logging.WARNING)
    logging.basicConfig(level=level, format="%(message)s", force=True)


def _format_failure_context() -> str:
    try:
        from dev.repo_resolution import format_workspace_context, resolve_workspace_context

        return format_workspace_context(resolve_workspace_context())
    except Exception:
        from dev.bootstrap import find_workspace_root

        cwd = Path.cwd().resolve()
        workspace_root = find_workspace_root(cwd)
        workspace_root_text = str(workspace_root) if workspace_root is not None else "-"
        return "\n".join(
            [
                "Resolved context:",
                f"  cwd: {cwd}",
                f"  workspace root: {workspace_root_text}",
                "  current project: -",
                "  current repo: -",
            ]
        )


def _print_failure_context(command_tokens: Sequence[str]) -> None:
    print(_format_failure_context(), file=sys.stderr)
    rerun_command = canonical_rerun_command(list(command_tokens))
    if rerun_command is None:
        return

    print(file=sys.stderr)
    print(heading("Retry from workspace root:", stream=sys.stderr), file=sys.stderr)
    print(f"  {command_text(rerun_command, stream=sys.stderr)}", file=sys.stderr)


async def async_main() -> int:
    if sys.platform.lower() == "win32":
        os.system("color")
        os.system("chcp 65001 > nul")
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore

    _configure_logging()

    from dev.typed_cli import maybe_run_typed_cli

    typed_exit_code = await maybe_run_typed_cli(sys.argv[1:], prog="dev")
    if typed_exit_code is None:
        print("dev: error: python-wabbit-cli is not available in this workspace.", file=sys.stderr)
        return 2
    return typed_exit_code


def main(*, launch_mode: Literal["script", "module"] = "script") -> None:
    maybe_reexec_to_workspace_venv(launch_mode=launch_mode)
    raise SystemExit(asyncio.run(async_main()))


__all__ = [
    "SuggestingArgumentParser",
    "async_main",
    "main",
    "_format_failure_context",
    "_print_failure_context",
]
