from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from dev.config import Config, DotnetProject, GradleProject, Project, PythonProject, load_config
from dev.discoverability import require_project
from dev.git_env import git_subprocess_env
from dev.json_types import JSONObject, JSONValue
from dev.maven import MAVEN_CENTRAL_BASE_URL, MavenMetadata, MavenVersion
from dev.messages import accent, heading, muted, style, warning
from dev.nuget import NuGetPackageMetadata, fetch_package_metadata
from dev.pypi import PyPiProjectMetadata
from dev.repo_resolution import (
    contextualize_resolution_error,
    inferred_project_targets,
    resolve_project_ids,
    resolve_workspace_context,
)
from dev.tasks.publish import PublishTarget, determine_publish_target

_VERSION_TAG_RE = re.compile(r"^v?(?P<version>\d+\.\d+\.\d+(?:[A-Za-z0-9+._-]*)?)$")


@dataclass(frozen=True)
class VersionTag:
    tag: str
    version: str


@dataclass(frozen=True)
class VersionDiagnostic:
    source: str
    message: str

    def to_payload(self) -> JSONObject:
        return {
            "source": self.source,
            "message": self.message,
        }


@dataclass(frozen=True)
class RegistrySnapshot:
    name: str
    package: str
    latest: str | None
    versions: tuple[str, ...]
    diagnostics: tuple[VersionDiagnostic, ...] = ()

    def to_payload(self) -> JSONObject:
        return {
            "name": self.name,
            "package": self.package,
            "latest": self.latest,
            "versions": list(self.versions),
        }


@dataclass(frozen=True)
class GitStatusEntry:
    code: str
    path: str

    def to_payload(self) -> JSONObject:
        return {
            "code": self.code,
            "path": self.path,
        }


@dataclass(frozen=True)
class GitWorkingTreeState:
    entries: tuple[GitStatusEntry, ...]

    @property
    def file_count(self) -> int:
        return len(self.entries)

    @property
    def clean(self) -> bool:
        return not self.entries

    @property
    def staged_count(self) -> int:
        return sum(1 for entry in self.entries if entry.code != "??" and entry.code[0] != " ")

    @property
    def unstaged_count(self) -> int:
        return sum(1 for entry in self.entries if entry.code != "??" and entry.code[1] != " ")

    @property
    def untracked_count(self) -> int:
        return sum(1 for entry in self.entries if entry.code == "??")

    @property
    def conflicted_count(self) -> int:
        conflict_codes = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
        return sum(1 for entry in self.entries if entry.code in conflict_codes)

    def to_payload(self) -> JSONObject:
        return {
            "clean": self.clean,
            "fileCount": self.file_count,
            "stagedCount": self.staged_count,
            "unstagedCount": self.unstaged_count,
            "untrackedCount": self.untracked_count,
            "conflictedCount": self.conflicted_count,
            "entries": [entry.to_payload() for entry in self.entries],
        }


@dataclass(frozen=True)
class LatestTagState:
    tag: str
    version: str
    commits_after: int

    def to_payload(self) -> JSONObject:
        return {
            "tag": self.tag,
            "version": self.version,
            "commitsAfter": self.commits_after,
        }


@dataclass(frozen=True)
class GitState:
    branch: str | None
    remote: str | None
    remote_branch: str | None
    remote_head: str | None
    unpushed_commits: int | None
    remote_only_commits: int | None
    latest_tag: LatestTagState | None
    working_tree: GitWorkingTreeState

    def to_payload(self) -> JSONObject:
        latest_tag = None
        if self.latest_tag is not None:
            latest_tag = self.latest_tag.to_payload()
        return {
            "branch": self.branch,
            "remote": self.remote,
            "remoteBranch": self.remote_branch,
            "remoteHead": self.remote_head,
            "unpushedCommits": self.unpushed_commits,
            "remoteOnlyCommits": self.remote_only_commits,
            "latestTag": latest_tag,
            "workingTree": self.working_tree.to_payload(),
        }


