from __future__ import annotations

from pathlib import Path


def test_build_workspace_venv_reexec_argv_for_script_mode(tmp_path: Path) -> None:
    from dev import bootstrap

    workspace_root = tmp_path / "workspace"
    nested = workspace_root / "apps" / "demo"
    venv_python = workspace_root / ".venv" / "bin" / "python"
    nested.mkdir(parents=True, exist_ok=True)
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("", encoding="utf-8")
    (workspace_root / "root.clj").write_text("()", encoding="utf-8")

    result = bootstrap.build_workspace_venv_reexec_argv(
        argv=["dev.py", "build", "demo"],
        launch_mode="script",
        cwd=nested,
        current_executable=workspace_root / "python3",
    )

    assert result == [str(venv_python), str(bootstrap.tool_dev_script()), "build", "demo"]


def test_build_workspace_venv_reexec_argv_for_module_mode(tmp_path: Path) -> None:
    from dev import bootstrap

    workspace_root = tmp_path / "workspace"
    nested = workspace_root / "apps" / "demo"
    venv_python = workspace_root / ".venv" / "bin" / "python"
    nested.mkdir(parents=True, exist_ok=True)
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("", encoding="utf-8")
    (workspace_root / "root.clj").write_text("()", encoding="utf-8")

    result = bootstrap.build_workspace_venv_reexec_argv(
        argv=["/tmp/dev/__main__.py", "build", "demo"],
        launch_mode="module",
        cwd=nested,
        current_executable=workspace_root / "python3",
    )

    assert result == [str(venv_python), "-m", "dev", "build", "demo"]


def test_canonical_rerun_command_uses_global_dev_name(tmp_path: Path) -> None:
    from dev.bootstrap import canonical_rerun_command

    workspace_root = tmp_path / "workspace"
    nested = workspace_root / "apps" / "demo"
    nested.mkdir(parents=True, exist_ok=True)
    (workspace_root / "root.clj").write_text("()", encoding="utf-8")

    command = canonical_rerun_command(["build", "demo"], cwd=nested)

    assert command is not None
    assert "&& dev build demo" in command
