from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from inspect import signature
from pathlib import Path

from mu.parser import parse
from mu.typed import DecodeError, decode
from mu.types import AtomExpr, Document, Expr, GroupExpr, MappingExpr, SequenceExpr, StringExpr

from dev import config_typed
from dev.config import CONFIG_FILE, Config, ProjectDependencyTarget, is_valid_maven_coordinate, load_config
from dev.messages import success
from dev.repo_resolution import inferred_project_targets, resolve_project_ids

type ProjectCommand = (
    config_typed.PythonProjectCommand
    | config_typed.PurescriptProjectCommand
    | config_typed.DataProjectCommand
    | config_typed.PremakeProjectCommand
    | config_typed.GradleProjectCommand
    | config_typed.FsharpProjectCommand
    | config_typed.CsharpProjectCommand
)


@dataclass(frozen=True)
class BuiltinEntry:
    index: int
    expr: Expr
    command: config_typed.BuiltinTopLevelCommand


@dataclass(frozen=True)
class ProjectEntry:
    project_id: str
    top_level_index: int
    repo_id: str | None
    command: ProjectCommand
    expr: GroupExpr


@dataclass(frozen=True)
class RepoField:
    key: str
    key_expr: Expr
    value_expr: Expr


@dataclass(frozen=True)
class RepoNestedProjectEntry:
    project_id: str
    command: ProjectCommand
    expr: GroupExpr


@dataclass(frozen=True)
class RepoEntry:
    top_level_index: int
    repo_id: str
    command: config_typed.RepoCommand
    expr: GroupExpr
    fields: tuple[RepoField, ...]
    nested_projects: tuple[RepoNestedProjectEntry, ...]


@dataclass(frozen=True)
class ConfigSourceIndex:
    source_text: str
    entry_by_index: dict[int, BuiltinEntry]
    project_entries: dict[str, ProjectEntry]
    repo_entries: dict[str, RepoEntry]
    define_entries: dict[str, list[int]]
    maven_repo_entries: dict[str, list[int]]
    plugin_entries: dict[str, list[int]]
    library_entries: dict[str, list[int]]
    library_group_entries: dict[str, list[int]]
    default_gradle_plugin_entries: list[int]
    default_maven_project_group_entries: list[int]
    jvm_version_entries: list[int]
    jvm_defaults_entries: list[int]
    python_defaults_entries: list[int]


def _parse_document_with_spans(text: str) -> Document:
    parse_params = signature(parse).parameters
    if "preserve_spans" in parse_params:
        return parse(text, preserve_spans=True)
    return parse(text, no_spans=False)  # type: ignore[call-arg]


def _expr_bounds(expr: Expr) -> tuple[int, int]:
    match expr:
        case AtomExpr(span=span) | StringExpr(span=span):
            assert span is not None
            return span.token.start.index, span.token.end.index
        case GroupExpr(open_bracket=open_bracket, close_bracket=close_bracket):
            return open_bracket.token.start.index, close_bracket.token.end.index
        case SequenceExpr(open_bracket=open_bracket, close_bracket=close_bracket):
            return open_bracket.token.start.index, close_bracket.token.end.index
        case MappingExpr(open_bracket=open_bracket, close_bracket=close_bracket):
            return open_bracket.token.start.index, close_bracket.token.end.index
        case _:
            raise TypeError(f"Unsupported expression type: {type(expr).__name__}")


def _slice_expr(source_text: str, expr: Expr) -> str:
    start, end = _expr_bounds(expr)
    return source_text[start:end]


def _pairwise(values: Sequence[Expr]) -> list[tuple[Expr, Expr]]:
    if len(values) % 2 != 0:
        raise ValueError("Expected an even number of repo field expressions")
    result: list[tuple[Expr, Expr]] = []
    for index in range(0, len(values), 2):
        result.append((values[index], values[index + 1]))
    return result


def _project_id_for(dir_name: str, repo_id: str | None) -> str:
    if repo_id is None:
        return dir_name
    return f"{repo_id}/{dir_name}"


def _command_dir_name(command: ProjectCommand) -> str:
    return command.dir_name


