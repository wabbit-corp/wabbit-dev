from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET
else:
    from defusedxml import ElementTree as ET

from dev.checks.base import Issue, IssueType, Severity
from dev.config import Project, PythonProject

DEFAULT_EXCLUDE_CSV = ".venv,.git,__pycache__,.mypy_cache,.pytest_cache"

ANSI_ESCAPE_RE = re.compile(r"\x1B(?:\[[0-?]*[ -/]*[@-~]|\].*?(?:\x07|\x1B\\))")


@dataclass(frozen=True)
class IssueLocation:
    path: str | None = None
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None


@dataclass
class RuffIssue:
    code: str
    message: str
    location: IssueLocation
    end_location: IssueLocation | None = None
    fix_available: bool = False
    url: str | None = None
    raw: str | None = None


@dataclass
class RuffFailure:
    message: str
    raw: str | None = None


@dataclass
class BlackIssue:
    path: str | None
    message: str
    raw: str | None = None


@dataclass
class BlackFailure:
    message: str
    raw: str | None = None


@dataclass
class ImportLinterIssue:
    contract: str
    message: str
    raw: str | None = None


@dataclass
class ImportLinterFailure:
    message: str
    raw: str | None = None


@dataclass
class MypyIssue:
    message: str
    severity: str
    code: str | None
    location: IssueLocation
    notes: list[str] = field(default_factory=list)
    raw: str | None = None


@dataclass
class MypyFailure:
    message: str
    raw: str | None = None


@dataclass
class PyrightIssue:
    message: str
    severity: str
    rule: str | None
    location: IssueLocation
    raw: str | None = None


@dataclass
class PyrightFailure:
    message: str
    raw: str | None = None


@dataclass
class PytestIssue:
    outcome: str
    nodeid: str
    message: str
    location: IssueLocation = field(default_factory=IssueLocation)
    raw: str | None = None


@dataclass
class PytestFailure:
    message: str
    raw: str | None = None


@dataclass
class UnittestIssue:
    outcome: str
    test: str
    message: str
    raw: str | None = None


@dataclass
class UnittestFailure:
    message: str
    raw: str | None = None


@dataclass
class DeptryIssue:
    code: str | None
    message: str
    location: IssueLocation = field(default_factory=IssueLocation)
    raw: str | None = None


@dataclass
class DeptryFailure:
    message: str
    raw: str | None = None


@dataclass
class VultureIssue:
    message: str
    location: IssueLocation
    raw: str | None = None


@dataclass
class VultureFailure:
    message: str
    raw: str | None = None


@dataclass
class SemgrepIssue:
    rule_id: str
    message: str
    severity: str
    location: IssueLocation
    metadata: dict[str, object] = field(default_factory=dict)
    raw: str | None = None


@dataclass
class SemgrepFailure:
    message: str
    raw: str | None = None


@dataclass
class BanditIssue:
    test_id: str
    message: str
    severity: str
    confidence: str | None
    location: IssueLocation
    details: list[str] = field(default_factory=list)
    raw: str | None = None


@dataclass
class BanditFailure:
    message: str
    raw: str | None = None


@dataclass
class PipAuditIssue:
    package: str
    installed_version: str
    vulnerability_id: str
    fix_versions: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    description: str | None = None
    raw: str | None = None


@dataclass
class PipAuditFailure:
    message: str
    raw: str | None = None


@dataclass
class DiffCoverFileIssue:
    path: str
    coverage: float | None
    missing_lines: list[int] = field(default_factory=list)
    raw: str | None = None


@dataclass
class DiffCoverSummaryIssue:
    missing_lines: int | None
    coverage: float | None
    message: str
    raw: str | None = None


@dataclass
class DiffCoverThresholdIssue:
    message: str
    required: int | None
    raw: str | None = None


@dataclass
class DiffCoverFailure:
    message: str
    raw: str | None = None


@dataclass
class CoverageReportIssue:
    total: float | None
    fail_under: int | None
    message: str
    raw: str | None = None


@dataclass
class CoverageReportFailure:
    message: str
    raw: str | None = None


@dataclass
class CoverageXmlIssue:
    total: float | None
    fail_under: int | None
    message: str
    raw: str | None = None


@dataclass
class CoverageXmlFailure:
    message: str
    raw: str | None = None


ParsedIssue = (
    RuffIssue
    | RuffFailure
    | BlackIssue
    | BlackFailure
    | ImportLinterIssue
    | ImportLinterFailure
    | MypyIssue
    | MypyFailure
    | PyrightIssue
    | PyrightFailure
    | PytestIssue
    | PytestFailure
    | UnittestIssue
    | UnittestFailure
    | DeptryIssue
    | DeptryFailure
    | VultureIssue
    | VultureFailure
    | SemgrepIssue
    | SemgrepFailure
    | BanditIssue
    | BanditFailure
    | PipAuditIssue
    | PipAuditFailure
    | DiffCoverFileIssue
    | DiffCoverSummaryIssue
    | DiffCoverThresholdIssue
    | DiffCoverFailure
    | CoverageReportIssue
    | CoverageReportFailure
    | CoverageXmlIssue
    | CoverageXmlFailure
)


E_PYQA_TOOL_MISSING = IssueType(
    "E_PYQA_TOOL_MISSING",
    "Tool '{tool}' is missing: {message}",
)
E_PYQA_TOOL_FAILED = IssueType(
    "E_PYQA_TOOL_FAILED",
    "Tool '{tool}' failed: {message}",
)

E_PYQA_RUFF = IssueType("E_PYQA_RUFF", "ruff {code}: {message}")
E_PYQA_RUFF_WARNING = IssueType("E_PYQA_RUFF_WARNING", "ruff {code}: {message}", severity=Severity.WARNING)

E_PYQA_BLACK = IssueType("E_PYQA_BLACK", "black {code}: {message}")
E_PYQA_BLACK_WARNING = IssueType("E_PYQA_BLACK_WARNING", "black {code}: {message}", severity=Severity.WARNING)

E_PYQA_IMPORT_LINTER = IssueType("E_PYQA_IMPORT_LINTER", "import-linter {code}: {message}")
E_PYQA_IMPORT_LINTER_WARNING = IssueType(
    "E_PYQA_IMPORT_LINTER_WARNING",
    "import-linter {code}: {message}",
    severity=Severity.WARNING,
)

E_PYQA_MYPY = IssueType("E_PYQA_MYPY", "mypy {code}: {message}")
E_PYQA_MYPY_WARNING = IssueType("E_PYQA_MYPY_WARNING", "mypy {code}: {message}", severity=Severity.WARNING)

E_PYQA_PYRIGHT = IssueType("E_PYQA_PYRIGHT", "pyright {code}: {message}")
E_PYQA_PYRIGHT_WARNING = IssueType("E_PYQA_PYRIGHT_WARNING", "pyright {code}: {message}", severity=Severity.WARNING)

E_PYQA_PYTEST = IssueType("E_PYQA_PYTEST", "pytest {code}: {message}")
E_PYQA_PYTEST_WARNING = IssueType("E_PYQA_PYTEST_WARNING", "pytest {code}: {message}", severity=Severity.WARNING)

E_PYQA_COVERAGE_REPORT = IssueType("E_PYQA_COVERAGE_REPORT", "coverage report {code}: {message}")
E_PYQA_COVERAGE_REPORT_WARNING = IssueType(
    "E_PYQA_COVERAGE_REPORT_WARNING",
    "coverage report {code}: {message}",
    severity=Severity.WARNING,
)

E_PYQA_COVERAGE_XML = IssueType("E_PYQA_COVERAGE_XML", "coverage xml {code}: {message}")
E_PYQA_COVERAGE_XML_WARNING = IssueType(
    "E_PYQA_COVERAGE_XML_WARNING",
    "coverage xml {code}: {message}",
    severity=Severity.WARNING,
)

E_PYQA_DIFF_COVER = IssueType("E_PYQA_DIFF_COVER", "diff-cover {code}: {message}")
E_PYQA_DIFF_COVER_WARNING = IssueType(
    "E_PYQA_DIFF_COVER_WARNING",
    "diff-cover {code}: {message}",
    severity=Severity.WARNING,
)

E_PYQA_UNITTEST = IssueType("E_PYQA_UNITTEST", "unittest {code}: {message}")
E_PYQA_UNITTEST_WARNING = IssueType("E_PYQA_UNITTEST_WARNING", "unittest {code}: {message}", severity=Severity.WARNING)

E_PYQA_DEPTRY = IssueType("E_PYQA_DEPTRY", "deptry {code}: {message}")
E_PYQA_DEPTRY_WARNING = IssueType("E_PYQA_DEPTRY_WARNING", "deptry {code}: {message}", severity=Severity.WARNING)

E_PYQA_VULTURE = IssueType("E_PYQA_VULTURE", "vulture {code}: {message}")
E_PYQA_VULTURE_WARNING = IssueType("E_PYQA_VULTURE_WARNING", "vulture {code}: {message}", severity=Severity.WARNING)

E_PYQA_SEMGREP = IssueType("E_PYQA_SEMGREP", "semgrep {code}: {message}")
E_PYQA_SEMGREP_WARNING = IssueType("E_PYQA_SEMGREP_WARNING", "semgrep {code}: {message}", severity=Severity.WARNING)

E_PYQA_BANDIT = IssueType("E_PYQA_BANDIT", "bandit {code}: {message}")
E_PYQA_BANDIT_WARNING = IssueType("E_PYQA_BANDIT_WARNING", "bandit {code}: {message}", severity=Severity.WARNING)

E_PYQA_PIP_AUDIT = IssueType("E_PYQA_PIP_AUDIT", "pip-audit {code}: {message}")
E_PYQA_PIP_AUDIT_WARNING = IssueType(
    "E_PYQA_PIP_AUDIT_WARNING",
    "pip-audit {code}: {message}",
    severity=Severity.WARNING,
)


_TOOL_ISSUE_TYPES: dict[str, tuple[IssueType, IssueType]] = {
    "ruff": (E_PYQA_RUFF, E_PYQA_RUFF_WARNING),
    "black": (E_PYQA_BLACK, E_PYQA_BLACK_WARNING),
    "import_linter": (E_PYQA_IMPORT_LINTER, E_PYQA_IMPORT_LINTER_WARNING),
    "mypy": (E_PYQA_MYPY, E_PYQA_MYPY_WARNING),
    "pyright": (E_PYQA_PYRIGHT, E_PYQA_PYRIGHT_WARNING),
    "pytest": (E_PYQA_PYTEST, E_PYQA_PYTEST_WARNING),
    "coverage_report": (E_PYQA_COVERAGE_REPORT, E_PYQA_COVERAGE_REPORT_WARNING),
    "coverage_xml": (E_PYQA_COVERAGE_XML, E_PYQA_COVERAGE_XML_WARNING),
    "diff_cover": (E_PYQA_DIFF_COVER, E_PYQA_DIFF_COVER_WARNING),
    "unittest": (E_PYQA_UNITTEST, E_PYQA_UNITTEST_WARNING),
    "deptry": (E_PYQA_DEPTRY, E_PYQA_DEPTRY_WARNING),
    "vulture": (E_PYQA_VULTURE, E_PYQA_VULTURE_WARNING),
    "semgrep": (E_PYQA_SEMGREP, E_PYQA_SEMGREP_WARNING),
    "bandit": (E_PYQA_BANDIT, E_PYQA_BANDIT_WARNING),
    "pip_audit": (E_PYQA_PIP_AUDIT, E_PYQA_PIP_AUDIT_WARNING),
}