@dataclass
class _VersionBuilder:
    version: str
    current: bool = False
    local_tags: set[str] = field(default_factory=set)
    remote_tags: set[str] = field(default_factory=set)
    registries: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class VersionRow:
    version: str
    current: bool
    local_tags: tuple[str, ...]
    remote_tags: tuple[str, ...]
    registries: tuple[str, ...]

    @property
    def sources(self) -> tuple[str, ...]:
        values: list[str] = []
        if self.current:
            values.append("current")
        if self.local_tags:
            values.append("local-tag")
        if self.remote_tags:
            values.append("remote-tag")
        values.extend(self.registries)
        return tuple(values)

    def to_payload(self) -> JSONObject:
        return {
            "version": self.version,
            "current": self.current,
            "localTags": list(self.local_tags),
            "remoteTags": list(self.remote_tags),
            "registries": list(self.registries),
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class ProjectVersionReport:
    project_id: str
    project_path: Path
    repo_root: Path
    current_version: str | None
    publish_target: PublishTarget
    registries: tuple[RegistrySnapshot, ...]
    git_state: GitState
    versions: tuple[VersionRow, ...]
    diagnostics: tuple[VersionDiagnostic, ...]

    @property
    def registry(self) -> RegistrySnapshot | None:
        return self.registries[0] if self.registries else None

    def to_payload(self) -> JSONObject:
        registry_payload = None
        primary_registry = self.registry
        if primary_registry is not None:
            registry_payload = primary_registry.to_payload()
        return {
            "projectId": self.project_id,
            "path": str(self.project_path.resolve()),
            "repoRoot": str(self.repo_root.resolve()),
            "currentVersion": self.current_version,
            "publishTarget": self.publish_target,
            "registry": registry_payload,
            "registries": [registry.to_payload() for registry in self.registries],
            "gitState": self.git_state.to_payload(),
            "versions": [row.to_payload() for row in self.versions],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }


def _normalize_version_tag(tag: str) -> VersionTag | None:
    match = _VERSION_TAG_RE.fullmatch(tag.strip())
    if match is None:
        return None
    return VersionTag(tag=tag, version=match.group("version"))


def _run_git(repo_root: Path, args: list[str], config: Config) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        env=git_subprocess_env(config),
        text=True,
        check=False,
    )


def _diagnostic_from_git_failure(source: str, result: subprocess.CompletedProcess[str]) -> VersionDiagnostic:
    message = result.stderr.strip() or result.stdout.strip() or f"git exited with code {result.returncode}"
    return VersionDiagnostic(source=source, message=message)


def _local_tag_versions(repo_root: Path, config: Config) -> tuple[tuple[VersionTag, ...], tuple[VersionDiagnostic, ...]]:
    result = _run_git(repo_root, ["tag", "--list"], config)
    if result.returncode != 0:
        return (), (_diagnostic_from_git_failure("local-tags", result),)

    tags: list[VersionTag] = []
    for line in result.stdout.splitlines():
        normalized = _normalize_version_tag(line)
        if normalized is not None:
            tags.append(normalized)
    return tuple(tags), ()


def _default_remote(repo_root: Path, config: Config) -> tuple[str | None, tuple[VersionDiagnostic, ...]]:
    result = _run_git(repo_root, ["remote"], config)
    if result.returncode != 0:
        return None, (_diagnostic_from_git_failure("remote-tags", result),)

    remotes = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not remotes:
        return None, (VersionDiagnostic(source="remote-tags", message="repository has no git remotes"),)
    if "origin" in remotes:
        return "origin", ()
    return remotes[0], ()


def _remote_tag_versions(repo_root: Path, config: Config) -> tuple[tuple[VersionTag, ...], tuple[VersionDiagnostic, ...]]:
    remote, diagnostics = _default_remote(repo_root, config)
    if remote is None:
        return (), diagnostics

    result = _run_git(repo_root, ["ls-remote", "--tags", remote], config)
    if result.returncode != 0:
        return (), (_diagnostic_from_git_failure("remote-tags", result),)

    tags: list[VersionTag] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        ref = parts[1]
        if ref.endswith("^{}"):
            continue
        tag = ref.removeprefix("refs/tags/")
        normalized = _normalize_version_tag(tag)
        if normalized is not None:
            tags.append(normalized)
    return tuple(tags), ()


def _int_from_git_stdout(source: str, result: subprocess.CompletedProcess[str]) -> tuple[int | None, tuple[VersionDiagnostic, ...]]:
    if result.returncode != 0:
        return None, (_diagnostic_from_git_failure(source, result),)
    value = result.stdout.strip()
    if not value.isdigit():
        return None, (VersionDiagnostic(source=source, message=f"expected integer git output, got {value!r}"),)
    return int(value), ()


