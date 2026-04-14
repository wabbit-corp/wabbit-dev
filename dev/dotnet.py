from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Collection
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from dev.config import DotnetProject

NUGET_V3_INDEX_URL = "https://api.nuget.org/v3/index.json"
LOCAL_NUGET_FEED_DIRNAME = ".nuget-local-feed"

_XML_NAMESPACE = "{http://schemas.microsoft.com/developer/msbuild/2003}"


@dataclass(frozen=True)
class PreservedMsbuildProjectSections:
    property_groups: tuple[str, ...] = ()
    item_groups: tuple[str, ...] = ()
    top_level_elements: tuple[str, ...] = ()


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
    root = _parse_msbuild_project(project_file)
    if root is None:
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


def preserved_msbuild_project_sections(
    project_file: Path,
    *,
    managed_property_names: Collection[str],
    managed_item_names: Collection[str],
) -> PreservedMsbuildProjectSections:
    root = _parse_msbuild_project(project_file)
    if root is None:
        return PreservedMsbuildProjectSections()

    preserved_property_groups: list[str] = []
    preserved_item_groups: list[str] = []
    preserved_top_level_elements: list[str] = []
    managed_property_name_set = set(managed_property_names)
    managed_item_name_set = set(managed_item_names)

    for child in list(root):
        local_name = _local_name(child.tag)
        match local_name:
            case "PropertyGroup":
                preserved_children = [
                    deepcopy(entry)
                    for entry in list(child)
                    if _local_name(entry.tag) not in managed_property_name_set
                ]
                if preserved_children:
                    property_group = ET.Element("PropertyGroup")
                    for entry in preserved_children:
                        property_group.append(entry)
                    preserved_property_groups.append(_serialize_xml_element(property_group))
            case "ItemGroup":
                preserved_children = [
                    deepcopy(entry)
                    for entry in list(child)
                    if _should_preserve_item(entry, managed_item_name_set)
                ]
                if preserved_children:
                    item_group = ET.Element("ItemGroup")
                    for entry in preserved_children:
                        item_group.append(entry)
                    preserved_item_groups.append(_serialize_xml_element(item_group))
            case _:
                preserved_top_level_elements.append(_serialize_xml_element(deepcopy(child)))

    return PreservedMsbuildProjectSections(
        property_groups=tuple(preserved_property_groups),
        item_groups=tuple(preserved_item_groups),
        top_level_elements=tuple(preserved_top_level_elements),
    )


def _include_project_candidate(path: Path) -> bool:
    ignored_parts = {".git", ".idea", ".venv", "bin", "obj"}
    return all(part not in ignored_parts for part in path.parts)


def _parse_msbuild_project(project_file: Path) -> ET.Element | None:
    if not project_file.is_file():
        return None

    try:
        return ET.fromstring(project_file.read_text(encoding="utf-8-sig"))
    except (ET.ParseError, OSError, UnicodeDecodeError):
        return None


def _is_tag(tag: str, expected_local_name: str) -> bool:
    return tag == expected_local_name or tag == f"{_XML_NAMESPACE}{expected_local_name}"


def _local_name(tag: str) -> str:
    _, separator, suffix = tag.rpartition("}")
    if separator:
        return suffix
    return tag


def _should_preserve_item(item: ET.Element, managed_item_names: Collection[str]) -> bool:
    local_name = _local_name(item.tag)
    if local_name in managed_item_names:
        return False
    if local_name != "None":
        return True

    if item.attrib.get("Pack") != "true":
        return True
    package_path = item.attrib.get("PackagePath")
    if package_path is None:
        return True
    normalized_package_path = package_path.replace("\\", "/")
    return normalized_package_path not in {"/", "LICENSE.md"}


def _serialize_xml_element(element: ET.Element) -> str:
    ET.indent(element, space="  ")
    return ET.tostring(element, encoding="unicode").rstrip()


__all__ = [
    "LOCAL_NUGET_FEED_DIRNAME",
    "NUGET_V3_INDEX_URL",
    "discover_dotnet_project_file",
    "dotnet_project_file",
    "fsharp_compile_entries",
    "nuget_source_args",
    "preserved_msbuild_project_sections",
    "PreservedMsbuildProjectSections",
    "relative_project_file",
    "workspace_local_nuget_feed",
]
