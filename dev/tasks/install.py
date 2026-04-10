from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dev.json_types import JSONObject
from dev.messages import command_text, info, success, warning
from dev.tool_paths import find_tool, managed_bin_dir, managed_tools_root, workspace_root


@dataclass(frozen=True)
class AppInstallResult:
    install_dir: Path
    wabbit_dev_path: Path
    dev_path: Path
    python_bin: Path
    dev_py: Path
    install_dir_on_path: bool


@dataclass(frozen=True)
class CompletionInstallResult:
    bash_paths: tuple[Path, ...]
    zsh_paths: tuple[Path, ...]
    bashrc_path: Path | None
    zshrc_path: Path | None
    updated_bashrc: bool
    updated_zshrc: bool


@dataclass(frozen=True)
class ToolInstallResult:
    name: str
    status: str
    executable: Path | None
    install_path: Path | None
    version: str | None
    verification: str
    details: str

    def to_payload(self) -> JSONObject:
        payload: JSONObject = {
            "name": self.name,
            "status": self.status,
            "verification": self.verification,
            "details": self.details,
        }
        if self.executable is not None:
            payload["executable"] = str(self.executable)
        if self.install_path is not None:
            payload["installPath"] = str(self.install_path)
        if self.version is not None:
            payload["version"] = self.version
        return payload


@dataclass(frozen=True)
class ToolsInstallResult:
    root: Path
    bin_dir: Path
    results: tuple[ToolInstallResult, ...]

    def to_payload(self) -> JSONObject:
        return {
            "toolsRoot": str(self.root),
            "binDir": str(self.bin_dir),
            "results": [result.to_payload() for result in self.results],
        }


@dataclass(frozen=True)
class GithubAsset:
    name: str
    download_url: str
    digest: str | None


@dataclass(frozen=True)
class GithubRelease:
    tag: str
    assets: tuple[GithubAsset, ...]


@dataclass(frozen=True)
class PythonToolSpec:
    package: str
    executable: str


_PYTHON_TOOLS = {
    "ruff": PythonToolSpec(package="ruff", executable="ruff"),
    "black": PythonToolSpec(package="black", executable="black"),
    "mypy": PythonToolSpec(package="mypy", executable="mypy"),
    "pyright": PythonToolSpec(package="pyright", executable="pyright"),
    "basedpyright": PythonToolSpec(package="basedpyright", executable="basedpyright"),
    "pytest": PythonToolSpec(package="pytest", executable="pytest"),
    "coverage": PythonToolSpec(package="coverage", executable="coverage"),
    "diff-cover": PythonToolSpec(package="diff-cover", executable="diff-cover"),
    "deptry": PythonToolSpec(package="deptry", executable="deptry"),
    "import-linter": PythonToolSpec(package="import-linter", executable="lint-imports"),
    "vulture": PythonToolSpec(package="vulture", executable="vulture"),
    "semgrep": PythonToolSpec(package="semgrep", executable="semgrep"),
    "bandit": PythonToolSpec(package="bandit", executable="bandit"),
    "pip-audit": PythonToolSpec(package="pip-audit", executable="pip-audit"),
    "clang-format": PythonToolSpec(package="clang-format", executable="clang-format"),
}

_GITHUB_TOOLS = {
    "gitleaks",
    "trufflehog",
    "shellcheck",
    "osv-scanner",
    "ktfmt",
}

_NPM_TOOLS = {
    "purs-tidy": "purs-tidy",
}

_DOTNET_TOOLS = {
    "csharpier": "csharpier",
}

_INSTALLABLE_TOOLS = (
    "gitleaks",
    "trufflehog",
    "shellcheck",
    "osv-scanner",
    "ktfmt",
    "ruff",
    "black",
    "mypy",
    "pyright",
    "basedpyright",
    "pytest",
    "coverage",
    "diff-cover",
    "deptry",
    "import-linter",
    "vulture",
    "semgrep",
    "bandit",
    "pip-audit",
    "clang-format",
    "purs-tidy",
    "csharpier",
)


def install_tool_names() -> tuple[str, ...]:
    return _INSTALLABLE_TOOLS


