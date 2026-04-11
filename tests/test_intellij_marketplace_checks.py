from __future__ import annotations

import os
import sys
from pathlib import Path

from dev.checks.intellij_marketplace import (
    E_INTELLIJ_MARKETPLACE_METADATA_INVALID,
    E_INTELLIJ_MARKETPLACE_SOURCE_LINK_MISSING,
    E_INTELLIJ_PLUGIN_ICON_MISSING,
    E_INTELLIJ_PLUGIN_ICON_SIZE_INVALID,
    E_INTELLIJ_PLUGIN_XML_DRIFT,
    E_INTELLIJ_PLUGIN_XML_MISSING,
    IntellijMarketplaceMetadataCheck,
    IntellijPluginXmlAssetsCheck,
)


def _load_from_temp_root(
    tmp_path: Path,
    root_clj: str,
    root_private_clj: str = '(github-token "dummy")\n',
):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.config import load_config

    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "root.clj").write_text(root_clj, encoding="utf-8")
    (tmp_path / "root.private.clj").write_text(root_private_clj, encoding="utf-8")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return load_config()
    finally:
        os.chdir(cwd)


def _intellij_project_root_clj(*, repo: str | None = "wabbit-corp/demo-ij", plugin_name: str = "Demo Tool") -> str:
    repo_form = f':repo "{repo}" ' if repo is not None else ""
    return "\n".join(
        [
            '(default-maven-project-group "one.wabbit")',
            "("
            'gradle "demo-ij" '
            ':version "0.1.0" '
            ':license "AGPL" '
            f"{repo_form}"
            ":features [("
            f'intellij-plugin "{plugin_name}" '
            ':pluginId "one.wabbit.demo" '
            ':sinceBuild "232" '
            ':vendorName "Wabbit Consulting Corporation" '
            ':vendorEmail "wabbit@wabbit.one" '
            ':vendorUrl "https://wabbit.one" '
            ':pluginDescription "Applies structured edits inside the IDE." '
            ':pluginChangeNotes "Initial release." '
            ':depends ["com.intellij.modules.platform"])]'
            ")",
            "",
        ]
    )


def test_intellij_marketplace_metadata_check_accepts_valid_plugin_metadata(tmp_path: Path) -> None:
    config = _load_from_temp_root(tmp_path, _intellij_project_root_clj())
    project = config.defined_projects["demo-ij"]
    project.path.mkdir(parents=True, exist_ok=True)

    issues = IntellijMarketplaceMetadataCheck().check(project.path, project)

    assert issues == []


def test_intellij_marketplace_metadata_check_reports_invalid_fields(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        _intellij_project_root_clj(repo=None, plugin_name="Demo Plugin")
        .replace(':vendorEmail "wabbit@wabbit.one" ', "")
        .replace(':vendorUrl "https://wabbit.one" ', ':vendorUrl "notaurl" ')
        .replace(':pluginChangeNotes "Initial release." ', ':pluginChangeNotes "Add change notes here" '),
    )
    project = config.defined_projects["demo-ij"]
    project.path.mkdir(parents=True, exist_ok=True)

    issues = IntellijMarketplaceMetadataCheck().check(project.path, project)

    issue_ids = [issue.issue_type for issue in issues]
    assert issue_ids.count(E_INTELLIJ_MARKETPLACE_METADATA_INVALID) == 4
    assert E_INTELLIJ_MARKETPLACE_SOURCE_LINK_MISSING in issue_ids
    reasons = {
        ((issue.data or {}).get("field"), (issue.data or {}).get("reason"))
        for issue in issues
        if issue.issue_type == E_INTELLIJ_MARKETPLACE_METADATA_INVALID
    }
    assert ("pluginName", "must not contain the reserved term 'plugin'") in reasons
    assert ("vendorEmail", "missing") in reasons
    assert ("vendorUrl", "invalid URL 'notaurl'") in reasons
    assert ("pluginChangeNotes", "contains placeholder text") in reasons


def test_intellij_plugin_xml_assets_check_reports_missing_managed_files(tmp_path: Path) -> None:
    config = _load_from_temp_root(tmp_path, _intellij_project_root_clj())
    project = config.defined_projects["demo-ij"]
    project.path.mkdir(parents=True, exist_ok=True)

    issues = IntellijPluginXmlAssetsCheck().check(project.path, project)

    assert [issue.issue_type for issue in issues] == [E_INTELLIJ_PLUGIN_XML_MISSING, E_INTELLIJ_PLUGIN_ICON_MISSING]
    assert issues[0].fix is not None
    assert issues[1].fix is None


def test_intellij_plugin_xml_assets_check_reports_xml_drift_and_icon_size(tmp_path: Path) -> None:
    config = _load_from_temp_root(tmp_path, _intellij_project_root_clj())
    project = config.defined_projects["demo-ij"]
    plugin_xml_path = project.path / "src" / "main" / "resources" / "META-INF" / "plugin.xml"
    plugin_xml_path.parent.mkdir(parents=True, exist_ok=True)
    plugin_xml_path.write_text(
        "\n".join(
            [
                "<idea-plugin>",
                "    <id>wrong.id</id>",
                "    <name>Demo Tool</name>",
                "    <version>0.1.0</version>",
                '    <vendor email="wabbit@wabbit.one" url="https://wabbit.one">Wabbit Consulting Corporation</vendor>',
                "    <description>Applies structured edits inside the IDE.</description>",
                "    <change-notes>Initial release.</change-notes>",
                '    <idea-version since-build="232" />',
                "    <depends>com.intellij.modules.platform</depends>",
                "</idea-plugin>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_xml_path.parent / "pluginIcon.svg").write_text(
        '<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"></svg>\n',
        encoding="utf-8",
    )

    issues = IntellijPluginXmlAssetsCheck().check(project.path, project)

    issue_types = [issue.issue_type for issue in issues]
    assert E_INTELLIJ_PLUGIN_XML_DRIFT in issue_types
    assert E_INTELLIJ_PLUGIN_ICON_SIZE_INVALID in issue_types
