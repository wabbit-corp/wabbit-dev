from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from dev.bootstrap import canonical_rerun_command, find_workspace_root


def _format_workspace_context() -> str:
    try:
        from dev.repo_resolution import format_workspace_context, resolve_workspace_context

        return format_workspace_context(resolve_workspace_context())
    except Exception:
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


def contextualize_failure(message: str, command_tokens: Sequence[str]) -> str:
    parts = [message]
    if "Resolved context:" not in message:
        parts.append(_format_workspace_context())
    rerun_command = canonical_rerun_command(list(command_tokens))
    if rerun_command is not None and "Retry from workspace root:" not in message:
        parts.extend(["", "Retry from workspace root:", f"  {rerun_command}"])
    return "\n".join(parts)
