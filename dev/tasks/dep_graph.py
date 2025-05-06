from typing import List

from graphviz import Digraph

from dev.config import load_config
from dev.messages import error, info, success
from dev.config import GradleProject


def get_project_dependencies(*, project_name: str, only_projects: bool = False, include_graph: bool = True) -> None:
    config = load_config()

    if project_name not in config.defined_projects:
        error(f"Project {project_name} not found")
        return

    project = config.defined_projects[project_name]

    # Collect direct dependencies
    project_deps: List[str] = []
    artifact_deps: List[str] = []

    for dep in project.resolved_dependencies:
        if dep.is_subproject:
            project_deps.append(dep.name)
        elif not only_projects:
            artifact_deps.append(dep.name)

    # Print dependencies
    if project_deps:
        info("Project Dependencies:")
        for dep_name in sorted(project_deps):
            success(f"  {dep_name}")

    if artifact_deps and not only_projects:
        info("Artifact Dependencies:")
        for dep_name in sorted(artifact_deps):
            success(f"  {dep_name}")

    # Generate dependency graph if requested
    if include_graph and project_deps:
        dot = Digraph(comment=f'Dependencies for {project_name}')
        dot.attr(rankdir='LR')

        # Add nodes
        dot.node(project_name, project_name, shape='box')
        seen = {project_name}

        def add_dependencies(proj_name: str, parent: str) -> None:
            if proj_name not in config.defined_projects:
                return

            proj = config.defined_projects[proj_name]
            assert isinstance(proj, GradleProject) # FIXME: For now, we only support Gradle projects

            for dep in proj.resolved_dependencies:
                if dep.is_subproject:
                    dot.edge(parent, dep.name)
                    if dep.name not in seen:
                        seen.add(dep.name)
                        dot.node(dep.name, dep.name, shape='box')
                        add_dependencies(dep.name, dep.name)

        # Build the graph
        add_dependencies(project_name, project_name)

        # Save the graph
        try:
            graph_file = f"{project_name}_dependencies"
            dot.render(graph_file, format='svg', cleanup=True)
            info(f"Dependency graph saved as {graph_file}.svg")
        except Exception as e:
            error(f"Failed to generate dependency graph: {e}")
