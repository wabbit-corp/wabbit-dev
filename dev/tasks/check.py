from __future__ import annotations

import inspect
import json
import re
import string
import sys
from argparse import SUPPRESS, ArgumentDefaultsHelpFormatter, ArgumentParser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import pathspec

from dev.base import Module
from dev.checks.base import (
    Check,
    CheckFailedWithReportedIssues,
    DirectoryCheck,
    FileCheck,
    FileContext,
    Issue,
    IssueList,
    IssueType,
    ProjectCheck,
    RepoCheck,
    RootCheck,
    ScopedFindingIgnoreRule,
    ScopedReadSuppressions,
    Severity,
    known_issue_types,
)
from dev.checks.root_paths import E_GITIGNORE_WITHOUT_REPO
from dev.config import Config, Project, find_workspace_root, load_config
from dev.discoverability import did_you_mean_suffix, unknown_name_message
from dev.ignore_files import IgnoreMatcher, read_checkignore_issue_directives
from dev.messages import accent, command_text, error, heading, info, style, warning
from dev.project_layout import build_check_ignore_matcher
from dev.repo_resolution import configured_repo_targets, inferred_project_targets, resolve_check_paths

_ISSUE_ID_RE = re.compile(r"\b(E_[A-Z0-9_]+)\b")
_QUOTED_MESSAGE_PLACEHOLDER_RE = re.compile(r"(['\"])\{(?P<field>[a-zA-Z_][a-zA-Z0-9_]*)(?P<spec>:[^}]*)?\}\1")
_MISSING_README_IDS = {
    "E_MISSING_README",
    "E_README_NO_BANNER",
    "E_README_NO_BADGES",
    "E_README_NO_INSTALL",
    "E_README_NO_USAGE",
    "E_README_NO_LICENSE",
    "E_README_NO_CONTRIBUTING",
}
_METADATA_ISSUE_TOKENS = (
    "CODEOWNERS",
    "EDITORCONFIG",
    "ISSUE_TEMPLATE",
    "PULL_REQUEST_TEMPLATE",
    "SECURITY_POLICY",
    "PUBLICATION_METADATA",
)
_LICENSING_ISSUE_TOKENS = ("SPDX", "LICENSE", "CLA", "LEGAL")
_SECURITY_ISSUE_TOKENS = ("SECRET", "ENTROPY", "HARDCODED")
_CHECK_BUNDLE_SUMMARIES = {
    "default": "Full loaded check suite.",
    "docs": "README, docs layout, and docs-surface checks.",
    "repo": "Repository root, generated-file, and layout checks.",
    "metadata": "Repository, publication, and project metadata drift checks.",
    "security": "Deterministic secret and hardcoded-value checks.",
    "licensing": "SPDX, license, CLA, and legal-layout checks.",
    "kmp": "Kotlin Multiplatform target, source-set, and layout checks.",
    "gradle": "Gradle-specific source, manifest, and publication checks.",
    "python": "Python package, include-path, and QA-related checks.",
}


def _check_cli_id(name: str) -> str:
    base = name.removesuffix("Check")
    collapsed = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", base)
    collapsed = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", collapsed)
    return collapsed.replace("_", "-").lower()


def _bundle_names() -> tuple[str, ...]:
    return tuple(_CHECK_BUNDLE_SUMMARIES)


def _check_module_name(check: Check) -> str:
    module = inspect.getmodule(check.__class__)
    if module is None:
        return ""
    return module.__name__.rpartition(".")[2]


def _bundles_for_check(check: Check, issue_types: Sequence[IssueType]) -> tuple[str, ...]:
    entry_id = _check_cli_id(check.__class__.__name__)
    issue_ids = {issue_type.id for issue_type in issue_types}
    module_name = _check_module_name(check)
    bundles: list[str] = ["default"]

    if _check_kind(check) in {"root", "repo"}:
        bundles.append("repo")

    if (
        entry_id.startswith("docs-")
        or entry_id.startswith("readme-")
        or any(issue_id.startswith("E_DOCS_") for issue_id in issue_ids)
        or any(issue_id in _MISSING_README_IDS for issue_id in issue_ids)
        or module_name in {"project_files"}
    ):
        bundles.append("docs")

    if entry_id.startswith("kmp-") or any(issue_id.startswith("E_KMP_") for issue_id in issue_ids):
        bundles.extend(["kmp", "gradle"])

    if entry_id.startswith("gradle-") or any(issue_id.startswith("E_GRADLE_") for issue_id in issue_ids):
        bundles.append("gradle")

    if (
        entry_id.startswith("python-")
        or any(issue_id.startswith("E_PYTHON_") or issue_id.startswith("E_PYQA_") for issue_id in issue_ids)
    ):
        bundles.append("python")

    if (
        "spdx" in entry_id
        or "license" in entry_id
        or "legal" in entry_id
        or any(any(token in issue_id for token in _LICENSING_ISSUE_TOKENS) for issue_id in issue_ids)
    ):
        bundles.append("licensing")

    if (
        "entropy" in entry_id
        or "secret" in entry_id
        or "hardcoded" in entry_id
        or any(any(token in issue_id for token in _SECURITY_ISSUE_TOKENS) for issue_id in issue_ids)
    ):
        bundles.append("security")

    if (
        "metadata" in entry_id
        or module_name in {"repo_properties"}
        or any(any(token in issue_id for token in _METADATA_ISSUE_TOKENS) for issue_id in issue_ids)
    ):
        bundles.extend(["metadata", "repo"])

    seen: set[str] = set()
    ordered: list[str] = []
    for bundle in bundles:
        if bundle in seen:
            continue
        seen.add(bundle)
        ordered.append(bundle)
    return tuple(ordered)


