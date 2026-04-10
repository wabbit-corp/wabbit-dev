from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def test_install_app_writes_global_wrappers(tmp_path: Path, monkeypatch) -> None:
    from dev.tasks.install import install_app

    bin_dir = tmp_path / "bin"
    monkeypatch.setenv("PATH", str(bin_dir))

    result = install_app(bin_dir=str(bin_dir))

    assert result.wabbit_dev_path == bin_dir / "wabbit-dev"
    assert result.dev_path == bin_dir / "dev"
    assert result.wabbit_dev_path.is_file()
    assert result.dev_path.is_symlink()
    assert result.dev_path.resolve() == result.wabbit_dev_path
    assert "dev.py" in result.wabbit_dev_path.read_text(encoding="utf-8")


def test_install_completions_writes_scripts_and_managed_rc_blocks(tmp_path: Path, monkeypatch) -> None:
    from dev.tasks.install import install_completions

    home = tmp_path / "home"
    data_home = tmp_path / "data"
    zdotdir = tmp_path / "zsh"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("ZDOTDIR", str(zdotdir))

    result = install_completions(
        shell="all",
        update_rc=True,
        dev_bash="# dev bash\n",
        wabbit_dev_bash="# wabbit-dev bash\n",
        dev_zsh="# dev zsh\n",
        wabbit_dev_zsh="# wabbit-dev zsh\n",
    )

    assert result.bash_paths == (
        data_home / "wabbit-dev" / "completions" / "bash" / "dev.bash",
        data_home / "wabbit-dev" / "completions" / "bash" / "wabbit-dev.bash",
    )
    assert result.zsh_paths == (
        data_home / "wabbit-dev" / "completions" / "zsh" / "dev.zsh",
        data_home / "wabbit-dev" / "completions" / "zsh" / "wabbit-dev.zsh",
    )
    assert result.bash_paths[0].read_text(encoding="utf-8") == "# dev bash\n"
    assert result.zsh_paths[1].read_text(encoding="utf-8") == "# wabbit-dev zsh\n"
    assert result.bashrc_path == home / ".bashrc"
    assert result.zshrc_path == zdotdir / ".zshrc"
    assert result.updated_bashrc is True
    assert result.updated_zshrc is True
    assert "# >>> wabbit-dev bash completions >>>" in result.bashrc_path.read_text(encoding="utf-8")
    assert "# >>> wabbit-dev zsh completions >>>" in result.zshrc_path.read_text(encoding="utf-8")


def test_install_completions_is_idempotent_for_managed_rc_blocks(tmp_path: Path, monkeypatch) -> None:
    from dev.tasks.install import install_completions

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("ZDOTDIR", raising=False)

    first = install_completions(
        shell="zsh",
        update_rc=True,
        dev_bash="",
        wabbit_dev_bash="",
        dev_zsh="# dev zsh\n",
        wabbit_dev_zsh="# wabbit-dev zsh\n",
    )
    second = install_completions(
        shell="zsh",
        update_rc=True,
        dev_bash="",
        wabbit_dev_bash="",
        dev_zsh="# dev zsh\n",
        wabbit_dev_zsh="# wabbit-dev zsh\n",
    )

    assert first.updated_zshrc is True
    assert second.updated_zshrc is False
    assert second.zshrc_path is not None
    assert second.zshrc_path.read_text(encoding="utf-8").count("# >>> wabbit-dev zsh completions >>>") == 1


def test_install_completions_no_rc_only_writes_scripts(tmp_path: Path, monkeypatch) -> None:
    from dev.tasks.install import install_completions

    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    result = install_completions(
        shell="bash",
        update_rc=False,
        dev_bash="# dev bash\n",
        wabbit_dev_bash="# wabbit-dev bash\n",
        dev_zsh="",
        wabbit_dev_zsh="",
    )

    assert len(result.bash_paths) == 2
    assert result.zsh_paths == ()
    assert result.bashrc_path is None
    assert not (home / ".bashrc").exists()


