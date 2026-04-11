from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from dev.check_fixers import can_regenerate_with_setup, rerun_setup_for_project
from dev.checks.base import Issue, IssueType, ProjectCheck
from dev.config import GradleProject, IntellijPlugin, Project
from dev.tasks.publish import determine_publish_target

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ASCII_PRINTABLE_RE = re.compile(r"^[ -~]+$")
SVG_DIMENSION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*$")
FORBIDDEN_PLUGIN_NAME_TERMS = ("plugin", "intellij", "jetbrains")
DESCRIPTION_PLACEHOLDERS = frozenset(
    {
        "todo",
        "lorem ipsum",
        "plugin description",
    }
)
CHANGE_NOTES_PLACEHOLDERS = frozenset(
    {
        "add change notes here",
        "most html tags may be used",
        "todo",
        "lorem ipsum",
    }
)

E_INTELLIJ_MARKETPLACE_METADATA_INVALID = IssueType(
    "E_INTELLIJ_MARKETPLACE_METADATA_INVALID",
    "IntelliJ Marketplace metadata {field} is invalid: {reason}.",
)
E_INTELLIJ_MARKETPLACE_SOURCE_LINK_MISSING = IssueType(
    "E_INTELLIJ_MARKETPLACE_SOURCE_LINK_MISSING",
    "Open-source IntelliJ plugin is missing a source repository link.",
)
E_INTELLIJ_PLUGIN_XML_MISSING = IssueType(
    "E_INTELLIJ_PLUGIN_XML_MISSING",
    "Missing IntelliJ plugin.xml file at src/main/resources/META-INF/plugin.xml.",
)
E_INTELLIJ_PLUGIN_XML_PARSE_ERROR = IssueType(
    "E_INTELLIJ_PLUGIN_XML_PARSE_ERROR",
    "Could not parse IntelliJ plugin.xml: {error}.",
)
E_INTELLIJ_PLUGIN_XML_DRIFT = IssueType(
    "E_INTELLIJ_PLUGIN_XML_DRIFT",
    "IntelliJ plugin.xml field {field} differs from configured metadata: expected {expected}, found {actual}.",
)
E_INTELLIJ_PLUGIN_ICON_MISSING = IssueType(
    "E_INTELLIJ_PLUGIN_ICON_MISSING",
    "Missing IntelliJ plugin icon at src/main/resources/META-INF/pluginIcon.svg.",
)
E_INTELLIJ_PLUGIN_ICON_PARSE_ERROR = IssueType(
    "E_INTELLIJ_PLUGIN_ICON_PARSE_ERROR",
    "Could not parse IntelliJ plugin icon SVG: {error}.",
)
E_INTELLIJ_PLUGIN_ICON_SIZE_INVALID = IssueType(
    "E_INTELLIJ_PLUGIN_ICON_SIZE_INVALID",
    "IntelliJ plugin icon must be a 40x40 SVG, found {width}x{height}.",
)


def _non_empty_trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed if collapsed else None


def _plugin_xml_path(project: GradleProject) -> Path:
    return project.path / "src" / "main" / "resources" / "META-INF" / "plugin.xml"


def _plugin_icon_path(project: GradleProject) -> Path:
    return project.path / "src" / "main" / "resources" / "META-INF" / "pluginIcon.svg"


def _marketplace_plugin(project: Project | None) -> tuple[GradleProject, IntellijPlugin] | None:
    match project:
        case GradleProject() as gradle_project:
            feature = gradle_project.resolved_features.get("intellij-plugin")
            match feature:
                case IntellijPlugin() as intellij_feature:
                    if determine_publish_target(gradle_project) == "intellij-marketplace":
                        return gradle_project, intellij_feature
                    return None
                case _:
                    return None
        case _:
            return None


def _is_valid_email(email: str) -> bool:
    return EMAIL_RE.fullmatch(email) is not None


def _is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _contains_placeholder(text: str, placeholders: frozenset[str]) -> bool:
    lowered = text.casefold()
    return any(placeholder in lowered for placeholder in placeholders)


