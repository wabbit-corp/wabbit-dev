from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dev.json_types import JSONArray, JSONObject

SEMVER_IMPACT_VALUES: tuple[str, ...] = ("MAJOR", "MINOR", "PATCH", "NONE")
SEMVER_IMPACT_PATTERN = re.compile(r"^Semver Impact: (MAJOR|MINOR|PATCH|NONE)$")
SEMVER_IMPACT_CANDIDATE_PATTERN = re.compile(r"^Semver Impact:")
SEMVER_TAG_PATTERN = re.compile(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")
VERSION_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^[+-]\s*version\s*=\s*[\"']?\d"),
    re.compile(r"^[+-]\s*version\s*:\s*[\"']?\d"),
    re.compile(r"^[+-]\s*\"version\"\s*:\s*[\"']?\d"),
    re.compile(r"^[+-]\s*\(?version\s+[\"']\d"),
    re.compile(r"^[+-].*\bproject\.version\s*="),
    re.compile(r"^[+-].*\bpluginVersion\s*="),
    re.compile(r"^[+-].*\bversionName\s*="),
    re.compile(r"^[+-].*\bversionCode\s*="),
)
CHANGELOG_NAMES: tuple[str, ...] = (
    "CHANGELOG.md",
    "CHANGELOG.rst",
    "CHANGES.md",
    "CHANGES.rst",
    "RELEASE_NOTES.md",
    "RELEASES.md",
)
POLICY_EXCEPTION_PATTERN = re.compile(r"^Policy Exception: (merge|revert|version-tag|vendored-import)$")
RELEASE_AUTOMATION_PATTERN = re.compile(r"^Release Automation: true$")
SUBJECT_MAX_LENGTH = 72


@dataclass(frozen=True)
class CommitDiffContext:
    version_changed: bool
    changelog_changed: bool
    has_version_tag: bool

    def to_payload(self) -> JSONObject:
        return {
            "versionChanged": self.version_changed,
            "changelogChanged": self.changelog_changed,
            "hasVersionTag": self.has_version_tag,
        }


@dataclass(frozen=True)
class CommitPolicyFinding:
    code: str
    message: str
    fix: str
    source: str
    commit: str | None = None

    def to_payload(self) -> JSONObject:
        payload: JSONObject = {
            "code": self.code,
            "message": self.message,
            "fix": self.fix,
            "source": self.source,
        }
        if self.commit is not None:
            payload["commit"] = self.commit
        return payload


@dataclass(frozen=True)
class CommitPolicyResult:
    source: str
    commit: str | None
    subject: str | None
    exception: str | None
    findings: tuple[CommitPolicyFinding, ...]
    diff_context: CommitDiffContext | None = None

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_payload(self) -> JSONObject:
        payload: JSONObject = {
            "source": self.source,
            "passed": self.passed,
            "findings": [finding.to_payload() for finding in self.findings],
        }
        if self.commit is not None:
            payload["commit"] = self.commit
        if self.subject is not None:
            payload["subject"] = self.subject
        if self.exception is not None:
            payload["exception"] = self.exception
        if self.diff_context is not None:
            payload["diffContext"] = self.diff_context.to_payload()
        return payload