def _current_branch(repo_root: Path, config: Config) -> tuple[str | None, tuple[VersionDiagnostic, ...]]:
    result = _run_git(repo_root, ["branch", "--show-current"], config)
    if result.returncode != 0:
        return None, (_diagnostic_from_git_failure("git-branch", result),)
    branch = result.stdout.strip()
    if not branch:
        return None, (VersionDiagnostic(source="git-branch", message="repository is in detached HEAD state"),)
    return branch, ()


def _upstream_target(
    repo_root: Path,
    config: Config,
    branch: str | None,
) -> tuple[str | None, str | None, tuple[VersionDiagnostic, ...]]:
    result = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], config)
    if result.returncode == 0:
        upstream = result.stdout.strip()
        match upstream.split("/", 1):
            case [remote, remote_branch] if remote and remote_branch:
                return remote, remote_branch, ()
            case _:
                return None, None, (
                    VersionDiagnostic(source="git-upstream", message=f"could not parse upstream branch {upstream!r}"),
                )

    remote, remote_diagnostics = _default_remote(repo_root, config)
    if remote is not None and branch is not None:
        return remote, branch, remote_diagnostics
    return remote, None, (
        *remote_diagnostics,
        VersionDiagnostic(source="git-upstream", message="current branch has no configured upstream"),
    )


def _remote_branch_state(
    repo_root: Path,
    config: Config,
    remote: str | None,
    remote_branch: str | None,
) -> tuple[str | None, int | None, int | None, tuple[VersionDiagnostic, ...]]:
    if remote is None or remote_branch is None:
        return None, None, None, ()

    fetch_result = _run_git(repo_root, ["fetch", "--quiet", "--no-tags", remote, remote_branch], config)
    if fetch_result.returncode != 0:
        return None, None, None, (_diagnostic_from_git_failure("git-upstream", fetch_result),)

    remote_head_result = _run_git(repo_root, ["rev-parse", "FETCH_HEAD"], config)
    if remote_head_result.returncode != 0:
        return None, None, None, (_diagnostic_from_git_failure("git-upstream", remote_head_result),)
    remote_head = remote_head_result.stdout.strip()

    unpushed_result = _run_git(repo_root, ["rev-list", "--count", "FETCH_HEAD..HEAD"], config)
    unpushed_count, unpushed_diagnostics = _int_from_git_stdout("git-unpushed", unpushed_result)
    remote_only_result = _run_git(repo_root, ["rev-list", "--count", "HEAD..FETCH_HEAD"], config)
    remote_only_count, remote_only_diagnostics = _int_from_git_stdout("git-unpushed", remote_only_result)
    return remote_head, unpushed_count, remote_only_count, (*unpushed_diagnostics, *remote_only_diagnostics)


def _working_tree_state(repo_root: Path, config: Config) -> tuple[GitWorkingTreeState, tuple[VersionDiagnostic, ...]]:
    result = _run_git(repo_root, ["status", "--porcelain=1", "--untracked-files=all"], config)
    if result.returncode != 0:
        return GitWorkingTreeState(entries=()), (_diagnostic_from_git_failure("git-status", result),)

    entries: list[GitStatusEntry] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        entries.append(GitStatusEntry(code=line[:2], path=line[3:]))
    return GitWorkingTreeState(entries=tuple(entries)), ()


def _commits_after_tag(repo_root: Path, config: Config, tag: VersionTag) -> tuple[int | None, tuple[VersionDiagnostic, ...]]:
    result = _run_git(repo_root, ["rev-list", "--count", f"{tag.tag}..HEAD"], config)
    return _int_from_git_stdout("git-latest-tag", result)


