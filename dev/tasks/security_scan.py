from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from dev.config import Config, find_workspace_root, load_config
from dev.ignore_files import IgnoreMatcher
from dev.json_types import JSONObject
from dev.messages import accent, command_text, error, heading, muted, style, success
from dev.repo_resolution import configured_repo_targets, inferred_repo_targets, resolve_repo_targets
from dev.tasks.build import gradle_command
from dev.tool_paths import find_tool

type SecurityToolName = str
type SecurityStatus = str

SECURITY_TOOLS: tuple[SecurityToolName, ...] = (
    "gitleaks",
    "trufflehog",
    "semgrep",
    "bandit",
    "shellcheck",
    "osv-scanner",
    "pip-audit",
    "gradle-dependency-check",
)

_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".py",
    ".rs",
    ".scala",
    ".sh",
    ".ts",
    ".tsx",
}
_PYTHON_SUFFIXES = {".py"}
_SHELL_SUFFIXES = {".bash", ".bats", ".ksh", ".sh", ".zsh"}
_DEPENDENCY_MANIFEST_NAMES = {
    "Cargo.lock",
    "Cargo.toml",
    "Gemfile.lock",
    "go.mod",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "yarn.lock",
}
_DEPENDENCY_MANIFEST_PREFIXES = ("requirements-", "requirements.")
_DEPENDENCY_MANIFEST_SUFFIXES = (".gradle", ".gradle.kts")
_GRADLE_SECURITY_MARKERS = (
    "dependencyCheckAnalyze",
    "dependencyCheckAggregate",
    "org.owasp.dependencycheck",
)
_DEFAULT_EXCLUDED_DIR_NAMES = {
    ".git",
    ".gradle",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site",
    "tmp",
    "venv",
}


@dataclass(frozen=True)
class SecurityScanTarget:
    name: str
    path: Path


@dataclass(frozen=True)
class ExternalCommandResult:
    return_code: int
    output: str


@dataclass(frozen=True)
class SecurityRunResult:
    target: str
    target_path: Path
    tool: SecurityToolName
    status: SecurityStatus
    reason: str | None = None
    command: tuple[str, ...] = ()
    return_code: int | None = None
    log_path: Path | None = None

    def to_payload(self) -> JSONObject:
        payload: JSONObject = {
            "target": self.target,
            "targetPath": str(self.target_path.resolve()),
            "tool": self.tool,
            "status": self.status,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.command:
            payload["command"] = list(self.command)
        if self.return_code is not None:
            payload["returnCode"] = self.return_code
        if self.log_path is not None:
            payload["logPath"] = str(self.log_path)
        return payload


@dataclass(frozen=True)
class SecurityScanReport:
    requested_targets: tuple[str, ...]
    selected_tools: tuple[SecurityToolName, ...]
    targets: tuple[SecurityScanTarget, ...]
    results: tuple[SecurityRunResult, ...]
    log_dir: Path

    def status_count(self, status: SecurityStatus) -> int:
        return sum(1 for result in self.results if result.status == status)

    def exit_code(self) -> int:
        if self.status_count("failed") > 0:
            return 2
        if self.status_count("findings") > 0:
            return 1
        return 0

    def to_payload(self) -> JSONObject:
        return {
            "requestedTargets": list(self.requested_targets),
            "selectedTools": list(self.selected_tools),
            "logDir": str(self.log_dir),
            "targets": [
                {
                    "name": target.name,
                    "path": str(target.path.resolve()),
                }
                for target in self.targets
            ],
            "summary": {
                "total": len(self.results),
                "clean": self.status_count("clean"),
                "findings": self.status_count("findings"),
                "failed": self.status_count("failed"),
                "skipped": self.status_count("skipped"),
            },
            "results": [result.to_payload() for result in self.results],
        }


def security_tool_names() -> tuple[SecurityToolName, ...]:
    return SECURITY_TOOLS


def _load_config_if_available() -> Config | None:
    if find_workspace_root() is None:
        return None
    return load_config()


def _normalize_tools(tools: Sequence[str] | None) -> tuple[SecurityToolName, ...]:
    if not tools:
        return SECURITY_TOOLS

    selected: list[SecurityToolName] = []
    seen: set[str] = set()
    for tool in tools:
        if tool not in SECURITY_TOOLS:
            expected = ", ".join(SECURITY_TOOLS)
            raise ValueError(f"Unknown security scan tool: {tool}. Expected one of: {expected}.")
        if tool in seen:
            continue
        seen.add(tool)
        selected.append(tool)
    return tuple(selected)


def _resolve_targets(targets: Sequence[str]) -> tuple[SecurityScanTarget, ...]:
    config = _load_config_if_available()
    if config is None:
        raw_targets = list(targets) if targets else ["."]
        return tuple(SecurityScanTarget(name=target, path=Path(target).resolve()) for target in raw_targets)

    selected_targets = list(targets)
    if not selected_targets:
        inferred_targets = inferred_repo_targets(config)
        if inferred_targets is not None:
            selected_targets = inferred_targets

    resolved_targets = (
        resolve_repo_targets(selected_targets, config=config) if selected_targets else configured_repo_targets(config)
    )
    return tuple(
        SecurityScanTarget(name=target.name, path=target.path.resolve())
        for target in resolved_targets
    )


def _default_ignore(path: Path, is_dir: bool) -> bool:
    del is_dir
    return path.name in _DEFAULT_EXCLUDED_DIR_NAMES or path.name.startswith("tmp.")


def _iter_scan_files(root: Path) -> list[Path]:
    matcher = IgnoreMatcher(root if root.is_dir() else root.parent, extra_predicates=(_default_ignore,))
    if root.is_file():
        return [] if matcher.matches(root, is_dir=False) else [root]

    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        directory = Path(dirpath)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not matcher.matches(directory / dirname, is_dir=True)
        ]
        for filename in filenames:
            path = directory / filename
            if matcher.matches(path, is_dir=False):
                continue
            files.append(path)
    return files