@dataclass(frozen=True)
class CheckCatalogEntry:
    id: str
    name: str
    kind: str
    summary: str
    fixable: str
    issue_types: tuple[IssueType, ...]
    bundles: tuple[str, ...]
    legacy_names: tuple[str, ...]
    config_commands: tuple[str, ...]


@dataclass(frozen=True)
class ScopedIssueIgnore:
    issue_id: str
    base_dir: Path
    spec: pathspec.PathSpec
    value: str | None = None
    field_name: str | None = None
    field_value: str | None = None
    field_regex: re.Pattern[str] | None = None

    def matches_path(self, path: Path, issue_id: str) -> bool:
        if self.issue_id != "*" and self.issue_id != issue_id:
            return False
        try:
            relative_path = path.resolve().relative_to(self.base_dir.resolve()).as_posix()
        except ValueError:
            return False
        return self.spec.match_file(relative_path)

    def matches_issue(self, issue: Issue, message: str) -> bool:
        if issue.location is None or not self.matches_path(issue.location.path, issue.issue_type.id):
            return False
        if self.field_name is not None:
            if issue.data is None:
                return False
            field_value = issue.data.get(self.field_name)
            if not isinstance(field_value, str):
                return False
            if self.field_value is not None:
                return field_value == self.field_value
            if self.field_regex is None:
                return False
            return self.field_regex.search(field_value) is not None
        if self.value is not None:
            return self.value in message
        return True


def _load_optional_config(start: str | Path = ".") -> Config | None:
    if find_workspace_root(Path(start)) is None:
        return None
    return load_config(Path(start))


def _load_check_modules(config: Config | None) -> dict[str, Module]:
    if config is not None:
        return config.modules

    try:
        return Module.load_modules()
    except Exception as ex:
        warning(f"Failed to auto-load checks without config: {ex}")
        return {}


def _load_all_checks(config: Config | None) -> dict[str, Check]:
    modules = _load_check_modules(config)
    return {check_name: check for check_name, check in modules.items() if isinstance(check, Check)}


def _check_kind(check: Check) -> str:
    if isinstance(check, RootCheck):
        return "root"
    if isinstance(check, RepoCheck):
        return "repo"
    if isinstance(check, ProjectCheck):
        return "project"
    if isinstance(check, DirectoryCheck):
        return "directory"
    if isinstance(check, FileCheck):
        return "file"
    return "check"