@dataclass
class ToolRunResult:
    rc: int
    issues: list[Issue]


@dataclass
class PythonQaRepoState:
    root: Path
    env: dict[str, str]
    venv: Path
    python: Path
    bin_dir: Path
    pyproject_config: Path | None
    mypy_config: Path | None
    pyright_config: Path | None
    import_linter_config: Path | None
    deptry_config: Path | None
    pytest_config: Path | None
    coverage_rcfile: Path | None
    coverage_fail_under: int
    run_coverage: bool
    run_diff_cover: bool
    run_bandit: bool
    run_unittest: bool
    use_json: bool
    semgrep_config: str
    diff_cover_compare_branch: str | None
    exclude_csv: str
    log_dir: Path
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    tool_results: dict[str, ToolRunResult] = field(default_factory=dict)
    pytest_rc: int | None = None
    pytest_label: str | None = None
    coverage_xml_path: Path | None = None


_STATES: dict[Path, PythonQaRepoState] = {}


def env_flag(name: str, default: str) -> bool:
    return os.environ.get(name, default) == "1"


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def to_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except ValueError:
        return None


def to_float(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    try:
        return float(value)
    except ValueError:
        return None


def get_str(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if isinstance(value, str):
        return value
    return None


def get_int(data: dict[str, object], key: str) -> int | None:
    value = data.get(key)
    if isinstance(value, int):
        return value
    return None


def get_dict(data: dict[str, object], key: str) -> dict[str, object] | None:
    value = data.get(key)
    if isinstance(value, dict):
        return value
    return None


def get_list(data: dict[str, object], key: str) -> list[object] | None:
    value = data.get(key)
    if isinstance(value, list):
        return value
    return None


def extract_json_payload(log_text: str) -> object | None:
    decoder = json.JSONDecoder()
    best_payload: object | None = None
    best_end = -1

    for match in re.finditer(r"[\[{]", log_text):
        start = match.start()
        try:
            payload, end = decoder.raw_decode(log_text[start:])
        except json.JSONDecodeError:
            continue

        end_index = start + end
        if end_index > best_end:
            best_end = end_index
            best_payload = payload

    return best_payload


def strip_ansi_escape_sequences(text: str) -> str:
    if not text:
        return text
    return ANSI_ESCAPE_RE.sub("", text)


def extract_json_lines(log_text: str) -> list[object]:
    out: list[object] = []
    for line in log_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] not in "{[":
            continue
        try:
            out.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return out


ANSI_CSI_RE = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]")
ANSI_OSC_RE = re.compile(rb"\x1b\][^\x1b]*\x1b\\")


def strip_ansi(data: bytes) -> bytes:
    data = ANSI_OSC_RE.sub(b"", data)
    return ANSI_CSI_RE.sub(b"", data)


def read_log_text(log_path: Path) -> str:
    try:
        data = log_path.read_bytes()
    except OSError:
        return ""
    clean = strip_ansi(data)
    return clean.decode("utf-8", errors="replace")


def issue_location(
    path: str | None,
    line: str | int | None = None,
    column: str | int | None = None,
    end_line: str | int | None = None,
    end_column: str | int | None = None,
) -> IssueLocation:
    return IssueLocation(
        path=path,
        line=to_int(line),
        column=to_int(column),
        end_line=to_int(end_line),
        end_column=to_int(end_column),
    )


# Parsers ported from the legacy checker implementation.


def parse_ruff_issues(log_text: str) -> Sequence[RuffIssue | RuffFailure]:
    payload = extract_json_payload(log_text)
    if isinstance(payload, list):
        json_issues: list[RuffIssue | RuffFailure] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            code = get_str(item, "code") or "UNKNOWN"
            message = get_str(item, "message") or ""
            filename = get_str(item, "filename") or get_str(item, "path")
            location_dict = get_dict(item, "location") or {}
            end_location_dict = get_dict(item, "end_location")
            line_number = get_int(location_dict, "row")
            if line_number is None:
                line_number = get_int(location_dict, "line")
            column_number = get_int(location_dict, "column")
            if column_number is None:
                column_number = get_int(location_dict, "col")
            end_line_number = None
            end_column_number = None
            if end_location_dict:
                end_line_number = get_int(end_location_dict, "row")
                if end_line_number is None:
                    end_line_number = get_int(end_location_dict, "line")
                end_column_number = get_int(end_location_dict, "column")
                if end_column_number is None:
                    end_column_number = get_int(end_location_dict, "col")
            location = issue_location(filename, line_number, column_number)
            end_location = None
            if end_line_number is not None or end_column_number is not None:
                end_location = issue_location(filename, end_line_number, end_column_number)
            fix_available = "fix" in item and item.get("fix") is not None
            url = get_str(item, "url")
            json_issues.append(
                RuffIssue(
                    code=code,
                    message=message,
                    location=location,
                    end_location=end_location,
                    fix_available=fix_available,
                    url=url,
                )
            )
        return json_issues

    text_issues: list[RuffIssue | RuffFailure] = []
    pending_code: str | None = None
    pending_message: str | None = None

    inline_re = re.compile(r"^(.+?):(\d+):(\d+):\s+([A-Z]{1,4}[0-9]{3,4})\s+(.*)$")
    code_re = re.compile(r"^([A-Z]{1,4}[0-9]{3,4})\s+(?:\[[^\]]*]\s+)?(.*)$")
    location_re = re.compile(r"^\s*--> (.+?):(\d+):(\d+)\s*$")

    for text_line in log_text.splitlines():
        inline_match = inline_re.match(text_line)
        if inline_match:
            text_issues.append(
                RuffIssue(
                    code=inline_match.group(4),
                    message=inline_match.group(5).strip(),
                    location=issue_location(
                        inline_match.group(1),
                        inline_match.group(2),
                        inline_match.group(3),
                    ),
                    raw=text_line,
                )
            )
            continue

        code_match = code_re.match(text_line)
        if code_match:
            pending_code = code_match.group(1)
            pending_message = code_match.group(2).strip()
            continue

        location_match = location_re.match(text_line)
        if location_match and pending_code:
            text_issues.append(
                RuffIssue(
                    code=pending_code,
                    message=pending_message or "",
                    location=issue_location(
                        location_match.group(1),
                        location_match.group(2),
                        location_match.group(3),
                    ),
                    raw=text_line,
                )
            )
            pending_code = None
            pending_message = None

    if pending_code:
        text_issues.append(
            RuffIssue(
                code=pending_code,
                message=pending_message or "",
                location=issue_location(None),
                raw=pending_message,
            )
        )

    return text_issues


def parse_black_issues(log_text: str) -> Sequence[BlackIssue | BlackFailure]:
    issues: list[BlackIssue | BlackFailure] = []
    reformat_re = re.compile(r"would reformat (.+)$")
    summary_re = re.compile(r"\d+ file(s)? would be reformatted")
    summary_line = None
    for line in log_text.splitlines():
        match = reformat_re.search(line)
        if match:
            issues.append(
                BlackIssue(
                    path=match.group(1).strip(),
                    message="File would be reformatted",
                    raw=line,
                )
            )
            continue
        if summary_re.search(line):
            summary_line = line.strip()
    if not issues and summary_line:
        issues.append(BlackIssue(path=None, message=summary_line, raw=summary_line))
    return issues


def parse_import_linter_issues(log_text: str) -> Sequence[ImportLinterIssue | ImportLinterFailure]:
    issues: list[ImportLinterIssue | ImportLinterFailure] = []
    broken_re = re.compile(r"^(.*?)\s+BROKEN$")
    summary_re = re.compile(r"Contracts: \d+ kept, (\d+) broken\.")
    for line in log_text.splitlines():
        match = broken_re.match(line.strip())
        if match:
            issues.append(
                ImportLinterIssue(
                    contract=match.group(1),
                    message="Contract broken",
                    raw=line,
                )
            )
    if not issues:
        summary_match = summary_re.search(log_text)
        if summary_match:
            broken_count = to_int(summary_match.group(1)) or 0
            if broken_count > 0:
                issues.append(
                    ImportLinterIssue(
                        contract="summary",
                        message=f"{broken_count} contracts broken",
                        raw=summary_match.group(0),
                    )
                )
    return issues


def parse_mypy_issues(log_text: str) -> Sequence[MypyIssue | MypyFailure]:
    json_lines = extract_json_lines(log_text)
    notes: list[str] = []
    if json_lines:
        issues: list[MypyIssue | MypyFailure] = []
        for item in json_lines:
            if not isinstance(item, dict):
                continue
            message = get_str(item, "message") or ""
            severity = get_str(item, "severity") or "error"
            code = get_str(item, "code")
            path = get_str(item, "file") or get_str(item, "path")
            line_number = get_int(item, "line")
            column_number = get_int(item, "column")
            end_line = get_int(item, "end_line")
            if end_line is None:
                end_line = get_int(item, "endLine")
            end_col = get_int(item, "end_column")
            if end_col is None:
                end_col = get_int(item, "endColumn")
            notes = []
            note_hint = get_str(item, "hint")
            if note_hint:
                notes.append(note_hint)
            issues.append(
                MypyIssue(
                    message=message,
                    severity=severity,
                    code=code,
                    location=issue_location(path, line_number, column_number, end_line, end_col),
                    notes=notes,
                )
            )
        return issues

    payload = extract_json_payload(log_text)
    items: list[object] | None = None
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        payload_items = get_list(payload, "errors") or get_list(payload, "results")
        if payload_items is not None:
            items = payload_items

    if items is not None:
        json_issues: list[MypyIssue | MypyFailure] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            message = get_str(item, "message") or ""
            severity = get_str(item, "severity") or "error"
            code = get_str(item, "code")
            path = get_str(item, "file") or get_str(item, "path")
            line_number = get_int(item, "line")
            column_number = get_int(item, "column")
            notes = []
            hints = get_list(item, "hints") or get_list(item, "notes")
            if hints:
                for note in hints:
                    if isinstance(note, str):
                        notes.append(note)
            json_issues.append(
                MypyIssue(
                    message=message,
                    severity=severity,
                    code=code,
                    location=issue_location(path, line_number, column_number),
                    notes=notes,
                )
            )
        return json_issues

    text_issues: list[MypyIssue | MypyFailure] = []
    error_re = re.compile(r"^(.+?):(\d+)(?::(\d+))?: error: (.*?)(?:\s+\[([^\]]+)\])?$")
    note_re = re.compile(r"^(.+?):(\d+)(?::(\d+))?: note: (.*)$")

    for text_line in log_text.splitlines():
        match = error_re.match(text_line)
        if match:
            issue = MypyIssue(
                message=match.group(4).strip(),
                severity="error",
                code=match.group(5),
                location=issue_location(match.group(1), match.group(2), match.group(3)),
                raw=text_line,
            )
            text_issues.append(issue)
            continue

        note_match = note_re.match(text_line)
        if note_match and text_issues:
            last = text_issues[-1]
            if isinstance(last, MypyIssue):
                last.notes.append(note_match.group(4).strip())

    return text_issues


