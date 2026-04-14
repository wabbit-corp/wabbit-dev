from __future__ import annotations

from pathlib import Path

from dev.config import GradleProject, IntellijPlugin, OwnershipType, Version
from dev.tasks.setup_kotlin import _sync_intellij_plugin_xml


def _make_gradle_project(path: Path) -> GradleProject:
    return GradleProject(
        path=path,
        group_name="one.wabbit",
        name="ij-diff-paste",
        version=Version.parse("0.0.1"),
        description="Applies clipboard diff patches directly to your open file.",
        authors=["Wabbit Consulting Corporation"],
        license="AGPL",
        quarantine=False,
        publish=True,
        github_repo="wabbit-corp/ij-diff-paste",
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
    )


def test_sync_intellij_plugin_xml_updates_metadata_and_preserves_actions(tmp_path: Path) -> None:
    project = _make_gradle_project(tmp_path)
    plugin_xml_path = project.path / "src" / "main" / "resources" / "META-INF" / "plugin.xml"
    plugin_xml_path.parent.mkdir(parents=True, exist_ok=True)
    plugin_xml_path.write_text(
        "\n".join(
            [
                "<idea-plugin>",
                "    <id>old.id</id>",
                "    <name>Old Name</name>",
                "    <version>9.9.9</version>",
                '    <vendor email="old@example.com">Old Vendor</vendor>',
                "    <depends>com.intellij.modules.platform</depends>",
                "    <actions>",
                '        <action id="ApplyDiffAction" class="one.wabbit.diffpaste.ApplyDiffAction" />',
                "    </actions>",
                "</idea-plugin>",
                "",
            ]
        ),
        encoding="utf-8",
    )

    feature = IntellijPlugin(
        pluginName="DiffPaste",
        pluginId="one.wabbit.diffpaste",
        sinceBuild="232",
        untilBuild=None,
        vendorName="Wabbit Consulting Corporation",
        vendorEmail="wabbit@wabbit.one",
        vendorUrl="https://wabbit.one",
        pluginDescription="Applies clipboard diff patches directly to your open file.",
        pluginChangeNotes="Initial release.",
        depends=["com.intellij.modules.platform"],
    )

    _sync_intellij_plugin_xml(project, feature, "Example Co")

    plugin_xml = plugin_xml_path.read_text(encoding="utf-8")
    assert "<id>one.wabbit.diffpaste</id>" in plugin_xml
    assert "<name>DiffPaste</name>" in plugin_xml
    assert "<version>0.0.1</version>" in plugin_xml
    assert 'email="wabbit@wabbit.one"' in plugin_xml
    assert 'url="https://wabbit.one"' in plugin_xml
    assert "<description>Applies clipboard diff patches directly to your open file.</description>" in plugin_xml
    assert "<change-notes>Initial release.</change-notes>" in plugin_xml
    assert '<idea-version since-build="232" />' in plugin_xml
    assert "until-build=" not in plugin_xml
    assert '<action id="ApplyDiffAction" class="one.wabbit.diffpaste.ApplyDiffAction" />' in plugin_xml


def test_sync_intellij_plugin_xml_prefers_standard_repo_changelog_entry(tmp_path: Path) -> None:
    project = _make_gradle_project(tmp_path)
    (project.effective_repo_root / "CHANGELOG.md").write_text(
        "\n".join(
            [
                "# Changelog",
                "",
                "## 0.0.1 - 2026-04-13",
                "",
                "Initial public release.",
                "",
                "- Adds structured IDE edits.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    feature = IntellijPlugin(
        pluginName="DiffPaste",
        pluginId="one.wabbit.diffpaste",
        sinceBuild="232",
        untilBuild=None,
        vendorName="Wabbit Consulting Corporation",
        vendorEmail="wabbit@wabbit.one",
        vendorUrl="https://wabbit.one",
        pluginDescription="Applies clipboard diff patches directly to your open file.",
        pluginChangeNotes="Stale manual notes.",
        depends=["com.intellij.modules.platform"],
    )

    _sync_intellij_plugin_xml(project, feature, "Example Co")

    plugin_xml_path = project.path / "src" / "main" / "resources" / "META-INF" / "plugin.xml"
    plugin_xml = plugin_xml_path.read_text(encoding="utf-8")
    assert "<change-notes>Initial public release.\n\n- Adds structured IDE edits.</change-notes>" in plugin_xml


def test_sync_intellij_plugin_xml_uses_default_vendor_name_when_missing(tmp_path: Path) -> None:
    project = _make_gradle_project(tmp_path)
    feature = IntellijPlugin(
        pluginName="DiffPaste",
        pluginId="one.wabbit.diffpaste",
        sinceBuild="232",
        untilBuild=None,
        vendorName=None,
        vendorEmail=None,
        vendorUrl=None,
        pluginDescription="Applies clipboard diff patches directly to your open file.",
        pluginChangeNotes="Initial release.",
        depends=["com.intellij.modules.platform"],
    )

    _sync_intellij_plugin_xml(project, feature, "Example Co")

    plugin_xml_path = project.path / "src" / "main" / "resources" / "META-INF" / "plugin.xml"
    plugin_xml = plugin_xml_path.read_text(encoding="utf-8")
    assert "<vendor>Example Co</vendor>" in plugin_xml
