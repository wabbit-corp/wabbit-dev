from typing import List, Optional, Dict, Set
from dataclasses import dataclass

from graphviz import Digraph

from dev.config import load_config
from dev.messages import error, info, success
from dev.config import GradleProject


def get_project_dependencies(
        *,
        focus_project_name: Optional[str] = None,
        include_artifacts: bool = False,
        output_filename: str = "dependency_graph",
        graph_title: Optional[str] = None
    ) -> None:
    config = load_config()

    if focus_project_name and focus_project_name not in config.defined_projects:
        error(f"Project '{focus_project_name}' not found in configuration.")
        return

    # Determine the graph title
    effective_graph_title = graph_title
    if not effective_graph_title:
        if focus_project_name:
            effective_graph_title = f'Dependencies for {focus_project_name}'
            if include_artifacts:
                effective_graph_title += ' (including artifacts)'
        else:
            effective_graph_title = 'All Project Dependencies'
            if include_artifacts:
                effective_graph_title += ' (including artifacts)'

    @dataclass(frozen=True)
    class Node:
        id: str
        label: str
        type: str

    @dataclass(frozen=True)
    class Edge:
        source: str
        target: str

    nodes: Dict[str, Node] = {}
    edges: Set[Edge] = set()


    def sanitize_id(artifact: str) -> str:
        id = artifact
        id = id.replace(':', '_')
        id = id.replace('.', '_')
        id = id.replace('/', '_')
        return id


    def add_dependencies(project_name: str) -> None:
        if project_name not in config.defined_projects:
            return
        project = config.defined_projects[project_name]
        if project_name not in nodes:
            nodes[project_name] = Node(id=sanitize_id(project_name), label=project_name, type='project')

        for dep in project.resolved_dependencies:
            if dep.is_subproject:
                nodes[dep.name] = Node(id=sanitize_id(dep.name), label=dep.name, type='project')
                edges.add(Edge(source=project_name, target=dep.name))
                add_dependencies(dep.name)
            elif include_artifacts:
                nodes[dep.name] = Node(id=sanitize_id(dep.name), label=dep.name, type='artifact')

    if focus_project_name is None:
        for project_name, project in config.defined_projects.items():
            add_dependencies(project_name)
    else:
        add_dependencies(focus_project_name)


    # Generate dependency graph if requested
    dot = Digraph(comment=effective_graph_title)
    dot.attr(label=effective_graph_title)
    dot.attr(rankdir='LR')

    # Add nodes to the graph
    for node in nodes.values():
        if node.type == 'project':
            dot.node(node.id, label=node.label, shape='box', style='filled', fillcolor='lightblue')
        else:
            dot.node(node.id, label=node.label, shape='ellipse', style='filled', fillcolor='lightgreen')
    # Add edges to the graph
    for edge in edges:
        dot.edge(edge.source, edge.target)

    # Save the graph
    try:
        graph_file = f"dependencies"
        dot.render(graph_file, format='svg', cleanup=True)
        info(f"Dependency graph saved as {graph_file}.svg")
    except Exception as e:
        error(f"Failed to generate dependency graph: {e}")