def parse_pyright_issues(log_text: str) -> Sequence[PyrightIssue | PyrightFailure]:
    payload = extract_json_payload(log_text)
    diagnostics: list[object] | None = None
    if isinstance(payload, dict):
        diagnostics = get_list(payload, "generalDiagnostics") or get_list(payload, "diagnostics")

    if diagnostics is not None:
        json_issues: list[PyrightIssue | PyrightFailure] = []
        for item in diagnostics:
            if not isinstance(item, dict):
                continue
            severity = get_str(item, "severity") or "error"
            message = get_str(item, "message") or ""
            rule = get_str(item, "rule")
            path = get_str(item, "file")
            range_data = get_dict(item, "range") or {}
            start = get_dict(range_data, "start") or {}
            end = get_dict(range_data, "end") or {}
            line_number = get_int(start, "line")
            if line_number is not None:
                line_number += 1
            column_number = get_int(start, "character")
            if column_number is not None:
                column_number += 1
            end_line_number = get_int(end, "line")
            if end_line_number is not None:
                end_line_number += 1
            end_column_number = get_int(end, "character")
            if end_column_number is not None:
                end_column_number += 1
            json_issues.append(
                PyrightIssue(
                    message=message,
                    severity=severity,
                    rule=rule,
                    location=issue_location(
                        path,
                        line_number,
                        column_number,
                        end_line_number,
                        end_column_number,
                    ),
                )
            )
        return json_issues

    text_issues: list[PyrightIssue | PyrightFailure] = []
    diag_re = re.compile(r"^\s*(.+?):(\d+):(\d+)\s+-\s+(error|warning):\s+(.*?)(?:\s+\(([^)]+)\))?$")
    for text_line in log_text.splitlines():
        match = diag_re.match(text_line)
        if match:
            text_issues.append(
                PyrightIssue(
                    message=match.group(5).strip(),
                    severity=match.group(4).lower(),
                    rule=match.group(6),
                    location=issue_location(match.group(1), match.group(2), match.group(3)),
                    raw=text_line,
                )
            )
    return text_issues


def parse_pytest_issues(log_text: str, log_path: Path | None = None) -> Sequence[PytestIssue | PytestFailure]:
    if log_path is not None:
        junit_path = log_path.with_suffix(".junit.xml")
        if junit_path.is_file():
            return parse_pytest_junit(junit_path)
    return _parse_pytest_text(log_text)


def parse_pytest_junit(junit_path: Path) -> list[PytestIssue | PytestFailure]:
    try:
        xml_text = junit_path.read_text(encoding="utf-8", errors="replace")
        root = ET.fromstring(xml_text)
    except Exception as exc:
        return [PytestFailure(message=f"failed to parse junit xml: {exc}", raw=None)]

    issues: list[PytestIssue | PytestFailure] = []
    for testcase in root.iter("testcase"):
        classname = testcase.attrib.get("classname", "")
        name = testcase.attrib.get("name", "")
        nodeid = f"{classname}::{name}" if classname else name

        for tag in ("failure", "error"):
            elem = testcase.find(tag)
            if elem is None:
                continue
            msg = (elem.attrib.get("message") or "").strip()
            text = (elem.text or "").strip()
            message = msg or (text.splitlines()[0] if text else "Test failed")
            # JUnit often reports "collection failure" as a generic message while
            # embedding the real import/trace context in the element text body.
            if message.lower() in {"collection failure", "test failed"} and text:
                for candidate in (line.strip() for line in text.splitlines()):
                    if not candidate:
                        continue
                    if candidate.startswith("="):
                        continue
                    if candidate.startswith("Traceback"):
                        continue
                    message = candidate
                    break
            file_ = testcase.attrib.get("file")
            line_ = testcase.attrib.get("line")
            issues.append(
                PytestIssue(
                    outcome=tag.upper(),
                    nodeid=nodeid,
                    message=message,
                    location=issue_location(file_, line_),
                    raw=text or None,
                )
            )
    return issues


def _parse_pytest_text(log_text: str) -> Sequence[PytestIssue | PytestFailure]:
    issues: list[PytestIssue | PytestFailure] = []
    summary_re = re.compile(r"^(FAILED|ERROR)\s+(.+?)(?:\s+-\s+(.*))?$")
    collecting_re = re.compile(r"^ERROR collecting (.+)$")

    for line in log_text.splitlines():
        collecting_match = collecting_re.match(line)
        if collecting_match:
            issues.append(
                PytestIssue(
                    outcome="ERROR",
                    nodeid=collecting_match.group(1).strip(),
                    message="Collection error",
                    location=issue_location(collecting_match.group(1).strip()),
                    raw=line,
                )
            )
            continue

        match = summary_re.match(line)
        if not match:
            continue
        outcome = match.group(1)
        nodeid = match.group(2).strip()
        message = match.group(3).strip() if match.group(3) else "Test failed"
        location = issue_location(None)
        if "::" in nodeid:
            path, _ = nodeid.split("::", 1)
            location = issue_location(path)
        else:
            location = issue_location(nodeid)
        issues.append(
            PytestIssue(
                outcome=outcome,
                nodeid=nodeid,
                message=message,
                location=location,
                raw=line,
            )
        )

    return issues


def _extract_unittest_reason(lines: list[str]) -> str | None:
    cleaned: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if re.fullmatch(r"[-=]{3,}", stripped):
            continue
        if stripped.startswith("Traceback (most recent call last):"):
            continue
        cleaned.append(stripped)

    if not cleaned:
        return None

    most_specific_prefixes = (
        "ModuleNotFoundError:",
        "FileNotFoundError:",
        "AssertionError:",
        "RuntimeError:",
        "TypeError:",
        "ValueError:",
        "NameError:",
        "AttributeError:",
        "SyntaxError:",
    )
    for line in reversed(cleaned):
        if line.startswith(most_specific_prefixes):
            return line

    general_prefixes = (
        "ImportError:",
        "Failed to import test module:",
    )
    for line in cleaned:
        if line.startswith(general_prefixes):
            return line

    return cleaned[-1]


def parse_unittest_issues(log_text: str) -> Sequence[UnittestIssue | UnittestFailure]:
    issues: list[UnittestIssue | UnittestFailure] = []
    issue_re = re.compile(r"^(FAIL|ERROR):\s+(.+)$")
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        match = issue_re.match(line.strip())
        if not match:
            i += 1
            continue

        outcome = match.group(1)
        test = match.group(2).strip()
        j = i + 1
        details: list[str] = []
        while j < len(lines):
            current = lines[j]
            stripped = current.strip()
            if issue_re.match(stripped):
                break
            if stripped.startswith("Ran "):
                break
            if stripped.startswith("FAILED"):
                break
            if stripped.startswith("OK"):
                break
            details.append(current)
            j += 1

        reason = _extract_unittest_reason(details) or "Unittest failure"
        issues.append(
            UnittestIssue(
                outcome=outcome,
                test=test,
                message=reason,
                raw="\n".join(lines[i:j]) if j > i else line,
            )
        )
        i = max(j, i + 1)
    return issues


def parse_deptry_issues(log_text: str, log_path: Path | None = None) -> Sequence[DeptryIssue | DeptryFailure]:
    log_text = strip_ansi_escape_sequences(log_text)
    payload = extract_json_payload(log_text)
    if payload is None and log_path is not None:
        json_output = log_path.parent / "deptry.json"
        if json_output.is_file():
            try:
                payload = json.loads(json_output.read_text(encoding="utf-8"))
            except Exception:
                payload = None
    if isinstance(payload, list):
        json_issues: list[DeptryIssue | DeptryFailure] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            error_block = get_dict(item, "error") or {}
            location_block = get_dict(item, "location") or {}
            code = get_str(error_block, "code") or get_str(item, "code")
            message = get_str(error_block, "message") or get_str(item, "message") or ""
            path = get_str(location_block, "file") or get_str(item, "path") or get_str(item, "file")
            line_number = get_int(location_block, "line") or get_int(item, "line")
            column_number = get_int(location_block, "column") or get_int(item, "column")
            json_issues.append(
                DeptryIssue(
                    code=code,
                    message=message,
                    location=issue_location(path, line_number, column_number),
                )
            )
        return json_issues

    text_issues: list[DeptryIssue | DeptryFailure] = []
    detail_re = re.compile(r"^(.+?):(\d+)(?::(\d+))?:\s*([A-Z]{1,4}[0-9]{3})\s+(.*)$")
    code_re = re.compile(r"^([A-Z]{1,4}[0-9]{3})\s+(.*)$")
    for text_line in log_text.splitlines():
        detail_match = detail_re.match(text_line.strip())
        if detail_match:
            text_issues.append(
                DeptryIssue(
                    code=detail_match.group(4),
                    message=detail_match.group(5).strip(),
                    location=issue_location(
                        detail_match.group(1),
                        detail_match.group(2),
                        detail_match.group(3),
                    ),
                    raw=text_line,
                )
            )
            continue
        code_match = code_re.match(text_line.strip())
        if code_match:
            text_issues.append(
                DeptryIssue(
                    code=code_match.group(1),
                    message=code_match.group(2).strip(),
                    raw=text_line,
                )
            )
    return text_issues


def parse_vulture_issues(log_text: str) -> Sequence[VultureIssue | VultureFailure]:
    issues: list[VultureIssue | VultureFailure] = []
    detail_re = re.compile(r"^(.+?):(\d+):\s+(.*)$")
    for line in log_text.splitlines():
        match = detail_re.match(line.strip())
        if match:
            issues.append(
                VultureIssue(
                    message=match.group(3).strip(),
                    location=issue_location(match.group(1), match.group(2)),
                    raw=line,
                )
            )
    return issues


