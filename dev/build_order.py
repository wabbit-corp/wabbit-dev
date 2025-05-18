#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Subproject Dependency Graph & Topological Sort
"""

from collections import deque, defaultdict
from typing import List, Dict, Tuple
from dev.config import Project


def build_dependency_graph(projects) -> Tuple[Dict[str, List[str]], Dict[str, int]]:
    """
    Creates adjacency lists for subproject dependencies {project: [depends_on...]}.
    Returns (graph, in_degs).
    """
    graph: Dict[str, List[str]] = dict()
    in_degs: Dict[str, int] = {name: 0 for name in projects}

    for name, proj in projects.items():
        graph[name] = []

    for name, proj in projects.items():
        for dep in proj.resolved_dependencies:
            if dep.is_subproject:
                dep_name = dep.name
                # Edge: dep_name -> name
                graph[dep_name].append(name)
                in_degs[name] += 1

    return dict(graph), in_degs


def toposort_projects(projects, target_project=None):
    """
    Return a list of project names in topological order. If target_project is not None,
    we only include the subgraph needed for that project.
    """
    graph, in_degs = build_dependency_graph(projects)

    if target_project is not None:
        # BFS upward from target_project in reversed edges
        rev = defaultdict(list)
        for src, children in graph.items():
            for c in children:
                rev[c].append(src)

        needed = set()
        queue = deque([target_project])
        while queue:
            cur = queue.popleft()
            if cur in needed:
                continue
            needed.add(cur)
            for p in rev[cur]:
                if p not in needed:
                    queue.append(p)

        # Filter
        sub_graph = {}
        sub_in = {}
        for p in needed:
            sub_in[p] = 0
        for p in needed:
            valid_children = [c for c in graph.get(p, []) if c in needed]
            sub_graph[p] = valid_children
            for c in valid_children:
                sub_in[c] += 1
        graph, in_degs = sub_graph, sub_in

    # Standard Kahn's algorithm
    queue = deque([p for p, deg in in_degs.items() if deg == 0])
    order = []
    while queue:
        cur = queue.popleft()
        order.append(cur)
        for nxt in graph[cur]:
            in_degs[nxt] -= 1
            if in_degs[nxt] == 0:
                queue.append(nxt)

    return order