def _metadata_issue(path: Path, *, field: str, reason: str) -> Issue:
    return E_INTELLIJ_MARKETPLACE_METADATA_INVALID.make(field=field, reason=reason).at(path)


def _xml_direct_child_text(root: ET.Element, tag: str) -> str | None:
    element = root.find(tag)
    if element is None:
        return None
    return _non_empty_trimmed(element.text)


def _xml_direct_child_attribute(root: ET.Element, tag: str, attribute: str) -> str | None:
    element = root.find(tag)
    if element is None:
        return None
    return _non_empty_trimmed(element.get(attribute))


def _expected_depends(feature: IntellijPlugin) -> list[str]:
    depends = feature.depends or ["com.intellij.modules.platform"]
    normalized: list[str] = []
    for value in depends:
        normalized_value = _non_empty_trimmed(value)
        if normalized_value is not None:
            normalized.append(normalized_value)
    if normalized:
        return normalized
    return ["com.intellij.modules.platform"]


def _xml_depends(root: ET.Element) -> list[str]:
    depends: list[str] = []
    for element in root.findall("depends"):
        value = _non_empty_trimmed(element.text)
        if value is not None:
            depends.append(value)
    return depends


def _expected_xml_fields(project: GradleProject, feature: IntellijPlugin) -> dict[str, str | None]:
    version = project.version
    return {
        "id": _non_empty_trimmed(feature.pluginId) or f"{project.group_name}.{project.name}",
        "name": _non_empty_trimmed(feature.pluginName),
        "version": str(version) if version is not None else None,
        "vendor": _non_empty_trimmed(feature.vendorName),
        "vendorEmail": _non_empty_trimmed(feature.vendorEmail),
        "vendorUrl": _non_empty_trimmed(feature.vendorUrl),
        "description": _non_empty_trimmed(feature.pluginDescription) or _non_empty_trimmed(project.description),
        "changeNotes": _non_empty_trimmed(feature.pluginChangeNotes),
        "sinceBuild": _non_empty_trimmed(feature.sinceBuild) or "232",
        "untilBuild": _non_empty_trimmed(feature.untilBuild),
    }


def _actual_xml_field(root: ET.Element, field_name: str) -> str | None:
    match field_name:
        case "id":
            return _xml_direct_child_text(root, "id")
        case "name":
            return _xml_direct_child_text(root, "name")
        case "version":
            return _xml_direct_child_text(root, "version")
        case "vendor":
            return _xml_direct_child_text(root, "vendor")
        case "vendorEmail":
            return _xml_direct_child_attribute(root, "vendor", "email")
        case "vendorUrl":
            return _xml_direct_child_attribute(root, "vendor", "url")
        case "description":
            return _xml_direct_child_text(root, "description")
        case "changeNotes":
            return _xml_direct_child_text(root, "change-notes")
        case "sinceBuild":
            return _xml_direct_child_attribute(root, "idea-version", "since-build")
        case "untilBuild":
            return _xml_direct_child_attribute(root, "idea-version", "until-build")
        case _:
            return None


def _display_value(value: str | None) -> str:
    return value if value is not None else "(missing)"