def parse_semgrep_issues(log_text: str) -> Sequence[SemgrepIssue | SemgrepFailure]:
    payload = extract_json_payload(log_text)
    if isinstance(payload, dict):
        results = get_list(payload, "results")
        if results is not None:
            json_issues: list[SemgrepIssue | SemgrepFailure] = []
            for item in results:
                if not isinstance(item, dict):
                    continue
                rule_id = get_str(item, "check_id") or "unknown"
                path = get_str(item, "path")
                start = get_dict(item, "start") or {}
                end = get_dict(item, "end") or {}
                line_number = get_int(start, "line")
                column_number = get_int(start, "col")
                if column_number is None:
                    column_number = get_int(start, "column")
                end_line_number = get_int(end, "line")
                end_column_number = get_int(end, "col")
                if end_column_number is None:
                    end_column_number = get_int(end, "column")
                extra = get_dict(item, "extra") or {}
                message = get_str(extra, "message") or ""
                severity = get_str(extra, "severity") or "error"
                metadata_raw = get_dict(extra, "metadata") or {}
                metadata: dict[str, object] = {}
                for key, value in metadata_raw.items():
                    metadata[key] = value
                json_issues.append(
                    SemgrepIssue(
                        rule_id=rule_id,
                        message=message,
                        severity=severity,
                        location=issue_location(
                            path,
                            line_number,
                            column_number,
                            end_line_number,
                            end_column_number,
                        ),
                        metadata=metadata,
                    )
                )
            return json_issues

    text_issues: list[SemgrepIssue | SemgrepFailure] = []
    inline_re = re.compile(r"^\s*(.+?):(\d+):(\d+):\s*([A-Za-z0-9_.-]+)\s*:\s*(.*)$")
    table_re = re.compile(
        r"^\s*(.+?):(\d+):(\d+)\s+(error|warning|info)\s+(\S+)\s+(.*)$",
        re.IGNORECASE,
    )
    for text_line in log_text.splitlines():
        inline_match = inline_re.match(text_line)
        if inline_match:
            text_issues.append(
                SemgrepIssue(
                    rule_id=inline_match.group(4),
                    message=inline_match.group(5).strip(),
                    severity="error",
                    location=issue_location(
                        inline_match.group(1),
                        inline_match.group(2),
                        inline_match.group(3),
                    ),
                    raw=text_line,
                )
            )
            continue

        table_match = table_re.match(text_line)
        if table_match:
            text_issues.append(
                SemgrepIssue(
                    rule_id=table_match.group(5),
                    message=table_match.group(6).strip(),
                    severity=table_match.group(4).lower(),
                    location=issue_location(
                        table_match.group(1),
                        table_match.group(2),
                        table_match.group(3),
                    ),
                    raw=text_line,
                )
            )
    return text_issues


def parse_bandit_issues(log_text: str) -> Sequence[BanditIssue | BanditFailure]:
    payload = extract_json_payload(log_text)
    if isinstance(payload, dict):
        results = get_list(payload, "results")
        if results is not None:
            json_issues: list[BanditIssue | BanditFailure] = []
            for item in results:
                if not isinstance(item, dict):
                    continue
                test_id = get_str(item, "test_id") or "B000"
                message = get_str(item, "issue_text") or ""
                severity = get_str(item, "issue_severity") or "HIGH"
                confidence = get_str(item, "issue_confidence")
                path = get_str(item, "filename")
                line_number = get_int(item, "line_number")
                column_number = get_int(item, "col_offset")
                end_column_number = get_int(item, "end_col_offset")
                if column_number is not None:
                    column_number += 1
                if end_column_number is not None:
                    end_column_number += 1
                details: list[str] = []
                more_info = get_str(item, "more_info")
                if more_info:
                    details.append(more_info)
                json_issues.append(
                    BanditIssue(
                        test_id=test_id,
                        message=message,
                        severity=severity,
                        confidence=confidence,
                        location=issue_location(
                            path,
                            line_number,
                            column_number,
                            line_number,
                            end_column_number,
                        ),
                        details=details,
                    )
                )
            return json_issues

    text_issues: list[BanditIssue | BanditFailure] = []
    current: BanditIssue | None = None
    issue_re = re.compile(r">> Issue: \[([^\]]+)\]\s+(.*)$")
    sev_re = re.compile(r"^\s*Severity:\s+(\w+)\s+Confidence:\s+(\w+)")
    loc_re = re.compile(r"^\s*Location:\s+(.+?):(\d+)")

    def flush_current() -> None:
        if current is not None:
            text_issues.append(current)

    for text_line in log_text.splitlines():
        issue_match = issue_re.match(text_line)
        if issue_match:
            flush_current()
            current = BanditIssue(
                test_id=issue_match.group(1),
                message=issue_match.group(2).strip(),
                severity="HIGH",
                confidence=None,
                location=issue_location(None),
                raw=text_line,
            )
            continue

        if current is None:
            continue

        sev_match = sev_re.match(text_line)
        if sev_match:
            current.severity = sev_match.group(1)
            current.confidence = sev_match.group(2)
            continue

        loc_match = loc_re.match(text_line)
        if loc_match:
            current.location = issue_location(loc_match.group(1), loc_match.group(2))
            continue

        stripped = text_line.strip()
        if stripped:
            current.details.append(stripped)

    flush_current()
    return text_issues


def parse_pip_audit_issues(log_text: str) -> Sequence[PipAuditIssue | PipAuditFailure]:
    payload = extract_json_payload(log_text)
    if isinstance(payload, dict):
        dependencies = get_list(payload, "dependencies")
        if dependencies is not None:
            json_issues: list[PipAuditIssue | PipAuditFailure] = []
            for dep in dependencies:
                if not isinstance(dep, dict):
                    continue
                package = get_str(dep, "name") or "unknown"
                installed_version = get_str(dep, "version") or ""
                vulns = get_list(dep, "vulns") or []
                for vuln in vulns:
                    if not isinstance(vuln, dict):
                        continue
                    vulnerability_id = get_str(vuln, "id") or "unknown"
                    json_fix_versions: list[str] = []
                    for fix in get_list(vuln, "fix_versions") or []:
                        if isinstance(fix, str):
                            json_fix_versions.append(fix)
                    aliases: list[str] = []
                    for alias in get_list(vuln, "aliases") or []:
                        if isinstance(alias, str):
                            aliases.append(alias)
                    description = get_str(vuln, "description") or get_str(vuln, "details")
                    json_issues.append(
                        PipAuditIssue(
                            package=package,
                            installed_version=installed_version,
                            vulnerability_id=vulnerability_id,
                            fix_versions=json_fix_versions,
                            aliases=aliases,
                            description=description,
                        )
                    )
            return json_issues

    if isinstance(payload, list):
        legacy_json_issues: list[PipAuditIssue | PipAuditFailure] = []
        for vuln in payload:
            if not isinstance(vuln, dict):
                continue
            package = get_str(vuln, "name") or get_str(vuln, "package") or "unknown"
            installed_version = get_str(vuln, "version") or get_str(vuln, "installed_version") or ""
            vulnerability_id = get_str(vuln, "id") or get_str(vuln, "vulnerability_id") or "unknown"
            legacy_fix_versions: list[str] = []
            for fix in get_list(vuln, "fix_versions") or []:
                if isinstance(fix, str):
                    legacy_fix_versions.append(fix)
            legacy_json_issues.append(
                PipAuditIssue(
                    package=package,
                    installed_version=installed_version,
                    vulnerability_id=vulnerability_id,
                    fix_versions=legacy_fix_versions,
                )
            )
        return legacy_json_issues

    text_issues: list[PipAuditIssue | PipAuditFailure] = []
    table_re = re.compile(r"^([A-Za-z0-9_.-]+)\s+([0-9][^\s]*)\s+([A-Za-z0-9_.-]+)\s*(.*)$")
    for text_line in log_text.splitlines():
        stripped = text_line.strip()
        if not stripped:
            continue
        if stripped.startswith("Found ") or stripped.startswith("No known vulnerabilities"):
            continue
        if stripped.startswith("Collecting ") or stripped.startswith("Auditing "):
            continue
        if stripped.startswith("name ") and "version" in stripped:
            continue
        match = table_re.match(stripped)
        if not match:
            continue
        package = match.group(1)
        installed_version = match.group(2)
        vulnerability_id = match.group(3)
        text_fix_versions: list[str] = []
        if match.group(4):
            text_fix_versions.append(match.group(4).strip())
        text_issues.append(
            PipAuditIssue(
                package=package,
                installed_version=installed_version,
                vulnerability_id=vulnerability_id,
                fix_versions=text_fix_versions,
                raw=text_line,
            )
        )
    return text_issues


def parse_line_ranges(text: str) -> list[int]:
    out: list[int] = []
    for part in (piece.strip() for piece in text.split(",") if piece.strip()):
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = to_int(start_text)
            end = to_int(end_text)
            if start is None or end is None:
                continue
            out.extend(range(min(start, end), max(start, end) + 1))
        else:
            value = to_int(part)
            if value is not None:
                out.append(value)
    return sorted(set(out))


def parse_diff_cover_issues(
    log_text: str,
    log_path: Path | None = None,
    fail_under: int | None = None,
) -> Sequence[DiffCoverFileIssue | DiffCoverSummaryIssue | DiffCoverThresholdIssue | DiffCoverFailure]:
    issues: list[DiffCoverFileIssue | DiffCoverSummaryIssue | DiffCoverThresholdIssue | DiffCoverFailure] = []
    json_path = None
    if log_path is not None:
        json_path = log_path.parent / "diff-cover.json"
    if json_path is not None and json_path.is_file():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            payload = None

        if isinstance(payload, dict):
            src_stats = payload.get("src_stats")
            if isinstance(src_stats, dict):
                for path, stats in src_stats.items():
                    if not isinstance(path, str) or not isinstance(stats, dict):
                        continue
                    pct = to_float(stats.get("percent_covered"))
                    lines_raw = stats.get("violation_lines")
                    lines: list[int] = []
                    if isinstance(lines_raw, list):
                        for item in lines_raw:
                            if isinstance(item, int):
                                lines.append(item)
                    if lines:
                        issues.append(
                            DiffCoverFileIssue(
                                path=path,
                                coverage=pct,
                                missing_lines=lines,
                            )
                        )
            total_violations = to_int(payload.get("total_num_violations"))
            total_pct = to_float(payload.get("total_percent_covered"))
            issues.append(
                DiffCoverSummaryIssue(
                    missing_lines=total_violations,
                    coverage=total_pct,
                    message="Diff coverage summary",
                )
            )
            if fail_under is not None and total_pct is not None and total_pct < fail_under:
                issues.append(
                    DiffCoverThresholdIssue(
                        message="Diff coverage below threshold",
                        required=fail_under,
                        raw=f"total={total_pct:.1f}%, fail-under={fail_under}%",
                    )
                )
            return issues
    file_re = re.compile(r"^(.+?) \((\d+(?:\.\d+)?)%\): Missing lines (.+)$")
    for line in log_text.splitlines():
        match = file_re.match(line.strip())
        if match:
            issues.append(
                DiffCoverFileIssue(
                    path=match.group(1),
                    coverage=to_float(match.group(2)),
                    missing_lines=parse_line_ranges(match.group(3)),
                    raw=line,
                )
            )
    missing_match = re.search(r"Missing:\s+(\d+) lines", log_text)
    coverage_match = re.search(r"Coverage:\s+(\d+(?:\.\d+)?)%", log_text)
    if missing_match or coverage_match:
        issues.append(
            DiffCoverSummaryIssue(
                missing_lines=to_int(missing_match.group(1)) if missing_match else None,
                coverage=to_float(coverage_match.group(1)) if coverage_match else None,
                message="Diff coverage summary",
                raw=missing_match.group(0) if missing_match else None,
            )
        )
    threshold_match = re.search(r"Coverage is below\s+(\d+)%", log_text)
    if threshold_match:
        issues.append(
            DiffCoverThresholdIssue(
                message="Diff coverage below threshold",
                required=to_int(threshold_match.group(1)),
                raw=threshold_match.group(0),
            )
        )
    elif re.search(r"^Failure\.", log_text, re.MULTILINE):
        issues.append(
            DiffCoverThresholdIssue(
                message="Diff coverage below threshold",
                required=None,
                raw="Failure.",
            )
        )
    return issues


