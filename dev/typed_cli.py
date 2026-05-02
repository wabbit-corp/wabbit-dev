from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dev.config import Config


def _ensure_wabbit_cli_importable() -> bool:
    workspace_root = Path(__file__).resolve().parents[2]
    project_root = workspace_root / "python-wabbit-cli"
    package_root = project_root / "wabbit_cli"
    if not package_root.is_dir():
        return False
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)
    return True


def _load_workspace_config() -> Config | None:
    from dev.config import find_workspace_root, load_config

    if find_workspace_root() is None:
        return None
    try:
        return load_config()
    except Exception:
        return None


async def maybe_run_typed_cli(argv: Sequence[str], *, prog: str) -> int | None:
    if not _ensure_wabbit_cli_importable():
        return None

    from wabbit_cli import (
        Argument,
        Command,
        CommandAlias,
        CommandCompletion,
        CommandFailure,
        CommandHelp,
        CommandParsed,
        CommandValue,
        CompletionCandidate,
        CompletionContext,
        CompletionSpec,
        CompletionTargetPositionalValue,
        Failure,
        Issue,
        ParsedValues,
        Success,
        Validated,
        ValidationFailed,
        Visibility,
        at_most_one_of,
        fail,
        flag,
        option,
        positional,
        succeed,
    )

    @dataclass(frozen=True)
    class WhereRequest:
        json_output: bool

    @dataclass(frozen=True)
    class ConfigCheckRequest:
        pass

    @dataclass(frozen=True)
    class ConfigCutRequest:
        output_path: str
        targets: list[str]

    @dataclass(frozen=True)
    class InstallAppRequest:
        bin_dir: str | None

    @dataclass(frozen=True)
    class InstallCompletionsRequest:
        shell: str
        update_rc: bool

    @dataclass(frozen=True)
    class InstallToolsRequest:
        tools: list[str]
        force: bool
        json_output: bool

    @dataclass(frozen=True)
    class InstallHooksRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class CompletionBashRequest:
        pass

    @dataclass(frozen=True)
    class CompletionZshRequest:
        pass

    @dataclass(frozen=True)
    class CompletionQueryRequest:
        shell: str
        index: int
        words: list[str]

    @dataclass(frozen=True)
    class DoctorRequest:
        targets: list[str]
        only: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class VerifyDocsRequest:
        targets: list[str]
        semantic: bool
        json_output: bool

    @dataclass(frozen=True)
    class VerifyReleaseRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class VerifySecurityRequest:
        targets: list[str]
        tools: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class DocsCheckRequest:
        targets: list[str]
        semantic: bool
        json_output: bool

    @dataclass(frozen=True)
    class DocsSnippetsRequest:
        targets: list[str]
        verify: bool
        json_output: bool

    @dataclass(frozen=True)
    class ReleaseVerifyRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class ReleaseBundleRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class SecurityScanRequest:
        targets: list[str]
        tools: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class LlmcopyRequest:
        paths: list[str]

    @dataclass(frozen=True)
    class AskRequest:
        provider: str
        conversation_id: str | None
        file_paths: list[str]
        prompt: str
        model: str | None

    @dataclass(frozen=True)
    class SetupRequest:
        targets: list[str]
        dev_mode: bool
        local_mode: bool
        commit_if_setup_only: bool
        json_output: bool

    @dataclass(frozen=True)
    class PublishRequest:
        targets: list[str]
        dry_run: bool

    @dataclass(frozen=True)
    class DuplicatesRequest:
        folders: list[str]
        exclude: list[str]
        include: list[str]
        min_size: int
        no_default_excludes: bool
        zip_contents: bool
        weak_encrypted_zip: bool

    @dataclass(frozen=True)
    class JitpackInfoRequest:
        group: str
        artifact: str
        version: str | None

    @dataclass(frozen=True)
    class DepGraphRequest:
        targets: list[str]
        artifacts: bool

    @dataclass(frozen=True)
    class DepUpdatesRequest:
        pass

    @dataclass(frozen=True)
    class BuildRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class CleanRequest:
        targets: list[str]

    @dataclass(frozen=True)
    class ClocRequest:
        targets: list[str]

    @dataclass(frozen=True)
    class StatusRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class CheckoutRequest:
        targets: list[str]
        dry_run: bool
        json_output: bool

    @dataclass(frozen=True)
    class ServiceStartRequest:
        interval_seconds: int

    @dataclass(frozen=True)
    class ServiceStopRequest:
        pass

    @dataclass(frozen=True)
    class ServiceStatusRequest:
        pass

    @dataclass(frozen=True)
    class ServiceDashboardRequest:
        interval_seconds: int

    @dataclass(frozen=True)
    class CommitRequest:
        targets: list[str]
        dry_run: bool

    @dataclass(frozen=True)
    class CommitVerifyRequest:
        target: str | None
        message_file: str | None
        message: str | None
        revision_range: str | None
        staged: bool
        json_output: bool
        quiet: bool

    @dataclass(frozen=True)
    class PushRequest:
        targets: list[str]
        dry_run: bool

    @dataclass(frozen=True)
    class BackupPushRequest:
        repo_targets: list[str]
        backup_target_name: str | None
        dry_run: bool
        json_output: bool

    @dataclass(frozen=True)
    class BackupRestoreRequest:
        repo_target: str | None
        backup_target_name: str | None
        snapshot: str
        into: str
        dry_run: bool
        json_output: bool

    @dataclass(frozen=True)
    class CheckRunRequest:
        target: str | None
        selectors: list[str]
        bundles: list[str]
        fix: bool
        json_output: bool

    @dataclass(frozen=True)
    class CheckListRequest:
        json_output: bool

    @dataclass(frozen=True)
    class CheckShowRequest:
        check: str
        json_output: bool

    @dataclass(frozen=True)
    class VerifyListRequest:
        json_output: bool

    @dataclass(frozen=True)
    class SpdxHeadersRequest:
        target: str | None
        fix: bool

    @dataclass(frozen=True)
    class SecretsScanRequest:
        target: str | None

    @dataclass(frozen=True)
    class ContributorsAuditRequest:
        pass

    @dataclass(frozen=True)
    class ProjectListRequest:
        pass

    @dataclass(frozen=True)
    class ProjectShowRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class ProjectDepsRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class ProjectRepoRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class ProjectTargetsRequest:
        targets: list[str]
        json_output: bool

    @dataclass(frozen=True)
    class ProjectVersionsRequest:
        targets: list[str]
        json_output: bool

    def _command_paths(command: Command[TypedRequest], prefix: tuple[str, ...] = ()) -> set[str]:
        paths: set[str] = set()
        for child in command.subcommands:
            child_path = (*prefix, child.name)
            paths.add("/".join(child_path))
            paths.update(_command_paths(child, child_path))
        return paths

    def _normalize_argv(raw_argv: Sequence[str], root_command: Command[TypedRequest]) -> list[str]:
        argv_list = list(raw_argv)
        if not argv_list:
            return []

        valid_paths = _command_paths(root_command)
        normalized: list[str] = []
        current_parts: list[str] = []
        index = 0

        while index < len(argv_list):
            token = argv_list[index]

            if token == "help" and index == len(argv_list) - 1:
                current_path = "/".join(current_parts)
                if not current_parts or current_path in valid_paths:
                    normalized.append("--help")
                    return normalized

            if token == "--" or token.startswith("-"):
                normalized.extend(argv_list[index:])
                return normalized

            if "/" in token:
                split_parts = [part for part in token.split("/") if part]
                split_path = "/".join([*current_parts, *split_parts])
                if split_parts and split_path in valid_paths:
                    normalized.extend(split_parts)
                    current_parts.extend(split_parts)
                    index += 1
                    continue

            candidate_path = "/".join([*current_parts, token])
            if candidate_path in valid_paths:
                normalized.append(token)
                current_parts.append(token)
                index += 1
                continue

            normalized.extend(argv_list[index:])
            return normalized

        return normalized

    TypedRequest = (
        WhereRequest
        | ConfigCheckRequest
        | ConfigCutRequest
        | InstallAppRequest
        | InstallCompletionsRequest
        | InstallToolsRequest
        | InstallHooksRequest
        | CompletionBashRequest
        | CompletionZshRequest
        | CompletionQueryRequest
        | DoctorRequest
        | VerifyDocsRequest
        | VerifyReleaseRequest
        | VerifySecurityRequest
        | DocsCheckRequest
        | DocsSnippetsRequest
        | ReleaseVerifyRequest
        | ReleaseBundleRequest
        | SecurityScanRequest
        | LlmcopyRequest
        | AskRequest
        | SetupRequest
        | PublishRequest
        | DuplicatesRequest
        | JitpackInfoRequest
        | DepGraphRequest
        | DepUpdatesRequest
        | BuildRequest
        | CleanRequest
        | ClocRequest
        | StatusRequest
        | CheckoutRequest
        | ServiceStartRequest
        | ServiceStopRequest
        | ServiceStatusRequest
        | ServiceDashboardRequest
        | CommitRequest
        | CommitVerifyRequest
        | PushRequest
        | BackupPushRequest
        | BackupRestoreRequest
        | CheckRunRequest
        | CheckListRequest
        | CheckShowRequest
        | VerifyListRequest
        | SpdxHeadersRequest
        | SecretsScanRequest
        | ContributorsAuditRequest
        | ProjectListRequest
        | ProjectShowRequest
        | ProjectDepsRequest
        | ProjectRepoRequest
        | ProjectTargetsRequest
        | ProjectVersionsRequest
        | None
    )

    def _string_list(value: CommandValue) -> list[str]:
        match value:
            case str() as item:
                return [item]
            case [*items]:
                result: list[str] = []
                for item in items:
                    match item:
                        case str() as text:
                            result.append(text)
                        case _:
                            return []
                return result
            case _:
                return []

    def _bool_value(values: ParsedValues, name: str, default: bool = False) -> bool:
        raw = values.option_or(name, default)
        assert isinstance(raw, bool)
        return raw

    def _int_value(values: ParsedValues, name: str, default: int) -> int:
        raw = values.option_or(name, default)
        assert isinstance(raw, int)
        return raw

    def _option_string_list(values: ParsedValues, name: str) -> list[str]:
        option_values = values.option_values.get(name)
        if option_values is None:
            return []

        result: list[str] = []
        for value in option_values.values:
            match value:
                case str() as item:
                    result.append(item)
                case _:
                    continue
        return result

    def _optional_string(value: CommandValue, meta_var: str) -> Validated[Issue, str | None]:
        match value:
            case None:
                return succeed(None)
            case str() as text:
                return succeed(text)
            case _:
                return fail([ValidationFailed(f"Expected <{meta_var}> to be a string.")])

    def _project_targets_with_defaults(targets: list[str]) -> list[str]:
        if targets:
            return targets
        config = _load_workspace_config()
        if config is None:
            return targets
        from dev.repo_resolution import inferred_project_targets

        inferred_targets = inferred_project_targets(config)
        return list(inferred_targets) if inferred_targets is not None else targets

    def _repo_targets_with_defaults(targets: list[str]) -> list[str]:
        if targets:
            return targets
        config = _load_workspace_config()
        if config is None:
            return targets
        from dev.repo_resolution import inferred_repo_targets

        inferred_targets = inferred_repo_targets(config)
        return list(inferred_targets) if inferred_targets is not None else targets

    def _guidance_target(targets: list[str]) -> str | None:
        for target in targets:
            if target not in {".", ":root"}:
                return target
        return None

    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _configured_names(config: Config | None) -> list[str]:
        if config is None:
            return []
        return _dedupe([*config.defined_projects.keys(), *config.defined_repos.keys()])

    def _path_completion_candidates(current_word: str, *, directories_only: bool = False) -> list[CompletionCandidate]:
        raw_path = Path(current_word) if current_word else Path(".")
        separator_suffix = current_word.endswith("/") or current_word.endswith("\\")
        if separator_suffix:
            parent = raw_path
            name_prefix = ""
            display_parent = current_word.rstrip("/\\")
        else:
            parent = raw_path.parent
            name_prefix = raw_path.name
            display_parent = "" if str(parent) == "." else str(parent)

        try:
            entries = sorted(parent.iterdir())
        except OSError:
            return []

        candidates: list[CompletionCandidate] = []
        for path in entries:
            if directories_only and not path.is_dir():
                continue
            if not path.name.startswith(name_prefix):
                continue
            if display_parent:
                candidates.append(CompletionCandidate(str(Path(display_parent) / path.name)))
            else:
                candidates.append(CompletionCandidate(path.name))
        return candidates

    def _completion_values_for_kind(kind: str, config: Config | None) -> list[str]:
        match kind:
            case "project-target" | "repo-target" | "path-or-target":
                return _configured_names(config)
            case "push-target":
                return _dedupe([".", *_configured_names(config)])
            case "check-target":
                configured = _configured_names(config)
                return _dedupe([".", ":root", *configured, *[f":{name}" for name in configured]])
            case "check-name":
                from dev.tasks.check import list_check_selectors

                return list(list_check_selectors(config))
            case "check-bundle":
                from dev.tasks.check import list_check_bundle_names

                return list_check_bundle_names()
            case "doctor-only":
                from dev.tasks.doctor import doctor_only_choices

                return list(doctor_only_choices())
            case _:
                return []

    def _completion_argument(
        kind: str,
        *,
        include_files: bool = False,
        directories_only: bool = False,
    ) -> Argument[str]:
        def callback(context: CompletionContext) -> list[CompletionCandidate]:
            config = _load_workspace_config()
            candidates = [CompletionCandidate(value) for value in _completion_values_for_kind(kind, config)]
            if include_files:
                candidates.extend(
                    _path_completion_candidates(
                        context.current_word,
                        directories_only=directories_only,
                    )
                )
            return candidates

        return Argument("string", "string", CompletionSpec.dynamic_callback(callback), lambda value: succeed(value))

    def _path_argument(*, directories_only: bool = False) -> Argument[str]:
        completion = CompletionSpec.directories() if directories_only else CompletionSpec.files()
        return Argument("path", "path", completion, lambda value: succeed(value))

    def _check_run_argument() -> Argument[str]:
        def callback(context: CompletionContext) -> list[CompletionCandidate]:
            match context.target:
                case CompletionTargetPositionalValue(index=0):
                    config = _load_workspace_config()
                    candidates = [CompletionCandidate(value) for value in _completion_values_for_kind("check-target", config)]
                    candidates.extend(
                        CompletionCandidate(value) for value in _completion_values_for_kind("check-bundle", config)
                    )
                    candidates.extend(CompletionCandidate(value) for value in _completion_values_for_kind("check-name", config))
                    candidates.extend(_path_completion_candidates(context.current_word))
                    return candidates
                case CompletionTargetPositionalValue():
                    config = _load_workspace_config()
                    candidates = [CompletionCandidate(value) for value in _completion_values_for_kind("check-name", config)]
                    candidates.extend(
                        CompletionCandidate(value) for value in _completion_values_for_kind("check-bundle", config)
                    )
                    candidates.extend(
                        CompletionCandidate(value) for value in _completion_values_for_kind("check-target", config)
                    )
                    candidates.extend(_path_completion_candidates(context.current_word))
                    return candidates
                case _:
                    return []

        return Argument("string", "string", CompletionSpec.dynamic_callback(callback), lambda value: succeed(value))

    project_target_argument = _completion_argument("project-target", include_files=True)
    repo_target_argument = _completion_argument("repo-target", include_files=True)
    path_or_target_argument = _completion_argument("path-or-target", include_files=True)
    push_target_argument = _completion_argument("push-target", include_files=True)
    check_target_argument = _completion_argument("check-target", include_files=True)
    check_name_argument = _completion_argument("check-name")
    check_bundle_argument = _completion_argument("check-bundle")
    doctor_only_argument = _completion_argument("doctor-only")

    def _security_tool_argument() -> Argument[str]:
        from dev.tasks.security_scan import security_tool_names

        return Argument.choice("tool", {tool: tool for tool in security_tool_names()})

    def _install_tool_argument() -> Argument[str]:
        from dev.tasks.install import install_tool_names

        return Argument.choice("tool", {tool: tool for tool in install_tool_names()})

    def _print_next_steps(
        command_path: str,
        *,
        targets: list[str],
        json_output: bool = False,
        dry_run: bool = False,
    ) -> None:
        if json_output:
            return

        target = _guidance_target(targets)
        steps: list[str]
        match command_path:
            case "doctor":
                steps = [
                    f"{prog} check config",
                    f"{prog} project list",
                    f"{prog} doctor --json",
                ]
            case "setup":
                if target is not None:
                    steps = [f"{prog} project show {target}", f"{prog} build {target}", f"{prog} check {target}"]
                else:
                    steps = [f"{prog} project list", f"{prog} build", f"{prog} check :root"]
            case "verify/release" | "release/verify":
                if target is not None:
                    steps = [
                        f"{prog} publish --dry-run {target}",
                        f"{prog} publish {target}",
                        f"{prog} status {target}",
                    ]
                else:
                    steps = [f"{prog} publish --dry-run", f"{prog} project list", f"{prog} status"]
            case "build":
                if target is not None:
                    steps = [
                        f"{prog} check {target}",
                        f"{prog} status {target}",
                        f"{prog} publish --dry-run {target}",
                    ]
                else:
                    steps = [f"{prog} check :root", f"{prog} project list", f"{prog} publish --dry-run"]
            case "checkout":
                if dry_run:
                    steps = [
                        f"{prog} checkout {target}" if target else f"{prog} checkout",
                        f"{prog} project repo {target}" if target else f"{prog} project list",
                        f"{prog} status {target}" if target else f"{prog} status",
                    ]
                else:
                    steps = [
                        f"{prog} status {target}" if target else f"{prog} status",
                        f"{prog} install hooks {target}" if target else f"{prog} install hooks",
                        f"{prog} setup --local {target}" if target else f"{prog} setup --local",
                    ]
            case "publish":
                if dry_run:
                    steps = [
                        f"{prog} publish {target}" if target else f"{prog} publish",
                        f"{prog} status {target}" if target else f"{prog} project list",
                        f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run",
                    ]
                else:
                    steps = [
                        f"{prog} status {target}" if target else f"{prog} project list",
                        f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run",
                        f"{prog} push {target}" if target else f"{prog} push",
                    ]
            case "project/show":
                if target is None:
                    return
                steps = [
                    f"{prog} project deps {target}",
                    f"{prog} project versions {target}",
                    f"{prog} build {target}",
                ]
            case "commit":
                if dry_run:
                    steps = [
                        f"{prog} commit {target}" if target else f"{prog} commit",
                        f"{prog} status {target}" if target else f"{prog} project list",
                        f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run",
                    ]
                else:
                    steps = [
                        f"{prog} status {target}" if target else f"{prog} project list",
                        f"{prog} push --dry-run {target}" if target else f"{prog} push --dry-run",
                        f"{prog} push {target}" if target else f"{prog} push",
                    ]
            case "push":
                if dry_run:
                    steps = [
                        f"{prog} push {target}" if target else f"{prog} push",
                        f"{prog} status {target}" if target else f"{prog} project list",
                    ]
                else:
                    steps = [
                        f"{prog} status {target}" if target else f"{prog} project list",
                        f"{prog} project repo {target}" if target else f"{prog} project list",
                    ]
            case _:
                return

        from dev.messages import command_text, heading

        print()
        print(heading("Next useful commands:"))
        for step in steps:
            print(f"  {command_text(step)}")

    def _format_failure_context() -> str:
        try:
            from dev.repo_resolution import format_workspace_context, resolve_workspace_context

            return format_workspace_context(resolve_workspace_context())
        except Exception:
            from dev.bootstrap import find_workspace_root

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

    def _request_command_tokens(request: TypedRequest) -> list[str] | None:
        match request:
            case WhereRequest(json_output=json_output):
                tokens = ["where"]
                if json_output:
                    tokens.append("--json")
                return tokens
            case ConfigCheckRequest():
                return ["check", "config"]
            case ConfigCutRequest(output_path=output_path, targets=targets):
                return ["config", "cut", output_path, *targets]
            case InstallHooksRequest(targets=targets, json_output=json_output):
                tokens = ["install", "hooks"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case DoctorRequest(targets=targets, only=only, json_output=json_output):
                tokens = ["doctor"]
                for value in only:
                    tokens.extend(["--only", value])
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case VerifyDocsRequest(targets=targets, semantic=semantic, json_output=json_output):
                tokens = ["verify", "docs"]
                if semantic:
                    tokens.append("--semantic")
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case VerifyReleaseRequest(targets=targets, json_output=json_output):
                tokens = ["verify", "release"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case VerifySecurityRequest(targets=targets, tools=tools, json_output=json_output):
                tokens = ["verify", "security"]
                for tool in tools:
                    tokens.extend(["--tool", tool])
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case DocsCheckRequest(targets=targets, semantic=semantic, json_output=json_output):
                tokens = ["verify", "docs"]
                if semantic:
                    tokens.append("--semantic")
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case DocsSnippetsRequest(targets=targets, verify=verify, json_output=json_output):
                tokens = ["docs", "snippets"]
                if verify:
                    tokens.append("--verify")
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case ReleaseVerifyRequest(targets=targets, json_output=json_output):
                tokens = ["verify", "release"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case SecurityScanRequest(targets=targets, tools=tools, json_output=json_output):
                tokens = ["verify", "security"]
                for tool in tools:
                    tokens.extend(["--tool", tool])
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case AskRequest(
                provider=provider,
                conversation_id=conversation_id,
                file_paths=file_paths,
                prompt=prompt,
                model=model,
            ):
                tokens = ["ask", provider]
                if conversation_id is not None:
                    tokens.extend(["--conversation", conversation_id])
                if model is not None:
                    tokens.extend(["--model", model])
                for file_path in file_paths:
                    tokens.extend(["--file", file_path])
                if prompt:
                    tokens.append(prompt)
                return tokens
            case SetupRequest(
                targets=targets,
                dev_mode=dev_mode,
                local_mode=local_mode,
                commit_if_setup_only=commit_if_setup_only,
                json_output=json_output,
            ):
                tokens = ["setup"]
                if dev_mode:
                    tokens.append("--dev")
                if local_mode:
                    tokens.append("--local")
                if commit_if_setup_only:
                    tokens.append("--commit-if-setup-only")
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case PublishRequest(targets=targets, dry_run=dry_run):
                tokens = ["publish"]
                if dry_run:
                    tokens.append("--dry-run")
                tokens.extend(targets)
                return tokens
            case DepGraphRequest(targets=targets, artifacts=artifacts):
                tokens = ["dep", "graph"]
                if artifacts:
                    tokens.append("--artifacts")
                tokens.extend(targets)
                return tokens
            case DepUpdatesRequest():
                return ["dep", "updates"]
            case BuildRequest(targets=targets, json_output=json_output):
                tokens = ["build"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case CleanRequest(targets=targets):
                return ["clean", *targets]
            case ClocRequest(targets=targets):
                return ["cloc", *targets]
            case StatusRequest(targets=targets, json_output=json_output):
                tokens = ["status"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case CheckoutRequest(targets=targets, dry_run=dry_run, json_output=json_output):
                tokens = ["checkout"]
                if dry_run:
                    tokens.append("--dry-run")
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case ServiceStartRequest(interval_seconds=interval_seconds):
                tokens = ["service", "start"]
                if interval_seconds != 60:
                    tokens.extend(["--interval-seconds", str(interval_seconds)])
                return tokens
            case ServiceStopRequest():
                return ["service", "stop"]
            case ServiceStatusRequest():
                return ["service", "status"]
            case ServiceDashboardRequest(interval_seconds=interval_seconds):
                tokens = ["service", "dashboard"]
                if interval_seconds != 60:
                    tokens.extend(["--interval-seconds", str(interval_seconds)])
                return tokens
            case CommitRequest(targets=targets, dry_run=dry_run):
                tokens = ["commit"]
                if dry_run:
                    tokens.append("--dry-run")
                tokens.extend(targets)
                return tokens
            case CommitVerifyRequest(
                target=target,
                message_file=message_file,
                message=message,
                revision_range=revision_range,
                staged=staged,
                json_output=json_output,
                quiet=quiet,
            ):
                tokens = ["commit", "verify"]
                if message_file is not None:
                    tokens.extend(["--message-file", message_file])
                if message is not None:
                    tokens.extend(["--message", message])
                if revision_range is not None:
                    tokens.extend(["--range", revision_range])
                if staged:
                    tokens.append("--staged")
                if json_output:
                    tokens.append("--json")
                if quiet:
                    tokens.append("--quiet")
                if target is not None:
                    tokens.append(target)
                return tokens
            case PushRequest(targets=targets, dry_run=dry_run):
                tokens = ["push"]
                if dry_run:
                    tokens.append("--dry-run")
                tokens.extend(targets)
                return tokens
            case CheckRunRequest(target=target, selectors=selectors, bundles=bundles, fix=fix, json_output=json_output):
                tokens = ["check"]
                if fix:
                    tokens.append("--fix")
                if json_output:
                    tokens.append("--json")
                for bundle_name in bundles:
                    tokens.extend(["--bundle", bundle_name])
                for selector in selectors:
                    tokens.extend(["--only", selector])
                if target is not None:
                    tokens.append(target)
                return tokens
            case CheckListRequest(json_output=json_output):
                tokens = ["check", "list"]
                if json_output:
                    tokens.append("--json")
                return tokens
            case CheckShowRequest(check=check, json_output=json_output):
                tokens = ["check", "show", check]
                if json_output:
                    tokens.append("--json")
                return tokens
            case SpdxHeadersRequest(target=target, fix=fix):
                tokens = ["spdx", "headers"]
                if fix:
                    tokens.append("--fix")
                if target is not None:
                    tokens.append(target)
                return tokens
            case SecretsScanRequest(target=target):
                tokens = ["secrets", "scan"]
                if target is not None:
                    tokens.append(target)
                return tokens
            case ContributorsAuditRequest():
                return ["contributors", "audit"]
            case ProjectListRequest():
                return ["project", "list"]
            case ProjectShowRequest(targets=targets, json_output=json_output):
                tokens = ["project", "show"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case ProjectDepsRequest(targets=targets, json_output=json_output):
                tokens = ["project", "deps"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case ProjectRepoRequest(targets=targets, json_output=json_output):
                tokens = ["project", "repo"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case ProjectTargetsRequest(targets=targets, json_output=json_output):
                tokens = ["project", "targets"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case ProjectVersionsRequest(targets=targets, json_output=json_output):
                tokens = ["project", "versions"]
                if json_output:
                    tokens.append("--json")
                tokens.extend(targets)
                return tokens
            case _:
                return None

    def _print_failure_context(request: TypedRequest | None) -> None:
        if request is None:
            return

        tokens = _request_command_tokens(request)
        if tokens is None:
            return

        from dev.bootstrap import canonical_rerun_command
        from dev.messages import command_text, heading

        print(_format_failure_context(), file=sys.stderr)
        rerun_command = canonical_rerun_command(tokens)
        if rerun_command is None:
            return

        print(file=sys.stderr)
        print(heading("Retry from workspace root:", stream=sys.stderr), file=sys.stderr)
        print(f"  {command_text(rerun_command, stream=sys.stderr)}", file=sys.stderr)

    def _docs_check_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            DocsCheckRequest(
                targets=_string_list(values.positional("target")),
                semantic=_bool_value(values, "--semantic"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _verify_docs_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            VerifyDocsRequest(
                targets=_string_list(values.positional("target")),
                semantic=_bool_value(values, "--semantic"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _docs_snippets_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            DocsSnippetsRequest(
                targets=_string_list(values.positional("target")),
                verify=_bool_value(values, "--verify"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _where_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(WhereRequest(json_output=_bool_value(values, "--json")))

    def _config_check_decode(_values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(ConfigCheckRequest())

    def _config_cut_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        match _optional_string(values.positional("output"), "output"):
            case Failure(issues=issues):
                return fail(issues)
            case Success(value=None):
                return fail([ValidationFailed("Expected <output> path.")])
            case Success(value=output_path):
                return succeed(
                    ConfigCutRequest(
                        output_path=output_path,
                        targets=_string_list(values.positional("target")),
                    )
                )

    def _completion_query_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        shell = values.positional("shell")
        index = values.positional("index")
        match (shell, index):
            case (str() as shell_text, int() as index_value):
                return succeed(
                    CompletionQueryRequest(
                        shell=shell_text,
                        index=index_value,
                        words=_string_list(values.positional("word")),
                    )
                )
            case _:
                return fail([ValidationFailed("Expected <shell> and <index> arguments.")])

    def _install_app_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        match _optional_string(values.option_or("--bin-dir", None), "bin-dir"):
            case Failure(issues=issues):
                return fail(issues)
            case Success(value=bin_dir):
                return succeed(InstallAppRequest(bin_dir=bin_dir))

    def _install_completions_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        raw_shell = values.option_or("--shell", "all")
        match raw_shell:
            case str() as shell:
                return succeed(
                    InstallCompletionsRequest(
                        shell=shell,
                        update_rc=not _bool_value(values, "--no-rc"),
                    )
                )
            case _:
                return fail([ValidationFailed("Expected --shell to be one of: all, bash, zsh.")])

    def _install_tools_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            InstallToolsRequest(
                tools=_option_string_list(values, "--tool"),
                force=_bool_value(values, "--force"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _install_hooks_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            InstallHooksRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _doctor_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            DoctorRequest(
                targets=_string_list(values.positional("target")),
                only=_option_string_list(values, "--only"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _release_verify_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            ReleaseVerifyRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _release_bundle_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            ReleaseBundleRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _verify_release_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            VerifyReleaseRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _security_scan_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            SecurityScanRequest(
                targets=_string_list(values.positional("target")),
                tools=_option_string_list(values, "--tool"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _verify_security_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            VerifySecurityRequest(
                targets=_string_list(values.positional("target")),
                tools=_option_string_list(values, "--tool"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _llmcopy_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        paths = _string_list(values.positional("path"))
        if not paths:
            return fail([ValidationFailed("Expected at least one <path> argument.")])
        return succeed(LlmcopyRequest(paths=paths))

    def _ask_decode(provider: str, values: ParsedValues) -> Validated[Issue, TypedRequest]:
        match _optional_string(values.option_or("--conversation", None), "conversation"):
            case Failure(issues=issues):
                return fail(issues)
            case Success(value=conversation_id):
                pass

        match _optional_string(values.option_or("--model", None), "model"):
            case Failure(issues=issues):
                return fail(issues)
            case Success(value=model):
                pass

        return succeed(
            AskRequest(
                provider=provider,
                conversation_id=conversation_id,
                file_paths=_option_string_list(values, "--file"),
                prompt=" ".join(_string_list(values.positional("text"))).strip(),
                model=model,
            )
        )

    def _setup_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            SetupRequest(
                targets=_string_list(values.positional("target")),
                dev_mode=_bool_value(values, "--dev"),
                local_mode=_bool_value(values, "--local"),
                commit_if_setup_only=_bool_value(values, "--commit-if-setup-only"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _publish_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            PublishRequest(
                targets=_string_list(values.positional("target")),
                dry_run=_bool_value(values, "--dry-run"),
            )
        )

    def _duplicates_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        folders = _string_list(values.positional("folder"))
        if not folders:
            return fail([ValidationFailed("Expected at least one <folder> argument.")])
        return succeed(
            DuplicatesRequest(
                folders=folders,
                exclude=_option_string_list(values, "--exclude"),
                include=_option_string_list(values, "--filter"),
                min_size=_int_value(values, "--size", 1),
                no_default_excludes=_bool_value(values, "--no-default-excludes"),
                zip_contents=_bool_value(values, "--zip-contents"),
                weak_encrypted_zip=_bool_value(values, "--weak-encrypted-zip"),
            )
        )

    def _jitpack_info_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        group = values.positional("group")
        artifact = values.positional("artifact")
        match (group, artifact):
            case (str() as group_text, str() as artifact_text):
                match _optional_string(values.positional("version"), "version"):
                    case Failure(issues=issues):
                        return fail(issues)
                    case Success(value=version):
                        return succeed(JitpackInfoRequest(group=group_text, artifact=artifact_text, version=version))
            case _:
                return fail([ValidationFailed("Expected <group> and <artifact> arguments.")])

    def _dep_graph_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            DepGraphRequest(
                targets=_string_list(values.positional("target")),
                artifacts=_bool_value(values, "--artifacts"),
            )
        )

    def _build_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            BuildRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _clean_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(CleanRequest(targets=_string_list(values.positional("target"))))

    def _cloc_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(ClocRequest(targets=_string_list(values.positional("target"))))

    def _status_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            StatusRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _checkout_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            CheckoutRequest(
                targets=_string_list(values.positional("target")),
                dry_run=_bool_value(values, "--dry-run"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _service_start_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(ServiceStartRequest(interval_seconds=_int_value(values, "--interval-seconds", 60)))

    def _service_dashboard_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(ServiceDashboardRequest(interval_seconds=_int_value(values, "--interval-seconds", 60)))

    def _commit_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            CommitRequest(
                targets=_string_list(values.positional("target")),
                dry_run=_bool_value(values, "--dry-run"),
            )
        )

    def _commit_verify_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        message_file = _optional_string(values.option_or("--message-file", None), "message-file")
        message = _optional_string(values.option_or("--message", None), "message")
        revision_range = _optional_string(values.option_or("--range", None), "range")
        target = _optional_string(values.positional("target"), "target")
        match (message_file, message, revision_range, target):
            case (Failure(issues=issues), _, _, _):
                return fail(issues)
            case (_, Failure(issues=issues), _, _):
                return fail(issues)
            case (_, _, Failure(issues=issues), _):
                return fail(issues)
            case (_, _, _, Failure(issues=issues)):
                return fail(issues)
            case (
                Success(value=message_file_value),
                Success(value=message_value),
                Success(value=revision_range_value),
                Success(value=target_value),
            ):
                return succeed(
                    CommitVerifyRequest(
                        target=target_value,
                        message_file=message_file_value,
                        message=message_value,
                        revision_range=revision_range_value,
                        staged=_bool_value(values, "--staged"),
                        json_output=_bool_value(values, "--json"),
                        quiet=_bool_value(values, "--quiet"),
                    )
                )
            case _:
                return fail([ValidationFailed("Invalid commit verify arguments.")])

    def _push_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            PushRequest(
                targets=_string_list(values.positional("target")),
                dry_run=_bool_value(values, "--dry-run"),
            )
        )

    def _backup_push_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        match _optional_string(values.option_or("--target", None), "target"):
            case Failure(issues=issues):
                return fail(issues)
            case Success(value=backup_target_name):
                return succeed(
                    BackupPushRequest(
                        repo_targets=_string_list(values.positional("repo")),
                        backup_target_name=backup_target_name,
                        dry_run=_bool_value(values, "--dry-run"),
                        json_output=_bool_value(values, "--json"),
                    )
                )

    def _backup_restore_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        repo_target = _optional_string(values.positional("repo"), "repo")
        backup_target_name = _optional_string(values.option_or("--target", None), "target")
        into = _optional_string(values.option_or("--into", None), "into")
        snapshot = _optional_string(values.option_or("--snapshot", "latest"), "snapshot")
        match (repo_target, backup_target_name, into, snapshot):
            case (Failure(issues=issues), _, _, _):
                return fail(issues)
            case (_, Failure(issues=issues), _, _):
                return fail(issues)
            case (_, _, Failure(issues=issues), _):
                return fail(issues)
            case (_, _, _, Failure(issues=issues)):
                return fail(issues)
            case (
                Success(value=repo_target_value),
                Success(value=backup_target_name_value),
                Success(value=None),
                _,
            ):
                return fail([ValidationFailed("Expected --into <DIR> for `backup restore`.")])
            case (
                Success(value=repo_target_value),
                Success(value=backup_target_name_value),
                Success(value=into_value),
                Success(value=snapshot_value),
            ):
                return succeed(
                    BackupRestoreRequest(
                        repo_target=repo_target_value,
                        backup_target_name=backup_target_name_value,
                        snapshot="latest" if snapshot_value is None else snapshot_value,
                        into=into_value,
                        dry_run=_bool_value(values, "--dry-run"),
                        json_output=_bool_value(values, "--json"),
                    )
                )
            case _:
                return fail([ValidationFailed("Invalid backup restore arguments.")])

    def _is_check_target_token(token: str, config: Config | None) -> bool:
        if token in {".", ":root"}:
            return True
        if token.startswith(":"):
            return True
        path = Path(token).expanduser()
        if path.exists():
            return True
        if config is None:
            return False
        return token in config.defined_projects or token in config.defined_repos

    def _decode_check_run_parts(
        args: list[str],
        only_values: list[str],
    ) -> tuple[str | None, list[str], list[str]]:
        from dev.tasks.check import list_check_bundle_names, list_check_selectors

        config = _load_workspace_config()
        known_bundles = set(list_check_bundle_names())
        known_selectors = set(list_check_selectors(config))

        target: str | None = None
        selectors: list[str] = []
        bundles: list[str] = []

        def add_bundle(value: str) -> None:
            if value not in bundles:
                bundles.append(value)

        def add_selector(value: str) -> None:
            selectors.append(value)

        def classify_positional(token: str) -> None:
            nonlocal target
            if token in known_bundles:
                add_bundle(token)
                return
            if token in known_selectors:
                add_selector(token)
                return
            if target is None and _is_check_target_token(token, config):
                target = token
                return
            add_selector(token)

        def classify_only(token: str) -> None:
            nonlocal target
            if token in known_bundles:
                add_bundle(token)
                return
            if token in known_selectors:
                add_selector(token)
                return
            if target is None and _is_check_target_token(token, config):
                target = token
                return
            add_selector(token)

        for token in args:
            classify_positional(token)
        for token in only_values:
            classify_only(token)

        return target, selectors, bundles

    def _check_run_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        args = _string_list(values.positional("arg"))
        target, selectors, inferred_bundles = _decode_check_run_parts(args, _option_string_list(values, "--only"))
        return succeed(
            CheckRunRequest(
                target=target,
                selectors=selectors,
                bundles=_dedupe([*inferred_bundles, *_option_string_list(values, "--bundle")]),
                fix=_bool_value(values, "--fix"),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _check_list_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(CheckListRequest(json_output=_bool_value(values, "--json")))

    def _check_show_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        check = values.positional("check")
        if not isinstance(check, str):
            return fail([ValidationFailed("Expected <check> argument.")])
        return succeed(CheckShowRequest(check=check, json_output=_bool_value(values, "--json")))

    def _verify_list_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(VerifyListRequest(json_output=_bool_value(values, "--json")))

    def _spdx_headers_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        match _optional_string(values.positional("target"), "target"):
            case Failure(issues=issues):
                return fail(issues)
            case Success(value=target):
                return succeed(SpdxHeadersRequest(target=target, fix=_bool_value(values, "--fix")))

    def _secrets_scan_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        match _optional_string(values.positional("target"), "target"):
            case Failure(issues=issues):
                return fail(issues)
            case Success(value=target):
                return succeed(SecretsScanRequest(target=target))

    def _project_show_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            ProjectShowRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _project_deps_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            ProjectDepsRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _project_repo_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            ProjectRepoRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _project_targets_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            ProjectTargetsRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _project_versions_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(
            ProjectVersionsRequest(
                targets=_string_list(values.positional("target")),
                json_output=_bool_value(values, "--json"),
            )
        )

    def _unused_decode(_values: ParsedValues) -> Validated[Issue, TypedRequest]:
        return succeed(None)

    def _root_decode(values: ParsedValues) -> Validated[Issue, TypedRequest]:
        match values.command_path:
            case ["where"]:
                return _where_decode(values)
            case ["check", "config"]:
                return _config_check_decode(values)
            case ["config", "check"]:
                return _config_check_decode(values)
            case ["config", "cut"]:
                return _config_cut_decode(values)
            case ["install", "app"]:
                return _install_app_decode(values)
            case ["install", "completions"]:
                return _install_completions_decode(values)
            case ["install", "tools"]:
                return _install_tools_decode(values)
            case ["install", "hooks"]:
                return _install_hooks_decode(values)
            case ["completion", "bash"]:
                return succeed(CompletionBashRequest())
            case ["completion", "zsh"]:
                return succeed(CompletionZshRequest())
            case ["completion", "query"]:
                return _completion_query_decode(values)
            case ["doctor"]:
                return _doctor_decode(values)
            case ["verify", "list"]:
                return _verify_list_decode(values)
            case ["verify", "docs"]:
                return _verify_docs_decode(values)
            case ["verify", "release"]:
                return _verify_release_decode(values)
            case ["verify", "security"]:
                return _verify_security_decode(values)
            case ["docs", "check"]:
                return _docs_check_decode(values)
            case ["docs", "snippets"]:
                return _docs_snippets_decode(values)
            case ["setup"]:
                return _setup_decode(values)
            case ["release", "verify"]:
                return _release_verify_decode(values)
            case ["release", "bundle"]:
                return _release_bundle_decode(values)
            case ["security", "scan"]:
                return _security_scan_decode(values)
            case ["llmcopy"]:
                return _llmcopy_decode(values)
            case ["ask", "gpt"]:
                return _ask_decode("gpt", values)
            case ["ask", "claude"]:
                return _ask_decode("claude", values)
            case ["ask", "gemini"]:
                return _ask_decode("gemini", values)
            case ["publish"]:
                return _publish_decode(values)
            case ["duplicates"]:
                return _duplicates_decode(values)
            case ["jitpack", "info"]:
                return _jitpack_info_decode(values)
            case ["dep", "updates"]:
                return succeed(DepUpdatesRequest())
            case ["dep", "graph"]:
                return _dep_graph_decode(values)
            case ["build"]:
                return _build_decode(values)
            case ["clean"]:
                return _clean_decode(values)
            case ["cloc"]:
                return _cloc_decode(values)
            case ["status"]:
                return _status_decode(values)
            case ["checkout"]:
                return _checkout_decode(values)
            case ["service", "start"]:
                return _service_start_decode(values)
            case ["service", "stop"]:
                return succeed(ServiceStopRequest())
            case ["service", "status"]:
                return succeed(ServiceStatusRequest())
            case ["service", "dashboard"]:
                return _service_dashboard_decode(values)
            case ["commit"]:
                return _commit_decode(values)
            case ["commit", "verify"]:
                return _commit_verify_decode(values)
            case ["push"]:
                return _push_decode(values)
            case ["backup", "push"]:
                return _backup_push_decode(values)
            case ["backup", "restore"]:
                return _backup_restore_decode(values)
            case ["check"]:
                return _check_run_decode(values)
            case ["check", "run"]:
                return _check_run_decode(values)
            case ["check", "list"]:
                return _check_list_decode(values)
            case ["check", "show"]:
                return _check_show_decode(values)
            case ["check", "describe"]:
                return _check_show_decode(values)
            case ["spdx", "headers"]:
                return _spdx_headers_decode(values)
            case ["secrets", "scan"]:
                return _secrets_scan_decode(values)
            case ["contributors", "audit"]:
                return succeed(ContributorsAuditRequest())
            case ["project", "list"]:
                return succeed(ProjectListRequest())
            case ["project", "show"]:
                return _project_show_decode(values)
            case ["project", "deps"]:
                return _project_deps_decode(values)
            case ["project", "repo"]:
                return _project_repo_decode(values)
            case ["project", "targets"]:
                return _project_targets_decode(values)
            case ["project", "versions"]:
                return _project_versions_decode(values)
            case _:
                return _unused_decode(values)

    where_command = Command(
        name="where",
        header="Show the workspace, repo, and project context inferred from the current directory.",
        options=(flag(long="json", help="Emit the resolved cwd context as JSON."),),
        decode=_unused_decode,
    )
    config_check_command = Command(
        name="check",
        header="Parse and validate root.clj and root.private.clj.",
        decode=_unused_decode,
    )
    config_cut_command = Command(
        name="cut",
        header="Write a reduced root.clj subset for selected projects and their transitive local dependencies.",
        positionals=(
            positional(_path_argument(), "output", help="Destination .clj file."),
            positional(
                project_target_argument,
                "target",
                help="Project IDs, repo IDs, or paths. Omit only when running from inside a configured project or repo.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    config_command = Command(
        name="config",
        header="Validate or extract workspace configuration files.",
        subcommands=(config_check_command, config_cut_command),
        decode=_unused_decode,
        help_on_empty=True,
    )
    install_app_command = Command(
        name="app",
        header="Install or refresh the global dev and wabbit-dev launcher wrappers.",
        options=(
            option(
                Argument.string(),
                long="bin-dir",
                help="Install wrappers into this directory instead of the first writable PATH directory.",
                meta_var="DIR",
            ),
        ),
        decode=_unused_decode,
    )
    install_completions_command = Command(
        name="completions",
        header="Install and register bash/zsh completions for dev and wabbit-dev.",
        options=(
            option(
                Argument.choice("shell", {"all": "all", "bash": "bash", "zsh": "zsh"}),
                long="shell",
                help="Install completions for one shell or all supported shells.",
                meta_var="SHELL",
            ),
            flag(long="no-rc", help="Write completion scripts without updating .bashrc or .zshrc."),
        ),
        decode=_unused_decode,
    )
    install_tools_command = Command(
        name="tools",
        header="Install optional local developer and security tools.",
        options=(
            option(
                _install_tool_argument(),
                long="tool",
                help="Install only this tool. Repeatable.",
                repeated=True,
                meta_var="TOOL",
            ),
            flag(long="force", help="Reinstall or upgrade tools even when an executable is already available."),
            flag(long="json", help="Emit a machine-readable install report."),
        ),
        decode=_unused_decode,
    )
    install_hooks_command = Command(
        name="hooks",
        header="Install local Git hooks that enforce dev commit policy.",
        options=(flag(long="json", help="Emit a machine-readable hook install report."),),
        positionals=(
            positional(
                repo_target_argument,
                "target",
                help="Repo IDs, project IDs, or paths. Omit to use the current repo, or all repos from the workspace root.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    install_command = Command(
        name="install",
        header="Install local developer entrypoints and shell integrations.",
        footer=(
            "Examples:\n"
            f"  {prog} install app\n"
            f"  {prog} install completions\n"
            f"  {prog} install completions --shell zsh\n"
            f"  {prog} install hooks\n"
            f"  {prog} install tools"
        ),
        subcommands=(install_app_command, install_completions_command, install_hooks_command, install_tools_command),
        decode=_unused_decode,
        help_on_empty=True,
    )
    completion_bash_command = Command(
        name="bash",
        header="Print a bash completion script.",
        decode=_unused_decode,
    )
    completion_zsh_command = Command(
        name="zsh",
        header="Print a zsh completion script.",
        decode=_unused_decode,
    )
    completion_query_command = Command(
        name="query",
        header="Internal compatibility completion query protocol.",
        visibility=Visibility.HIDDEN,
        positionals=(
            positional(Argument.string(), "shell", help="Completion shell name."),
            positional(Argument.integer(), "index", help="Current completion word index."),
            positional(Argument.string(), "word", help="Shell words.", repeated=True),
        ),
        decode=_unused_decode,
    )
    completion_command = Command(
        name="completion",
        header="Generate shell completion scripts.",
        footer=(
            "Examples:\n"
            f"  source <({prog} completion bash)\n"
            f"  autoload -Uz compinit && compinit && source <({prog} completion zsh)\n\n"
            "Completion scripts query the typed command grammar at completion time, so command, target, "
            "and check-name candidates stay consistent with the CLI."
        ),
        subcommands=(completion_bash_command, completion_zsh_command, completion_query_command),
        decode=_unused_decode,
        help_on_empty=True,
    )
    doctor_command = Command(
        name="doctor",
        header="Diagnose workspace, toolchain, and credential readiness.",
        options=(
            option(
                doctor_only_argument,
                long="only",
                help="Limit the report to one check ID or command readiness group. Repeatable.",
                repeated=True,
                meta_var="CHECK_OR_COMMAND",
            ),
            flag(long="json", help="Emit the doctor report as JSON instead of human-oriented text."),
        ),
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="Optional project IDs, repo IDs, or paths used to scope project-related checks.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    verify_list_command = Command(
        name="list",
        header="List the available verification workflows.",
        options=(flag(long="json", help="Emit the verification workflow catalog as JSON."),),
        decode=_unused_decode,
    )
    verify_docs_command = Command(
        name="docs",
        header="Run documentation verification workflows.",
        options=(
            flag(long="semantic", help="Add an LLM-based advisory review for semantic docs quality issues."),
            flag(long="json", help="Emit a machine-readable docs report instead of human-oriented output."),
        ),
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="Project IDs, repo IDs, or paths. Omit to verify the current inferred project or repo, or the full workspace from root.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    verify_release_command = Command(
        name="release",
        header="Verify publishable Python and Gradle projects without uploading them.",
        options=(flag(long="json", help="Emit a machine-readable release verification report."),),
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="Optional project or repo targets.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    verify_security_command = Command(
        name="security",
        header="Run opt-in external security scanners against selected repos or paths.",
        options=(
            option(
                _security_tool_argument(),
                long="tool",
                help="Run only this external security tool. Repeatable.",
                repeated=True,
                meta_var="TOOL",
            ),
            flag(long="json", help="Emit a machine-readable security scan report."),
        ),
        positionals=(
            positional(
                repo_target_argument,
                "target",
                help="Repo IDs, project IDs, or paths inside git repositories.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    verify_command = Command(
        name="verify",
        header="Run slower workflow-oriented verification commands.",
        subcommands=(verify_docs_command, verify_release_command, verify_security_command, verify_list_command),
        decode=_unused_decode,
        help_on_empty=True,
    )
    docs_check_command = Command(
        name="check",
        header="Check project documentation links, sections, snippets, and optional semantic quality.",
        options=(
            flag(long="semantic", help="Add an LLM-based advisory review for semantic docs quality issues."),
            flag(long="json", help="Emit a machine-readable docs report instead of human-oriented output."),
        ),
        positionals=(positional(project_target_argument, "target", help="Optional project or repo targets.", repeated=True),),
        decode=_unused_decode,
    )
    docs_snippets_command = Command(
        name="snippets",
        header="Check fenced documentation snippets with optional project-specific deeper verification.",
        options=(
            flag(long="verify", help="Enable deeper project-specific snippet verification."),
            flag(long="json", help="Emit a machine-readable snippet report instead of human-oriented output."),
        ),
        positionals=(positional(project_target_argument, "target", help="Optional project or repo targets.", repeated=True),),
        decode=_unused_decode,
    )
    docs_command = Command(
        name="docs",
        header="Validate project documentation quality.",
        subcommands=(docs_check_command, docs_snippets_command),
        decode=_unused_decode,
        help_on_empty=True,
        visibility=Visibility.HIDDEN,
    )
    setup_command = Command(
        name="setup",
        header="Generate or refresh project files from root.clj.",
        options=(
            flag(long="dev", help="Run setup in DEV mode instead of the default PROD mode."),
            flag(long="local", help="Run setup in LOCAL mode and generate local dependency overlays."),
            flag(
                long="commit-if-setup-only",
                help=(
                    "After PROD setup, auto-commit repo changes only when they stay within the safe setup-only "
                    "scope: root.clj, .gitignore, and setup-managed generated files, with no untracked files."
                ),
            ),
            flag(long="json", help="Emit a machine-readable setup summary instead of human-oriented progress output."),
        ),
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="Project IDs, repo IDs, or paths. Omit to process every configured project.",
                repeated=True,
            ),
        ),
        exclusive_groups=(at_most_one_of("--dev", "--local"),),
        decode=_unused_decode,
    )
    release_verify_command = Command(
        name="verify",
        header="Verify publishable Python and Gradle projects and inspect release metadata.",
        options=(flag(long="json", help="Emit a machine-readable release verification report."),),
        positionals=(positional(project_target_argument, "target", help="Optional project or repo targets.", repeated=True),),
        decode=_unused_decode,
    )
    release_bundle_command = Command(
        name="bundle",
        header="Build and package GitHub Release assets for publishable Python and Gradle projects.",
        options=(flag(long="json", help="Emit a machine-readable release bundle report."),),
        positionals=(positional(project_target_argument, "target", help="Optional project or repo targets.", repeated=True),),
        decode=_unused_decode,
    )
    release_command = Command(
        name="release",
        header="Verify or package release assets for publishable projects.",
        subcommands=(release_verify_command, release_bundle_command),
        decode=_unused_decode,
        help_on_empty=True,
        visibility=Visibility.HIDDEN,
    )
    security_scan_command = Command(
        name="scan",
        header="Run opt-in external security scanners against selected repos or paths.",
        options=(
            option(
                _security_tool_argument(),
                long="tool",
                help="Run only this external security tool. Repeatable.",
                repeated=True,
                meta_var="TOOL",
            ),
            flag(long="json", help="Emit a machine-readable security scan report."),
        ),
        positionals=(
            positional(
                repo_target_argument,
                "target",
                help="Repo IDs, project IDs, or paths inside git repositories.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    security_command = Command(
        name="security",
        header="Run opt-in external security tooling.",
        subcommands=(security_scan_command,),
        decode=_unused_decode,
        help_on_empty=True,
        visibility=Visibility.HIDDEN,
    )
    llmcopy_command = Command(
        name="llmcopy",
        header="Copy file contents to the clipboard in an LLM-friendly envelope and report GPT-5.4 token totals.",
        positionals=(
            positional(
                _path_argument(),
                "path",
                help="Files, directories, or glob patterns to include in the clipboard bundle.",
                repeated=True,
                required=True,
            ),
        ),
        decode=_unused_decode,
    )
    ask_gpt_command = Command(
        name="gpt",
        header="Ask OpenAI GPT with optional cached conversation history and file attachments.",
        options=(
            option(
                Argument.string(),
                long="conversation",
                help="Resume or name a cached conversation. Omit to start a new one.",
                meta_var="ID",
            ),
            option(
                _path_argument(),
                long="file",
                help="Attach a UTF-8 text file or a raster image. Repeatable.",
                repeated=True,
                meta_var="FILE",
            ),
            option(
                Argument.string(),
                long="model",
                help="Override the default GPT model for this turn or conversation.",
                meta_var="MODEL",
            ),
        ),
        positionals=(
            positional(
                Argument.string(),
                "text",
                help="Prompt text. Omit when you want to send only attached files.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    ask_claude_command = Command(
        name="claude",
        header="Ask Anthropic Claude with optional cached conversation history and file attachments.",
        options=ask_gpt_command.options,
        positionals=ask_gpt_command.positionals,
        decode=_unused_decode,
    )
    ask_gemini_command = Command(
        name="gemini",
        header="Ask Google Gemini with optional cached conversation history and file attachments.",
        options=ask_gpt_command.options,
        positionals=ask_gpt_command.positionals,
        decode=_unused_decode,
    )
    ask_command = Command(
        name="ask",
        header="Ask GPT, Claude, or Gemini and cache the conversation locally for reuse.",
        subcommands=(ask_gpt_command, ask_claude_command, ask_gemini_command),
        decode=_unused_decode,
        help_on_empty=True,
    )
    publish_command = Command(
        name="publish",
        header="Publish configured projects in dependency order.",
        options=(flag(long="dry-run", help="Print the publish plan without uploading artifacts or contacting publish targets."),),
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="Project IDs, repo IDs, or paths. Omit to publish every publishable configured project.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    dep_graph_command = Command(
        name="graph",
        header="Render an SVG graph of project dependencies.",
        options=(flag(long="artifacts", help="Include external dependency artifacts in addition to project nodes."),),
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="Project IDs, repo IDs, or paths. Omit to graph the full workspace.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    dep_updates_command = Command(
        name="updates",
        header="Check configured Maven libraries and pinned Python deps for newer upstream versions.",
        decode=_unused_decode,
    )
    dep_command = Command(
        name="dep",
        header="Analyze the dependency metadata loaded from root.clj.",
        subcommands=(dep_graph_command, dep_updates_command),
        decode=_unused_decode,
        help_on_empty=True,
    )
    duplicates_command = Command(
        name="duplicates",
        header="Find duplicate files and directory trees.",
        options=(
            option(
                Argument.string(),
                long="exclude",
                short="e",
                help="Git-style filename filters to exclude from scanning.",
                meta_var="PATTERN",
                multiple_values=True,
            ),
            option(
                Argument.string(),
                long="filter",
                short="f",
                help="Restrict scanning to files matching one or more filename filters.",
                meta_var="PATTERN",
                multiple_values=True,
            ),
            option(
                Argument.integer(),
                long="size",
                short="s",
                help="Minimum file size to include in duplicate file reporting.",
                meta_var="BYTES",
            ),
            flag(long="no-default-excludes", help="Do not automatically exclude common metadata directories."),
            flag(long="zip-contents", help="Also compare directory trees against zip archive contents."),
            flag(
                long="weak-encrypted-zip",
                help="Allow metadata-only comparison of encrypted zip entries when zip contents are enabled.",
            ),
        ),
        positionals=(
            positional(
                _path_argument(directories_only=True),
                "folder",
                help="Folders to scan for duplicate files and directory trees.",
                repeated=True,
                required=True,
            ),
        ),
        decode=_unused_decode,
    )
    jitpack_info_command = Command(
        name="info",
        header="Show refs, commits, versions, and build info for a JitPack artifact.",
        positionals=(
            positional(Argument.string(), "group", help="JitPack group or GitHub owner/organization."),
            positional(Argument.string(), "artifact", help="JitPack artifact or repository name."),
            positional(Argument.string(), "version", help="Optional version to narrow the output.", required=False),
        ),
        decode=_unused_decode,
    )
    jitpack_command = Command(
        name="jitpack",
        header="Inspect JitPack metadata for an artifact.",
        subcommands=(jitpack_info_command,),
        decode=_unused_decode,
        help_on_empty=True,
    )
    build_command = Command(
        name="build",
        header="Build configured Gradle or Python projects in dependency order.",
        options=(flag(long="json", help="Emit a machine-readable build report instead of human-oriented progress output."),),
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="Project IDs, repo IDs, or paths. Omit to build every buildable configured project.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    clean_command = Command(
        name="clean",
        header="Delete generated caches and build outputs for configured projects.",
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="Project IDs, repo IDs, or paths. Omit to clean every configured project.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    cloc_command = Command(
        name="cloc",
        header="Summarize lines of code for configured targets or paths.",
        positionals=(
            positional(
                path_or_target_argument,
                "target",
                help="Project IDs, repo IDs, or filesystem paths. Omit to analyze every configured project.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    status_command = Command(
        name="status",
        header="Show repo status for selected targets.",
        options=(flag(long="json", help="Emit staged, unstaged, and untracked repo status details as JSON."),),
        positionals=(
            positional(
                repo_target_argument,
                "target",
                help="Repo IDs, project IDs, or paths inside git repositories.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    checkout_command = Command(
        name="checkout",
        header="Clone missing configured repositories from GitHub into their root.clj paths.",
        options=(
            flag(long="dry-run", help="Print the checkout plan without running git clone."),
            flag(long="json", help="Emit checkout results as JSON."),
        ),
        positionals=(
            positional(
                repo_target_argument,
                "target",
                help="Repo IDs, project IDs, or configured repo paths.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    service_start_command = Command(
        name="start",
        header="Start the macOS repo monitor menubar process for this workspace.",
        options=(
            option(
                Argument.integer(),
                long="interval-seconds",
                help="Polling interval for repo status refresh.",
                meta_var="SECONDS",
            ),
        ),
        decode=_unused_decode,
    )
    service_stop_command = Command(
        name="stop",
        header="Stop the workspace monitor and dashboard processes.",
        decode=_unused_decode,
    )
    service_status_command = Command(
        name="status",
        header="Show the current monitor and dashboard processes for this workspace.",
        decode=_unused_decode,
    )
    service_dashboard_command = Command(
        name="dashboard",
        header="Start or open the localhost dashboard for this workspace.",
        options=(
            option(
                Argument.integer(),
                long="interval-seconds",
                help="Polling interval for the dashboard repo-status loop.",
                meta_var="SECONDS",
            ),
        ),
        decode=_unused_decode,
    )
    service_command = Command(
        name="service",
        header="Run the workspace monitor and dashboard services.",
        subcommands=(service_start_command, service_stop_command, service_status_command, service_dashboard_command),
        decode=_unused_decode,
        help_on_empty=True,
    )
    commit_verify_command = Command(
        name="verify",
        header="Verify commit message policy for a message file or commit range.",
        options=(
            option(
                Argument.string(),
                long="message-file",
                help="Validate a commit message file, usually .git/COMMIT_EDITMSG from a commit-msg hook.",
                meta_var="FILE",
            ),
            option(
                Argument.string(),
                long="message",
                help="Validate this commit message string.",
                meta_var="TEXT",
            ),
            option(
                Argument.string(),
                long="range",
                help="Validate every commit message in this revision range.",
                meta_var="REVISION_RANGE",
            ),
            flag(long="staged", help="Also validate staged diff context, such as version/changelog coupling."),
            flag(long="json", help="Emit a machine-readable verification report."),
            flag(long="quiet", help="Suppress success output."),
        ),
        positionals=(
            positional(
                repo_target_argument,
                "target",
                help="Optional repo ID, project ID, or path. Omit to use the current git repo.",
                required=False,
            ),
        ),
        decode=_unused_decode,
    )
    commit_command = Command(
        name="commit",
        header="Run setup, stage changes, and create commits for configured projects.",
        options=(flag(long="dry-run", help="Print the setup and repo commit plan without modifying files or creating commits."),),
        subcommands=(commit_verify_command,),
        subcommand_fallback_to_positionals=True,
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="Project IDs, repo IDs, or paths. Omit to process every configured project.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    push_command = Command(
        name="push",
        header="Push the current branch to its configured upstream when the remote can fast-forward.",
        options=(flag(long="dry-run", help="Print pushability and upstream state without sending branch updates."),),
        positionals=(
            positional(
                push_target_argument,
                "target",
                help="Use `.` for all configured repos, or provide repo IDs, project IDs, or paths.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    backup_push_command = Command(
        name="push",
        header="Create immutable restic snapshots for selected repos.",
        options=(
            option(
                Argument.string(),
                long="target",
                help="Backup target name from root.clj. Defaults to the active backup-policy target(s).",
                meta_var="NAME",
            ),
            flag(long="dry-run", help="Validate selection and print the backup plan without writing snapshots."),
            flag(long="json", help="Emit a machine-readable backup report."),
        ),
        positionals=(
            positional(
                repo_target_argument,
                "repo",
                help="Repo IDs, project IDs, or paths. Omit to use the current repo, or all configured repos from the workspace root.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    backup_restore_command = Command(
        name="restore",
        header="Restore one repo snapshot into a destination directory.",
        options=(
            option(
                Argument.string(),
                long="target",
                help="Backup target name from root.clj. Defaults to the active backup-policy target.",
                meta_var="NAME",
            ),
            option(
                Argument.string(),
                long="snapshot",
                help="Snapshot ID to restore. Defaults to latest.",
                meta_var="SNAPSHOT",
            ),
            option(
                _path_argument(directories_only=True),
                long="into",
                help="Destination directory for the restored repo tree.",
                meta_var="DIR",
            ),
            flag(long="dry-run", help="Show what would be restored without writing files."),
            flag(long="json", help="Emit a machine-readable restore report."),
        ),
        positionals=(
            positional(
                repo_target_argument,
                "repo",
                help="Optional repo ID, project ID, or path. Omit to use the current inferred repo.",
                required=False,
            ),
        ),
        decode=_unused_decode,
    )
    backup_command = Command(
        name="backup",
        header="Create or restore immutable repo backups with restic targets configured in root.clj.",
        subcommands=(backup_push_command, backup_restore_command),
        decode=_unused_decode,
        help_on_empty=True,
    )
    check_run_command = Command(
        name="run",
        header="Run the configured check suite against a project, directory, or file.",
        options=(
            option(
                check_bundle_argument,
                long="bundle",
                help="Restrict the run to one check bundle. Repeatable.",
                repeated=True,
                meta_var="BUNDLE",
            ),
            option(
                check_name_argument,
                long="only",
                help="Restrict the run to specific check IDs or legacy class names. Repeatable.",
                repeated=True,
                meta_var="CHECK",
            ),
            flag(long="fix", help="Apply fixes for issues that provide an automatic fix callback."),
            flag(long="json", help="Emit a machine-readable check report instead of text."),
        ),
        positionals=(
            positional(
                _check_run_argument(),
                "arg",
                help="Optional target followed by optional explicit check IDs or legacy class names.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    check_list_command = Command(
        name="list",
        header="List check bundles and the loaded checks with scope, fixability, and summaries.",
        options=(flag(long="json", help="Emit the check catalog as JSON instead of text."),),
        decode=_unused_decode,
    )
    check_show_command = Command(
        name="show",
        aliases=(CommandAlias("describe", hidden=True),),
        header="Show issue IDs, bundles, config knobs, and suppression examples for one check.",
        options=(flag(long="json", help="Emit the detailed check description as JSON instead of text."),),
        positionals=(positional(check_name_argument, "check", help="The stable check ID or legacy class name to inspect."),),
        decode=_unused_decode,
    )
    check_config_command = Command(
        name="config",
        header="Parse and validate root.clj and root.private.clj.",
        decode=_unused_decode,
    )
    check_command = Command(
        name="check",
        header="Run repository and source checks, or inspect the loaded check catalog.",
        options=(
            option(
                check_bundle_argument,
                long="bundle",
                help="Restrict the run to one check bundle. Repeatable.",
                repeated=True,
                meta_var="BUNDLE",
            ),
            option(
                check_name_argument,
                long="only",
                help="Restrict the run to specific check IDs or legacy class names. Repeatable.",
                repeated=True,
                meta_var="CHECK",
            ),
            flag(long="fix", help="Apply fixes for issues that provide an automatic fix callback."),
        ),
        positionals=(
            positional(
                _check_run_argument(),
                "arg",
                help="Target, check bundle names such as `docs` or `python`, and/or explicit check IDs in any order.",
                repeated=True,
            ),
        ),
        subcommands=(check_run_command, check_list_command, check_show_command, check_config_command),
        subcommand_fallback_to_positionals=True,
        decode=_unused_decode,
        help_on_empty=True,
    )
    spdx_headers_command = Command(
        name="headers",
        header="Audit or fix SPDX file headers.",
        options=(flag(long="fix", help="Insert or normalize SPDX headers when the check can do so safely."),),
        positionals=(
            positional(
                check_target_argument,
                "target",
                help="Filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`.",
                required=False,
            ),
        ),
        decode=_unused_decode,
    )
    spdx_command = Command(
        name="spdx",
        header="SPDX-related quality commands.",
        subcommands=(spdx_headers_command,),
        decode=_unused_decode,
        help_on_empty=True,
        visibility=Visibility.HIDDEN,
    )
    secrets_scan_command = Command(
        name="scan",
        header="Run the high-entropy-string secret check.",
        positionals=(
            positional(
                check_target_argument,
                "target",
                help="Filesystem path, bare project/repo ID, `:project-id`, `:repo-id`, or `:root`.",
                required=False,
            ),
        ),
        decode=_unused_decode,
    )
    secrets_command = Command(
        name="secrets",
        header="Scan for secrets and secret-like strings.",
        subcommands=(secrets_scan_command,),
        decode=_unused_decode,
        help_on_empty=True,
        visibility=Visibility.HIDDEN,
    )
    contributors_audit_command = Command(
        name="audit",
        header="Audit git contributor identity mismatches across configured repos.",
        decode=_unused_decode,
    )
    contributors_command = Command(
        name="contributors",
        header="Inspect repository contributor identity.",
        subcommands=(contributors_audit_command,),
        decode=_unused_decode,
        help_on_empty=True,
        visibility=Visibility.HIDDEN,
    )
    project_list_command = Command(
        name="list",
        header="List configured projects grouped by repository.",
        decode=_unused_decode,
    )
    project_show_command = Command(
        name="show",
        header="Show detailed metadata for one or more configured projects.",
        options=(flag(long="json", help="Emit project metadata as JSON."),),
        positionals=(positional(project_target_argument, "target", help="Project IDs, repo IDs, or paths.", repeated=True),),
        decode=_unused_decode,
    )
    project_deps_command = Command(
        name="deps",
        header="Show resolved dependencies for one or more configured projects.",
        options=(flag(long="json", help="Emit resolved dependencies as JSON."),),
        positionals=(positional(project_target_argument, "target", help="Project IDs, repo IDs, or paths.", repeated=True),),
        decode=_unused_decode,
    )
    project_repo_command = Command(
        name="repo",
        header="Show repository metadata for one or more configured targets.",
        options=(flag(long="json", help="Emit repo metadata as JSON."),),
        positionals=(positional(repo_target_argument, "target", help="Project IDs, repo IDs, or paths.", repeated=True),),
        decode=_unused_decode,
    )
    project_targets_command = Command(
        name="targets",
        header="Show Kotlin Multiplatform target platforms for configured projects.",
        options=(flag(long="json", help="Emit KMP target platform data as JSON."),),
        positionals=(positional(project_target_argument, "target", help="Project IDs, repo IDs, or paths.", repeated=True),),
        decode=_unused_decode,
    )
    project_versions_command = Command(
        name="versions",
        header="Show current, tagged, and registry-visible versions for one configured project.",
        options=(flag(long="json", help="Emit version source data as JSON."),),
        positionals=(
            positional(
                project_target_argument,
                "target",
                help="One project ID or path inside a configured project.",
                repeated=True,
            ),
        ),
        decode=_unused_decode,
    )
    project_command = Command(
        name="project",
        header="Explore the projects defined in root.clj and how repo-managed projects are grouped under their parent repositories.",
        subcommands=(
            project_list_command,
            project_show_command,
            project_deps_command,
            project_repo_command,
            project_targets_command,
            project_versions_command,
        ),
        decode=_unused_decode,
        help_on_empty=True,
    )
    root = Command(
        name=prog,
        header=(
            "Wabbit development toolkit.\n\n"
            "The CLI reads workspace metadata from root.clj and root.private.clj to\n"
            "generate project files, run checks, inspect dependencies, build projects,\n"
            "publish releases, and automate repository maintenance tasks."
        ),
        subcommands=(
            where_command,
            config_command,
            install_command,
            completion_command,
            doctor_command,
            verify_command,
            docs_command,
            setup_command,
            release_command,
            security_command,
            llmcopy_command,
            ask_command,
            dep_command,
            publish_command,
            build_command,
            duplicates_command,
            jitpack_command,
            clean_command,
            cloc_command,
            status_command,
            checkout_command,
            service_command,
            commit_command,
            push_command,
            backup_command,
            check_command,
            spdx_command,
            secrets_command,
            contributors_command,
            project_command,
        ),
        decode=_root_decode,
        help_on_empty=True,
        footer=(
            "Examples:\n"
            f"  {prog} doctor\n"
            f"  {prog} where\n"
            f"  {prog} service start\n"
            f"  {prog} service dashboard\n"
            f"  {prog} backup push\n"
            f"  {prog} completion bash\n"
            f"  {prog} ask gpt \"Summarize the last release blockers.\"\n"
            f"  {prog} setup --local app-datatron\n"
            f"  {prog} build app-datatron\n"
            f"  {prog} check --bundle security .\n"
            f"  {prog} verify security .\n"
            f"  {prog} project list\n\n"
            "Notes:\n"
            "  - Install the package and run `dev` (or `wabbit-dev`) from anywhere in the workspace.\n"
            "  - When a workspace `.venv` exists next to `root.clj`, the launcher prefers it automatically.\n"
            "  - Config-driven commands walk upward from the current directory to find root.clj and root.private.clj."
        ),
    )

    def _preflight(command_path: str, targets: list[str] | None = None, *, dry_run: bool = False) -> bool:
        from dev.tasks.doctor import preflight_for_command

        projects = tuple(targets) if targets else None
        return preflight_for_command(command_path, prog=prog, projects=projects, dry_run=dry_run)

    async def _run_request(request: TypedRequest, _issues: Sequence[Issue]) -> int:
        match request:
            case WhereRequest(json_output=json_output):
                if not _preflight("where"):
                    return 2
                from dev.tasks.where import show_where

                return show_where(json_output=json_output)
            case ConfigCheckRequest():
                if not _preflight("check/config"):
                    return 2
                from dev.tasks.check_config import check_config

                check_config()
                return 0
            case ConfigCutRequest(output_path=output_path, targets=targets):
                from dev.tasks.config_cut import config_cut

                config_cut(output_path, requested_targets=targets)
                return 0
            case InstallAppRequest(bin_dir=bin_dir):
                from dev.tasks.install import install_app

                install_app(bin_dir=bin_dir)
                return 0
            case InstallCompletionsRequest(shell=shell, update_rc=update_rc):
                from dev.tasks.install import install_completions

                install_completions(
                    shell=shell,
                    update_rc=update_rc,
                    dev_bash=root.render_bash_completion("dev"),
                    wabbit_dev_bash=root.render_bash_completion("wabbit-dev"),
                    dev_zsh=root.render_zsh_completion("dev"),
                    wabbit_dev_zsh=root.render_zsh_completion("wabbit-dev"),
                )
                return 0
            case InstallToolsRequest(tools=tools, force=force, json_output=json_output):
                from dev.tasks.install import install_tools

                result = install_tools(tools, force=force, json_output=json_output)
                if any(tool_result.status == "failed" for tool_result in result.results):
                    return 1
                return 0
            case InstallHooksRequest(targets=targets, json_output=json_output):
                targets = _repo_targets_with_defaults(targets)
                from dev.tasks.install import install_hooks

                hook_install_result = install_hooks(targets, json_output=json_output)
                if any(hook_result.status == "failed" for hook_result in hook_install_result.results):
                    return 1
                return 0
            case CompletionBashRequest():
                print(root.render_bash_completion(prog))
                return 0
            case CompletionZshRequest():
                print(root.render_zsh_completion(prog))
                return 0
            case CompletionQueryRequest(shell=shell, index=index, words=words):
                del shell
                response = root.completion_response(["__complete", str(index), "--", *words])
                if response is not None:
                    print(response)
                return 0
            case DoctorRequest(targets=targets, only=only, json_output=json_output):
                from dev.tasks.doctor import doctor

                exit_code = doctor(
                    json_output=json_output,
                    only=only if only else None,
                    targets=targets,
                )
                _print_next_steps("doctor", targets=targets, json_output=json_output)
                return exit_code
            case VerifyListRequest(json_output=json_output):
                from dev.tasks.verify import list_verify_workflows

                return list_verify_workflows(json_output=json_output)
            case VerifyDocsRequest(targets=targets, semantic=semantic, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("verify/docs", targets):
                    return 2
                from dev.tasks.docs_check import docs_check

                return docs_check(targets, semantic=semantic, json_output=json_output)
            case VerifyReleaseRequest(targets=targets, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("verify/release", targets):
                    return 2
                from dev.tasks.release_verify import release_verify

                exit_code = release_verify(targets, json_output=json_output)
                _print_next_steps("verify/release", targets=targets, json_output=json_output)
                return exit_code
            case VerifySecurityRequest(targets=targets, tools=tools, json_output=json_output):
                targets = _repo_targets_with_defaults(targets)
                if not _preflight("verify/security", targets):
                    return 2
                from dev.tasks.security_scan import security_scan

                return security_scan(targets, tools=tools, json_output=json_output)
            case DocsCheckRequest(targets=targets, semantic=semantic, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("docs/check", targets):
                    return 2
                from dev.tasks.docs_check import docs_check

                return docs_check(targets, semantic=semantic, json_output=json_output)
            case DocsSnippetsRequest(targets=targets, verify=verify, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("docs/snippets", targets):
                    return 2
                from dev.tasks.docs_check import docs_snippets

                return docs_snippets(targets, verify=verify, json_output=json_output)
            case SetupRequest(
                targets=targets,
                dev_mode=dev_mode,
                local_mode=local_mode,
                commit_if_setup_only=commit_if_setup_only,
                json_output=json_output,
            ):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("setup", targets):
                    return 2
                from dev.tasks.setup import RepoSetupMode, setup

                if local_mode:
                    mode = RepoSetupMode.LOCAL
                elif dev_mode:
                    mode = RepoSetupMode.DEV
                else:
                    mode = RepoSetupMode.PROD
                exit_code = setup(
                    mode,
                    projects=targets,
                    interactive=sys.stdin.isatty() and not json_output,
                    commit_if_setup_only=commit_if_setup_only,
                    json_output=json_output,
                )
                _print_next_steps("setup", targets=targets, json_output=json_output)
                return exit_code
            case ReleaseVerifyRequest(targets=targets, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("release/verify", targets):
                    return 2
                from dev.tasks.release_verify import release_verify

                exit_code = release_verify(targets, json_output=json_output)
                _print_next_steps("release/verify", targets=targets, json_output=json_output)
                return exit_code
            case ReleaseBundleRequest(targets=targets, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("release/bundle", targets):
                    return 2
                from dev.tasks.release_bundle import release_bundle

                exit_code = release_bundle(targets, json_output=json_output)
                _print_next_steps("release/bundle", targets=targets, json_output=json_output)
                return exit_code
            case SecurityScanRequest(targets=targets, tools=tools, json_output=json_output):
                targets = _repo_targets_with_defaults(targets)
                if not _preflight("security/scan", targets):
                    return 2
                from dev.tasks.security_scan import security_scan

                return security_scan(targets, tools=tools, json_output=json_output)
            case LlmcopyRequest(paths=paths):
                from dev.tasks.llmcopy import llmcopy

                llmcopy(paths)
                return 0
            case AskRequest(
                provider=provider,
                conversation_id=conversation_id,
                file_paths=file_paths,
                prompt=prompt,
                model=model,
            ):
                from dev.tasks.ask import ask as ask_task

                return ask_task(
                    provider,
                    prompt=prompt,
                    conversation_id=conversation_id,
                    file_paths=file_paths,
                    model=model,
                )
            case PublishRequest(targets=targets, dry_run=dry_run):
                if not _preflight("publish", targets, dry_run=dry_run):
                    return 2
                from dev.tasks.publish import publish_main

                exit_code = await publish_main(targets, dry_run=dry_run)
                _print_next_steps("publish", targets=targets, dry_run=dry_run)
                return exit_code
            case DuplicatesRequest(
                folders=folders,
                exclude=exclude,
                include=include,
                min_size=min_size,
                no_default_excludes=no_default_excludes,
                zip_contents=zip_contents,
                weak_encrypted_zip=weak_encrypted_zip,
            ):
                from dev.tasks.duplicates import check_for_duplicates

                check_for_duplicates(
                    folders,
                    exclude,
                    include,
                    min_size,
                    no_default_excludes,
                    include_zip_contents=zip_contents,
                    include_weak_encrypted_zip=weak_encrypted_zip,
                )
                return 0
            case JitpackInfoRequest(group=group, artifact=artifact, version=version):
                from dev.tasks.jitpack import get_jitpack_info

                await get_jitpack_info(group, artifact, version)
                return 0
            case DepGraphRequest(targets=targets, artifacts=artifacts):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("dep/graph", targets):
                    return 2
                from dev.tasks.dep_graph import get_project_dependencies

                get_project_dependencies(
                    focus_project_names=targets if targets else None,
                    include_artifacts=artifacts,
                )
                return 0
            case DepUpdatesRequest():
                if not _preflight("dep/updates"):
                    return 2
                from dev.tasks.dep_updates import check_for_updates

                check_for_updates()
                return 0
            case BuildRequest(targets=targets, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("build", targets):
                    return 2
                from dev.tasks.build import build

                exit_code = build(targets, json_output=json_output)
                _print_next_steps("build", targets=targets, json_output=json_output)
                return exit_code
            case CleanRequest(targets=targets):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("clean", targets):
                    return 2
                from dev.tasks.clean import clean

                clean(targets)
                return 0
            case ClocRequest(targets=targets):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("cloc", targets):
                    return 2
                from dev.tasks.cloc import cloc

                cloc(targets)
                return 0
            case StatusRequest(targets=targets, json_output=json_output):
                targets = _repo_targets_with_defaults(targets)
                if not _preflight("status", targets):
                    return 2
                from dev.tasks.status import status

                return status(targets, json_output=json_output)
            case CheckoutRequest(targets=targets, dry_run=dry_run, json_output=json_output):
                targets = _repo_targets_with_defaults(targets)
                if not _preflight("checkout", targets, json_output=json_output, dry_run=dry_run):
                    return 2
                from dev.tasks.checkout import checkout

                exit_code = checkout(targets, dry_run=dry_run, json_output=json_output)
                _print_next_steps("checkout", targets=targets, json_output=json_output, dry_run=dry_run)
                return exit_code
            case ServiceStartRequest(interval_seconds=interval_seconds):
                from dev.tasks.service import service_start

                return service_start(interval_seconds=interval_seconds)
            case ServiceStopRequest():
                from dev.tasks.service import service_stop

                return service_stop()
            case ServiceStatusRequest():
                from dev.tasks.service import service_status

                return service_status()
            case ServiceDashboardRequest(interval_seconds=interval_seconds):
                from dev.tasks.service import service_dashboard

                return service_dashboard(interval_seconds=interval_seconds)
            case CommitRequest(targets=targets, dry_run=dry_run):
                if not _preflight("commit", targets, dry_run=dry_run):
                    return 2
                from dev.tasks.commit import commit

                exit_code = commit(targets, dry_run=dry_run)
                _print_next_steps("commit", targets=targets, dry_run=dry_run)
                return exit_code
            case CommitVerifyRequest(
                target=target,
                message_file=message_file,
                message=message,
                revision_range=revision_range,
                staged=staged,
                json_output=json_output,
                quiet=quiet,
            ):
                from dev.tasks.commit_verify import commit_verify

                return commit_verify(
                    target=target,
                    message_file=message_file,
                    message=message,
                    revision_range=revision_range,
                    staged=staged,
                    json_output=json_output,
                    quiet=quiet,
                )
            case PushRequest(targets=targets, dry_run=dry_run):
                if not _preflight("push", targets, dry_run=dry_run):
                    return 2
                from dev.tasks.push import push

                exit_code = push(targets, dry_run=dry_run)
                _print_next_steps("push", targets=targets, dry_run=dry_run)
                return exit_code
            case BackupPushRequest(
                repo_targets=repo_targets,
                backup_target_name=backup_target_name,
                dry_run=dry_run,
                json_output=json_output,
            ):
                from dev.tasks.backup import push

                return push(
                    repo_targets,
                    backup_target_name=backup_target_name,
                    dry_run=dry_run,
                    json_output=json_output,
                )
            case BackupRestoreRequest(
                repo_target=repo_target,
                backup_target_name=backup_target_name,
                snapshot=snapshot,
                into=into,
                dry_run=dry_run,
                json_output=json_output,
            ):
                from dev.tasks.backup import restore

                return restore(
                    repo_target,
                    backup_target_name=backup_target_name,
                    snapshot=snapshot,
                    into=into,
                    dry_run=dry_run,
                    json_output=json_output,
                )
            case CheckRunRequest(
                target=target,
                selectors=selectors,
                bundles=bundles,
                fix=fix,
                json_output=json_output,
            ):
                if not _preflight("check/run"):
                    return 2
                from dev.tasks.check import check_main

                return check_main(
                    target,
                    selectors if selectors else None,
                    fix,
                    bundles=bundles,
                    json_output=json_output,
                )
            case CheckListRequest(json_output=json_output):
                if not _preflight("check/list"):
                    return 2
                from dev.tasks.check import list_checks

                return list_checks(json_output=json_output)
            case CheckShowRequest(check=check, json_output=json_output):
                if not _preflight("check/show"):
                    return 2
                from dev.tasks.check import show_check

                return show_check(check, json_output=json_output)
            case SpdxHeadersRequest(target=target, fix=fix):
                if not _preflight("spdx/headers"):
                    return 2
                from dev.tasks.spdx_headers import spdx_headers

                return spdx_headers(target, fix)
            case SecretsScanRequest(target=target):
                if not _preflight("secrets/scan"):
                    return 2
                from dev.tasks.check import secrets_scan

                return secrets_scan(target)
            case ContributorsAuditRequest():
                if not _preflight("contributors/audit"):
                    return 2
                from dev.tasks.contributors_audit import audit_contributors

                return audit_contributors()
            case ProjectListRequest():
                if not _preflight("project/list"):
                    return 2
                from dev.tasks.project_list import list_projects

                list_projects()
                return 0
            case ProjectShowRequest(targets=targets, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("project/show", targets):
                    return 2
                from dev.tasks.project_list import show_projects

                show_projects(targets, json_output=json_output)
                _print_next_steps("project/show", targets=targets, json_output=json_output)
                return 0
            case ProjectDepsRequest(targets=targets, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("project/deps", targets):
                    return 2
                from dev.tasks.project_list import show_project_dependencies

                show_project_dependencies(targets, json_output=json_output)
                return 0
            case ProjectRepoRequest(targets=targets, json_output=json_output):
                targets = _repo_targets_with_defaults(targets)
                if not _preflight("project/repo", targets):
                    return 2
                from dev.tasks.project_list import show_project_repos

                show_project_repos(targets, json_output=json_output)
                return 0
            case ProjectTargetsRequest(targets=targets, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("project/targets", targets):
                    return 2
                from dev.tasks.project_list import show_project_targets

                show_project_targets(targets, json_output=json_output)
                return 0
            case ProjectVersionsRequest(targets=targets, json_output=json_output):
                targets = _project_targets_with_defaults(targets)
                if not _preflight("project/versions", targets):
                    return 2
                from dev.tasks.project_versions import show_project_versions

                return show_project_versions(targets, json_output=json_output)
            case None:
                return 0

    active_request: TypedRequest | None = None
    try:
        normalized_argv = _normalize_argv(argv, root)
        match root.dispatch(normalized_argv):
            case CommandCompletion(text=text):
                print(text)
                return 0
            case CommandHelp(text=text):
                print(text)
                return 0
            case CommandFailure(issues=issues):
                print(root.render_failure(issues), file=sys.stderr)
                return 2
            case CommandParsed(value=request, issues=issues):
                active_request = request
                return await _run_request(request, issues)
    except ModuleNotFoundError as ex:
        print(f"{prog}: error: Missing Python dependency: {ex.name!r}.", file=sys.stderr)
        _print_failure_context(active_request)
        return 2
    except ValueError as ex:
        print(f"{prog}: error: {ex}", file=sys.stderr)
        _print_failure_context(active_request)
        return 2
    return None