def install_tools(
    tools: Sequence[str] | None = None,
    *,
    force: bool = False,
    json_output: bool = False,
) -> ToolsInstallResult:
    root = workspace_root()
    tools_root = managed_tools_root(root)
    bin_dir = managed_bin_dir(root)
    tools_root.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    _ensure_tools_gitignored(root, tools_root)

    selected_tools = _normalize_tools(tools)
    results: list[ToolInstallResult] = []
    for tool in selected_tools:
        try:
            results.append(_install_one_tool(tool, root=root, force=force))
        except Exception as ex:
            results.append(
                ToolInstallResult(
                    name=tool,
                    status="failed",
                    executable=None,
                    install_path=None,
                    version=None,
                    verification="failed",
                    details=f"{type(ex).__name__}: {ex}",
                )
            )

    result = ToolsInstallResult(root=tools_root, bin_dir=bin_dir, results=tuple(results))
    if json_output:
        print(json.dumps(result.to_payload(), indent=2))
    else:
        _print_tools_install_result(result)
    return result


def _normalize_tools(tools: Sequence[str] | None) -> tuple[str, ...]:
    if not tools:
        return _INSTALLABLE_TOOLS

    selected: list[str] = []
    seen: set[str] = set()
    for tool in tools:
        if tool not in _INSTALLABLE_TOOLS:
            expected = ", ".join(_INSTALLABLE_TOOLS)
            raise ValueError(f"Unknown installable tool: {tool}. Expected one of: {expected}.")
        if tool in seen:
            continue
        selected.append(tool)
        seen.add(tool)
    return tuple(selected)


def _install_one_tool(tool: str, *, root: Path, force: bool) -> ToolInstallResult:
    if tool in _PYTHON_TOOLS:
        return _install_python_tool(tool, spec=_PYTHON_TOOLS[tool], root=root, force=force)
    if tool in _GITHUB_TOOLS:
        return _install_github_tool(tool, root=root, force=force)
    if tool in _NPM_TOOLS:
        return _install_npm_tool(tool, package=_NPM_TOOLS[tool], root=root, force=force)
    if tool in _DOTNET_TOOLS:
        return _install_dotnet_tool(tool, package=_DOTNET_TOOLS[tool], root=root, force=force)
    raise ValueError(f"Unknown installable tool: {tool}")


def _install_python_tool(tool: str, *, spec: PythonToolSpec, root: Path, force: bool) -> ToolInstallResult:
    existing = find_tool(spec.executable, root=root)
    if existing is not None and not force:
        return ToolInstallResult(
            name=tool,
            status="present",
            executable=existing,
            install_path=None,
            version=None,
            verification="existing executable",
            details="already available on PATH or in a local tool directory",
        )

    python_bin = _tools_python_bin(root)
    command = [
        str(python_bin),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--upgrade",
        spec.package,
    ]
    completed = _run_command(command, cwd=root)
    if completed.returncode != 0:
        return ToolInstallResult(
            name=tool,
            status="failed",
            executable=None,
            install_path=None,
            version=None,
            verification="failed",
            details=_command_output(completed),
        )

    executable = python_bin.parent / spec.executable
    if not executable.is_file():
        executable = find_tool(spec.executable, root=root) or executable

    return ToolInstallResult(
        name=tool,
        status="installed",
        executable=executable if executable.is_file() else None,
        install_path=python_bin.parent,
        version=_pypi_latest_version(spec.package),
        verification="PyPI package installed through pip; upstream package signatures are not published",
        details="pip verifies HTTPS transport; transitive dependency hashes are delegated to pip",
    )


def _tools_python_bin(root: Path) -> Path:
    workspace_venv = root / ".venv" / "bin" / "python"
    if workspace_venv.is_file():
        return workspace_venv
    return _python_bin(_repo_root())