def _has_suffix(files: Sequence[Path], suffixes: set[str]) -> bool:
    return any(path.suffix in suffixes for path in files)


def _has_source_files(files: Sequence[Path]) -> bool:
    return _has_suffix(files, _SOURCE_SUFFIXES)


def _is_shell_file(path: Path) -> bool:
    if path.suffix in _SHELL_SUFFIXES:
        return True
    try:
        with path.open("rb") as file:
            first_line = file.readline(256).decode("utf-8", errors="replace").casefold()
    except OSError:
        return False
    return first_line.startswith("#!") and any(shell in first_line for shell in (" sh", "bash", "zsh", "ksh"))


def _shell_files(files: Sequence[Path]) -> list[Path]:
    return [path for path in files if _is_shell_file(path)]


def _requirements_files(files: Sequence[Path]) -> list[Path]:
    result: list[Path] = []
    for path in files:
        name = path.name
        if name == "requirements.txt" or name.startswith(_DEPENDENCY_MANIFEST_PREFIXES):
            result.append(path)
    return sorted(result)


def _has_dependency_manifest(files: Sequence[Path]) -> bool:
    for path in files:
        name = path.name
        if name in _DEPENDENCY_MANIFEST_NAMES:
            return True
        if name.startswith(_DEPENDENCY_MANIFEST_PREFIXES):
            return True
        if name.endswith(_DEPENDENCY_MANIFEST_SUFFIXES):
            return True
    return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _configured_gradle_security_roots(root: Path, files: Sequence[Path]) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        if path.name not in {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}:
            continue
        text = _read_text(path)
        if not any(marker in text for marker in _GRADLE_SECURITY_MARKERS):
            continue
        gradle_root = path.parent.resolve()
        if gradle_root not in seen:
            seen.add(gradle_root)
            roots.append(gradle_root)

    if not roots and root.is_dir():
        root_files = [root / "build.gradle.kts", root / "build.gradle", root / "settings.gradle.kts", root / "settings.gradle"]
        text = "\n".join(_read_text(path) for path in root_files if path.is_file())
        if any(marker in text for marker in _GRADLE_SECURITY_MARKERS):
            roots.append(root.resolve())
    return roots


def _sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return sanitized or "target"