def test_install_tools_downloads_verified_ktfmt_into_managed_tools(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dev.tasks import install as install_task

    root = tmp_path / "workspace"
    root.mkdir()
    (root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    jar_bytes = b"fake ktfmt jar"
    digest = hashlib.sha256(jar_bytes).hexdigest()

    release = install_task.GithubRelease(
        tag="v0.62",
        assets=(
            install_task.GithubAsset(
                name="ktfmt-0.62-with-dependencies.jar",
                download_url="https://example.invalid/ktfmt.jar",
                digest=f"sha256:{digest}",
            ),
        ),
    )

    def fake_download(_url: str, path: Path) -> None:
        path.write_bytes(jar_bytes)

    monkeypatch.setattr(install_task, "workspace_root", lambda: root)
    monkeypatch.setattr(install_task, "find_tool", lambda _tool, *, root=None: None)
    monkeypatch.setattr(install_task, "_fetch_github_release", lambda _repo: release)
    monkeypatch.setattr(install_task, "_download_url", fake_download)

    result = install_task.install_tools(["ktfmt"], force=True)

    assert result.results[0].status == "installed"
    assert result.results[0].verification.startswith("sha256 release asset digest verified")
    assert (root / ".tools" / "ktfmt" / "v0.62" / "ktfmt-0.62-with-dependencies.jar").read_bytes() == jar_bytes
    wrapper = root / ".tools" / "bin" / "ktfmt"
    assert wrapper.is_file()
    assert "java -jar" in wrapper.read_text(encoding="utf-8")
    assert "/.tools/" in (root / ".gitignore").read_text(encoding="utf-8")


def test_install_tools_installs_python_tool_with_workspace_python(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dev.tasks import install as install_task

    root = tmp_path / "workspace"
    root.mkdir()
    python_bin = tmp_path / "app" / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    installed_bandit = python_bin.parent / "bandit"

    commands: list[tuple[str, ...]] = []

    def fake_run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        commands.append(tuple(command))
        installed_bandit.write_text("#!/bin/sh\n", encoding="utf-8")
        installed_bandit.chmod(0o755)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(install_task, "workspace_root", lambda: root)
    monkeypatch.setattr(install_task, "find_tool", lambda _tool, *, root=None: None)
    monkeypatch.setattr(install_task, "_repo_root", lambda: tmp_path / "app")
    monkeypatch.setattr(install_task, "_python_bin", lambda _repo_root: python_bin)
    monkeypatch.setattr(install_task, "_run_command", fake_run)
    monkeypatch.setattr(install_task, "_pypi_latest_version", lambda _package: "1.9.4")

    result = install_task.install_tools(["bandit"], force=False, json_output=True)

    assert result.results[0].status == "installed"
    assert result.results[0].executable == installed_bandit
    assert commands == [
        (
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--upgrade",
            "bandit",
        )
    ]


def test_install_tools_installs_npm_tool_into_managed_prefix(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dev.tasks import install as install_task

    root = tmp_path / "workspace"
    root.mkdir()
    npm_bin = tmp_path / "npm"
    npm_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    purs_tidy = root / ".tools" / "npm" / "bin" / "purs-tidy"

    commands: list[tuple[str, ...]] = []

    def fake_run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        commands.append(tuple(command))
        purs_tidy.parent.mkdir(parents=True)
        purs_tidy.write_text("#!/bin/sh\n", encoding="utf-8")
        purs_tidy.chmod(0o755)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(install_task, "workspace_root", lambda: root)
    monkeypatch.setattr(install_task, "find_tool", lambda _tool, *, root=None: None)
    monkeypatch.setattr(install_task.shutil, "which", lambda executable: str(npm_bin) if executable == "npm" else None)
    monkeypatch.setattr(install_task, "_run_command", fake_run)
    monkeypatch.setattr(install_task, "_npm_latest_version", lambda _package: "0.10.0")

    result = install_task.install_tools(["purs-tidy"], force=True, json_output=True)

    assert result.results[0].status == "installed"
    assert result.results[0].executable == root / ".tools" / "bin" / "purs-tidy"
    assert commands == [(str(npm_bin), "install", "--prefix", str(root / ".tools" / "npm"), "purs-tidy")]


def test_install_tools_installs_dotnet_tool_into_managed_bin(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dev.tasks import install as install_task

    root = tmp_path / "workspace"
    root.mkdir()
    dotnet_bin = tmp_path / "dotnet"
    dotnet_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    csharpier = root / ".tools" / "bin" / "csharpier"

    commands: list[tuple[str, ...]] = []

    def fake_run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        commands.append(tuple(command))
        csharpier.parent.mkdir(parents=True, exist_ok=True)
        csharpier.write_text("#!/bin/sh\n", encoding="utf-8")
        csharpier.chmod(0o755)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(install_task, "workspace_root", lambda: root)
    monkeypatch.setattr(install_task, "find_tool", lambda _tool, *, root=None: None)
    monkeypatch.setattr(install_task.shutil, "which", lambda executable: str(dotnet_bin) if executable == "dotnet" else None)
    monkeypatch.setattr(install_task, "_run_command", fake_run)

    result = install_task.install_tools(["csharpier"], force=False, json_output=True)

    assert result.results[0].status == "installed"
    assert result.results[0].executable == csharpier
    assert commands == [
        (
            str(dotnet_bin),
            "tool",
            "install",
            "csharpier",
            "--tool-path",
            str(root / ".tools" / "bin"),
        )
    ]