def parse_coverage_report_issues(
    log_text: str, coverage_fail_under: int
) -> Sequence[CoverageReportIssue | CoverageReportFailure]:
    issues: list[CoverageReportIssue | CoverageReportFailure] = []
    failure_match = re.search(
        r"Coverage failure: total of (\d+(?:\.\d+)?) is less than fail-under=(\d+)",
        log_text,
    )
    if failure_match:
        issues.append(
            CoverageReportIssue(
                total=to_float(failure_match.group(1)),
                fail_under=to_int(failure_match.group(2)),
                message="Coverage below threshold",
                raw=failure_match.group(0),
            )
        )
        return issues

    total_match = re.search(
        r"^TOTAL\s+.*\s(\d+(?:\.\d+)?)%$",
        log_text,
        flags=re.MULTILINE,
    )
    if total_match:
        total = total_match.group(1)
        total_value = to_int(total.split(".", maxsplit=1)[0])
        if total_value is not None and total_value < coverage_fail_under:
            issues.append(
                CoverageReportIssue(
                    total=to_float(total),
                    fail_under=coverage_fail_under,
                    message="Coverage below threshold",
                    raw=total_match.group(0),
                )
            )
    return issues


@dataclass
class CoberturaTotals:
    line_rate: float | None
    branch_rate: float | None
    lines_covered: int | None
    lines_valid: int | None
    branches_covered: int | None
    branches_valid: int | None


def read_cobertura_totals(xml_path: Path) -> CoberturaTotals | None:
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return None

    def _f(name: str) -> float | None:
        value = root.attrib.get(name)
        return to_float(value) if value is not None else None

    def _i(name: str) -> int | None:
        value = root.attrib.get(name)
        return to_int(value) if value is not None else None

    return CoberturaTotals(
        line_rate=_f("line-rate"),
        branch_rate=_f("branch-rate"),
        lines_covered=_i("lines-covered"),
        lines_valid=_i("lines-valid"),
        branches_covered=_i("branches-covered"),
        branches_valid=_i("branches-valid"),
    )


def parse_coverage_xml_issues(
    log_text: str,
    coverage_fail_under: int,
    log_path: Path | None = None,
) -> Sequence[CoverageXmlIssue | CoverageXmlFailure]:
    issues: list[CoverageXmlIssue | CoverageXmlFailure] = []
    xml_path = None
    if log_path is not None:
        candidate = log_path.parent / "coverage.xml"
        if candidate.is_file():
            xml_path = candidate

    if xml_path is not None:
        totals = read_cobertura_totals(xml_path)
        if totals and totals.branch_rate is not None:
            branch_pct = totals.branch_rate * 100.0
            if branch_pct < coverage_fail_under:
                issues.append(
                    CoverageXmlIssue(
                        total=branch_pct,
                        fail_under=coverage_fail_under,
                        message="Branch coverage below threshold",
                        raw=f"branch={branch_pct:.2f}%, fail-under={coverage_fail_under}%",
                    )
                )
            return issues

        issues.append(
            CoverageXmlFailure(
                message="coverage xml produced no readable branch coverage",
                raw=str(xml_path),
            )
        )
        return issues

    failure_match = re.search(
        r"Coverage failure: total of (\d+(?:\.\d+)?) is less than fail-under=(\d+)",
        log_text,
    )
    if failure_match:
        issues.append(
            CoverageXmlIssue(
                total=to_float(failure_match.group(1)),
                fail_under=to_int(failure_match.group(2)),
                message="Coverage below threshold",
                raw=failure_match.group(0),
            )
        )
        return issues

    if re.search(r"Coverage failure:", log_text):
        issues.append(
            CoverageXmlIssue(
                total=None,
                fail_under=coverage_fail_under,
                message="Coverage below threshold",
                raw=log_text,
            )
        )
    return issues


def parse_issues(label: str, log_path: Path, coverage_fail_under: int) -> Sequence[ParsedIssue]:
    log_text = strip_ansi_escape_sequences(read_log_text(log_path))

    if label == "ruff":
        return parse_ruff_issues(log_text)
    if label == "black --check":
        return parse_black_issues(log_text)
    if label == "import-linter":
        return parse_import_linter_issues(log_text)
    if label == "mypy":
        return parse_mypy_issues(log_text)
    if label in ("pyright", "basedpyright"):
        return parse_pyright_issues(log_text)
    if label in ("pytest", "coverage run (pytest)"):
        return parse_pytest_issues(log_text, log_path)
    if label == "unittest":
        return parse_unittest_issues(log_text)
    if label == "deptry":
        return parse_deptry_issues(log_text, log_path)
    if label == "vulture":
        return parse_vulture_issues(log_text)
    if label == "semgrep":
        return parse_semgrep_issues(log_text)
    if label == "bandit":
        return parse_bandit_issues(log_text)
    if label == "pip-audit":
        return parse_pip_audit_issues(log_text)
    if label == "diff-cover":
        return parse_diff_cover_issues(log_text, log_path, coverage_fail_under)
    if label == "coverage report":
        return parse_coverage_report_issues(log_text, coverage_fail_under)
    if label == "coverage xml":
        return parse_coverage_xml_issues(log_text, coverage_fail_under, log_path)

    return []


def normalize_severity(value: str) -> str:
    lowered = value.lower()
    if lowered in {"warning", "warn"}:
        return "warning"
    if lowered in {"info", "note"}:
        return "warning"
    return "error"


def issue_severity(issue: ParsedIssue) -> str:
    if isinstance(issue, (VultureIssue, DiffCoverFileIssue, DiffCoverSummaryIssue)):
        return "warning"
    if isinstance(issue, SemgrepIssue):
        return normalize_severity(issue.severity)
    if isinstance(issue, BanditIssue):
        if issue.severity.lower() in {"low", "medium"}:
            return "warning"
        return "error"
    if isinstance(issue, (MypyIssue, PyrightIssue)):
        return normalize_severity(issue.severity)
    return "error"


def _issue_span(issue: ParsedIssue) -> tuple[str | None, int | None, int | None, int | None, int | None]:
    if isinstance(issue, RuffIssue):
        path = issue.location.path
        line = issue.location.line
        col = issue.location.column
        if issue.end_location:
            return (path, line, col, issue.end_location.line, issue.end_location.column)
        return (path, line, col, None, None)

    if isinstance(issue, DiffCoverFileIssue):
        return (issue.path, None, None, None, None)

    loc = getattr(issue, "location", None)
    if isinstance(loc, IssueLocation):
        return (
            loc.path,
            loc.line,
            loc.column,
            loc.end_line,
            loc.end_column,
        )

    if isinstance(issue, BlackIssue) and issue.path:
        return (issue.path, None, None, None, None)

    return (None, None, None, None, None)


def failure_issue(label: str, log_text: str, rc: int | None = None) -> ParsedIssue:
    message = summarize_failure_message(label, log_text, rc)
    if label == "ruff":
        return RuffFailure(message=message, raw=log_text)
    if label == "black --check":
        return BlackFailure(message=message, raw=log_text)
    if label == "import-linter":
        return ImportLinterFailure(message=message, raw=log_text)
    if label == "mypy":
        return MypyFailure(message=message, raw=log_text)
    if label in ("pyright", "basedpyright"):
        return PyrightFailure(message=message, raw=log_text)
    if label in ("pytest", "coverage run (pytest)"):
        return PytestFailure(message=message, raw=log_text)
    if label == "unittest":
        return UnittestFailure(message=message, raw=log_text)
    if label == "deptry":
        return DeptryFailure(message=message, raw=log_text)
    if label == "vulture":
        return VultureFailure(message=message, raw=log_text)
    if label == "semgrep":
        return SemgrepFailure(message=message, raw=log_text)
    if label == "bandit":
        return BanditFailure(message=message, raw=log_text)
    if label == "pip-audit":
        return PipAuditFailure(message=message, raw=log_text)
    if label == "diff-cover":
        return DiffCoverFailure(message=message, raw=log_text)
    if label == "coverage report":
        return CoverageReportFailure(message=message, raw=log_text)
    if label == "coverage xml":
        return CoverageXmlFailure(message=message, raw=log_text)
    return RuffFailure(message=message, raw=log_text)


def summarize_failure_message(label: str, log_text: str, rc: int | None = None) -> str:
    base = f"{label} failed"
    if rc is not None:
        base = f"{base} (exit code {rc})"
    cleaned_text = strip_ansi_escape_sequences(log_text)
    lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]
    if not lines:
        return base

    def is_noise(line: str) -> bool:
        if re.fullmatch(r"[-=]{3,}", line):
            return True
        if line.startswith("Traceback (most recent call last):"):
            return True
        if line.startswith("Ran "):
            return True
        if line.startswith("FAILED"):
            return True
        if line.startswith("OK"):
            return True
        return False

    filtered = [line for line in lines if not is_noise(line)]
    if not filtered:
        return base

    def score(line: str) -> tuple[int, int]:
        lowered = line.lower()
        weight = 0
        if "error" in lowered:
            weight += 4
        if "exception" in lowered:
            weight += 3
        if "failed" in lowered:
            weight += 2
        if "module" in lowered:
            weight += 1
        # prefer earlier lines for equal weight
        return (weight, -filtered.index(line))

    detail = max(filtered, key=score)
    detail = detail[:260]
    if detail.lower() == base.lower():
        return base
    return f"{base}: {detail}"