def _write_log(
    log_dir: Path,
    target: SecurityScanTarget,
    tool: SecurityToolName,
    command: Sequence[str],
    result: ExternalCommandResult,
) -> Path:
    target_dir = log_dir / _sanitize_filename(target.name)
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / f"{_sanitize_filename(tool)}.log"
    command_text_value = " ".join(command)
    log_path.write_text(
        f"$ {command_text_value}\n\n{result.output}",
        encoding="utf-8",
        errors="replace",
    )
    return log_path


def _run_command(command: Sequence[str], *, cwd: Path) -> ExternalCommandResult:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as ex:
        return ExternalCommandResult(return_code=127, output=f"{type(ex).__name__}: {ex}")

    output = completed.stdout
    if completed.stderr:
        output = output + ("\n" if output else "") + completed.stderr
    return ExternalCommandResult(return_code=completed.returncode, output=output)


def _tool_missing(target: SecurityScanTarget, tool: SecurityToolName, executable: str) -> SecurityRunResult:
    return SecurityRunResult(
        target=target.name,
        target_path=target.path,
        tool=tool,
        status="skipped",
        reason=f"{executable} is not installed or not on PATH",
    )


def _not_applicable(target: SecurityScanTarget, tool: SecurityToolName, reason: str) -> SecurityRunResult:
    return SecurityRunResult(
        target=target.name,
        target_path=target.path,
        tool=tool,
        status="skipped",
        reason=reason,
    )


def _command_result(
    target: SecurityScanTarget,
    tool: SecurityToolName,
    command: Sequence[str],
    result: ExternalCommandResult,
    *,
    log_dir: Path,
    finding_return_codes: set[int] | None = None,
) -> SecurityRunResult:
    log_path = _write_log(log_dir, target, tool, command, result)
    if result.return_code == 0:
        return SecurityRunResult(
            target=target.name,
            target_path=target.path,
            tool=tool,
            status="clean",
            command=tuple(command),
            return_code=result.return_code,
            log_path=log_path,
        )

    finding_codes = finding_return_codes if finding_return_codes is not None else {1}
    status = "findings" if result.return_code in finding_codes else "failed"
    reason = "tool reported security findings" if status == "findings" else "tool failed"
    return SecurityRunResult(
        target=target.name,
        target_path=target.path,
        tool=tool,
        status=status,
        reason=reason,
        command=tuple(command),
        return_code=result.return_code,
        log_path=log_path,
    )


def _tool_path(executable: str) -> str | None:
    tool_path = find_tool(executable)
    return str(tool_path) if tool_path is not None else None


def _scan_gitleaks(
    target: SecurityScanTarget,
    files: Sequence[Path],
    log_dir: Path,
) -> SecurityRunResult:
    del files
    tool = _tool_path("gitleaks")
    if tool is None:
        return _tool_missing(target, "gitleaks", "gitleaks")
    command = [tool, "detect", "--source", str(target.path), "--redact", "--no-banner"]
    result = _run_command(command, cwd=target.path if target.path.is_dir() else target.path.parent)
    return _command_result(target, "gitleaks", command, result, log_dir=log_dir)


def _scan_trufflehog(
    target: SecurityScanTarget,
    files: Sequence[Path],
    log_dir: Path,
) -> SecurityRunResult:
    del files
    tool = _tool_path("trufflehog")
    if tool is None:
        return _tool_missing(target, "trufflehog", "trufflehog")
    command = [tool, "filesystem", "--no-update", "--json", str(target.path)]
    result = _run_command(command, cwd=target.path if target.path.is_dir() else target.path.parent)
    return _command_result(target, "trufflehog", command, result, log_dir=log_dir, finding_return_codes={1, 183})


def _scan_semgrep(
    target: SecurityScanTarget,
    files: Sequence[Path],
    log_dir: Path,
) -> SecurityRunResult:
    if not _has_source_files(files):
        return _not_applicable(target, "semgrep", "no source files found")
    tool = _tool_path("semgrep")
    if tool is None:
        return _tool_missing(target, "semgrep", "semgrep")
    command = [tool, "scan", "--config", "auto", "--quiet", "--error", str(target.path)]
    result = _run_command(command, cwd=target.path if target.path.is_dir() else target.path.parent)
    return _command_result(target, "semgrep", command, result, log_dir=log_dir)