def _is_project_command(command: config_typed.BuiltinTopLevelCommand) -> bool:
    match command:
        case (
            config_typed.PythonProjectCommand()
            | config_typed.PurescriptProjectCommand()
            | config_typed.DataProjectCommand()
            | config_typed.PremakeProjectCommand()
            | config_typed.GradleProjectCommand()
            | config_typed.FsharpProjectCommand()
            | config_typed.CsharpProjectCommand()
        ):
            return True
        case _:
            return False


def _project_command(command: config_typed.BuiltinTopLevelCommand) -> ProjectCommand:
    match command:
        case (
            config_typed.PythonProjectCommand()
            | config_typed.PurescriptProjectCommand()
            | config_typed.DataProjectCommand()
            | config_typed.PremakeProjectCommand()
            | config_typed.GradleProjectCommand()
            | config_typed.FsharpProjectCommand()
            | config_typed.CsharpProjectCommand()
        ) as project_command:
            return project_command
        case _:
            raise TypeError(f"Unsupported project command: {type(command).__name__}")


def _decode_builtin_entries(source_text: str) -> list[BuiltinEntry]:
    doc = _parse_document_with_spans(source_text)
    target = config_typed.make_top_level_target(())
    entries: list[BuiltinEntry] = []
    for index, expr in enumerate(doc.exprs):
        try:
            command = decode(expr, target, path=f"root[{index}]")
        except DecodeError:
            continue
        entries.append(BuiltinEntry(index=index, expr=expr, command=command))
    return entries


def _build_source_index(source_text: str) -> ConfigSourceIndex:
    entries = _decode_builtin_entries(source_text)
    entry_by_index = {entry.index: entry for entry in entries}

    project_entries: dict[str, ProjectEntry] = {}
    repo_entries: dict[str, RepoEntry] = {}
    define_entries: dict[str, list[int]] = defaultdict(list)
    maven_repo_entries: dict[str, list[int]] = defaultdict(list)
    plugin_entries: dict[str, list[int]] = defaultdict(list)
    library_entries: dict[str, list[int]] = defaultdict(list)
    library_group_entries: dict[str, list[int]] = defaultdict(list)
    default_gradle_plugin_entries: list[int] = []
    default_maven_project_group_entries: list[int] = []
    jvm_version_entries: list[int] = []
    jvm_defaults_entries: list[int] = []
    python_defaults_entries: list[int] = []

    for entry in entries:
        match entry.command:
            case config_typed.DefineCommand(name=name):
                define_entries[name].append(entry.index)
            case config_typed.DefineMavenRepoCommand(name=name):
                maven_repo_entries[name].append(entry.index)
            case config_typed.DefineKotlinPluginCommand(name=name):
                plugin_entries[name].append(entry.index)
            case config_typed.DefineMavenLibraryCommand(name=name):
                library_entries[name].append(entry.index)
            case config_typed.DefineMavenLibraryGroupCommand(name=name):
                library_group_entries[name].append(entry.index)
            case config_typed.AddDefaultGradlePluginCommand():
                default_gradle_plugin_entries.append(entry.index)
            case config_typed.DefaultMavenProjectGroupCommand():
                default_maven_project_group_entries.append(entry.index)
            case config_typed.JvmVersionCommand():
                jvm_version_entries.append(entry.index)
            case config_typed.JvmDefaultsCommand():
                jvm_defaults_entries.append(entry.index)
            case config_typed.PythonDefaultsCommand():
                python_defaults_entries.append(entry.index)
            case config_typed.RepoCommand(dir_name=repo_id, projects=projects):
                match entry.expr:
                    case GroupExpr(values=values) as repo_expr:
                        pass
                    case _:
                        raise TypeError("Repo command must decode from a group expression")

                fields: list[RepoField] = []
                projects_expr: SequenceExpr | None = None
                for key_expr, value_expr in _pairwise(values[2:]):
                    match key_expr:
                        case AtomExpr(value=str() as key):
                            fields.append(RepoField(key=key, key_expr=key_expr, value_expr=value_expr))
                            if key == ":projects":
                                match value_expr:
                                    case SequenceExpr() as sequence_expr:
                                        projects_expr = sequence_expr
                                    case _:
                                        raise TypeError("Repo :projects field must be a sequence expression")
                        case _:
                            raise TypeError("Repo field key must be an atom")

                project_commands = list(projects or [])
                project_exprs = list(projects_expr.values) if projects_expr is not None else []
                if len(project_commands) != len(project_exprs):
                    raise ValueError(f"Repo {repo_id} nested project count does not match source expressions")

                nested_projects: list[RepoNestedProjectEntry] = []
                for project_command, project_expr in zip(project_commands, project_exprs, strict=True):
                    match project_expr:
                        case GroupExpr() as group_expr:
                            pass
                        case _:
                            raise TypeError("Nested repo project must be a group expression")
                    project_id = _project_id_for(_command_dir_name(project_command), repo_id)
                    nested_projects.append(
                        RepoNestedProjectEntry(project_id=project_id, command=project_command, expr=group_expr)
                    )
                    project_entries[project_id] = ProjectEntry(
                        project_id=project_id,
                        top_level_index=entry.index,
                        repo_id=repo_id,
                        command=project_command,
                        expr=group_expr,
                    )

                repo_entries[repo_id] = RepoEntry(
                    top_level_index=entry.index,
                    repo_id=repo_id,
                    command=entry.command,
                    expr=repo_expr,
                    fields=tuple(fields),
                    nested_projects=tuple(nested_projects),
                )
            case _ if _is_project_command(entry.command):
                project_command = _project_command(entry.command)
                match entry.expr:
                    case GroupExpr() as group_expr:
                        pass
                    case _:
                        raise TypeError("Project command must decode from a group expression")
                project_id = _project_id_for(_command_dir_name(project_command), None)
                project_entries[project_id] = ProjectEntry(
                    project_id=project_id,
                    top_level_index=entry.index,
                    repo_id=None,
                    command=project_command,
                    expr=group_expr,
                )
            case _:
                continue

    return ConfigSourceIndex(
        source_text=source_text,
        entry_by_index=entry_by_index,
        project_entries=project_entries,
        repo_entries=repo_entries,
        define_entries=dict(define_entries),
        maven_repo_entries=dict(maven_repo_entries),
        plugin_entries=dict(plugin_entries),
        library_entries=dict(library_entries),
        library_group_entries=dict(library_group_entries),
        default_gradle_plugin_entries=default_gradle_plugin_entries,
        default_maven_project_group_entries=default_maven_project_group_entries,
        jvm_version_entries=jvm_version_entries,
        jvm_defaults_entries=jvm_defaults_entries,
        python_defaults_entries=python_defaults_entries,
    )


