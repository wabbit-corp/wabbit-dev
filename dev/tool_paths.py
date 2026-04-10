from __future__ import annotations

import os
import shutil
from pathlib import Path

from dev.bootstrap import find_workspace_root


def app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def workspace_root() -> Path:
    return find_workspace_root(Path.cwd()) or app_root().parent


def managed_tools_root(root: Path | None = None) -> Path:
    actual_root = root if root is not None else workspace_root()
    return actual_root / ".tools"


def managed_bin_dir(root: Path | None = None) -> Path:
    return managed_tools_root(root) / "bin"


def local_tool_dirs(root: Path | None = None) -> tuple[Path, ...]:
    actual_root = root if root is not None else workspace_root()
    return (
        actual_root / ".tools" / "bin",
        actual_root / ".tools" / "npm" / "bin",
        actual_root / ".venv" / "bin",
        app_root() / ".venv" / "bin",
    )


def find_tool(executable: str, *, root: Path | None = None) -> Path | None:
    global_path = shutil.which(executable)
    if global_path is not None:
        return Path(global_path)

    for directory in local_tool_dirs(root):
        candidate = directory / executable
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


__all__ = [
    "app_root",
    "find_tool",
    "local_tool_dirs",
    "managed_bin_dir",
    "managed_tools_root",
    "workspace_root",
]