def _scan_bandit(
    target: SecurityScanTarget,
    files: Sequence[Path],
    log_dir: Path,
) -> SecurityRunResult:
    if not _has_suffix(files, _PYTHON_SUFFIXES):
        return _not_applicable(target, "bandit", "no Python files found")
    tool = _tool_path("bandit")
    if tool is None:
        return _tool_missing(target, "bandit", "bandit")
    excludes = ",".join(sorted(_DEFAULT_EXCLUDED_DIR_NAMES))
    command = [tool, "-q", "-r", str(target.path), "-x", excludes]
    result = _run_command(command, cwd=target.path if target.path.is_dir() else target.path.parent)
    return _command_result(target, "bandit", command, result, log_dir=log_dir)


def _scan_shellcheck(
    target: SecurityScanTarget,
    files: Sequence[Path],
    log_dir: Path,
) -> SecurityRunResult:
    shell_files = _shell_files(files)
    if not shell_files:
        return _not_applicable(target, "shellcheck", "no shell scripts found")
    tool = _tool_path("shellcheck")
    if tool is None:
        return _tool_missing(target, "shellcheck", "shellcheck")
    command = [tool, *[str(path) for path in shell_files]]
    result = _run_command(command, cwd=target.path if target.path.is_dir() else target.path.parent)
    return _command_result(target, "shellcheck", command, result, log_dir=log_dir)


def _looks_like_osv_cli_shape_error(result: ExternalCommandResult) -> bool:
    if result.return_code == 0:
        return False
    output = result.output.casefold()
    return "unknown command" in output or "unknown flag" in output or "unrecognized" in output


def _scan_osv_scanner(
    target: SecurityScanTarget,
    files: Sequence[Path],
    log_dir: Path,
) -> SecurityRunResult:
    if not _has_dependency_manifest(files):
        return _not_applicable(target, "osv-scanner", "no dependency manifests found")
    tool = _tool_path("osv-scanner")
    if tool is None:
        return _tool_missing(target, "osv-scanner", "osv-scanner")

    command = [tool, "scan", "source", "--recursive", str(target.path)]
    result = _run_command(command, cwd=target.path if target.path.is_dir() else target.path.parent)
    if _looks_like_osv_cli_shape_error(result):
        command = [tool, "--recursive", str(target.path)]
        result = _run_command(command, cwd=target.path if target.path.is_dir() else target.path.parent)
    return _command_result(target, "osv-scanner", command, result, log_dir=log_dir)


def _scan_pip_audit(
    target: SecurityScanTarget,
    files: Sequence[Path],
    log_dir: Path,
) -> SecurityRunResult:
    requirements_files = _requirements_files(files)
    if not requirements_files:
        return _not_applicable(target, "pip-audit", "no requirements*.txt files found")
    tool = _tool_path("pip-audit")
    if tool is None:
        return _tool_missing(target, "pip-audit", "pip-audit")
    command = [tool, "--progress-spinner", "off"]
    for requirement_file in requirements_files:
        command.extend(["-r", str(requirement_file)])
    result = _run_command(command, cwd=target.path if target.path.is_dir() else target.path.parent)
    return _command_result(target, "pip-audit", command, result, log_dir=log_dir)


def _gradle_security_task(root: Path) -> str:
    texts = "\n".join(
        _read_text(path)
        for path in (root / "build.gradle.kts", root / "build.gradle", root / "settings.gradle.kts", root / "settings.gradle")
        if path.is_file()
    )
    if "dependencyCheckAggregate" in texts:
        return "dependencyCheckAggregate"
    return "dependencyCheckAnalyze"


def _scan_gradle_dependency_check(
    target: SecurityScanTarget,
    files: Sequence[Path],
    log_dir: Path,
) -> SecurityRunResult:
    roots = _configured_gradle_security_roots(target.path, files)
    if not roots:
        return _not_applicable(
            target,
            "gradle-dependency-check",
            "no configured Gradle dependency-check task found",
        )
    root = roots[0]
    command = [*gradle_command(root), "--no-daemon", _gradle_security_task(root)]
    result = _run_command(command, cwd=root)
    return _command_result(target, "gradle-dependency-check", command, result, log_dir=log_dir)