def _latest_tag_state(repo_root: Path, config: Config) -> tuple[LatestTagState | None, tuple[VersionDiagnostic, ...]]:
    result = _run_git(repo_root, ["tag", "--merged", "HEAD", "--list"], config)
    if result.returncode != 0:
        return None, (_diagnostic_from_git_failure("git-latest-tag", result),)

    version_tags: list[VersionTag] = []
    for line in result.stdout.splitlines():
        normalized = _normalize_version_tag(line)
        if normalized is not None:
            version_tags.append(normalized)
    if not version_tags:
        return None, (VersionDiagnostic(source="git-latest-tag", message="no version-like tag is reachable from HEAD"),)

    highest_version = max(MavenVersion.parse(tag.version) for tag in version_tags)
    candidates = [tag for tag in version_tags if MavenVersion.parse(tag.version) == highest_version]
    best_state: LatestTagState | None = None
    diagnostics: list[VersionDiagnostic] = []
    for tag in candidates:
        commits_after, count_diagnostics = _commits_after_tag(repo_root, config, tag)
        diagnostics.extend(count_diagnostics)
        if commits_after is None:
            continue
        candidate_state = LatestTagState(tag=tag.tag, version=tag.version, commits_after=commits_after)
        if best_state is None or candidate_state.commits_after < best_state.commits_after:
            best_state = candidate_state

    return best_state, tuple(diagnostics)


def _git_state(repo_root: Path, config: Config) -> tuple[GitState, tuple[VersionDiagnostic, ...]]:
    diagnostics: list[VersionDiagnostic] = []
    working_tree, working_tree_diagnostics = _working_tree_state(repo_root, config)
    diagnostics.extend(working_tree_diagnostics)

    branch, branch_diagnostics = _current_branch(repo_root, config)
    diagnostics.extend(branch_diagnostics)

    remote, remote_branch, upstream_diagnostics = _upstream_target(repo_root, config, branch)
    diagnostics.extend(upstream_diagnostics)

    remote_head, unpushed_commits, remote_only_commits, remote_branch_diagnostics = _remote_branch_state(
        repo_root,
        config,
        remote,
        remote_branch,
    )
    diagnostics.extend(remote_branch_diagnostics)

    latest_tag, latest_tag_diagnostics = _latest_tag_state(repo_root, config)
    diagnostics.extend(latest_tag_diagnostics)

    return (
        GitState(
            branch=branch,
            remote=remote,
            remote_branch=remote_branch,
            remote_head=remote_head,
            unpushed_commits=unpushed_commits,
            remote_only_commits=remote_only_commits,
            latest_tag=latest_tag,
            working_tree=working_tree,
        ),
        tuple(diagnostics),
    )


def _current_version(project: Project) -> str | None:
    match project:
        case GradleProject(version=version):
            return str(version) if version is not None else None
        case DotnetProject(version=version):
            return str(version) if version is not None else None
        case PythonProject(version=version):
            return str(version) if version is not None else None
        case _:
            return None


def _fetch_maven_central_metadata(group_id: str, artifact_id: str) -> MavenMetadata:
    import requests

    url = f"{MAVEN_CENTRAL_BASE_URL}{group_id.replace('.', '/')}/{artifact_id}/maven-metadata.xml"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return MavenMetadata.parse(response.text)


def _fetch_pypi_project_metadata(project_name: str) -> PyPiProjectMetadata:
    from urllib.parse import quote

    import requests

    encoded_name = quote(project_name, safe="")
    url = f"https://pypi.org/pypi/{encoded_name}/json"  # check:ignore E_HARDCODED_URL value=https://pypi.org/pypi/
    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    return PyPiProjectMetadata.parse(response.json())


def _maven_central_registry(project: GradleProject) -> RegistrySnapshot:
    package = f"{project.group_name}:{project.effective_artifact_id}"
    try:
        metadata = _fetch_maven_central_metadata(project.group_name, project.effective_artifact_id)
    except Exception as ex:
        return RegistrySnapshot(
            name="maven-central",
            package=package,
            latest=None,
            versions=(),
            diagnostics=(
                VersionDiagnostic(
                    source="maven-central",
                    message=f"could not query Maven Central metadata for {package}: {ex}",
                ),
            ),
        )
    return RegistrySnapshot(
        name="maven-central",
        package=package,
        latest=metadata.release or metadata.latest,
        versions=tuple(metadata.versions),
    )


def _pypi_registry(project: PythonProject) -> RegistrySnapshot:
    try:
        metadata = _fetch_pypi_project_metadata(project.name)
    except Exception as ex:
        return RegistrySnapshot(
            name="pypi",
            package=project.name,
            latest=None,
            versions=(),
            diagnostics=(
                VersionDiagnostic(
                    source="pypi",
                    message=f"could not query PyPI metadata for {project.name}: {ex}",
                ),
            ),
        )
    return RegistrySnapshot(
        name="pypi",
        package=project.name,
        latest=metadata.latest_version,
        versions=tuple(metadata.releases),
    )


