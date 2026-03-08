from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Literal

import git
from git.objects.tag import TagObject

from dev.config import Version
from dev.messages import info, warning


def format_commit_message(message: str | bytes) -> str:
    if isinstance(message, bytes):
        return message.decode("utf-8", errors="replace").strip()
    return message.strip()


def get_latest_version(repo: git.Repo) -> tuple[Version | None, git.Commit | None]:
    versions: list[tuple[Version, git.Commit]] = []
    for tag in repo.tags:
        tag_name = tag.name
        tag_commit = tag.object

        if isinstance(tag_commit, TagObject):
            tag_commit = tag_commit.object

        if not isinstance(tag_commit, git.Commit):
            continue
        tag_version = Version.parse_or_null(tag_name)
        if tag_version is not None:
            versions.append((tag_version, tag_commit))
    versions.sort(key=lambda x: x[0], reverse=True)

    if versions:
        latest_version = versions[0][0]
        latest_version_commit = versions[0][1]
    else:
        latest_version = None
        latest_version_commit = None

    return latest_version, latest_version_commit


def resolve_tag_commit(repo: git.Repo, tag_name: str, project_name: str) -> git.Commit:
    tag_ref = next((t for t in repo.tags if t.name == tag_name), None)
    if tag_ref is not None:
        warning(f"Tag {tag_name} already exists for {project_name}.")
        return tag_ref.commit

    repo.create_tag(tag_name, message=f"Release {tag_name}")
    return repo.head.commit


def set_project_version_in_root_clj(
    project_name: str,
    current_version: str,
    new_version: str,
    root_file: str = "root.clj",
) -> None:
    if not os.path.isfile(root_file):
        raise ValueError(f"No {root_file} found, cannot update version for {project_name}.")

    with open(root_file, encoding="utf-8") as f:
        lines = f.readlines()

    updated_lines: list[str] = []
    found_and_replaced = False
    project_types = ["gradle", "python", "data", "purescript", "premake"]
    re_project = re.compile(rf"^\s*\((?:{'|'.join(project_types)})\s+\"([^\"]+)\"")
    re_repo = re.compile(r'^\s*\(repo\s+"([^"]+)"')

    repo_name: str | None = None
    nested_project_name: str | None = None
    if "/" in project_name:
        repo_name, nested_project_name = project_name.split("/", 1)

    current_repo_name: str | None = None
    current_repo_depth = -1
    current_project_depth = -1
    in_target_project_block = False
    depth = 0

    for line in lines:
        repo_match = re_repo.match(line)
        if repo_match is not None:
            current_repo_name = repo_match.group(1)
            current_repo_depth = depth

        project_match = re_project.match(line)
        if project_match is not None:
            current_name = project_match.group(1)
            matches_target = False
            if repo_name is None:
                matches_target = current_name == project_name and current_repo_name is None
            else:
                matches_target = current_repo_name == repo_name and current_name == nested_project_name
            in_target_project_block = matches_target
            if matches_target:
                current_project_depth = depth

        if in_target_project_block:
            if ":version " in line:
                version_marker = ':version "'
                idx = line.find(version_marker)
                if idx != -1:
                    start_idx = idx + len(version_marker)
                    end_idx = line.find('"', start_idx)
                    if end_idx != -1:
                        existing_version = line[start_idx:end_idx]
                        if existing_version != current_version:
                            raise ValueError(
                                f'Found :version "{existing_version}" but expected "{current_version}" '
                                f"for project '{project_name}'. Aborting update."
                            )
                        before = line[:start_idx]
                        after = line[end_idx:]
                        line = before + new_version + after
                        found_and_replaced = True

        updated_lines.append(line)
        depth += line.count("(") - line.count(")")

        if in_target_project_block and depth <= current_project_depth:
            in_target_project_block = False
            current_project_depth = -1

        if current_repo_name is not None and depth <= current_repo_depth:
            current_repo_name = None
            current_repo_depth = -1

    if not found_and_replaced:
        raise ValueError(
            f'Could not find a matching project block for "{project_name}" with '
            f':version "{current_version}" in {root_file}. Nothing updated.'
        )

    with open(root_file, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    info(f"Updated version for '{project_name}' from '{current_version}' to '{new_version}' in {root_file}")


class PublishError(Exception):
    pass


@dataclass
class Timer:
    name: str | None = None
    start_time: float = 0.0

    def __enter__(self) -> Timer:
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> Literal[False]:
        elapsed_time = time.time() - self.start_time
        if self.name:
            info(f"{self.name} took {elapsed_time:.2f} seconds")
        else:
            info(f"Elapsed time: {elapsed_time:.2f} seconds")
        return False


__all__ = [
    "PublishError",
    "Timer",
    "format_commit_message",
    "get_latest_version",
    "resolve_tag_commit",
    "set_project_version_in_root_clj",
]
