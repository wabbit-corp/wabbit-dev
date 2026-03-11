from dev.config import (
    Config,
    DataProject,
    GradleProject,
    PremakeProject,
    Project,
    PurescriptProject,
    PythonProject,
    load_config,
)


def _colored(text: str, color: str, *, attrs: tuple[str, ...] = ()) -> str:
    try:
        from termcolor import colored
    except ImportError:
        return text
    return colored(text, color, attrs=list(attrs))


def _project_type_label(project: Project) -> str:
    if isinstance(project, PythonProject):
        return "python"
    if isinstance(project, GradleProject):
        if "scala" in project.resolved_features:
            return "scala/kmp" if project.is_kmp else "scala/jvm"
        if "kotlin" in project.resolved_features or project.is_kmp:
            return "kotlin/kmp" if project.is_kmp else "kotlin/jvm"
        return "gradle/kmp" if project.is_kmp else "gradle/jvm"
    if isinstance(project, PurescriptProject):
        return "purescript"
    if isinstance(project, PremakeProject):
        return "premake"
    if isinstance(project, DataProject):
        return "data"
    return type(project).__name__.removesuffix("Project").lower()


def _project_type_color(project_type: str) -> str:
    if project_type == "python":
        return "green"
    if project_type.endswith("/kmp"):
        return "magenta"
    if project_type.endswith("/jvm"):
        return "blue"
    if project_type == "purescript":
        return "yellow"
    return "cyan"


def _project_display_name(project: Project) -> str:
    project_id = project.project_id
    if not project.is_repo_managed:
        return project_id if project_id is not None else project.path.as_posix()

    relative_path = project.path.relative_to(project.effective_repo_root)
    return f"  {relative_path.as_posix()}"


def _repo_display_name(project: Project) -> str:
    repo_id = project.repo_id
    if repo_id is not None:
        return f"{repo_id}/"
    return f"{project.effective_repo_root.name}/"


def render_project_list_lines(config: Config, *, colorize: bool = True) -> list[str]:
    display_rows: list[tuple[str, str]] = []
    for project in config.defined_projects.values():
        display_rows.append((_project_display_name(project), _project_type_label(project)))

    width = max((len(label) for label, _project_type in display_rows), default=0)

    lines: list[str] = []
    active_repo_key: str | None = None
    for project in config.defined_projects.values():
        if project.is_repo_managed:
            repo_key = project.repo_id or project.effective_repo_root.as_posix()
            if repo_key != active_repo_key:
                repo_name = _repo_display_name(project)
                if colorize:
                    repo_name = _colored(repo_name, "cyan", attrs=("bold",))
                lines.append(repo_name)
                active_repo_key = repo_key
        else:
            active_repo_key = None

        label = _project_display_name(project)
        project_type = _project_type_label(project)
        padded_label = label.ljust(width)
        rendered_type = project_type
        if colorize:
            rendered_type = _colored(project_type, _project_type_color(project_type), attrs=("bold",))
        lines.append(f"{padded_label}  {rendered_type}")

    return lines


def list_projects(config: Config | None = None) -> None:
    active_config = load_config() if config is None else config
    for line in render_project_list_lines(active_config):
        print(line)
