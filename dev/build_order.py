#!/usr/bin/env python3

"""
Subproject Dependency Graph & Topological Sort
"""

from collections import defaultdict, deque

from dev.config import Project


def build_dependency_graph(projects: dict[str, Project]) -> tuple[dict[str, list[str]], dict[str, int]]:
    """
    Creates adjacency lists for subproject dependencies {project: [depends_on...]}.
    Returns (graph, in_degs).
    """
    graph: dict[str, list[str]] = dict()
    in_degs: dict[str, int] = {name: 0 for name in projects}

    for name, _proj in projects.items():
        graph[name] = []

    for name, proj in projects.items():
        for dep in proj.resolved_dependencies:
            if dep.is_subproject:
                dep_name = dep.name
                if dep_name not in graph:
                    raise ValueError(f"Project {name} depends on unknown project {dep_name}")
                # Edge: dep_name -> name
                graph[dep_name].append(name)
                in_degs[name] += 1

    return dict(graph), in_degs


def toposort_projects(projects: dict[str, Project], target_project: str | None = None) -> list[str]:
    """
    Return a list of project names in topological order. If target_project is not None,
    we only include the subgraph needed for that project.
    """
    graph, in_degs = build_dependency_graph(projects)

    if target_project is not None:
        if target_project not in projects:
            raise ValueError(f"Unknown project: {target_project}")

        # BFS upward from target_project in reversed edges
        rev: defaultdict[str, list[str]] = defaultdict(list)
        for src, children in graph.items():
            for c in children:
                rev[c].append(src)

        needed: set[str] = set()
        queue: deque[str] = deque([target_project])
        while queue:
            cur = queue.popleft()
            if cur in needed:
                continue
            needed.add(cur)
            for p in rev[cur]:
                if p not in needed:
                    queue.append(p)

        # Filter
        ordered_needed = [name for name in projects if name in needed]
        sub_graph: dict[str, list[str]] = {}
        sub_in: dict[str, int] = {name: 0 for name in ordered_needed}
        for p in ordered_needed:
            valid_children = [c for c in graph.get(p, []) if c in needed]
            sub_graph[p] = valid_children
            for c in valid_children:
                sub_in[c] += 1
        graph, in_degs = sub_graph, sub_in

    # Standard Kahn's algorithm
    queue = deque([p for p, deg in in_degs.items() if deg == 0])
    order: list[str] = []
    while queue:
        cur = queue.popleft()
        order.append(cur)
        for nxt in graph[cur]:
            in_degs[nxt] -= 1
            if in_degs[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(in_degs):
        raise ValueError("Cyclic project dependency detected")

    return order