@dataclass(frozen=True)
class CommitPolicyReport:
    results: tuple[CommitPolicyResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_payload(self) -> JSONObject:
        results: JSONArray = []
        for result in self.results:
            results.append(result.to_payload())
        return {
            "passed": self.passed,
            "checked": len(self.results),
            "failed": sum(1 for result in self.results if not result.passed),
            "results": results,
        }


def clean_commit_message(raw_message: str) -> str:
    lines = [line.rstrip() for line in raw_message.splitlines() if not line.lstrip().startswith("#")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def ensure_semver_impact_line(commit_message: str) -> str:
    message = clean_commit_message(commit_message)
    if not message:
        return "chore: update repository\n\nSemver Impact: NONE"
    if _semver_line_indexes(message.splitlines()):
        return message
    return f"{message}\n\nSemver Impact: NONE"


def verify_commit_message(
    raw_message: str,
    *,
    source: str,
    commit: str | None = None,
    parent_count: int = 1,
    tags: tuple[str, ...] = (),
    diff_context: CommitDiffContext | None = None,
) -> CommitPolicyResult:
    message = clean_commit_message(raw_message)
    lines = message.splitlines()
    subject = _first_nonblank_line(lines)
    exception = _policy_exception(lines, subject=subject, parent_count=parent_count, tags=tags)
    findings: list[CommitPolicyFinding] = []

    def add(code: str, message_text: str, fix: str) -> None:
        findings.append(CommitPolicyFinding(code=code, message=message_text, fix=fix, source=source, commit=commit))

    if subject is None:
        add(
            "E_EMPTY_COMMIT_MESSAGE",
            "Commit message is empty.",
            "Add a concise subject and a final `Semver Impact: MAJOR|MINOR|PATCH|NONE` line.",
        )
        return CommitPolicyResult(
            source=source,
            commit=commit,
            subject=None,
            exception=exception,
            findings=tuple(findings),
            diff_context=diff_context,
        )

    unknown_exceptions = _unknown_policy_exception_lines(lines)
    for line in unknown_exceptions:
        add(
            "E_UNKNOWN_POLICY_EXCEPTION",
            f"Unknown policy exception marker: {line}",
            "Use `Policy Exception: merge|revert|version-tag|vendored-import`, or remove the marker.",
        )

    if exception is None:
        _verify_standard_message_rules(lines, subject=subject, add=add)

    if (
        diff_context is not None
        and diff_context.has_version_tag
        and diff_context.version_changed
        and not diff_context.changelog_changed
        and not _has_release_automation_marker(lines)
    ):
        add(
            "E_VERSION_CHANGE_WITHOUT_CHANGELOG",
            "A project version changed, but no changelog or release-notes file changed in the same commit.",
            "Update CHANGELOG.md/release notes, or add `Release Automation: true` for a release automation commit.",
        )

    return CommitPolicyResult(
        source=source,
        commit=commit,
        subject=subject,
        exception=exception,
        findings=tuple(findings),
        diff_context=diff_context,
    )


def staged_diff_context(repo_root: Path) -> CommitDiffContext:
    files_text = _run_git(repo_root, ("diff", "--cached", "--name-only"))
    diff_text = _run_git(repo_root, ("diff", "--cached", "--unified=0"))
    tags_text = _run_git(repo_root, ("tag", "--list"))
    return CommitDiffContext(
        version_changed=_version_changed(diff_text),
        changelog_changed=_changelog_changed(files_text.splitlines()),
        has_version_tag=_has_semver_tag(tags_text.splitlines()),
    )


def commit_diff_context(repo_root: Path, commit: str) -> CommitDiffContext:
    files_text = _run_git(repo_root, ("show", "--format=", "--name-only", commit))
    diff_text = _run_git(repo_root, ("show", "--format=", "--unified=0", commit))
    tags_text = _run_git(repo_root, ("tag", "--list"))
    return CommitDiffContext(
        version_changed=_version_changed(diff_text),
        changelog_changed=_changelog_changed(files_text.splitlines()),
        has_version_tag=_has_semver_tag(tags_text.splitlines()),
    )


def commit_message(repo_root: Path, commit: str) -> str:
    return _run_git(repo_root, ("log", "-1", "--format=%B", commit))


def commit_parent_count(repo_root: Path, commit: str) -> int:
    line = _run_git(repo_root, ("rev-list", "--parents", "-n", "1", commit)).strip()
    if not line:
        return 1
    return max(0, len(line.split()) - 1)


def commit_tags(repo_root: Path, commit: str) -> tuple[str, ...]:
    return tuple(line for line in _run_git(repo_root, ("tag", "--points-at", commit)).splitlines() if line.strip())


def commits_in_range(repo_root: Path, revision_range: str) -> tuple[str, ...]:
    text = _run_git(repo_root, ("rev-list", "--reverse", revision_range))
    return tuple(line.strip() for line in text.splitlines() if line.strip())


def git_root(start: Path) -> Path:
    return Path(_run_git(start, ("rev-parse", "--show-toplevel")).strip())


def git_hooks_path(repo_root: Path) -> Path:
    return repo_root / _run_git(repo_root, ("rev-parse", "--git-path", "wabbit-dev-hooks")).strip()


type CommitFindingAdder = Callable[[str, str, str], None]


def _verify_standard_message_rules(
    lines: list[str],
    *,
    subject: str,
    add: CommitFindingAdder,
) -> None:
    if len(subject) > SUBJECT_MAX_LENGTH:
        add(
            "E_SUBJECT_TOO_LONG",
            f"Commit subject is {len(subject)} characters; the limit is {SUBJECT_MAX_LENGTH}.",
            "Shorten the first line to 72 characters or less.",
        )

    if subject.endswith("."):
        add(
            "E_SUBJECT_TRAILING_PERIOD",
            "Commit subject must not end with a period.",
            "Remove the trailing period from the subject line.",
        )

    candidate_indexes = _semver_candidate_indexes(lines)
    exact_indexes = _semver_line_indexes(lines)
    if len(exact_indexes) != 1:
        if not candidate_indexes:
            add(
                "E_MISSING_SEMVER_IMPACT",
                "Commit message is missing the required Semver Impact line.",
                "Add exactly one final line: `Semver Impact: MAJOR|MINOR|PATCH|NONE`.",
            )
        elif len(candidate_indexes) == 1:
            add(
                "E_INVALID_SEMVER_IMPACT",
                "Commit message has a malformed Semver Impact line.",
                "Use exactly `Semver Impact: MAJOR`, `MINOR`, `PATCH`, or `NONE` as the final non-empty line.",
            )
        else:
            add(
                "E_MULTIPLE_SEMVER_IMPACT",
                "Commit message has more than one Semver Impact line.",
                "Keep exactly one final `Semver Impact: MAJOR|MINOR|PATCH|NONE` line.",
            )
        return

    semver_index = exact_indexes[0]
    if semver_index != _last_nonblank_line_index(lines):
        add(
            "E_SEMVER_IMPACT_NOT_TRAILING",
            "Semver Impact must be the final non-empty line.",
            "Move the `Semver Impact: MAJOR|MINOR|PATCH|NONE` line to the end of the commit message.",
        )


def _first_nonblank_line(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _last_nonblank_line_index(lines: list[str]) -> int | None:
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip():
            return index
    return None


def _semver_candidate_indexes(lines: list[str]) -> tuple[int, ...]:
    return tuple(index for index, line in enumerate(lines) if SEMVER_IMPACT_CANDIDATE_PATTERN.match(line.strip()))


def _semver_line_indexes(lines: list[str]) -> tuple[int, ...]:
    return tuple(index for index, line in enumerate(lines) if SEMVER_IMPACT_PATTERN.match(line.strip()))


def _policy_exception(
    lines: list[str],
    *,
    subject: str | None,
    parent_count: int,
    tags: tuple[str, ...],
) -> str | None:
    for line in lines:
        stripped = line.strip()
        if POLICY_EXCEPTION_PATTERN.match(stripped) is None:
            continue
        match stripped:
            case "Policy Exception: merge":
                return "merge"
            case "Policy Exception: revert":
                return "revert"
            case "Policy Exception: version-tag":
                return "version-tag"
            case "Policy Exception: vendored-import":
                return "vendored-import"

    if parent_count > 1 and subject is not None and subject.startswith("Merge "):
        return "merge"
    if subject is not None and subject.startswith("Revert ") and any(
        "This reverts commit" in line for line in lines
    ):
        return "revert"
    if any(SEMVER_TAG_PATTERN.fullmatch(tag) for tag in tags):
        return "version-tag"
    return None


def _unknown_policy_exception_lines(lines: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Policy Exception:") and POLICY_EXCEPTION_PATTERN.match(stripped) is None:
            result.append(stripped)
    return tuple(result)


def _has_release_automation_marker(lines: list[str]) -> bool:
    return any(RELEASE_AUTOMATION_PATTERN.match(line.strip()) is not None for line in lines)


def _version_changed(diff_text: str) -> bool:
    for line in diff_text.splitlines():
        if not line or line.startswith("+++") or line.startswith("---"):
            continue
        if not (line.startswith("+") or line.startswith("-")):
            continue
        if any(pattern.match(line) is not None for pattern in VERSION_LINE_PATTERNS):
            return True
    return False


def _changelog_changed(paths: list[str]) -> bool:
    for path in paths:
        if Path(path).name in CHANGELOG_NAMES:
            return True
    return False


def _has_semver_tag(tags: list[str]) -> bool:
    return any(SEMVER_TAG_PATTERN.fullmatch(tag.strip()) is not None for tag in tags)


def _run_git(cwd: Path, args: tuple[str, ...]) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"git exited with {completed.returncode}"
        raise ValueError(detail)
    return completed.stdout


__all__ = [
    "CommitDiffContext",
    "CommitPolicyFinding",
    "CommitPolicyReport",
    "CommitPolicyResult",
    "clean_commit_message",
    "commit_diff_context",
    "commit_message",
    "commit_parent_count",
    "commit_tags",
    "commits_in_range",
    "ensure_semver_impact_line",
    "git_hooks_path",
    "git_root",
    "staged_diff_context",
    "verify_commit_message",
]