def _nuget_registry(project: DotnetProject) -> RegistrySnapshot:
    package_id = project.effective_package_id
    try:
        metadata: NuGetPackageMetadata = fetch_package_metadata(package_id)
    except Exception as ex:
        return RegistrySnapshot(
            name="nuget",
            package=package_id,
            latest=None,
            versions=(),
            diagnostics=(
                VersionDiagnostic(
                    source="nuget",
                    message=f"could not query NuGet metadata for {package_id}: {ex}",
                ),
            ),
        )
    return RegistrySnapshot(
        name="nuget",
        package=package_id,
        latest=metadata.latest_version,
        versions=metadata.versions,
    )


def _jitpack_cookies(session_cookie: str | None) -> dict[str, str]:
    if session_cookie is None:
        return {}
    cookie = session_cookie.strip()
    if not cookie:
        return {}
    match cookie.split("=", 1):
        case [key, value] if key and value:
            return {key: value}
        case _:
            return {"sessionId": cookie}


def _parse_jitpack_versions_payload(payload: JSONValue, group_id: str, artifact_id: str) -> tuple[str, ...]:
    match payload:
        case dict() as root:
            group_payload = root.get(group_id)
        case _:
            raise ValueError("JitPack versions response must be a JSON object.")

    match group_payload:
        case dict() as grouped_payload:
            project_payload = grouped_payload.get(artifact_id)
        case _:
            raise ValueError(f"JitPack response is missing group {group_id!r}.")

    match project_payload:
        case dict() as version_payloads:
            pass
        case _:
            raise ValueError(f"JitPack response is missing artifact {artifact_id!r}.")

    versions: list[str] = []
    for version_key, version_payload in version_payloads.items():
        fallback_version: str | None = None
        match version_key:
            case str() as raw_key if raw_key.strip():
                fallback_version = raw_key.strip()
            case _:
                fallback_version = None

        match version_payload:
            case dict() as version_data:
                version = fallback_version
                match version_data.get("version"):
                    case str() as raw_version if raw_version.strip():
                        version = raw_version.strip()
                    case _:
                        pass
                match version_data.get("status"):
                    case "ok" if version is not None:
                        versions.append(version)
                    case _:
                        continue
            case _:
                continue

    return tuple(sorted(set(versions), key=MavenVersion.parse))


def _fetch_jitpack_versions(config: Config, group_id: str, artifact_id: str) -> tuple[str, ...]:
    import requests

    url = f"https://jitpack.io/api/versions/{group_id}/{artifact_id}"  # check:ignore E_HARDCODED_URL value=https://jitpack.io/api/versions/
    response = requests.get(
        url,
        cookies=_jitpack_cookies(config.jitpack_cookie),
        timeout=10,
    )
    response.raise_for_status()
    payload: JSONValue = response.json()
    return _parse_jitpack_versions_payload(payload, group_id, artifact_id)


def _jitpack_registry(project: GradleProject, config: Config) -> RegistrySnapshot:
    github_repo = project.github_repo
    artifact_id = project.effective_artifact_id
    if github_repo is None:
        return RegistrySnapshot(
            name="jitpack",
            package=f"<missing github_repo>:{artifact_id}",
            latest=None,
            versions=(),
            diagnostics=(
                VersionDiagnostic(
                    source="jitpack",
                    message=f"cannot query JitPack for {project.name}: project has no github_repo",
                ),
            ),
        )

    github_owner = github_repo.split("/", 1)[0].strip()
    group_id = f"com.github.{github_owner}"
    package = f"{group_id}:{artifact_id}"
    try:
        versions = _fetch_jitpack_versions(config, group_id, artifact_id)
    except Exception as ex:
        return RegistrySnapshot(
            name="jitpack",
            package=package,
            latest=None,
            versions=(),
            diagnostics=(
                VersionDiagnostic(
                    source="jitpack",
                    message=f"could not query JitPack metadata for {package}: {ex}",
                ),
            ),
        )

    latest = max(versions, key=MavenVersion.parse) if versions else None
    return RegistrySnapshot(
        name="jitpack",
        package=package,
        latest=latest,
        versions=versions,
    )


