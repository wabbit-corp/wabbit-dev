from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path
from typing import Literal

CONFIG_FILE = "root.clj"
AUTO_VENV_SKIP_ENV = "WABBIT_DEV_SKIP_AUTO_VENV"
LaunchMode = Literal["script", "module"]


def find_workspace_root(start: Path | None = None) -> Path | None:
    current = Path.cwd() if start is None else start
    if current.is_file():
        current = current.parent
    current = current.resolve()

    for candidate in (current, *current.parents):
        if (candidate / CONFIG_FILE).is_file():
            return candidate
    return None


def workspace_venv_python(workspace_root: Path) -> Path:
    if os.name == "nt":
        return workspace_root / ".venv" / "Scripts" / "python.exe"
    return workspace_root / ".venv" / "bin" / "python"


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except FileNotFoundError:
        return False


def _tool_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def tool_dev_script() -> Path:
    return _tool_repo_root() / "dev.py"


def _relative_command_path(path: Path, workspace_root: Path) -> str:
    try:
        relative = path.relative_to(workspace_root)
    except ValueError:
        return str(path)
    return f"./{relative.as_posix()}"


def build_workspace_venv_reexec_argv(
    *,
    argv: list[str] | None = None,
    launch_mode: LaunchMode = "script",
    cwd: Path | None = None,
    current_executable: Path | None = None,
) -> list[str] | None:
    if os.environ.get(AUTO_VENV_SKIP_ENV):
        return None

    workspace_root = find_workspace_root(cwd)
    if workspace_root is None:
        return None

    venv_python = workspace_venv_python(workspace_root)
    if not venv_python.is_file():
        return None

    active_executable = (Path(sys.executable) if current_executable is None else current_executable).resolve()
    if _same_file(venv_python, active_executable):
        return None

    active_argv = list(sys.argv) if argv is None else list(argv)
    if launch_mode == "module":
        return [str(venv_python), "-m", "dev", *active_argv[1:]]

    return [str(venv_python), str(tool_dev_script()), *active_argv[1:]]


def maybe_reexec_to_workspace_venv(
    *,
    argv: list[str] | None = None,
    launch_mode: LaunchMode = "script",
) -> bool:
    reexec_argv = build_workspace_venv_reexec_argv(argv=argv, launch_mode=launch_mode)
    if reexec_argv is None:
        return False

    env = os.environ.copy()
    env[AUTO_VENV_SKIP_ENV] = "1"
    os.execve(reexec_argv[0], reexec_argv, env)
    raise AssertionError("os.execve returned unexpectedly")


def canonical_rerun_command(
    args: list[str],
    *,
    cwd: Path | None = None,
) -> str | None:
    workspace_root = find_workspace_root(cwd)
    if workspace_root is None:
        return None

    workspace_dev = workspace_root / "dev"
    if workspace_dev.is_file():
        command_parts = ["./dev", *args]
    else:
        venv_python = workspace_venv_python(workspace_root)
        if not venv_python.is_file():
            return None
        command_parts = [
            _relative_command_path(venv_python, workspace_root),
            _relative_command_path(tool_dev_script(), workspace_root),
            *args,
        ]

    return f"cd {shlex.quote(str(workspace_root))} && {shlex.join(command_parts)}"