def _normalize_summary(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    cleaned = re.sub(r"\s*\(\{[^}]+\}\)", "", cleaned)
    cleaned = re.sub(r"\{[^}]+\}", "value", cleaned)
    cleaned = cleaned.replace("'value'", "value").replace('"value"', "value")
    cleaned = cleaned.strip(" -*")
    return cleaned.rstrip(".") + "." if cleaned else ""


def _humanize_check_name(name: str) -> str:
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", name.removesuffix("Check")).strip().lower()
    if not words:
        return name
    return f"Check {words}."


def _issue_types_for_check(check: Check) -> tuple[IssueType, ...]:
    module = inspect.getmodule(check.__class__)
    if module is None:
        return ()

    issue_types_by_name = {name: value for name, value in vars(module).items() if isinstance(value, IssueType)}
    if not issue_types_by_name:
        return ()

    try:
        source = inspect.getsource(check.__class__)
    except OSError:
        source = ""

    ordered_ids: list[str] = []
    seen: set[str] = set()
    for issue_id in _ISSUE_ID_RE.findall(source):
        for value in issue_types_by_name.values():
            if value.id != issue_id or value.id in seen:
                continue
            ordered_ids.append(value.id)
            seen.add(value.id)

    if ordered_ids:
        ordered: list[IssueType] = []
        for issue_id in ordered_ids:
            for value in issue_types_by_name.values():
                if value.id == issue_id:
                    ordered.append(value)
                    break
        return tuple(ordered)

    if len(issue_types_by_name) == 1:
        return tuple(issue_types_by_name.values())

    return ()


def _config_commands_for_check(check: Check) -> tuple[str, ...]:
    try:
        registrations = check.register_typed_config_commands()
    except Exception:
        return ()

    tags = [
        tag
        for registration in registrations
        if (tag := getattr(registration.command_type, "__mu_tag__", None)) is not None
    ]
    return tuple(tags)


def _check_fixable(check: Check) -> str:
    try:
        source = inspect.getsource(check.__class__)
    except OSError:
        return "unknown"

    if "fix=" in source or ".fixable(" in source:
        return "yes"
    return "no"


def _check_summary(check: Check, issue_types: Sequence[IssueType]) -> str:
    raw_doc = check.__class__.__doc__
    if raw_doc:
        doc = inspect.cleandoc(raw_doc)
        first_paragraph = doc.split("\n\n", 1)[0].replace("\n", " ")
        if ":" in first_paragraph:
            head, tail = first_paragraph.split(":", 1)
            if "- " in tail:
                return _normalize_summary(head)
        sentence_match = re.search(r"(.+?[.?!])(?:\s|$)", first_paragraph)
        if sentence_match is not None:
            return _normalize_summary(sentence_match.group(1))
        return _normalize_summary(first_paragraph)
    if issue_types:
        return _normalize_summary(issue_types[0].message)
    return _humanize_check_name(check.__class__.__name__)


def _catalog_entry(check: Check) -> CheckCatalogEntry:
    issue_types = _issue_types_for_check(check)
    return CheckCatalogEntry(
        id=_check_cli_id(check.__class__.__name__),
        name=check.__class__.__name__,
        kind=_check_kind(check),
        summary=_check_summary(check, issue_types),
        fixable=_check_fixable(check),
        issue_types=issue_types,
        bundles=_bundles_for_check(check, issue_types),
        legacy_names=(check.__class__.__name__,),
        config_commands=_config_commands_for_check(check),
    )


def _catalog(config: Config | None = None) -> dict[str, CheckCatalogEntry]:
    checks = _load_all_checks(config)
    return {name: _catalog_entry(check) for name, check in checks.items()}


def load_check_catalog(config: Config | None = None) -> dict[str, CheckCatalogEntry]:
    return _catalog(config)


def list_check_names(config: Config | None = None) -> list[str]:
    return sorted(load_check_catalog(config))


def list_check_selectors(config: Config | None = None) -> list[str]:
    catalog = load_check_catalog(config)
    return sorted(entry.id for entry in catalog.values())


def list_check_bundle_names() -> list[str]:
    return list(_bundle_names())


def _config_target_choices(config: Config | None) -> list[str]:
    if config is None:
        return []
    return list(dict.fromkeys([*config.defined_projects.keys(), *config.defined_repos.keys()]))


def _issue_type_payload(issue_type: IssueType) -> dict[str, str]:
    return {
        "id": issue_type.id,
        "message": issue_type.message,
        "severity": issue_type.severity.value,
    }


def _check_catalog_payload(entry: CheckCatalogEntry) -> dict[str, object]:
    return {
        "id": entry.id,
        "name": entry.name,
        "kind": entry.kind,
        "summary": entry.summary,
        "fixable": entry.fixable,
        "bundles": list(entry.bundles),
        "legacyNames": list(entry.legacy_names),
        "configCommands": list(entry.config_commands),
        "issueTypes": [_issue_type_payload(issue_type) for issue_type in entry.issue_types],
    }


def _kind_color(kind: str) -> str:
    return {
        "root": "magenta",
        "repo": "blue",
        "project": "cyan",
        "directory": "yellow",
        "file": "green",
    }.get(kind, "white")


def _severity_color(severity: Severity) -> str:
    if severity == Severity.INFO:
        return "blue"
    if severity == Severity.WARNING:
        return "yellow"
    if severity == Severity.CRITICAL:
        return "magenta"
    return "red"


def _severity_reporter(severity: Severity) -> Callable[[str], None]:
    if severity == Severity.INFO:
        return info
    if severity == Severity.WARNING:
        return warning
    return error


def _selector_lookup(catalog: dict[str, CheckCatalogEntry]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for entry in catalog.values():
        lookup[entry.id] = entry.name
        for legacy_name in entry.legacy_names:
            lookup[legacy_name] = entry.name
    return lookup


def _resolve_check_names(catalog: dict[str, CheckCatalogEntry], selectors: Sequence[str]) -> tuple[str, ...]:
    lookup = _selector_lookup(catalog)
    resolved: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        resolved_name = lookup.get(selector)
        if resolved_name is None:
            raise ValueError(unknown_name_message("check", selector, lookup))
        if resolved_name in seen:
            continue
        seen.add(resolved_name)
        resolved.append(resolved_name)
    return tuple(resolved)


def _validate_bundle_names(bundle_names: Sequence[str]) -> tuple[str, ...]:
    known = set(_bundle_names())
    selected: list[str] = []
    seen: set[str] = set()
    for bundle_name in bundle_names:
        if bundle_name not in known:
            expected = ", ".join(sorted(known))
            raise ValueError(f"Unknown check bundle: {bundle_name}. Expected one of: {expected}.")
        if bundle_name in seen:
            continue
        seen.add(bundle_name)
        selected.append(bundle_name)
    return tuple(selected)


def _select_check_names(
    catalog: dict[str, CheckCatalogEntry],
    *,
    only_selectors: Sequence[str],
    bundle_names: Sequence[str],
) -> tuple[str, ...] | None:
    selected_by_bundle: set[str] | None = None
    normalized_bundles = _validate_bundle_names(bundle_names)
    if normalized_bundles:
        selected_by_bundle = {
            entry.name
            for entry in catalog.values()
            if any(bundle_name in entry.bundles for bundle_name in normalized_bundles)
        }

    selected_by_name: set[str] | None = None
    if only_selectors:
        selected_by_name = set(_resolve_check_names(catalog, only_selectors))

    match (selected_by_bundle, selected_by_name):
        case (None, None):
            return None
        case (set() as selected, None):
            return tuple(sorted(selected))
        case (None, set() as selected):
            return tuple(sorted(selected))
        case (set() as bundle_selected, set() as name_selected):
            return tuple(sorted(bundle_selected & name_selected))


def list_checks(*, json_output: bool = False) -> int:
    catalog = _catalog(_load_optional_config())
    if not catalog:
        warning("No checks were loaded.")
        return 1

    entries = sorted(catalog.values(), key=lambda entry: (entry.kind, entry.name))
    if json_output:
        print(
            json.dumps(
                {
                    "bundles": [
                        {"id": bundle_name, "summary": _CHECK_BUNDLE_SUMMARIES[bundle_name]}
                        for bundle_name in _bundle_names()
                    ],
                    "checks": [_check_catalog_payload(entry) for entry in entries],
                },
                indent=2,
            )
        )
        return 0

    print(heading("Available bundles:"))
    for bundle_name in _bundle_names():
        print(f"  {accent(bundle_name)}  {_CHECK_BUNDLE_SUMMARIES[bundle_name]}")
    print()
    print(heading(f"Available checks ({len(entries)}):"))
    for entry in entries:
        fix_color = "green" if entry.fixable == "yes" else "yellow" if entry.fixable == "unknown" else "white"
        print(
            f"  {accent(entry.id)}  "
            f"[{style(entry.kind, _kind_color(entry.kind), attrs=('bold',))}]  "
            f"fix:{style(entry.fixable, fix_color, attrs=('bold',) if entry.fixable == 'yes' else ())}  "
            f"bundles:{','.join(entry.bundles)}  "
            f"{entry.summary}"
        )
        print(f"    legacy: {entry.name}")
    print()
    print(f"Run `{command_text('check show <check-id>')}` for issue IDs, config knobs, and suppression examples.")
    return 0


def show_check(check_selector: str, *, json_output: bool = False) -> int:
    catalog = _catalog(_load_optional_config())
    resolved_names = _resolve_check_names(catalog, [check_selector])
    entry = catalog[resolved_names[0]]

    issue_id = entry.issue_types[0].id if entry.issue_types else "E_SOME_ISSUE"
    payload = {
        "check": {
            **_check_catalog_payload(entry),
            "suppressionExamples": {
                "rootCljDisable": f'(checks/disable "{issue_id}" "**/*")',
                "rootCljIgnoreFinding": f'(checks/ignore-finding "{issue_id}" "**/*" "needle")',
                "inlineIgnore": f"# check:ignore {issue_id}" if entry.kind == "file" else None,
                "inlineIgnoreValue": f"# check:ignore {issue_id} value=needle" if entry.kind == "file" else None,
            },
        }
    }
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"{heading('Check')}: {accent(entry.id)}")
    print(f"{heading('Legacy name')}: {entry.name}")
    print(f"{heading('Kind')}: {style(entry.kind, _kind_color(entry.kind), attrs=('bold',))}")
    print(f"{heading('Bundles')}: {', '.join(entry.bundles)}")
    print(f"{heading('Summary')}: {entry.summary}")
    fix_color = "green" if entry.fixable == "yes" else "yellow" if entry.fixable == "unknown" else "white"
    print(
        f"{heading('Auto-fix support')}: "
        f"{style(entry.fixable, fix_color, attrs=('bold',) if entry.fixable == 'yes' else ())}"
    )
    if entry.config_commands:
        print(heading("Config commands:"))
        for command in entry.config_commands:
            print(f"  - {command_text(command)}")
    else:
        print(f"{heading('Config commands')}: none")

    if entry.issue_types:
        print(heading("Issue types:"))
        for issue_type in entry.issue_types:
            print(
                f"  - {style(issue_type.id, _severity_color(issue_type.severity), attrs=('bold',))}: "
                f"{issue_type.message}"
            )
    else:
        print(f"{heading('Issue types')}: not detected automatically")

    disable_example = f'(checks/disable "{issue_id}" "**/*")'
    ignore_example = f'(checks/ignore-finding "{issue_id}" "**/*" "needle")'
    print(heading("Suppression examples:"))
    print(f"  - root.clj disable: {command_text(disable_example)}")
    print("  - root.clj ignore finding text: " + command_text(ignore_example))
    if entry.kind == "file":
        print("  - inline ignore (content-based checks only): " + command_text(f"# check:ignore {issue_id}"))
        print("  - inline ignore specific value: " + command_text(f"# check:ignore {issue_id} value=needle"))
    return 0


def describe_check(check_name: str, *, json_output: bool = False) -> int:
    return show_check(check_name, json_output=json_output)


def secrets_scan(
    project_or_dir_or_file: str | None = None,
    fix: bool = False,
) -> int:
    return check_main(project_or_dir_or_file, ["high-entropy-string"], fix)


def check_main(
    project_or_dir_or_file: str | None,
    enabled_checks: list[str] | None = None,
    fix: bool = False,
    *,
    bundles: Sequence[str] = (),
) -> int:
    """
    Main function to run checks on the project.
    """

    lookup_target = project_or_dir_or_file or "."
    config = _load_optional_config(lookup_target)
    if config is None:
        warning("No config file found. Some checks may not have sufficient context to run.")

    effective_target = lookup_target
    if project_or_dir_or_file is None and config is not None:
        inferred_targets = inferred_project_targets(config)
        if inferred_targets is not None:
            effective_target = inferred_targets[0]

    config_root = (
        config.workspace_root if config is not None and config.workspace_root is not None else Path.cwd().resolve()
    )

    projects_by_path: dict[Path, Project] = {}
    if config is not None:
        for project in config.defined_projects.values():
            projects_by_path[project.path.resolve()] = project

    root_paths = [path.resolve() for path in resolve_check_paths(effective_target, config=config)]

    for path in root_paths:
        if not path.exists():
            suggestion = did_you_mean_suffix(effective_target, _config_target_choices(config))
            raise ValueError(f"Path does not exist: {path}.{suggestion}")

    all_checks = _load_all_checks(config)
    catalog = _catalog(config)
    selected_check_names = _select_check_names(
        catalog,
        only_selectors=enabled_checks or (),
        bundle_names=bundles,
    )
    if selected_check_names is not None:
        if not selected_check_names:
            raise ValueError("No loaded checks matched the selected bundles or check selectors.")
        all_checks = {name: check for name, check in all_checks.items() if name in set(selected_check_names)}

    TCheck = TypeVar("TCheck", bound=Check)

    def sort_checks_typed(checks: Sequence[TCheck]) -> list[TCheck]:
        return sorted(
            checks,
            key=lambda c: (getattr(c, "order", 1000), c.__class__.__name__),
        )

    root_checks: list[RootCheck] = sort_checks_typed([v for v in all_checks.values() if isinstance(v, RootCheck)])
    repo_checks: list[RepoCheck] = sort_checks_typed([v for v in all_checks.values() if isinstance(v, RepoCheck)])
    project_checks: list[ProjectCheck] = sort_checks_typed(
        [v for v in all_checks.values() if isinstance(v, ProjectCheck)]
    )
    file_checks: list[FileCheck] = sort_checks_typed([v for v in all_checks.values() if isinstance(v, FileCheck)])
    dir_checks: list[DirectoryCheck] = sort_checks_typed(
        [v for v in all_checks.values() if isinstance(v, DirectoryCheck)]
    )
    needs_recursive_walk = bool(file_checks or dir_checks)

    disabled_checks: dict[str, pathspec.PathSpec] = {}
    ignored_findings: list[ScopedIssueIgnore] = []
    known_types = known_issue_types()
    if config is not None:
        patterns_by_error_name: dict[str, list[str]] = {}
        for error_name, pattern in config.disabled_checks:
            assert isinstance(error_name, str), f"Expected string, got {type(error_name)}"
            assert isinstance(pattern, str), f"Expected string, got {type(pattern)}"
            assert (
                error_name in known_types or error_name == "*"
            ), f"Unknown error type in disabled_checks: {repr(error_name)}"

            if error_name == "*":
                for known_error in known_types:
                    if known_error not in patterns_by_error_name:
                        patterns_by_error_name[known_error] = []
                    patterns_by_error_name[known_error].append(pattern)
            else:
                if error_name not in patterns_by_error_name:
                    patterns_by_error_name[error_name] = []
                patterns_by_error_name[error_name].append(pattern)

        for error_name, patterns in patterns_by_error_name.items():
            disabled_checks[error_name] = pathspec.PathSpec.from_lines(
                pathspec.patterns.gitwildmatch.GitWildMatchPattern, patterns
            )

        for error_name, pattern, value in config.ignored_findings:
            assert isinstance(error_name, str), f"Expected string, got {type(error_name)}"
            assert isinstance(pattern, str), f"Expected string, got {type(pattern)}"
            assert isinstance(value, str), f"Expected string, got {type(value)}"
            assert (
                error_name in known_types or error_name == "*"
            ), f"Unknown error type in ignored_findings: {repr(error_name)}"
            ignored_findings.append(
                ScopedIssueIgnore(
                    issue_id=error_name,
                    base_dir=config_root,
                    spec=pathspec.PathSpec.from_lines(
                        pathspec.patterns.gitwildmatch.GitWildMatchPattern,
                        [pattern],
                    ),
                    value=value,
                )
            )

    checkignore_paths: set[Path] = set()
    for root_path in root_paths:
        if root_path.is_file():
            current = root_path.parent
        else:
            current = root_path
        while True:
            checkignore_path = current / ".checkignore"
            if checkignore_path.is_file():
                checkignore_paths.add(checkignore_path.resolve())
            if current.parent == current:
                break
            current = current.parent
        if root_path.is_dir():
            for checkignore_path in root_path.rglob(".checkignore"):
                checkignore_paths.add(checkignore_path.resolve())

    for checkignore_path in sorted(checkignore_paths):
        for directive in read_checkignore_issue_directives(checkignore_path):
            assert (
                directive.issue_id in known_types or directive.issue_id == "*"
            ), f"Unknown error type in .checkignore: {directive.issue_id!r} ({checkignore_path})"
            compiled_field_regex: re.Pattern[str] | None = None
            if directive.matcher is not None and directive.matcher.field_regex is not None:
                try:
                    compiled_field_regex = re.compile(directive.matcher.field_regex)
                except re.error as ex:
                    raise ValueError(
                        f"Invalid .checkignore regex {directive.matcher.field_regex!r} in {checkignore_path}: {ex}"
                    ) from ex
            ignored_findings.append(
                ScopedIssueIgnore(
                    issue_id=directive.issue_id,
                    base_dir=checkignore_path.parent,
                    spec=pathspec.PathSpec.from_lines(
                        pathspec.patterns.gitwildmatch.GitWildMatchPattern,
                        [directive.pathspec],
                    ),
                    value=directive.matcher.value if directive.matcher is not None else None,
                    field_name=directive.matcher.field_name if directive.matcher is not None else None,
                    field_value=directive.matcher.field_value if directive.matcher is not None else None,
                    field_regex=compiled_field_regex,
                )
            )

    # print(f"Disabled checks: {disabled_checks}")

    def _format_issue_field_value(value: object) -> str:
        if isinstance(value, Path):
            value = value.as_posix()
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    def issue_message(issue: Issue, report_format_error: bool = False) -> str:
        try:
            data = dict(issue.data or {})
            template = _QUOTED_MESSAGE_PLACEHOLDER_RE.sub(
                lambda match: "{" + match.group("field") + (match.group("spec") or "") + "}",
                issue.issue_type.message,
            )

            formatter = string.Formatter()
            parts: list[str] = []
            for literal_text, field_name, format_spec, conversion in formatter.parse(template):
                parts.append(literal_text)
                if field_name is None:
                    continue
                if field_name not in data:
                    raise KeyError(field_name)
                value = data[field_name]
                if conversion == "r":
                    value = repr(value)
                elif conversion == "s":
                    value = str(value)
                elif conversion == "a":
                    value = ascii(value)

                if format_spec:
                    rendered_value = format(value, format_spec)
                else:
                    rendered_value = _format_issue_field_value(value)
                parts.append(f"{field_name}:{rendered_value}")
            return "".join(parts)
        except Exception as e:
            if report_format_error:
                error(f"Error formatting issue message: {e} with type: {issue.issue_type} and data: {issue.data}")
            return issue.issue_type.message

    def issue_relative_path(path: Path) -> str:
        abs_path = path.absolute()
        try:
            rel_path = abs_path.relative_to(config_root)
        except ValueError:
            rel_path = abs_path
        return str(rel_path)

    def is_check_disabled(issue: Issue) -> bool:
        if issue.location is not None and issue.issue_type.id in disabled_checks:
            spec = disabled_checks[issue.issue_type.id]
            result = spec.match_file(issue_relative_path(issue.location.path))
            if result:
                return True

        if issue.location is not None and ignored_findings:
            message = issue_message(issue, report_format_error=False)
            for rule in ignored_findings:
                if rule.matches_issue(issue, message):
                    return True

        return False

    def scoped_read_suppressions_for(path: Path) -> ScopedReadSuppressions | None:
        if not ignored_findings:
            return None
        scoped_rules: list[ScopedFindingIgnoreRule] = []
        for rule in ignored_findings:
            if rule.value is None or rule.field_name is not None:
                continue
            if not rule.matches_path(path, rule.issue_id):
                continue
            scoped_rules.append(
                ScopedFindingIgnoreRule(
                    issue_id=rule.issue_id,
                    value=rule.value,
                )
            )
        if not scoped_rules:
            return None
        return ScopedReadSuppressions(config_ignores=tuple(scoped_rules))

    has_errors = False

    def _is_error_issue(issue: Issue) -> bool:
        return issue.issue_type.severity not in (Severity.INFO, Severity.WARNING)

    def report(issue: Issue) -> None:
        if is_check_disabled(issue):
            return

        parts: list[str] = []
        parts.append(style(f"[{issue.issue_type.id}]", _severity_color(issue.issue_type.severity), attrs=("bold",)))
        if issue.fix:
            parts.append(style("(fixable)", "green", attrs=("bold",)))

        if issue.location is not None:
            location = accent(issue.location.path, "cyan")
            if issue.location.lines:
                lines = ",".join(
                    f"{line[0]}-{line[1]}" if line[0] != line[1] else str(line[0])
                    for line in issue.location.lines.ranges
                )
                location += style(f":{lines}", "magenta")
            parts.append(location)
        else:
            parts.append(style("workspace", "cyan", attrs=("bold",)))

        parts.append(style(">", "blue"))
        parts.append(issue_message(issue, report_format_error=True))

        # data_str = (
        #     ", ".join(f"{k}={v}" for k, v in issue.data.items() if v is not None)
        #     if issue.data
        #     else ""
        # )
        # if data_str:
        #     msg += f" ({data_str})"

        _severity_reporter(issue.issue_type.severity)(" ".join(parts))

    def handle_issue(issue: Issue | IssueList | list[Issue]) -> None:
        nonlocal has_errors
        if isinstance(issue, IssueList) or isinstance(issue, list):
            for i in issue:
                handle_issue(i)
            return

        if is_check_disabled(issue):
            return

        report(issue)

        was_fixed = False
        if issue.fix and fix:
            info("Fixing")
            issue.fix()
            was_fixed = True

        if _is_error_issue(issue) and not was_fixed:
            has_errors = True

    @dataclass(frozen=True)
    class RepoContext:
        root: Path
        matcher: IgnoreMatcher

    def repo_ignores_path(path: Path, repo: RepoContext) -> bool:
        return repo.matcher.matches(path, is_dir=path.is_dir())

    def configured_projects_for_repo_root(repo_root: Path) -> list[Project]:
        resolved_root = repo_root.resolve()
        return sorted(
            [
                candidate
                for candidate in projects_by_path.values()
                if candidate.effective_repo_root.resolve() == resolved_root
            ],
            key=lambda candidate: candidate.path.as_posix(),
        )

    def find_repo_root(path: Path) -> Path | None:
        current = path.absolute()
        if current.is_file():
            current = current.parent
        while True:
            if (current / ".git").exists():
                return current
            if current.parent == current:
                return None
            current = current.parent

    seen_repo_roots: set[Path] = set()
    seen_project_paths: set[Path] = set()

    def is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def maybe_run_repo_checks(repo_root: Path, project: Project | None) -> None:
        resolved = repo_root.resolve()
        if resolved in seen_repo_roots:
            return
        for check in repo_checks:
            issues = check.check(repo_root, project=project)
            handle_issue(issues)
        seen_repo_roots.add(resolved)

    configured_repo_paths: list[Path] = []
    if config is not None:
        configured_repo_paths = sorted(
            {resolved_target.path.resolve() for resolved_target in configured_repo_targets(config)},
            key=lambda path: (len(path.parts), path.as_posix()),
        )

    def selected_projects_for_root(root_path: Path) -> list[Project]:
        if config is None or not root_path.is_dir():
            return []
        resolved_root = root_path.resolve()
        return sorted(
            [
                project
                for project in config.defined_projects.values()
                if is_within(project.path.resolve(), resolved_root)
            ],
            key=lambda project: (len(project.path.resolve().parts), project.path.as_posix()),
        )

    def selected_configured_repo_roots_for_root(root_path: Path) -> list[Path]:
        if not root_path.is_dir():
            return []
        resolved_root = root_path.resolve()
        return [repo_root for repo_root in configured_repo_paths if is_within(repo_root, resolved_root)]

    def maybe_run_project_checks(project: Project) -> None:
        resolved_project_path = project.path.resolve()
        if resolved_project_path in seen_project_paths:
            return
        for project_check in project_checks:
            issues = project_check.check(project.path, project)
            handle_issue(issues)
        seen_project_paths.add(resolved_project_path)

    def run_without_recursive_walk(path: Path) -> None:
        repo_root = find_repo_root(path)
        if repo_root is not None:
            maybe_run_repo_checks(repo_root, projects_by_path.get(repo_root.resolve()))

        if not path.is_dir():
            return

        for project in selected_projects_for_root(path):
            maybe_run_project_checks(project)

        for repo_root in selected_configured_repo_roots_for_root(path):
            maybe_run_repo_checks(repo_root, projects_by_path.get(repo_root.resolve()))

    # print(f"project_paths: {projects_by_path.keys()}")

    def go(path: Path, project: Project | None = None, repo: RepoContext | None = None) -> None:
        if repo is not None:
            if repo_ignores_path(path, repo):
                # info(f"Skipping {path} due to .gitignore")
                return

        if repo is None:
            repo_root = find_repo_root(path)
            if repo_root is not None:
                repo = RepoContext(
                    root=repo_root,
                    matcher=build_check_ignore_matcher(
                        repo_root,
                        projects=configured_projects_for_repo_root(repo_root),
                    ),
                )
                project_at_root = projects_by_path.get(repo_root.resolve())
                maybe_run_repo_checks(repo_root, project_at_root)

        if path.is_dir():
            # It could be a project
            # print(f"path: {repr(path)} -> {path in projects_by_path}")
            if not project:
                project_at_path = projects_by_path.get(path.resolve())
            else:
                project_at_path = None
            if project_at_path is not None:
                for project_check in project_checks:
                    issues = project_check.check(path, project_at_path)
                    handle_issue(issues)
                project = project_at_path

            # It could be a repo
            if (path / ".git").exists():
                repo = RepoContext(
                    root=path,
                    matcher=build_check_ignore_matcher(
                        path,
                        project=project,
                        projects=configured_projects_for_repo_root(path),
                    ),
                )
                maybe_run_repo_checks(path, project)
            elif (path / ".checkignore").exists() and repo is None:
                repo = RepoContext(
                    root=path,
                    matcher=build_check_ignore_matcher(path, project=project),
                )

            accumulated_issues = IssueList()
            for directory_check in dir_checks:
                ctx = FileContext(
                    path=path,
                    check_name=directory_check.__class__.__name__,
                    project=project,
                    ignore_matcher=repo.matcher if repo is not None else None,
                )
                try:
                    directory_check.check(ctx=ctx)
                except CheckFailedWithReportedIssues:
                    pass  # Issues already reported in context
                accumulated_issues.extend(ctx.issues)
            handle_issue(accumulated_issues)

            for child in path.iterdir():
                if repo is not None:
                    if repo_ignores_path(child, repo):
                        # info(f"Skipping {child} due to .gitignore")
                        continue
                go(child, project=project, repo=repo)

        else:
            file_scope = project.get_coarse_file_scope(path) if project else None
            project_type = project.coarse_project_type if project else None

            accumulated_issues = IssueList()
            scoped_suppressions = scoped_read_suppressions_for(path)
            for file_check in file_checks:
                # print(f"Checking {path} with {check} {ctx}")
                ctx = FileContext(
                    check_name=file_check.__class__.__name__,
                    path=path,
                    project=project,
                    ignore_matcher=repo.matcher if repo is not None else None,
                    project_type=project_type,
                    file_scope=file_scope,
                    scoped_read_suppressions=scoped_suppressions,
                )
                try:
                    file_check.check(ctx=ctx)
                except CheckFailedWithReportedIssues:
                    pass  # Issues already reported in context
                accumulated_issues.extend(ctx.issues)

            for issue in accumulated_issues:
                handle_issue(issue)

    for path in root_paths:
        project_at_root = projects_by_path.get(path.resolve()) if path.is_dir() else None
        for root_check in root_checks:
            issues = root_check.check(path, project_at_root)
            handle_issue(issues)
        if needs_recursive_walk or config is None:
            go(path)
        else:
            run_without_recursive_walk(path)

    return 1 if has_errors else 0


if __name__ == "__main__":
    raw_argv = sys.argv[1:]
    if not raw_argv:
        normalized_argv = ["run"]
    elif raw_argv[0] in {"run", "list", "show", "describe"}:
        normalized_argv = raw_argv
    else:
        normalized_argv = ["run", *raw_argv]

    parser = ArgumentParser(
        description=(
            "Run the loaded repository, project, directory, and file checks "
            "against a path or configured project, or inspect the available checks."
        ),
        epilog=(
            "Examples:\n"
            "  check.py list\n"
            "  check.py show spdx-header\n"
            "  check.py .\n"
            "  check.py :root --fix\n"
            "  check.py app-wabbit-dev/dev/cli.py --checks spdx-header"
        ),
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the configured check suite.")
    run_parser.add_argument(
        "project_or_dir_or_file",
        type=str,
        nargs="?",
        default=".",
        help="Project or directory or file to check.",
    )
    run_parser.add_argument("--checks", nargs="+", default=[], help="List of checks to run.")
    run_parser.add_argument("--bundle", nargs="+", default=[], help="Check bundle IDs to run.")
    run_parser.add_argument("--fix", action="store_true", help="Fix issues found during checks.")

    list_parser = subparsers.add_parser("list", help="List all loaded checks.")
    list_parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")

    show_parser = subparsers.add_parser("show", help="Describe one loaded check.")
    show_parser.add_argument("check", help="Check ID or legacy class name to describe.")
    show_parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    describe_parser = subparsers.add_parser("describe", help=SUPPRESS)
    describe_parser.add_argument("check", help=SUPPRESS)
    describe_parser.add_argument("--json", action="store_true", help=SUPPRESS)

    args = parser.parse_args(normalized_argv)
    try:
        command = args.command or "run"
        if command == "list":
            raise SystemExit(list_checks(json_output=args.json))
        if command in {"show", "describe"}:
            raise SystemExit(show_check(args.check, json_output=args.json))
        raise SystemExit(check_main(args.project_or_dir_or_file, args.checks, args.fix, bundles=args.bundle))
    except ValueError as ex:
        parser.exit(2, f"{parser.prog}: error: {ex}\n")


__all__ = [
    "Module",
    "E_GITIGNORE_WITHOUT_REPO",
    "check_main",
    "describe_check",
    "list_check_bundle_names",
    "load_check_catalog",
    "list_check_names",
    "list_check_selectors",
    "list_checks",
    "secrets_scan",
    "show_check",
]
