#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dev.config import GradleProject, load_config
from dev.jvms import (
    criteria_from_policy_name,
    discover_installed_jvms,
    rank_jvms,
    resolve_project_jvm_policy,
    select_jvm,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "query",
        nargs="*",
        help="Legacy JVM query, for example: 21 latest amazon",
    )
    parser.add_argument(
        "--policy",
        help="Named JVM policy, for example: android-agp-21 or jvm-21",
    )
    parser.add_argument(
        "--project",
        help="Project id from root.clj, for example: jeeves/client",
    )
    parser.add_argument(
        "--task",
        help="Optional Gradle task name used for jvmTaskPolicies matching",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the selected JVM as JSON instead of shell exports",
    )
    return parser


def _resolve_policy_from_project(project_id: str, task_name: str | None) -> str:
    config = load_config()
    if project_id not in config.defined_projects:
        raise ValueError(f"Unknown project {project_id!r}")

    project = config.defined_projects[project_id]
    if not isinstance(project, GradleProject):
        raise ValueError(f"Project {project_id!r} is not a Gradle project")

    repo_policy: str | None = None
    if project.repo_id is not None:
        repo_definition = config.defined_repos.get(project.repo_id)
        if repo_definition is not None:
            repo_policy = repo_definition.jvm_policy

    return resolve_project_jvm_policy(
        project,
        task_name=task_name,
        repo_policy=repo_policy,
        global_jvm_version=config.jvm_version,
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    legacy_query = " ".join(args.query).strip() or None
    if args.policy is not None and legacy_query is not None:
        parser.error("Specify either a legacy query or --policy, not both")
    if args.project is not None and (args.policy is not None or legacy_query is not None):
        parser.error("Specify --project on its own, or use --policy / legacy query directly")

    try:
        policy_name = args.policy
        if args.project is not None:
            policy_name = _resolve_policy_from_project(args.project, args.task)

        installed_jvms = discover_installed_jvms()
        selected = select_jvm(
            installed_jvms,
            policy_name=policy_name,
            legacy_query=legacy_query,
        )
    except ValueError as ex:
        print(str(ex), file=sys.stderr)
        return 1

    if selected is None:
        print("No JVM installations found.", file=sys.stderr)
        return 1

    try:
        if policy_name is not None:
            criteria = criteria_from_policy_name(policy_name)
        elif legacy_query is not None:
            from dev.jvms import parse_legacy_query

            criteria = parse_legacy_query(legacy_query)
        else:
            criteria = criteria_from_policy_name("auto")
    except ValueError as ex:
        print(str(ex), file=sys.stderr)
        return 1

    ranked = rank_jvms(installed_jvms, criteria)
    if args.json:
        print(
            json.dumps(
                {
                    "policy": policy_name,
                    "legacyQuery": legacy_query,
                    "selected": {
                        "home": str(selected.home),
                        "version": list(selected.version),
                        "implementor": selected.implementor,
                        "architecture": selected.architecture,
                        "source": selected.source,
                    },
                    "candidates": [
                        {
                            "home": str(jvm.home),
                            "version": list(jvm.version),
                            "implementor": jvm.implementor,
                            "architecture": jvm.architecture,
                            "source": jvm.source,
                        }
                        for jvm in ranked
                    ],
                },
                indent=2,
            )
        )
        return 0

    for jvm in ranked:
        version_text = ".".join(str(component) for component in jvm.version)
        print(
            f"candidate: {version_text} {jvm.implementor!r} {jvm.home}",
            file=sys.stderr,
        )

    print(f'export JAVA_HOME="{selected.home}"')
    print(f'export PATH="{selected.home / "bin"}:$PATH"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