def _latest_before(indices: list[int], before_index: int, label: str) -> int:
    position = bisect_left(indices, before_index)
    if position == 0:
        raise ValueError(f"Could not find {label} before config entry {before_index}")
    return indices[position - 1]


def _latest_before_or_last(indices: list[int], before_index: int, label: str) -> int:
    if not indices:
        raise ValueError(f"Could not find {label}")
    position = bisect_left(indices, before_index)
    if position == 0:
        return indices[-1]
    return indices[position - 1]


def _all_before(indices: list[int], before_index: int) -> list[int]:
    position = bisect_left(indices, before_index)
    return list(indices[:position])


def _normalize_project_reference(reference: str) -> str | None:
    if not reference:
        return None
    if reference.startswith(":"):
        return reference[1:]
    return reference


def _resolve_repo_local_project_reference(reference: str, *, repo_id: str | None, active_config: Config) -> str | None:
    project_id = _normalize_project_reference(reference)
    if project_id is None:
        return None
    if project_id in active_config.defined_projects:
        return project_id
    if repo_id is None:
        return None
    repo_project_id = f"{repo_id}/{project_id}"
    if repo_project_id in active_config.defined_projects:
        return repo_project_id
    return None


def _indent_block(text: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" for line in text.splitlines())


def _render_trimmed_repo(
    repo_entry: RepoEntry,
    *,
    selected_project_ids: set[str],
    source_text: str,
) -> str:
    head = _slice_expr(source_text, repo_entry.expr.values[0])
    repo_id_text = _slice_expr(source_text, repo_entry.expr.values[1])
    parts = [f"({head} {repo_id_text}"]

    for field in repo_entry.fields:
        if field.key == ":docsProject":
            match field.value_expr:
                case StringExpr(value=str() as docs_project_name):
                    docs_project_id = _project_id_for(docs_project_name, repo_entry.repo_id)
                    if docs_project_id not in selected_project_ids:
                        continue
                case _:
                    pass

        if field.key == ":projects":
            selected_nested_projects = [
                nested_project
                for nested_project in repo_entry.nested_projects
                if nested_project.project_id in selected_project_ids
            ]
            parts.append("    :projects [")
            for nested_project in selected_nested_projects:
                nested_text = _slice_expr(source_text, nested_project.expr)
                parts.append(_indent_block(nested_text, "        "))
            parts.append("    ]")
            continue

        field_text = f"{_slice_expr(source_text, field.key_expr)} {_slice_expr(source_text, field.value_expr)}"
        parts.append(_indent_block(field_text, "    "))

    parts.append(")")
    return "\n".join(parts)


def _selected_project_ids_for_cut(
    requested_targets: Sequence[str],
    *,
    source_index: ConfigSourceIndex,
    active_config: Config,
) -> list[str]:
    initial_targets = list(requested_targets)
    if not initial_targets:
        inferred_targets = inferred_project_targets(active_config)
        if inferred_targets is None or not inferred_targets:
            raise ValueError(
                "Expected at least one project or repo target, or run the command from inside a configured project."
            )
        initial_targets = inferred_targets

    pending: deque[str] = deque(resolve_project_ids(active_config, initial_targets))
    selected: list[str] = []
    seen: set[str] = set()

    while pending:
        project_id = pending.popleft()
        if project_id in seen:
            continue
        seen.add(project_id)
        selected.append(project_id)

        project = active_config.defined_projects[project_id]
        for dependency in project.resolved_dependencies:
            match dependency.target:
                case ProjectDependencyTarget(project=dependency_project_id):
                    pending.append(dependency_project_id)
                case _:
                    continue

        project_entry = source_index.project_entries.get(project_id)
        if project_entry is None:
            raise ValueError(f"Could not locate source config entry for project {project_id}")

        match project_entry.command:
            case config_typed.GradleProjectCommand(features=features):
                for application_index in _all_before(
                    source_index.default_gradle_plugin_entries,
                    project_entry.top_level_index,
                ):
                    application_entry = source_index.entry_by_index[application_index]
                    match application_entry.command:
                        case config_typed.AddDefaultGradlePluginCommand(name=plugin_name):
                            plugin_definition = active_config.plugins.get(plugin_name)
                            if plugin_definition is None:
                                raise ValueError(f"Gradle plugin {plugin_name} is not defined")
                            if plugin_definition.project is not None:
                                pending.append(plugin_definition.project)
                            compiler_project = _normalize_project_reference(plugin_definition.compiler_plugin or "")
                            if compiler_project is not None and compiler_project in active_config.defined_projects:
                                pending.append(compiler_project)
                        case _:
                            continue

                for feature in features or []:
                    match feature:
                        case config_typed.GradlePluginCommand(name=plugin_name):
                            plugin_definition = active_config.plugins.get(plugin_name)
                            if plugin_definition is None:
                                raise ValueError(f"Gradle plugin {plugin_name} is not defined")
                            if plugin_definition.project is not None:
                                pending.append(plugin_definition.project)
                            compiler_project = _normalize_project_reference(plugin_definition.compiler_plugin or "")
                            if compiler_project is not None and compiler_project in active_config.defined_projects:
                                pending.append(compiler_project)
                        case config_typed.KotlinCompilerGradlePluginCommand(
                            compilerPluginProject=compiler_plugin_project
                        ):
                            resolved_project_id = _resolve_repo_local_project_reference(
                                compiler_plugin_project,
                                repo_id=project_entry.repo_id,
                                active_config=active_config,
                            )
                            if resolved_project_id is not None:
                                pending.append(resolved_project_id)
                        case _:
                            continue
            case _:
                continue

    return selected


def config_cut(output_path: str, requested_targets: Sequence[str] | None = None) -> list[str]:
    active_config = load_config()
    workspace_root = active_config.workspace_root.resolve()
    root_path = workspace_root / CONFIG_FILE
    output_file = Path(output_path).expanduser()
    if not output_file.is_absolute():
        output_file = (Path.cwd() / output_file).resolve()
    if output_file == root_path:
        raise ValueError("Refusing to overwrite the active root.clj; write the cut config to a different file.")

    source_text = root_path.read_text(encoding="utf-8")
    source_index = _build_source_index(source_text)
    selected_project_ids = _selected_project_ids_for_cut(
        list(requested_targets or []),
        source_index=source_index,
        active_config=active_config,
    )
    selected_project_id_set = set(selected_project_ids)

    included_entry_indices: set[int] = set()
    selected_projects_by_repo: dict[str, set[str]] = defaultdict(set)

    def include_entry(index: int) -> None:
        included_entry_indices.add(index)

    def include_latest_optional(indices: list[int], before_index: int) -> None:
        position = bisect_left(indices, before_index)
        if position == 0:
            return
        include_entry(indices[position - 1])

    def include_define(name: str, before_index: int) -> None:
        indices = source_index.define_entries.get(name)
        if not indices:
            raise ValueError(f"Required define {name!r} is not present in root.clj")
        include_entry(_latest_before(indices, before_index, f"define {name!r}"))

    def include_maven_repo(name: str, before_index: int, *, allow_after: bool) -> None:
        indices = source_index.maven_repo_entries.get(name)
        if not indices:
            raise ValueError(f"Required maven repo {name!r} is not present in root.clj")
        selected_index = (
            _latest_before_or_last(indices, before_index, f"maven repo {name!r}")
            if allow_after
            else _latest_before(indices, before_index, f"maven repo {name!r}")
        )
        include_entry(selected_index)

    def include_plugin_definition(name: str, consumer_index: int) -> None:
        indices = source_index.plugin_entries.get(name)
        if not indices:
            raise ValueError(f"Required Kotlin plugin {name!r} is not present in root.clj")
        plugin_index = _latest_before_or_last(indices, consumer_index, f"Kotlin plugin {name!r}")
        include_entry(plugin_index)
        plugin_entry = source_index.entry_by_index[plugin_index]
        match plugin_entry.command:
            case config_typed.DefineKotlinPluginCommand(repo=repo_name):
                if repo_name is not None:
                    include_maven_repo(repo_name, consumer_index, allow_after=True)
            case _:
                raise TypeError("Plugin entry must decode to DefineKotlinPluginCommand")

    def include_gradle_dependency_reference(reference: str, *, before_index: int, project_index: int) -> None:
        if reference.startswith(":") or reference.startswith(".") or reference.startswith("/") or reference.startswith("npm:"):
            return
        if is_valid_maven_coordinate(reference):
            return

        group_indices = source_index.library_group_entries.get(reference)
        if group_indices:
            group_index = _latest_before(group_indices, before_index, f"library group {reference!r}")
            include_entry(group_index)
            group_entry = source_index.entry_by_index[group_index]
            match group_entry.command:
                case config_typed.DefineMavenLibraryGroupCommand(children=children):
                    for child in children:
                        match child:
                            case str() as child_reference:
                                include_gradle_dependency_reference(
                                    child_reference,
                                    before_index=group_index,
                                    project_index=project_index,
                                )
                            case config_typed.DepCall(name=child_reference):
                                include_gradle_dependency_reference(
                                    child_reference,
                                    before_index=group_index,
                                    project_index=project_index,
                                )
                            case _:
                                continue
                case _:
                    raise TypeError("Library group entry must decode to DefineMavenLibraryGroupCommand")
            return

        library_indices = source_index.library_entries.get(reference)
        if library_indices:
            library_index = _latest_before(library_indices, before_index, f"library {reference!r}")
            include_entry(library_index)
            library_entry = source_index.entry_by_index[library_index]
            match library_entry.command:
                case config_typed.DefineMavenLibraryCommand(maven_urn=maven_urn, repo=repo_name):
                    match maven_urn.version:
                        case config_typed.VarName(name=var_name):
                            include_define(var_name, library_index)
                        case config_typed.Const():
                            pass
                    if repo_name is not None:
                        include_maven_repo(repo_name, project_index, allow_after=False)
                case _:
                    raise TypeError("Library entry must decode to DefineMavenLibraryCommand")
            return

        raise ValueError(f"Unknown Gradle dependency reference {reference!r}")

    def include_gradle_dependency_input(
        dependency: config_typed.DependencyInput,
        *,
        before_index: int,
        project_index: int,
    ) -> None:
        match dependency:
            case str() as reference:
                include_gradle_dependency_reference(reference, before_index=before_index, project_index=project_index)
            case config_typed.DepCall(name=reference):
                include_gradle_dependency_reference(reference, before_index=before_index, project_index=project_index)
            case _:
                return

    def include_project_support(entry: ProjectEntry) -> None:
        consumer_index = entry.top_level_index
        match entry.command:
            case config_typed.GradleProjectCommand(
                dependencies=dependencies,
                sourceSetDependencies=source_set_dependencies,
                sourceSets=source_sets,
                features=features,
            ):
                include_entry(
                    _latest_before(
                        source_index.default_maven_project_group_entries,
                        consumer_index,
                        "default-maven-project-group",
                    )
                )
                include_latest_optional(source_index.jvm_version_entries, consumer_index)
                include_latest_optional(source_index.jvm_defaults_entries, consumer_index)

                for application_index in _all_before(source_index.default_gradle_plugin_entries, consumer_index):
                    include_entry(application_index)
                    application_entry = source_index.entry_by_index[application_index]
                    match application_entry.command:
                        case config_typed.AddDefaultGradlePluginCommand(name=plugin_name):
                            include_plugin_definition(plugin_name, consumer_index)
                        case _:
                            continue

                for dependency in dependencies or []:
                    include_gradle_dependency_input(
                        dependency,
                        before_index=consumer_index,
                        project_index=consumer_index,
                    )

                for dependency_list in (source_set_dependencies or {}).values():
                    for dependency in dependency_list:
                        include_gradle_dependency_input(
                            dependency,
                            before_index=consumer_index,
                            project_index=consumer_index,
                        )

                for source_set in (source_sets or {}).values():
                    for dependency in source_set.dependencies or []:
                        include_gradle_dependency_input(
                            dependency,
                            before_index=consumer_index,
                            project_index=consumer_index,
                        )

                for feature in features or []:
                    match feature:
                        case config_typed.GradlePluginCommand(name=plugin_name):
                            include_plugin_definition(plugin_name, consumer_index)
                        case _:
                            continue
            case config_typed.PythonProjectCommand():
                include_latest_optional(source_index.python_defaults_entries, consumer_index)
            case _:
                return

    for project_id in selected_project_ids:
        project_entry = source_index.project_entries.get(project_id)
        if project_entry is None:
            raise ValueError(f"Could not locate source config entry for project {project_id}")
        include_entry(project_entry.top_level_index)
        if project_entry.repo_id is not None:
            selected_projects_by_repo[project_entry.repo_id].add(project_id)
        include_project_support(project_entry)

    rendered_entries: list[tuple[int, str]] = []
    for index in sorted(included_entry_indices):
        entry = source_index.entry_by_index[index]
        match entry.command:
            case config_typed.RepoCommand(dir_name=repo_id):
                repo_entry = source_index.repo_entries[repo_id]
                repo_project_ids = {nested.project_id for nested in repo_entry.nested_projects}
                selected_repo_project_ids = selected_projects_by_repo.get(repo_id, set())
                if repo_project_ids == selected_repo_project_ids:
                    rendered_entries.append((index, _slice_expr(source_text, entry.expr)))
                else:
                    rendered_entries.append(
                        (
                            index,
                            _render_trimmed_repo(
                                repo_entry,
                                selected_project_ids=selected_project_id_set,
                                source_text=source_text,
                            ),
                        )
                    )
            case _:
                rendered_entries.append((index, _slice_expr(source_text, entry.expr)))

    rendered_entries.sort(key=lambda item: item[0])
    output_text = "\n\n".join(text.rstrip() for _, text in rendered_entries).rstrip() + "\n"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(output_text, encoding="utf-8")
    success(
        f"Wrote {output_file} with {len(rendered_entries)} config entries for "
        f"{', '.join(selected_project_ids)}"
    )
    return selected_project_ids