def _display_svg_dimension(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value.is_integer():
        return str(int(value))
    return str(value)


def _parse_svg_dimension(value: str | None) -> float | None:
    if value is None:
        return None
    match = SVG_DIMENSION_RE.fullmatch(value)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _svg_size(root: ET.Element) -> tuple[float | None, float | None]:
    width = _parse_svg_dimension(root.get("width"))
    height = _parse_svg_dimension(root.get("height"))
    if width is not None and height is not None:
        return width, height

    view_box = _non_empty_trimmed(root.get("viewBox"))
    if view_box is None:
        return width, height
    parts = view_box.replace(",", " ").split()
    if len(parts) != 4:
        return width, height
    try:
        return float(parts[2]), float(parts[3])
    except ValueError:
        return width, height


def _is_40_by_40(width: float | None, height: float | None) -> bool:
    if width is None or height is None:
        return False
    return abs(width - 40.0) < 0.001 and abs(height - 40.0) < 0.001


class IntellijMarketplaceMetadataCheck(ProjectCheck):
    order = 236

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        del path
        plugin = _marketplace_plugin(project)
        if plugin is None:
            return []

        gradle_project, feature = plugin
        issues: list[Issue] = []
        location = gradle_project.path

        plugin_name = _non_empty_trimmed(feature.pluginName)
        if plugin_name is None:
            issues.append(_metadata_issue(location, field="pluginName", reason="missing"))
        else:
            if len(plugin_name) > 30:
                issues.append(
                    _metadata_issue(
                        location,
                        field="pluginName",
                        reason=f"must be at most 30 characters, found {len(plugin_name)}",
                    )
                )
            if ASCII_PRINTABLE_RE.fullmatch(plugin_name) is None:
                issues.append(
                    _metadata_issue(
                        location,
                        field="pluginName",
                        reason="must use ASCII/Latin characters and printable symbols only",
                    )
                )
            lowered_name = plugin_name.casefold()
            for term in FORBIDDEN_PLUGIN_NAME_TERMS:
                if re.search(rf"\b{re.escape(term)}\b", lowered_name) is not None:
                    issues.append(
                        _metadata_issue(
                            location,
                            field="pluginName",
                            reason=f"must not contain the reserved term {term!r}",
                        )
                    )
                    break

        if _non_empty_trimmed(feature.pluginId) is None:
            issues.append(_metadata_issue(location, field="pluginId", reason="missing"))

        vendor_email = _non_empty_trimmed(feature.vendorEmail)
        if vendor_email is None:
            issues.append(_metadata_issue(location, field="vendorEmail", reason="missing"))
        elif not _is_valid_email(vendor_email):
            issues.append(_metadata_issue(location, field="vendorEmail", reason=f"invalid email {vendor_email!r}"))

        vendor_url = _non_empty_trimmed(feature.vendorUrl)
        if vendor_url is None:
            issues.append(_metadata_issue(location, field="vendorUrl", reason="missing"))
        elif not _is_valid_url(vendor_url):
            issues.append(_metadata_issue(location, field="vendorUrl", reason=f"invalid URL {vendor_url!r}"))

        plugin_description = _non_empty_trimmed(feature.pluginDescription) or _non_empty_trimmed(
            gradle_project.description
        )
        if plugin_description is None:
            issues.append(_metadata_issue(location, field="pluginDescription", reason="missing"))
        elif _contains_placeholder(plugin_description, DESCRIPTION_PLACEHOLDERS):
            issues.append(
                _metadata_issue(location, field="pluginDescription", reason="contains placeholder text")
            )

        change_notes = _non_empty_trimmed(feature.pluginChangeNotes)
        if change_notes is None:
            issues.append(_metadata_issue(location, field="pluginChangeNotes", reason="missing"))
        elif _contains_placeholder(change_notes, CHANGE_NOTES_PLACEHOLDERS):
            issues.append(
                _metadata_issue(location, field="pluginChangeNotes", reason="contains placeholder text")
            )

        if gradle_project.license is not None and gradle_project.github_repo is None:
            issues.append(E_INTELLIJ_MARKETPLACE_SOURCE_LINK_MISSING.at(location))

        return issues


class IntellijPluginXmlAssetsCheck(ProjectCheck):
    order = 237

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        del path
        plugin = _marketplace_plugin(project)
        if plugin is None:
            return []

        gradle_project, feature = plugin
        issues: list[Issue] = []
        plugin_xml_path = _plugin_xml_path(gradle_project)
        fix_plugin_xml = (
            (lambda: rerun_setup_for_project(gradle_project)) if can_regenerate_with_setup(gradle_project) else None
        )

        if not plugin_xml_path.is_file():
            issue = E_INTELLIJ_PLUGIN_XML_MISSING.at(plugin_xml_path)
            if fix_plugin_xml is not None:
                issue = issue.fixable(fix_plugin_xml)
            issues.append(issue)
        else:
            try:
                root = ET.fromstring(plugin_xml_path.read_text(encoding="utf-8"))
            except OSError as ex:
                issues.append(E_INTELLIJ_PLUGIN_XML_PARSE_ERROR.make(error=str(ex)).at(plugin_xml_path))
            except ET.ParseError as ex:
                issues.append(E_INTELLIJ_PLUGIN_XML_PARSE_ERROR.make(error=str(ex)).at(plugin_xml_path))
            else:
                if root.tag != "idea-plugin":
                    issues.append(
                        E_INTELLIJ_PLUGIN_XML_PARSE_ERROR.make(
                            error=f"unexpected root tag {root.tag!r}",
                        ).at(plugin_xml_path)
                    )
                else:
                    for field_name, expected_value in _expected_xml_fields(gradle_project, feature).items():
                        if expected_value is None:
                            continue
                        actual_value = _actual_xml_field(root, field_name)
                        if actual_value != expected_value:
                            issue = E_INTELLIJ_PLUGIN_XML_DRIFT.make(
                                field=field_name,
                                expected=_display_value(expected_value),
                                actual=_display_value(actual_value),
                            ).at(plugin_xml_path)
                            if fix_plugin_xml is not None:
                                issue = issue.fixable(fix_plugin_xml)
                            issues.append(issue)

                    expected_depends = _expected_depends(feature)
                    actual_depends = _xml_depends(root)
                    if actual_depends != expected_depends:
                        issue = E_INTELLIJ_PLUGIN_XML_DRIFT.make(
                            field="depends",
                            expected=", ".join(expected_depends),
                            actual=", ".join(actual_depends) if actual_depends else "(missing)",
                        ).at(plugin_xml_path)
                        if fix_plugin_xml is not None:
                            issue = issue.fixable(fix_plugin_xml)
                        issues.append(issue)

        icon_path = _plugin_icon_path(gradle_project)
        if not icon_path.is_file():
            issues.append(E_INTELLIJ_PLUGIN_ICON_MISSING.at(icon_path))
            return issues

        try:
            icon_root = ET.fromstring(icon_path.read_text(encoding="utf-8"))
        except OSError as ex:
            issues.append(E_INTELLIJ_PLUGIN_ICON_PARSE_ERROR.make(error=str(ex)).at(icon_path))
            return issues
        except ET.ParseError as ex:
            issues.append(E_INTELLIJ_PLUGIN_ICON_PARSE_ERROR.make(error=str(ex)).at(icon_path))
            return issues

        if not icon_root.tag.endswith("svg"):
            issues.append(E_INTELLIJ_PLUGIN_ICON_PARSE_ERROR.make(error="root element is not <svg>").at(icon_path))
            return issues

        width, height = _svg_size(icon_root)
        if not _is_40_by_40(width, height):
            issues.append(
                E_INTELLIJ_PLUGIN_ICON_SIZE_INVALID.make(
                    width=_display_svg_dimension(width),
                    height=_display_svg_dimension(height),
                ).at(icon_path)
            )

        return issues


__all__ = [
    "E_INTELLIJ_MARKETPLACE_METADATA_INVALID",
    "E_INTELLIJ_MARKETPLACE_SOURCE_LINK_MISSING",
    "E_INTELLIJ_PLUGIN_ICON_MISSING",
    "E_INTELLIJ_PLUGIN_ICON_PARSE_ERROR",
    "E_INTELLIJ_PLUGIN_ICON_SIZE_INVALID",
    "E_INTELLIJ_PLUGIN_XML_DRIFT",
    "E_INTELLIJ_PLUGIN_XML_MISSING",
    "E_INTELLIJ_PLUGIN_XML_PARSE_ERROR",
    "IntellijMarketplaceMetadataCheck",
    "IntellijPluginXmlAssetsCheck",
]