def _scanner_for_tool(
    tool: SecurityToolName,
) -> Callable[[SecurityScanTarget, Sequence[Path], Path], SecurityRunResult]:
    match tool:
        case "gitleaks":
            return _scan_gitleaks
        case "trufflehog":
            return _scan_trufflehog
        case "semgrep":
            return _scan_semgrep
        case "bandit":
            return _scan_bandit
        case "shellcheck":
            return _scan_shellcheck
        case "osv-scanner":
            return _scan_osv_scanner
        case "pip-audit":
            return _scan_pip_audit
        case "gradle-dependency-check":
            return _scan_gradle_dependency_check
        case _:
            raise ValueError(f"Unknown security scan tool: {tool}")


def build_security_scan_report(
    targets: Sequence[str] | None = None,
    *,
    tools: Sequence[str] | None = None,
) -> SecurityScanReport:
    requested_targets = tuple(targets or ())
    selected_tools = _normalize_tools(tools)
    resolved_targets = _resolve_targets(requested_targets)
    log_dir = Path(tempfile.mkdtemp(prefix="wabbit-security-scan-"))

    results: list[SecurityRunResult] = []
    for target in resolved_targets:
        files = _iter_scan_files(target.path)
        for tool in selected_tools:
            scanner = _scanner_for_tool(tool)
            results.append(scanner(target, files, log_dir))

    return SecurityScanReport(
        requested_targets=requested_targets,
        selected_tools=selected_tools,
        targets=resolved_targets,
        results=tuple(results),
        log_dir=log_dir,
    )


def _status_color(status: SecurityStatus) -> str:
    if status == "clean":
        return "green"
    if status == "findings":
        return "red"
    if status == "failed":
        return "yellow"
    return "blue"


def _print_human_report(report: SecurityScanReport) -> None:
    print(heading("Security Scan"))
    print(f"{heading('Logs')}: {muted(report.log_dir)}")
    print()

    current_target: str | None = None
    for result in report.results:
        if current_target != result.target:
            if current_target is not None:
                print()
            current_target = result.target
            print(f"{heading(result.target)} {muted(result.target_path)}")

        label = style(result.status, _status_color(result.status), attrs=("bold",))
        line = f"  {accent(result.tool)}: {label}"
        if result.reason is not None:
            line += f" ({result.reason})"
        print(line)
        if result.command:
            print(f"    {command_text(' '.join(result.command))}")
        if result.log_path is not None:
            print(f"    log: {muted(result.log_path)}")

    print()
    summary: JSONObject = {
        "clean": report.status_count("clean"),
        "findings": report.status_count("findings"),
        "failed": report.status_count("failed"),
        "skipped": report.status_count("skipped"),
    }
    print(
        f"{heading('Summary')}: "
        f"{_colored_summary_count(summary, 'clean', 'green')} clean, "
        f"{_colored_summary_count(summary, 'findings', 'red')} findings, "
        f"{_colored_summary_count(summary, 'failed', 'yellow')} failed, "
        f"{_colored_summary_count(summary, 'skipped', 'blue')} skipped"
    )


def _colored_summary_count(summary: JSONObject, key: str, color: str) -> str:
    value = summary.get(key)
    match value:
        case int() as count:
            return accent(count, color)
        case _:
            return accent(0, color)


def security_scan(
    targets: Sequence[str] | None = None,
    *,
    tools: Sequence[str] | None = None,
    json_output: bool = False,
) -> int:
    report = build_security_scan_report(targets, tools=tools)
    if json_output:
        print(json.dumps(report.to_payload(), indent=2))
        return report.exit_code()

    _print_human_report(report)
    exit_code = report.exit_code()
    if exit_code == 0:
        success("No external security findings reported.")
    elif exit_code == 1:
        error("External security scanners reported findings.")
    else:
        error("One or more external security scanners failed.")
    return exit_code


__all__ = [
    "SecurityRunResult",
    "SecurityScanReport",
    "SecurityScanTarget",
    "build_security_scan_report",
    "security_scan",
    "security_tool_names",
]