def _registry_snapshots(
    project: Project,
    config: Config,
) -> tuple[PublishTarget, tuple[RegistrySnapshot, ...], tuple[VersionDiagnostic, ...]]:
    publish_target = determine_publish_target(project)
    registries: list[RegistrySnapshot] = []
    match (publish_target, project):
        case ("maven-central", GradleProject() as gradle_project):
            registries.append(_maven_central_registry(gradle_project))
            registries.append(_jitpack_registry(gradle_project, config))
        case ("pypi", PythonProject() as python_project):
            registries.append(_pypi_registry(python_project))
        case ("nuget", DotnetProject() as dotnet_project):
            registries.append(_nuget_registry(dotnet_project))
        case ("jitpack", GradleProject() as gradle_project):
            registries.append(_jitpack_registry(gradle_project, config))
        case ("intellij-marketplace", GradleProject()):
            diagnostic = VersionDiagnostic(
                source="intellij-marketplace",
                message="IntelliJ Marketplace version visibility is not checked yet.",
            )
            return publish_target, (), (diagnostic,)
        case _:
            return publish_target, (), ()

    diagnostics: list[VersionDiagnostic] = []
    for registry in registries:
        diagnostics.extend(registry.diagnostics)
    return publish_target, tuple(registries), tuple(diagnostics)


def _version_sort_key(row: VersionRow) -> MavenVersion:
    return MavenVersion.parse(row.version)


def _registry_source_key(source: str) -> tuple[int, str]:
    match source:
        case "maven-central" | "pypi" | "nuget":
            return (0, source)
        case "jitpack":
            return (1, source)
        case _:
            return (2, source)


def build_project_version_report(project_id: str, config: Config) -> ProjectVersionReport:
    project = require_project(config, project_id)
    builders: dict[str, _VersionBuilder] = {}
    diagnostics: list[VersionDiagnostic] = []

    current_version = _current_version(project)
    if current_version is not None:
        builders[current_version] = _VersionBuilder(version=current_version, current=True)

    local_tags, local_diagnostics = _local_tag_versions(project.effective_repo_root, config)
    diagnostics.extend(local_diagnostics)
    for tag in local_tags:
        builder = builders.setdefault(tag.version, _VersionBuilder(version=tag.version))
        builder.local_tags.add(tag.tag)

    remote_tags, remote_diagnostics = _remote_tag_versions(project.effective_repo_root, config)
    diagnostics.extend(remote_diagnostics)
    for tag in remote_tags:
        builder = builders.setdefault(tag.version, _VersionBuilder(version=tag.version))
        builder.remote_tags.add(tag.tag)

    git_state, git_diagnostics = _git_state(project.effective_repo_root, config)
    diagnostics.extend(git_diagnostics)

    publish_target, registries, registry_diagnostics = _registry_snapshots(project, config)
    diagnostics.extend(registry_diagnostics)
    for registry in registries:
        for version in registry.versions:
            builder = builders.setdefault(version, _VersionBuilder(version=version))
            builder.registries.add(registry.name)

    rows = [
        VersionRow(
            version=builder.version,
            current=builder.current,
            local_tags=tuple(sorted(builder.local_tags)),
            remote_tags=tuple(sorted(builder.remote_tags)),
            registries=tuple(sorted(builder.registries, key=_registry_source_key)),
        )
        for builder in builders.values()
    ]

    return ProjectVersionReport(
        project_id=project.project_id or project.name,
        project_path=project.path,
        repo_root=project.effective_repo_root,
        current_version=current_version,
        publish_target=publish_target,
        registries=registries,
        git_state=git_state,
        versions=tuple(sorted(rows, key=_version_sort_key)),
        diagnostics=tuple(diagnostics),
    )


def _source_color(source: str) -> str:
    match source:
        case "current":
            return "green"
        case "local-tag":
            return "yellow"
        case "remote-tag":
            return "blue"
        case "maven-central" | "nuget" | "pypi" | "jitpack":
            return "cyan"
        case _:
            return "white"


def _render_source(source: str) -> str:
    return style(source, _source_color(source), attrs=("bold",))