def _install_npm_tool(tool: str, *, package: str, root: Path, force: bool) -> ToolInstallResult:
    existing = find_tool(tool, root=root)
    if existing is not None and not force:
        return ToolInstallResult(
            name=tool,
            status="present",
            executable=existing,
            install_path=None,
            version=None,
            verification="existing executable",
            details="already available on PATH or in a local tool directory",
        )

    npm = shutil.which("npm")
    if npm is None:
        return ToolInstallResult(
            name=tool,
            status="failed",
            executable=None,
            install_path=None,
            version=None,
            verification="failed",
            details="npm is required to install this tool",
        )

    prefix = managed_tools_root(root) / "npm"
    prefix.mkdir(parents=True, exist_ok=True)
    completed = _run_command([npm, "install", "--prefix", str(prefix), package], cwd=root)
    if completed.returncode != 0:
        return ToolInstallResult(
            name=tool,
            status="failed",
            executable=None,
            install_path=prefix,
            version=None,
            verification="failed",
            details=_command_output(completed),
        )

    executable = prefix / "bin" / tool
    if not executable.is_file():
        return ToolInstallResult(
            name=tool,
            status="failed",
            executable=None,
            install_path=prefix,
            version=None,
            verification="failed",
            details=f"npm install completed but {executable} was not created",
        )

    link = _link_managed_executable(tool, executable, root=root)
    return ToolInstallResult(
        name=tool,
        status="installed",
        executable=link,
        install_path=prefix,
        version=_npm_latest_version(package),
        verification="npm package installed through npm; upstream package signatures are not consistently published",
        details="npm verifies HTTPS transport and registry integrity metadata",
    )


def _install_dotnet_tool(tool: str, *, package: str, root: Path, force: bool) -> ToolInstallResult:
    existing = find_tool(tool, root=root)
    if existing is not None and not force:
        return ToolInstallResult(
            name=tool,
            status="present",
            executable=existing,
            install_path=None,
            version=None,
            verification="existing executable",
            details="already available on PATH or in a local tool directory",
        )

    dotnet = shutil.which("dotnet")
    if dotnet is None:
        return ToolInstallResult(
            name=tool,
            status="failed",
            executable=None,
            install_path=None,
            version=None,
            verification="failed",
            details="dotnet is required to install this tool",
        )

    bin_dir = managed_bin_dir(root)
    bin_dir.mkdir(parents=True, exist_ok=True)
    action = "update" if force else "install"
    completed = _run_command([dotnet, "tool", action, package, "--tool-path", str(bin_dir)], cwd=root)
    if completed.returncode != 0 and not force:
        completed = _run_command([dotnet, "tool", "update", package, "--tool-path", str(bin_dir)], cwd=root)
    if completed.returncode != 0:
        return ToolInstallResult(
            name=tool,
            status="failed",
            executable=None,
            install_path=bin_dir,
            version=None,
            verification="failed",
            details=_command_output(completed),
        )

    executable = _find_dotnet_tool_executable(bin_dir, tool)
    return ToolInstallResult(
        name=tool,
        status="installed",
        executable=executable,
        install_path=bin_dir,
        version=None,
        verification="dotnet tool installed through NuGet; package verification is delegated to dotnet/NuGet",
        details="system dotnet installation is required",
    )


def _install_github_tool(tool: str, *, root: Path, force: bool) -> ToolInstallResult:
    existing = find_tool(tool, root=root)
    if existing is not None and not force:
        return ToolInstallResult(
            name=tool,
            status="present",
            executable=existing,
            install_path=None,
            version=None,
            verification="existing executable",
            details="already available on PATH or in a local tool directory",
        )

    release = _fetch_github_release(_github_repo(tool))
    asset = _select_github_asset(tool, release)
    tools_root = managed_tools_root(root)
    install_dir = tools_root / tool / release.tag
    if install_dir.exists():
        shutil.rmtree(install_dir)
    install_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"{tool}-", dir=tools_root) as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        download_path = temp_dir / asset.name
        _download_url(asset.download_url, download_path)
        digest = _verify_github_asset(asset, download_path)
        executable = _materialize_github_asset(tool, asset, download_path, install_dir, root=root)

    return ToolInstallResult(
        name=tool,
        status="installed",
        executable=executable,
        install_path=install_dir,
        version=release.tag,
        verification=f"sha256 release asset digest verified: {digest[:12]}...",
        details=_github_verification_details(tool, release),
    )