def _sanitize_label(label: str) -> str:
    sanitized = []
    for char in label:
        if char in " /":
            sanitized.append("_")
            continue
        if char.isalnum() or char in "._-":
            sanitized.append(char)
        else:
            sanitized.append("_")
    return "".join(sanitized)


def _tool_key_for_label(label: str) -> str:
    if label in {"pyright", "basedpyright"}:
        return "pyright"
    if label == "black --check":
        return "black"
    if label == "import-linter":
        return "import_linter"
    if label in {"coverage run (pytest)", "pytest"}:
        return "pytest"
    if label == "coverage report":
        return "coverage_report"
    if label == "coverage xml":
        return "coverage_xml"
    if label == "diff-cover":
        return "diff_cover"
    if label == "pip-audit":
        return "pip_audit"
    if label == "ruff":
        return "ruff"
    if label == "mypy":
        return "mypy"
    if label == "unittest":
        return "unittest"
    if label == "deptry":
        return "deptry"
    if label == "vulture":
        return "vulture"
    if label == "semgrep":
        return "semgrep"
    if label == "bandit":
        return "bandit"
    return "ruff"


def _issue_code_and_message(issue: ParsedIssue) -> tuple[str, str]:
    if isinstance(issue, RuffIssue):
        return (issue.code, issue.message)
    if isinstance(issue, BlackIssue):
        return ("reformat", issue.message)
    if isinstance(issue, ImportLinterIssue):
        return (issue.contract, issue.message)
    if isinstance(issue, MypyIssue):
        return (issue.code or "-", issue.message)
    if isinstance(issue, PyrightIssue):
        return (issue.rule or "-", issue.message)
    if isinstance(issue, PytestIssue):
        if issue.nodeid:
            if issue.message:
                return (issue.outcome, f"{issue.nodeid}: {issue.message}")
            return (issue.outcome, issue.nodeid)
        return (issue.outcome, issue.message)
    if isinstance(issue, UnittestIssue):
        if issue.test:
            if issue.message:
                return (issue.outcome, f"{issue.test}: {issue.message}")
            return (issue.outcome, issue.test)
        return (issue.outcome, issue.message)
    if isinstance(issue, DeptryIssue):
        return (issue.code or "-", issue.message)
    if isinstance(issue, VultureIssue):
        return ("unused", issue.message)
    if isinstance(issue, SemgrepIssue):
        return (issue.rule_id, issue.message)
    if isinstance(issue, BanditIssue):
        return (issue.test_id, issue.message)
    if isinstance(issue, PipAuditIssue):
        return (
            issue.vulnerability_id,
            f"{issue.package} {issue.installed_version}: vulnerability {issue.vulnerability_id}",
        )
    if isinstance(issue, DiffCoverFileIssue):
        return ("missing-lines", "Missing lines")
    if isinstance(issue, DiffCoverSummaryIssue):
        return ("summary", issue.message)
    if isinstance(issue, DiffCoverThresholdIssue):
        return ("threshold", issue.message)
    if isinstance(issue, CoverageReportIssue):
        return ("fail-under", issue.message)
    if isinstance(issue, CoverageXmlIssue):
        return ("fail-under", issue.message)

    message = getattr(issue, "message", str(issue))
    return ("failure", message)