def render_project_version_lines(report: ProjectVersionReport) -> list[str]:
    lines = [
        f"Project: {accent(report.project_id)}",
        f"Current version: {report.current_version or '-'}",
        f"Publish target: {report.publish_target}",
    ]
    if not report.registries:
        lines.append("Registry: -")
    elif len(report.registries) == 1:
        registry = report.registries[0]
        latest = registry.latest or "-"
        lines.append(f"Registry: {registry.name} ({registry.package}, latest {latest})")
    else:
        lines.append("Registries:")
        for registry in report.registries:
            latest = registry.latest or "-"
            lines.append(f"  - {registry.name} ({registry.package}, latest {latest})")

    git_state = report.git_state
    branch_text = git_state.branch or "-"
    if git_state.remote is not None and git_state.remote_branch is not None:
        branch_text = f"{branch_text} -> {git_state.remote}/{git_state.remote_branch}"
    lines.append("")
    lines.append(str(heading("Git State")))
    lines.append(f"Branch: {branch_text}")
    if git_state.unpushed_commits is None:
        lines.append("Local commits not pushed: unknown")
    else:
        lines.append(f"Local commits not pushed: {git_state.unpushed_commits}")
    if git_state.remote_only_commits is not None and git_state.remote_only_commits > 0:
        lines.append(f"Remote commits not present locally: {git_state.remote_only_commits}")
    if git_state.latest_tag is None:
        lines.append("Commits after latest tag: unknown")
    else:
        lines.append(
            f"Commits after latest tag {git_state.latest_tag.tag}: {git_state.latest_tag.commits_after}"
        )
    working_tree = git_state.working_tree
    if working_tree.clean:
        lines.append("Local changes: none")
    else:
        lines.append(
            "Local changes: "
            f"{working_tree.file_count} file(s) "
            f"({working_tree.staged_count} staged, "
            f"{working_tree.unstaged_count} unstaged, "
            f"{working_tree.untracked_count} untracked)"
        )

    lines.append("")
    if not report.versions:
        lines.append("No version-like tags or registry versions found.")
    else:
        version_width = max(len("Version"), *(len(row.version) for row in report.versions))
        lines.append(f"{heading('Version').ljust(version_width)}  {heading('State')}")
        for row in report.versions:
            sources = ", ".join(_render_source(source) for source in row.sources)
            tag_details: list[str] = []
            if row.local_tags:
                tag_details.append(f"local={','.join(row.local_tags)}")
            if row.remote_tags:
                tag_details.append(f"remote={','.join(row.remote_tags)}")
            suffix = f" {muted('(' + '; '.join(tag_details) + ')')}" if tag_details else ""
            lines.append(f"{row.version.ljust(version_width)}  {sources}{suffix}")

    if report.diagnostics:
        lines.append("")
        lines.append(str(heading("Diagnostics")))
        for diagnostic in report.diagnostics:
            message_lines = diagnostic.message.splitlines() or [""]
            lines.append(f"  - {diagnostic.source}: {message_lines[0]}")
            lines.extend(f"    {message_line}" for message_line in message_lines[1:])

    return lines


def _resolve_single_project_id(project_targets: list[str] | None, config: Config) -> str:
    requested_targets = inferred_project_targets(config, project_targets)
    if requested_targets is None:
        context = resolve_workspace_context(config=config)
        raise ValueError(
            contextualize_resolution_error(
                "No project target was provided, and the current directory does not map to a configured project. "
                "Use `where` or pass an explicit project target.",
                context,
            )
        )

    project_ids = resolve_project_ids(config, requested_targets)
    if len(project_ids) != 1:
        resolved = ", ".join(project_ids) if project_ids else "none"
        raise ValueError(f"`project versions` expects exactly one project target; resolved targets: {resolved}.")
    return project_ids[0]


def show_project_versions(
    project_targets: list[str] | None = None,
    config: Config | None = None,
    *,
    json_output: bool = False,
) -> int:
    active_config = load_config() if config is None else config
    project_id = _resolve_single_project_id(project_targets, active_config)
    report = build_project_version_report(project_id, active_config)

    if json_output:
        print(json.dumps(report.to_payload(), indent=2))
    else:
        for line in render_project_version_lines(report):
            print(line)
        if any(
            diagnostic.source in {"maven-central", "nuget", "pypi", "jitpack", "remote-tags"}
            for diagnostic in report.diagnostics
        ):
            warning("Some version sources were unavailable; see diagnostics above.")
    return 0


__all__ = [
    "ProjectVersionReport",
    "RegistrySnapshot",
    "VersionDiagnostic",
    "VersionRow",
    "VersionTag",
    "build_project_version_report",
    "render_project_version_lines",
    "show_project_versions",
]