def _ensure_tools_gitignored(root: Path, tools_root: Path) -> None:
    tools_root.mkdir(parents=True, exist_ok=True)
    marker = tools_root / ".gitignore"
    if not marker.is_file():
        marker.write_text("*\n!.gitignore\n", encoding="utf-8")

    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return

    text = gitignore.read_text(encoding="utf-8")
    if "/.tools/" in text or ".tools/" in text:
        return
    managed_block = "\n# Local tools installed by dev install tools\n/.tools/\n"
    separator = "" if text.endswith("\n") else "\n"
    gitignore.write_text(f"{text}{separator}{managed_block}", encoding="utf-8")


def _github_repo(tool: str) -> str:
    match tool:
        case "gitleaks":
            return "gitleaks/gitleaks"
        case "trufflehog":
            return "trufflesecurity/trufflehog"
        case "shellcheck":
            return "koalaman/shellcheck"
        case "osv-scanner":
            return "google/osv-scanner"
        case "ktfmt":
            return "facebook/ktfmt"
        case _:
            raise ValueError(f"Unsupported GitHub-backed tool: {tool}")


def _fetch_github_release(repo: str) -> GithubRelease:
    data = _read_json_url(f"https://api.github.com/repos/{repo}/releases/latest")
    match data:
        case {"tag_name": str() as tag, "assets": list() as assets_raw}:
            assets: list[GithubAsset] = []
            for item in assets_raw:
                match item:
                    case {
                        "name": str() as name,
                        "browser_download_url": str() as download_url,
                    }:
                        digest = item.get("digest")
                        match digest:
                            case str() as digest_text:
                                assets.append(GithubAsset(name=name, download_url=download_url, digest=digest_text))
                            case _:
                                assets.append(GithubAsset(name=name, download_url=download_url, digest=None))
                    case _:
                        pass
            return GithubRelease(tag=tag, assets=tuple(assets))
        case _:
            raise ValueError(f"Unexpected GitHub release response for {repo}")


def _pypi_latest_version(package: str) -> str | None:
    try:
        data = _read_json_url(f"https://pypi.org/pypi/{package}/json")
    except Exception:
        return None
    match data:
        case {"info": {"version": str() as version}}:
            return version
        case _:
            return None


def _npm_latest_version(package: str) -> str | None:
    try:
        data = _read_json_url(f"https://registry.npmjs.org/{package}/latest")
    except Exception:
        return None
    match data:
        case {"version": str() as version}:
            return version
        case _:
            return None


