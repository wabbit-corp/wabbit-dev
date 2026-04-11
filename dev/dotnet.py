from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dev.config import DotnetProject

NUGET_V3_INDEX_URL = "https://api.nuget.org/v3/index.json"
LOCAL_NUGET_FEED_DIRNAME = ".nuget-local-feed"

_XML_NAMESPACE = "{http://schemas.microsoft.com/developer/msbuild/2003}"


def workspace_local_nuget_feed(workspace_root: Path) -> Path:
    return workspace_root.resolve() / LOCAL_NUGET_FEED_DIRNAME


def nuget_source_args(*, workspace_root: Path | None, include_local: bool) -> list[str]:
    args = ["--source", NUGET_V3_INDEX_URL]
    if include_local and workspace_root is not None:
        args.extend(["--source", str(workspace_local_nuget_feed(workspace_root))])
    return args


def _project_suffix(project: DotnetProject) -> str:
    if project.language == "fsharp":
        return ".fsproj"
    return ".csproj"


def discover_dotnet_project_file(project_root: Path, project: DotnetProject) -> Path | None:
    suffix = _project_suffix(project)
    candidates = sorted(
        path
        for path in project_root.rglob(f"*{suffix}")
        if _include_project_candidate(path)
    )
    if not candidates:
        return None
    return candidates[0]


def dotnet_project_file(project: DotnetProject) -> Path:
    expected = project.project_file_path
    if expected.is_file():
        return expected
    discovered = discover_dotnet_project_file(project.path, project)
    if discovered is not None:
        return discovered
    return expected


def relative_project_file(project: DotnetProject) -> str:
    return dotnet_project_file(project).relative_to(project.path).as_posix()


def fsharp_compile_entries(project_file: Path) -> list[str]:
    if not project_file.is_file():
        return []

    try:
        root = ET.fromstring(project_file.read_text(encoding="utf-8-sig"))
    except (ET.ParseError, OSError, UnicodeDecodeError):
        return []

    entries: list[str] = []
    for item_group in list(root):
        if not _is_tag(item_group.tag, "ItemGroup"):
            continue
        for child in list(item_group):
            if not _is_tag(child.tag, "Compile"):
                continue
            include = child.attrib.get("Include")
            if include is None:
                continue
            normalized = include.strip()
            if normalized:
                entries.append(normalized)
    return entries


def _include_project_candidate(path: Path) -> bool:
    ignored_parts = {".git", ".idea", ".venv", "bin", "obj"}
    return all(part not in ignored_parts for part in path.parts)


def _is_tag(tag: str, expected_local_name: str) -> bool:
    return tag == expected_local_name or tag == f"{_XML_NAMESPACE}{expected_local_name}"


__all__ = [
    "LOCAL_NUGET_FEED_DIRNAME",
    "NUGET_V3_INDEX_URL",
    "discover_dotnet_project_file",
    "dotnet_project_file",
    "fsharp_compile_entries",
    "nuget_source_args",
    "relative_project_file",
    "workspace_local_nuget_feed",
]