def _to_path(repo_root: Path, raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return repo_root / path


def _to_check_issue(repo_root: Path, label: str, parsed_issue: ParsedIssue) -> Issue:
    key = _tool_key_for_label(label)
    severity = issue_severity(parsed_issue)
    t_error, t_warn = _TOOL_ISSUE_TYPES[key]
    issue_type = t_error if severity == "error" else t_warn
    code, message = _issue_code_and_message(parsed_issue)
    issue = issue_type.make(code=code, message=message)
    path, line, _, _, _ = _issue_span(parsed_issue)
    path_obj = _to_path(repo_root, path)
    if path_obj is not None:
        issue = issue.at(path_obj, line=line)
    return issue


def _merge_label(prefix: str, values: set[str], total_count: int) -> str:
    if not values:
        return prefix

    sorted_values = sorted(values)
    preview = ", ".join(sorted_values[:3])
    remaining = total_count - len(sorted_values[:3])
    if remaining > 0:
        preview = f"{preview} (+{remaining} more)"
    return preview


def _dedupe_parsed_issues(parsed_issues: Sequence[ParsedIssue]) -> list[ParsedIssue]:
    out: list[ParsedIssue] = []
    seen: set[
        tuple[
            str,
            str,
            str,
            str | None,
            int | None,
            int | None,
            int | None,
            int | None,
        ]
    ] = set()
    merged_pytest_nodes: dict[int, set[str]] = {}
    merged_unittest_tests: dict[int, set[str]] = {}
    merged_counts: dict[int, int] = {}

    for issue in parsed_issues:
        if isinstance(issue, PytestIssue):
            path, line, col, end_line, end_col = _issue_span(issue)
            key = (
                type(issue).__name__,
                issue.outcome,
                issue.message,
                path,
                line,
                col,
                end_line,
                end_col,
            )
            if key in seen:
                idx = next(
                    i
                    for i, existing in enumerate(out)
                    if isinstance(existing, PytestIssue)
                    and _issue_span(existing) == (path, line, col, end_line, end_col)
                    and existing.outcome == issue.outcome
                    and existing.message == issue.message
                )
                merged_counts[idx] = merged_counts.get(idx, 1) + 1
                if issue.nodeid:
                    merged_pytest_nodes.setdefault(idx, set()).add(issue.nodeid)
                continue

            seen.add(key)
            idx = len(out)
            out.append(issue)
            merged_counts[idx] = 1
            if issue.nodeid:
                merged_pytest_nodes[idx] = {issue.nodeid}
            continue

        if isinstance(issue, UnittestIssue):
            key = (
                type(issue).__name__,
                issue.outcome,
                issue.message,
                None,
                None,
                None,
                None,
                None,
            )
            if key in seen:
                idx = next(
                    i
                    for i, existing in enumerate(out)
                    if isinstance(existing, UnittestIssue)
                    and existing.outcome == issue.outcome
                    and existing.message == issue.message
                )
                merged_counts[idx] = merged_counts.get(idx, 1) + 1
                if issue.test:
                    merged_unittest_tests.setdefault(idx, set()).add(issue.test)
                continue

            seen.add(key)
            idx = len(out)
            out.append(issue)
            merged_counts[idx] = 1
            if issue.test:
                merged_unittest_tests[idx] = {issue.test}
            continue

        code, message = _issue_code_and_message(issue)
        path, line, col, end_line, end_col = _issue_span(issue)
        key = (
            type(issue).__name__,
            code,
            message,
            path,
            line,
            col,
            end_line,
            end_col,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(issue)

    for idx, names in merged_pytest_nodes.items():
        issue = out[idx]
        if not isinstance(issue, PytestIssue):
            continue
        total_count = merged_counts.get(idx, len(names))
        issue.nodeid = _merge_label(issue.nodeid, names, total_count)

    for idx, names in merged_unittest_tests.items():
        issue = out[idx]
        if not isinstance(issue, UnittestIssue):
            continue
        total_count = merged_counts.get(idx, len(names))
        issue.test = _merge_label(issue.test, names, total_count)

    return out


def _missing_issue(tool: str, message: str, repo_root: Path | None = None) -> Issue:
    issue = E_PYQA_TOOL_MISSING.make(tool=tool, message=message)
    if repo_root is not None:
        issue = issue.at(repo_root)
    return issue


def _failed_issue(tool: str, message: str, repo_root: Path | None = None) -> Issue:
    issue = E_PYQA_TOOL_FAILED.make(tool=tool, message=message)
    if repo_root is not None:
        issue = issue.at(repo_root)
    return issue


def _resolve_existing(path: Path) -> Path | None:
    if path.is_file():
        return path
    return None


def _resolve_existing_dir(path: Path) -> Path | None:
    if path.is_dir():
        return path
    return None


def _resolve_target_first(repo_root: Path, filename: str, fallback: Path | None) -> Path | None:
    target = repo_root / filename
    resolved_target = _resolve_existing(target)
    if resolved_target is not None:
        return resolved_target
    if fallback is None:
        return None
    return _resolve_existing(fallback)


def _parse_csv_items(value: str | None) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _dedupe_preserving_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _read_simple_checkignore_paths(repo_root: Path) -> list[str]:
    checkignore = repo_root / ".checkignore"
    if not checkignore.is_file():
        return []
    try:
        lines = checkignore.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    paths: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if any(ch in line for ch in "*?[]"):
            continue
        normalized = line.strip("/")
        if normalized:
            paths.append(normalized)
    return paths


def _resolve_default_config_file(
    env: dict[str, str],
    explicit_env_key: str,
    defaults_root: Path | None,
    filename: str,
) -> Path | None:
    explicit = env.get(explicit_env_key)
    if explicit:
        return _resolve_existing(Path(explicit).expanduser())
    if defaults_root is not None:
        return _resolve_existing(defaults_root / filename)
    return None


def _discover_defaults_root(repo_root: Path) -> Path | None:
    workspace_root = repo_root.parent
    try:
        candidates = sorted(workspace_root.iterdir())
    except OSError:
        return None

    for candidate in candidates:
        if not candidate.is_dir() or candidate == repo_root:
            continue
        has_pyproject = (candidate / "pyproject.toml").is_file()
        has_mypy = (candidate / "mypy.ini").is_file()
        has_pyright = (candidate / "pyrightconfig.json").is_file()
        if has_pyproject and has_mypy and has_pyright:
            return candidate
    return None


def _read_coverage_fail_under_from_pyproject(pyproject_path: Path | None) -> int | None:
    if pyproject_path is None:
        return None
    try:
        import tomllib

        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    tool = data.get("tool")
    if not isinstance(tool, dict):
        return None
    coverage = tool.get("coverage")
    if not isinstance(coverage, dict):
        return None
    report = coverage.get("report")
    if not isinstance(report, dict):
        return None
    value = report.get("fail_under")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _has_import_linter_contracts(pyproject_path: Path | None) -> bool:
    if pyproject_path is None:
        return False
    try:
        import tomllib

        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    tool = data.get("tool")
    if not isinstance(tool, dict):
        return False
    importlinter = tool.get("importlinter")
    if not isinstance(importlinter, dict):
        return False
    contracts = importlinter.get("contracts")
    return isinstance(contracts, list) and len(contracts) > 0


def _new_state(repo_root: Path) -> PythonQaRepoState:
    env = os.environ.copy()
    venv = repo_root / ".venv"
    python = venv / "bin" / "python"
    bin_dir = venv / "bin"
    defaults_root = (
        _resolve_existing_dir(Path(env["PYTHON_QA_DEFAULTS_ROOT"]).expanduser())
        if env.get("PYTHON_QA_DEFAULTS_ROOT")
        else None
    )
    if defaults_root is None:
        defaults_root = _discover_defaults_root(repo_root)
    pyproject_fallback = _resolve_default_config_file(
        env,
        "PYTHON_QA_DEFAULT_PYPROJECT",
        defaults_root,
        "pyproject.toml",
    )
    mypy_fallback = _resolve_default_config_file(
        env,
        "PYTHON_QA_DEFAULT_MYPY",
        defaults_root,
        "mypy.ini",
    )
    pyright_fallback = _resolve_default_config_file(
        env,
        "PYTHON_QA_DEFAULT_PYRIGHT",
        defaults_root,
        "pyrightconfig.json",
    )

    pyproject_config = _resolve_target_first(
        repo_root,
        "pyproject.toml",
        pyproject_fallback,
    )
    mypy_config = _resolve_target_first(repo_root, "mypy.ini", mypy_fallback)
    pyright_config = _resolve_target_first(
        repo_root,
        "pyrightconfig.json",
        pyright_fallback,
    )

    fail_under = env_int("COVERAGE_FAIL_UNDER", -1)
    if fail_under < 0:
        fail_under = _read_coverage_fail_under_from_pyproject(pyproject_config) or 15
    configured_excludes = _parse_csv_items(env.get("PYTHON_QA_EXCLUDE_CSV", DEFAULT_EXCLUDE_CSV))
    checkignore_excludes = _read_simple_checkignore_paths(repo_root)
    combined_excludes = _dedupe_preserving_order(configured_excludes + checkignore_excludes)

    state = PythonQaRepoState(
        root=repo_root,
        env=env,
        venv=venv,
        python=python,
        bin_dir=bin_dir,
        pyproject_config=pyproject_config,
        mypy_config=mypy_config,
        pyright_config=pyright_config,
        import_linter_config=pyproject_config,
        deptry_config=pyproject_config,
        pytest_config=pyproject_config,
        coverage_rcfile=pyproject_config,
        coverage_fail_under=fail_under,
        run_coverage=env_flag("RUN_COVERAGE", "1"),
        run_diff_cover=env_flag("RUN_DIFF_COVER", "1"),
        run_bandit=env_flag("RUN_BANDIT", "0"),
        run_unittest=env_flag("RUN_UNITTEST", "1"),
        use_json=env_flag("USE_JSON_OUTPUT", "1"),
        semgrep_config=env.get("SEMGREP_CONFIG", "p/python"),
        diff_cover_compare_branch=env.get("DIFF_COVER_COMPARE_BRANCH") or None,
        exclude_csv=",".join(combined_excludes),
        log_dir=Path(tempfile.mkdtemp(prefix="qa")),
    )
    return state


def _get_state(repo_root: Path) -> PythonQaRepoState:
    key = repo_root.resolve()
    if key not in _STATES:
        _STATES[key] = _new_state(key)
    return _STATES[key]


def _tool_executable(state: PythonQaRepoState, name: str) -> Path | None:
    tool = state.bin_dir / name
    if tool.is_file() and os.access(tool, os.X_OK):
        return tool
    return None


def _has_python_repo_markers(repo_root: Path) -> bool:
    if (repo_root / "pyproject.toml").is_file():
        return True
    if any(repo_root.glob("requirements*.txt")):
        return True
    return False


def should_run_python_qa(repo_root: Path, project: Project | None) -> bool:
    if project is not None:
        return isinstance(project, PythonProject)
    return _has_python_repo_markers(repo_root)


def _command_success(cmd: Sequence[str], env: dict[str, str], cwd: Path) -> bool:
    return (
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=cwd,
            check=False,
        ).returncode
        == 0
    )


def _git_ref_exists(ref: str, env: dict[str, str], cwd: Path) -> bool:
    return _command_success(
        ["git", "show-ref", "--verify", "--quiet", ref],
        env,
        cwd,
    )


def choose_compare_branch(state: PythonQaRepoState) -> str | None:
    if state.diff_cover_compare_branch:
        return state.diff_cover_compare_branch

    candidates = [
        ("refs/remotes/origin/main", "origin/main"),
        ("refs/remotes/origin/master", "origin/master"),
        ("refs/heads/main", "main"),
        ("refs/heads/master", "master"),
    ]
    for ref, name in candidates:
        if _git_ref_exists(ref, state.env, state.root):
            return name
    return None


def has_dependency_metadata(repo_root: Path) -> bool:
    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        try:
            if "[project]" in pyproject.read_text(errors="replace"):
                return True
        except OSError:
            pass
    return any(repo_root.glob("requirements*.txt"))


def _run_subprocess(
    state: PythonQaRepoState,
    label: str,
    cmd: Sequence[str],
) -> ToolRunResult:
    safe_label = _sanitize_label(label)
    log_path = state.log_dir / f"{safe_label}.log"

    try:
        result = subprocess.run(
            cmd,
            cwd=state.root,
            capture_output=True,
            text=True,
            env=state.env,
            check=False,
        )
    except OSError as exc:
        message = f"{type(exc).__name__}: {exc}"
        try:
            log_path.write_text(message, encoding="utf-8", errors="replace")
        except OSError:
            pass
        return ToolRunResult(
            rc=127,
            issues=[_failed_issue(label, message, state.root)],
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        try:
            log_path.write_text(message, encoding="utf-8", errors="replace")
        except OSError:
            pass
        return ToolRunResult(
            rc=1,
            issues=[_failed_issue(label, message, state.root)],
        )

    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        if output:
            output += "\n"
        output += result.stderr
    try:
        log_path.write_text(output, encoding="utf-8", errors="replace")
    except OSError:
        pass

    parsed_issues = list(parse_issues(label, log_path, state.coverage_fail_under))
    if not parsed_issues and result.returncode != 0:
        failure_output = output
        if not failure_output.strip():
            command_preview = " ".join(str(part) for part in cmd)
            failure_output = f"command produced no output (rc={result.returncode}): {command_preview}"
        parsed_issues = [failure_issue(label, failure_output, result.returncode)]
    parsed_issues = _dedupe_parsed_issues(parsed_issues)

    issues = [_to_check_issue(state.root, label, issue) for issue in parsed_issues]
    return ToolRunResult(rc=result.returncode, issues=issues)


def _run_once(
    state: PythonQaRepoState,
    label: str,
    run: Callable[[], ToolRunResult],
) -> ToolRunResult:
    with state.lock:
        cached = state.tool_results.get(label)
        if cached is not None:
            return cached

    result = run()

    with state.lock:
        state.tool_results[label] = result

    return result


def _require_python(state: PythonQaRepoState, tool_name: str) -> ToolRunResult | None:
    if state.python.is_file() and os.access(state.python, os.X_OK):
        return None
    message = f".venv python not found at {state.python}"
    return ToolRunResult(rc=127, issues=[_missing_issue(tool_name, message, state.root)])


def _require_tool(
    state: PythonQaRepoState, tool_name: str, install_hint: str | None = None
) -> tuple[Path | None, ToolRunResult | None]:
    tool_path = _tool_executable(state, tool_name)
    if tool_path is not None:
        return tool_path, None
    hint = install_hint or f"install {tool_name} in {state.venv}"
    missing = ToolRunResult(rc=127, issues=[_missing_issue(tool_name, hint, state.root)])
    return None, missing


def _append_config_arg(args: list[str], flag: str, cfg: Path | None) -> None:
    if cfg is not None:
        args.extend([flag, str(cfg)])


def run_ruff(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        py_req = _require_python(state, "ruff")
        if py_req is not None:
            return py_req
        tool, missing = _require_tool(
            state,
            "ruff",
            f"Install: {state.python} -m pip install ruff",
        )
        if missing is not None:
            return missing

        args = [str(tool), "check"]
        if state.use_json:
            args.extend(["--output-format", "json"])
        _append_config_arg(args, "--config", state.pyproject_config)
        args.append(".")
        return _run_subprocess(state, "ruff", args)

    return _run_once(state, "ruff", _runner).issues


def run_black(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        py_req = _require_python(state, "black")
        if py_req is not None:
            return py_req
        tool, missing = _require_tool(
            state,
            "black",
            f"Install: {state.python} -m pip install black",
        )
        if missing is not None:
            return missing

        args = [str(tool), "--check"]
        _append_config_arg(args, "--config", state.pyproject_config)
        args.append(".")
        return _run_subprocess(state, "black --check", args)

    return _run_once(state, "black --check", _runner).issues


def run_import_linter(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        if state.import_linter_config is None or state.import_linter_config.parent != state.root:
            return ToolRunResult(rc=0, issues=[])
        if not _has_import_linter_contracts(state.import_linter_config):
            return ToolRunResult(rc=0, issues=[])

        py_req = _require_python(state, "import-linter")
        if py_req is not None:
            return py_req
        tool, missing = _require_tool(
            state,
            "lint-imports",
            f"Install: {state.python} -m pip install import-linter",
        )
        if missing is not None:
            return ToolRunResult(
                rc=missing.rc,
                issues=[
                    _missing_issue(
                        "import-linter",
                        f"Install: {state.python} -m pip install import-linter",
                        state.root,
                    )
                ],
            )

        args = [str(tool)]
        _append_config_arg(args, "--config", state.import_linter_config)
        return _run_subprocess(state, "import-linter", args)

    return _run_once(state, "import-linter", _runner).issues


def run_mypy(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        py_req = _require_python(state, "mypy")
        if py_req is not None:
            return py_req
        tool, missing = _require_tool(
            state,
            "mypy",
            f"Install: {state.python} -m pip install mypy",
        )
        if missing is not None:
            return missing

        args = [str(tool)]
        exclude_paths = _parse_csv_items(state.exclude_csv)
        exclude_patterns = [rf"(^|/){re.escape(path.strip('/'))}(/|$)" for path in exclude_paths if path.strip("/")]
        mypy_exclude = state.env.get("PYTHON_QA_MYPY_EXCLUDE")
        if mypy_exclude:
            exclude_patterns.append(mypy_exclude)
        if exclude_patterns:
            args.extend(["--exclude", "|".join(f"(?:{pattern})" for pattern in exclude_patterns)])
        if state.use_json:
            args.extend(["--output", "json"])
        _append_config_arg(args, "--config-file", state.mypy_config)
        args.append(".")
        return _run_subprocess(state, "mypy", args)

    return _run_once(state, "mypy", _runner).issues


def run_pyright(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        py_req = _require_python(state, "pyright")
        if py_req is not None:
            return py_req

        based = _tool_executable(state, "basedpyright")
        pyright = _tool_executable(state, "pyright")
        if based is None and pyright is None:
            return ToolRunResult(
                rc=127,
                issues=[
                    _missing_issue(
                        "pyright/basedpyright",
                        f"Install: {state.python} -m pip install pyright",
                        state.root,
                    )
                ],
            )

        selected = based if based is not None else pyright
        assert selected is not None
        label = "basedpyright" if selected == based else "pyright"

        args = [str(selected)]
        if state.use_json:
            args.append("--outputjson")
        project_cfg = state.pyright_config if state.pyright_config is not None else state.root
        args.extend(["--project", str(project_cfg)])
        return _run_subprocess(state, label, args)

    result = _run_once(state, "pyright", _runner)
    return result.issues


def _coverage_available(state: PythonQaRepoState) -> bool:
    return _command_success([str(state.python), "-m", "coverage", "--version"], state.env, state.root)


def run_pytest(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        py_req = _require_python(state, "pytest")
        if py_req is not None:
            return py_req

        pytest_bin = _tool_executable(state, "pytest")
        if pytest_bin is None:
            return ToolRunResult(
                rc=127,
                issues=[
                    _missing_issue(
                        "pytest",
                        f"Install: {state.python} -m pip install pytest",
                        state.root,
                    )
                ],
            )
        pytest_ignore_paths = _dedupe_preserving_order(
            _parse_csv_items(state.exclude_csv) + _parse_csv_items(state.env.get("PYTHON_QA_PYTEST_IGNORE_CSV"))
        )

        if state.run_coverage and _coverage_available(state):
            label = "coverage run (pytest)"
            junit_path = state.log_dir / f"{_sanitize_label(label)}.junit.xml"
            args = [
                str(state.python),
                "-m",
                "coverage",
                "run",
                "--branch",
                "-m",
                "pytest",
                "--color=yes",
                "--junitxml",
                str(junit_path),
            ]
            for ignore_path in pytest_ignore_paths:
                args.extend(["--ignore", ignore_path])
            if state.pytest_config is not None:
                args.extend(["-c", str(state.pytest_config)])
            result = _run_subprocess(state, label, args)
            state.pytest_label = label
            state.pytest_rc = result.rc
            return result

        label = "pytest"
        junit_path = state.log_dir / f"{_sanitize_label(label)}.junit.xml"
        args = [str(pytest_bin), "--color=yes", "--junitxml", str(junit_path)]
        for ignore_path in pytest_ignore_paths:
            args.extend(["--ignore", ignore_path])
        if state.pytest_config is not None:
            args.extend(["-c", str(state.pytest_config)])
        result = _run_subprocess(state, label, args)
        state.pytest_label = label
        state.pytest_rc = result.rc
        return result

    return _run_once(state, "pytest", _runner).issues


def _ensure_pytest_run(state: PythonQaRepoState, project: Project | None) -> None:
    if "pytest" not in state.tool_results:
        run_pytest(state.root, project)


def run_coverage_report(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        if not state.run_coverage:
            return ToolRunResult(rc=0, issues=[])
        _ensure_pytest_run(state, project)
        if state.pytest_rc is None or state.pytest_rc != 0:
            return ToolRunResult(rc=0, issues=[])
        if not _coverage_available(state):
            return ToolRunResult(rc=127, issues=[_missing_issue("coverage", "coverage module missing", state.root)])

        args = [str(state.python), "-m", "coverage", "report", "--show-missing"]
        _append_config_arg(args, "--rcfile", state.coverage_rcfile)
        return _run_subprocess(state, "coverage report", args)

    return _run_once(state, "coverage report", _runner).issues


def run_coverage_xml(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        if not state.run_coverage:
            return ToolRunResult(rc=0, issues=[])
        _ensure_pytest_run(state, project)
        if state.pytest_rc is None or state.pytest_rc != 0:
            return ToolRunResult(rc=0, issues=[])
        if not _coverage_available(state):
            return ToolRunResult(rc=127, issues=[_missing_issue("coverage", "coverage module missing", state.root)])

        coverage_xml_path = state.log_dir / "coverage.xml"
        args = [str(state.python), "-m", "coverage", "xml", "-o", str(coverage_xml_path)]
        _append_config_arg(args, "--rcfile", state.coverage_rcfile)
        result = _run_subprocess(state, "coverage xml", args)
        if result.rc == 0:
            state.coverage_xml_path = coverage_xml_path
        return result

    return _run_once(state, "coverage xml", _runner).issues


def run_diff_cover(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        if not state.run_coverage or not state.run_diff_cover:
            return ToolRunResult(rc=0, issues=[])

        run_coverage_xml(repo_root, project)
        if state.coverage_xml_path is None or not state.coverage_xml_path.is_file():
            return ToolRunResult(rc=0, issues=[])

        tool, missing = _require_tool(
            state,
            "diff-cover",
            "Install: python -m pip install diff-cover",
        )
        if missing is not None:
            return ToolRunResult(rc=0, issues=[])

        if not _command_success(["git", "rev-parse", "--is-inside-work-tree"], state.env, state.root):
            return ToolRunResult(rc=0, issues=[])

        compare_branch = choose_compare_branch(state)
        if compare_branch is None:
            return ToolRunResult(rc=0, issues=[])

        json_report = state.log_dir / "diff-cover.json"
        args = [
            str(tool),
            str(state.coverage_xml_path),
            f"--fail-under={state.coverage_fail_under}",
            f"--compare-branch={compare_branch}",
            "--format",
            f"json:{json_report}",
        ]
        return _run_subprocess(state, "diff-cover", args)

    return _run_once(state, "diff-cover", _runner).issues


def run_unittest(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        if not state.run_unittest:
            return ToolRunResult(rc=0, issues=[])
        py_req = _require_python(state, "unittest")
        if py_req is not None:
            return py_req
        result = _run_subprocess(
            state,
            "unittest",
            [str(state.python), "-m", "unittest", "discover", "-s", "dev"],
        )
        if result.rc == 5:
            return ToolRunResult(rc=0, issues=[])
        return result

    return _run_once(state, "unittest", _runner).issues


def run_deptry(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        py_req = _require_python(state, "deptry")
        if py_req is not None:
            return py_req
        tool, missing = _require_tool(
            state,
            "deptry",
            f"Install: {state.python} -m pip install deptry",
        )
        if missing is not None:
            return missing
        if not has_dependency_metadata(state.root):
            return ToolRunResult(rc=0, issues=[])

        json_output = state.log_dir / "deptry.json"
        args = [str(tool), ".", "--json-output", str(json_output)]
        deptry_path_excludes = [
            rf"(.*/)?{re.escape(path.strip('/'))}(/.*)?$"
            for path in _parse_csv_items(state.exclude_csv)
            if path.strip("/")
        ]
        deptry_extra_patterns = _parse_csv_items(state.env.get("PYTHON_QA_DEPTRY_EXTEND_EXCLUDE_CSV"))
        for exclude_pattern in _dedupe_preserving_order(deptry_path_excludes + deptry_extra_patterns):
            args.extend(["--extend-exclude", exclude_pattern])
        _append_config_arg(args, "--config", state.deptry_config)
        return _run_subprocess(state, "deptry", args)

    return _run_once(state, "deptry", _runner).issues


def run_vulture(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        py_req = _require_python(state, "vulture")
        if py_req is not None:
            return py_req
        tool, missing = _require_tool(
            state,
            "vulture",
            f"Install: {state.python} -m pip install vulture",
        )
        if missing is not None:
            return missing
        args = [str(tool), ".", "--exclude", state.exclude_csv]
        return _run_subprocess(state, "vulture", args)

    return _run_once(state, "vulture", _runner).issues


def run_semgrep(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        py_req = _require_python(state, "semgrep")
        if py_req is not None:
            return py_req
        tool, missing = _require_tool(
            state,
            "semgrep",
            f"Install: {state.python} -m pip install semgrep",
        )
        if missing is not None:
            return missing

        args = [str(tool), "scan"]
        if state.use_json:
            args.append("--json")
        args.extend(["--config", state.semgrep_config])
        for exclude_path in _parse_csv_items(state.exclude_csv):
            args.extend(["--exclude", exclude_path])
        args.append(".")
        return _run_subprocess(state, "semgrep", args)

    return _run_once(state, "semgrep", _runner).issues


def run_bandit(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        if not state.run_bandit:
            return ToolRunResult(rc=0, issues=[])

        py_req = _require_python(state, "bandit")
        if py_req is not None:
            return py_req

        if not _command_success([str(state.python), "-m", "bandit", "--version"], state.env, state.root):
            return ToolRunResult(
                rc=127,
                issues=[_missing_issue("bandit", f"Install: {state.python} -m pip install bandit", state.root)],
            )

        args = [str(state.python), "-m", "bandit"]
        if state.use_json:
            args.extend(["-f", "json"])

        args.extend(["-r", ".", "-x", state.exclude_csv, "-s", "B101"])
        return _run_subprocess(state, "bandit", args)

    return _run_once(state, "bandit", _runner).issues


def run_pip_audit(repo_root: Path, project: Project | None) -> list[Issue]:
    if not should_run_python_qa(repo_root, project):
        return []
    state = _get_state(repo_root)

    def _runner() -> ToolRunResult:
        py_req = _require_python(state, "pip-audit")
        if py_req is not None:
            return py_req
        tool, missing = _require_tool(
            state,
            "pip-audit",
            f"Install: {state.python} -m pip install pip-audit",
        )
        if missing is not None:
            return missing

        args = [str(tool)]
        if state.use_json:
            args.extend(["-f", "json", "--progress-spinner", "off"])
        return _run_subprocess(state, "pip-audit", args)

    return _run_once(state, "pip-audit", _runner).issues


def cleanup_python_qa_state(repo_root: Path) -> None:
    key = repo_root.resolve()
    state = _STATES.pop(key, None)
    if state is None:
        return
    shutil.rmtree(state.log_dir, ignore_errors=True)


def reset_all_python_qa_state() -> None:
    roots = list(_STATES.keys())
    for root in roots:
        cleanup_python_qa_state(root)


__all__ = [
    "run_ruff",
    "run_black",
    "run_import_linter",
    "run_mypy",
    "run_pyright",
    "run_pytest",
    "run_coverage_report",
    "run_coverage_xml",
    "run_diff_cover",
    "run_unittest",
    "run_deptry",
    "run_vulture",
    "run_semgrep",
    "run_bandit",
    "run_pip_audit",
    "reset_all_python_qa_state",
    "parse_ruff_issues",
    "parse_black_issues",
    "parse_import_linter_issues",
    "parse_mypy_issues",
    "parse_pyright_issues",
    "parse_pytest_issues",
    "parse_unittest_issues",
    "parse_deptry_issues",
    "parse_vulture_issues",
    "parse_semgrep_issues",
    "parse_bandit_issues",
    "parse_pip_audit_issues",
    "parse_diff_cover_issues",
    "parse_coverage_report_issues",
    "parse_coverage_xml_issues",
]