def _read_json_url(url: str) -> JSONObject:
    request = urllib.request.Request(url, headers={"User-Agent": "wabbit-dev"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    match data:
        case dict() as payload:
            return payload
        case _:
            raise ValueError(f"Expected JSON mapping from {url}")


def _select_github_asset(tool: str, release: GithubRelease) -> GithubAsset:
    version = release.tag.removeprefix("v")
    platform_info = _platform_info()
    match tool:
        case "gitleaks":
            name = f"gitleaks_{version}_{platform_info.gitleaks_os}_{platform_info.gitleaks_arch}.tar.gz"
        case "trufflehog":
            name = f"trufflehog_{version}_{platform_info.trufflehog_os}_{platform_info.trufflehog_arch}.tar.gz"
        case "shellcheck":
            name = f"shellcheck-{release.tag}.{platform_info.shellcheck_os}.{platform_info.shellcheck_arch}.tar.gz"
        case "osv-scanner":
            name = f"osv-scanner_{platform_info.osv_os}_{platform_info.osv_arch}"
        case "ktfmt":
            name = f"ktfmt-{version}-with-dependencies.jar"
        case _:
            raise ValueError(f"Unsupported GitHub-backed tool: {tool}")
    return _release_asset(release, name)


@dataclass(frozen=True)
class _PlatformInfo:
    gitleaks_os: str
    gitleaks_arch: str
    trufflehog_os: str
    trufflehog_arch: str
    shellcheck_os: str
    shellcheck_arch: str
    osv_os: str
    osv_arch: str


def _platform_info() -> _PlatformInfo:
    system = sys.platform.lower()
    machine = platform.machine().lower()

    match system:
        case "darwin":
            os_token = "darwin"
        case value if value.startswith("linux"):
            os_token = "linux"
        case _:
            raise ValueError(f"Unsupported tool install platform: {sys.platform}")

    match machine:
        case "arm64" | "aarch64":
            return _PlatformInfo(
                gitleaks_os=os_token,
                gitleaks_arch="arm64",
                trufflehog_os=os_token,
                trufflehog_arch="arm64",
                shellcheck_os=os_token,
                shellcheck_arch="aarch64",
                osv_os=os_token,
                osv_arch="arm64",
            )
        case "x86_64" | "amd64":
            return _PlatformInfo(
                gitleaks_os=os_token,
                gitleaks_arch="x64",
                trufflehog_os=os_token,
                trufflehog_arch="amd64",
                shellcheck_os=os_token,
                shellcheck_arch="x86_64",
                osv_os=os_token,
                osv_arch="amd64",
            )
        case _:
            raise ValueError(f"Unsupported tool install architecture: {platform.machine()}")


def _release_asset(release: GithubRelease, name: str) -> GithubAsset:
    for asset in release.assets:
        if asset.name == name:
            return asset
    available = ", ".join(asset.name for asset in release.assets)
    raise ValueError(f"Release {release.tag} does not contain asset {name}. Available assets: {available}")


def _download_url(url: str, path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "wabbit-dev"})
    with urllib.request.urlopen(request, timeout=120) as response:
        with path.open("wb") as file:
            shutil.copyfileobj(response, file)


def _verify_github_asset(asset: GithubAsset, path: Path) -> str:
    if asset.digest is None:
        raise ValueError(f"GitHub did not provide a digest for {asset.name}")
    expected = _normalize_sha256_digest(asset.digest)
    actual = _sha256_file(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {asset.name}: expected {expected}, got {actual}")
    return actual


def _normalize_sha256_digest(digest: str) -> str:
    return digest.removeprefix("sha256:").strip().lower()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _materialize_github_asset(
    tool: str,
    asset: GithubAsset,
    download_path: Path,
    install_dir: Path,
    *,
    root: Path,
) -> Path:
    if asset.name.endswith(".jar"):
        jar_path = install_dir / asset.name
        shutil.copy2(download_path, jar_path)
        return _write_ktfmt_wrapper(jar_path, root=root)

    if ".tar." in asset.name or asset.name.endswith(".tgz"):
        _extract_tar(download_path, install_dir)
        executable = _find_executable_file(install_dir, tool)
        return _link_managed_executable(tool, executable, root=root)

    if asset.name.endswith(".zip"):
        _extract_zip(download_path, install_dir)
        executable = _find_executable_file(install_dir, tool)
        return _link_managed_executable(tool, executable, root=root)

    executable = install_dir / tool
    shutil.copy2(download_path, executable)
    executable.chmod(0o755)
    return _link_managed_executable(tool, executable, root=root)


def _extract_tar(path: Path, destination: Path) -> None:
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            _ensure_safe_archive_member(destination, member.name)
        archive.extractall(destination)


def _extract_zip(path: Path, destination: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            _ensure_safe_archive_member(destination, name)
        archive.extractall(destination)


def _ensure_safe_archive_member(destination: Path, name: str) -> None:
    target = (destination / name).resolve()
    destination_root = destination.resolve()
    if target == destination_root:
        return
    if destination_root not in target.parents:
        raise ValueError(f"Archive member escapes install directory: {name}")


def _find_executable_file(root: Path, name: str) -> Path:
    executable_name = f"{name}.exe" if sys.platform.lower() == "win32" else name
    for path in root.rglob(executable_name):
        if path.is_file():
            path.chmod(path.stat().st_mode | 0o755)
            return path
    raise ValueError(f"Could not find executable {executable_name} under {root}")


def _find_dotnet_tool_executable(bin_dir: Path, name: str) -> Path:
    candidates = (bin_dir / name, bin_dir / f"dotnet-{name}")
    for candidate in candidates:
        if candidate.is_file():
            candidate.chmod(candidate.stat().st_mode | 0o755)
            return candidate
    available = ", ".join(path.name for path in bin_dir.iterdir() if path.is_file())
    raise ValueError(f"Could not find dotnet tool executable for {name} under {bin_dir}. Files: {available}")


def _link_managed_executable(name: str, executable: Path, *, root: Path) -> Path:
    bin_dir = managed_bin_dir(root)
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / name
    _replace_symlink(link, executable)
    return link


def _write_ktfmt_wrapper(jar_path: Path, *, root: Path) -> Path:
    bin_dir = managed_bin_dir(root)
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / "ktfmt"
    _write_executable(
        wrapper,
        "#!/bin/sh\n"
        f"exec java -jar {shlex.quote(str(jar_path))} \"$@\"\n",
    )
    return wrapper


def _github_verification_details(tool: str, release: GithubRelease) -> str:
    if tool == "trufflehog" and _has_trufflehog_signature_assets(release):
        return "downloaded asset digest verified; release also publishes cosign checksum signature metadata"
    return "downloaded asset digest verified against GitHub release metadata"


def _has_trufflehog_signature_assets(release: GithubRelease) -> bool:
    names = {asset.name for asset in release.assets}
    version = release.tag.removeprefix("v")
    return {
        f"trufflehog_{version}_checksums.txt",
        f"trufflehog_{version}_checksums.txt.pem",
        f"trufflehog_{version}_checksums.txt.sig",
    }.issubset(names)


def _run_command(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def _command_output(completed: subprocess.CompletedProcess[str]) -> str:
    parts = [part.strip() for part in (completed.stdout, completed.stderr) if part.strip()]
    if parts:
        return "\n".join(parts)
    return f"exited with status {completed.returncode}"


def install_app(*, bin_dir: str | None = None) -> AppInstallResult:
    if sys.platform.lower() == "win32":
        raise ValueError("Global dev wrapper installation is currently supported on POSIX shells only.")

    repo_root = _repo_root()
    python_bin = _python_bin(repo_root)
    dev_py = repo_root / "dev.py"
    if not dev_py.is_file():
        raise ValueError(f"Expected dev.py at {dev_py}")

    install_dir = _pick_install_dir(bin_dir)
    install_dir.mkdir(parents=True, exist_ok=True)

    wabbit_dev_path = install_dir / "wabbit-dev"
    dev_path = install_dir / "dev"
    _write_executable(
        wabbit_dev_path,
        "#!/bin/sh\n"
        f"exec {shlex.quote(str(python_bin))} {shlex.quote(str(dev_py))} \"$@\"\n",
    )
    _replace_symlink(dev_path, wabbit_dev_path)

    result = AppInstallResult(
        install_dir=install_dir,
        wabbit_dev_path=wabbit_dev_path,
        dev_path=dev_path,
        python_bin=python_bin,
        dev_py=dev_py,
        install_dir_on_path=_path_contains(install_dir),
    )
    _print_app_install_result(result)
    return result


def install_completions(
    *,
    shell: str,
    update_rc: bool,
    dev_bash: str,
    wabbit_dev_bash: str,
    dev_zsh: str,
    wabbit_dev_zsh: str,
) -> CompletionInstallResult:
    selected_shells = _selected_shells(shell)
    data_home = _data_home()

    bash_paths: list[Path] = []
    zsh_paths: list[Path] = []
    bashrc_path: Path | None = None
    zshrc_path: Path | None = None
    updated_bashrc = False
    updated_zshrc = False

    if "bash" in selected_shells:
        bash_dir = data_home / "wabbit-dev" / "completions" / "bash"
        bash_dir.mkdir(parents=True, exist_ok=True)
        dev_path = bash_dir / "dev.bash"
        wabbit_dev_path = bash_dir / "wabbit-dev.bash"
        dev_path.write_text(dev_bash, encoding="utf-8")
        wabbit_dev_path.write_text(wabbit_dev_bash, encoding="utf-8")
        bash_paths.extend([dev_path, wabbit_dev_path])
        if update_rc:
            bashrc_path = _home() / ".bashrc"
            updated_bashrc = _update_managed_block(
                bashrc_path,
                "wabbit-dev bash completions",
                _bash_completion_rc_block(dev_path, wabbit_dev_path),
            )

    if "zsh" in selected_shells:
        zsh_dir = data_home / "wabbit-dev" / "completions" / "zsh"
        zsh_dir.mkdir(parents=True, exist_ok=True)
        dev_path = zsh_dir / "dev.zsh"
        wabbit_dev_path = zsh_dir / "wabbit-dev.zsh"
        dev_path.write_text(dev_zsh, encoding="utf-8")
        wabbit_dev_path.write_text(wabbit_dev_zsh, encoding="utf-8")
        zsh_paths.extend([dev_path, wabbit_dev_path])
        if update_rc:
            zshrc_path = _zdotdir() / ".zshrc"
            updated_zshrc = _update_managed_block(
                zshrc_path,
                "wabbit-dev zsh completions",
                _zsh_completion_rc_block(dev_path, wabbit_dev_path),
            )

    result = CompletionInstallResult(
        bash_paths=tuple(bash_paths),
        zsh_paths=tuple(zsh_paths),
        bashrc_path=bashrc_path,
        zshrc_path=zshrc_path,
        updated_bashrc=updated_bashrc,
        updated_zshrc=updated_zshrc,
    )
    _print_completion_install_result(result, update_rc=update_rc)
    return result


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _home() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser()


def _zdotdir() -> Path:
    return Path(os.environ.get("ZDOTDIR", str(_home()))).expanduser()


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(_home() / ".local" / "share"))).expanduser()


def _python_bin(repo_root: Path) -> Path:
    local_venv = repo_root / ".venv" / "bin" / "python"
    if local_venv.is_file():
        return local_venv
    workspace_venv = repo_root.parent / ".venv" / "bin" / "python"
    if workspace_venv.is_file():
        return workspace_venv
    return Path(sys.executable)


def _pick_install_dir(explicit_bin_dir: str | None) -> Path:
    if explicit_bin_dir is not None:
        return Path(explicit_bin_dir).expanduser()

    env_bin_dir = os.environ.get("BIN_DIR")
    if env_bin_dir:
        return Path(env_bin_dir).expanduser()

    home_local = _home() / ".local" / "bin"
    for candidate in [Path("/opt/homebrew/bin"), Path("/usr/local/bin"), home_local]:
        if _is_writable_dir_on_path(candidate):
            return candidate

    for candidate_text in os.environ.get("PATH", "").split(os.pathsep):
        if not candidate_text:
            continue
        candidate = Path(candidate_text).expanduser()
        if _is_writable_dir(candidate):
            return candidate

    return home_local


def _is_writable_dir_on_path(path: Path) -> bool:
    return _path_contains(path) and _is_writable_dir(path)


def _is_writable_dir(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


def _path_contains(path: Path) -> bool:
    normalized = str(path.expanduser())
    return normalized in {str(Path(entry).expanduser()) for entry in os.environ.get("PATH", "").split(os.pathsep) if entry}


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _replace_symlink(link_path: Path, target_path: Path) -> None:
    if link_path.exists() or link_path.is_symlink():
        if link_path.is_dir() and not link_path.is_symlink():
            raise ValueError(f"Cannot replace directory with dev symlink: {link_path}")
        link_path.unlink()
    link_path.symlink_to(target_path)


def _selected_shells(shell: str) -> tuple[str, ...]:
    match shell:
        case "all":
            return ("bash", "zsh")
        case "bash" | "zsh":
            return (shell,)
        case _:
            raise ValueError(f"Unsupported shell for completions: {shell}")


def _update_managed_block(path: Path, label: str, body: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    begin = f"# >>> {label} >>>"
    end = f"# <<< {label} <<<"
    block = f"{begin}\n{body.rstrip()}\n{end}\n"
    old_text = path.read_text(encoding="utf-8") if path.is_file() else ""

    start = old_text.find(begin)
    stop = old_text.find(end)
    if start >= 0 and stop >= start:
        stop += len(end)
        new_text = old_text[:start] + block.rstrip() + old_text[stop:]
        if not new_text.endswith("\n"):
            new_text += "\n"
    else:
        separator = "\n" if old_text and not old_text.endswith("\n") else ""
        padding = "\n" if old_text else ""
        new_text = f"{old_text}{separator}{padding}{block}"

    if new_text == old_text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def _bash_completion_rc_block(dev_path: Path, wabbit_dev_path: Path) -> str:
    return (
        f"if [ -r {shlex.quote(str(dev_path))} ]; then\n"
        f"  . {shlex.quote(str(dev_path))}\n"
        "fi\n"
        f"if [ -r {shlex.quote(str(wabbit_dev_path))} ]; then\n"
        f"  . {shlex.quote(str(wabbit_dev_path))}\n"
        "fi"
    )


def _zsh_completion_rc_block(dev_path: Path, wabbit_dev_path: Path) -> str:
    return (
        "autoload -Uz compinit\n"
        "if ! whence -w compdef >/dev/null 2>&1; then\n"
        "  compinit\n"
        "fi\n"
        f"if [ -r {shlex.quote(str(dev_path))} ]; then\n"
        f"  source {shlex.quote(str(dev_path))}\n"
        "fi\n"
        f"if [ -r {shlex.quote(str(wabbit_dev_path))} ]; then\n"
        f"  source {shlex.quote(str(wabbit_dev_path))}\n"
        "fi"
    )


def _print_app_install_result(result: AppInstallResult) -> None:
    success("Installed dev wrappers.")
    print(f"  {result.wabbit_dev_path}")
    print(f"  {result.dev_path} -> {result.wabbit_dev_path}")
    if not result.install_dir_on_path:
        warning(f"{result.install_dir} is not currently on PATH.")
        print(f"  Add it to PATH before using {command_text('dev')} or {command_text('wabbit-dev')}.")
    print()
    info("Smoke test commands:")
    print(f"  {command_text('dev where')}")
    print(f"  {command_text('wabbit-dev where')}")


def _print_completion_install_result(result: CompletionInstallResult, *, update_rc: bool) -> None:
    success("Installed completion scripts.")
    for path in [*result.bash_paths, *result.zsh_paths]:
        print(f"  {path}")

    if result.bashrc_path is not None:
        verb = "Updated" if result.updated_bashrc else "Already configured"
        info(f"{verb}: {result.bashrc_path}")
    if result.zshrc_path is not None:
        verb = "Updated" if result.updated_zshrc else "Already configured"
        info(f"{verb}: {result.zshrc_path}")

    if not update_rc:
        warning("Shell rc files were not updated.")
        for path in result.bash_paths:
            print(f"  source {shlex.quote(str(path))}")
        for path in result.zsh_paths:
            print(f"  source {shlex.quote(str(path))}")


def _print_tools_install_result(result: ToolsInstallResult) -> None:
    success("Tool installation complete.")
    print(f"  tools: {result.root}")
    print(f"  bin:   {result.bin_dir}")
    print()
    for tool_result in result.results:
        print(f"  {tool_result.name}: {tool_result.status}")
        if tool_result.executable is not None:
            print(f"    executable: {tool_result.executable}")
        if tool_result.version is not None:
            print(f"    version: {tool_result.version}")
        print(f"    verification: {tool_result.verification}")
        if tool_result.details:
            print(f"    details: {tool_result.details}")

    if result.bin_dir not in _path_entries():
        print()
        warning(f"{result.bin_dir} is not currently on PATH.")
        print("  dev commands will still search it automatically; shell commands need PATH updated.")
        print(f"  export PATH={shlex.quote(str(result.bin_dir))}:$PATH")


def _path_entries() -> set[Path]:
    return {Path(entry).expanduser() for entry in os.environ.get("PATH", "").split(os.pathsep) if entry}


__all__ = [
    "AppInstallResult",
    "CompletionInstallResult",
    "ToolInstallResult",
    "ToolsInstallResult",
    "install_app",
    "install_completions",
    "install_tool_names",
    "install_tools",
]
