from __future__ import annotations

from dev.config import IntellijPlugin
from dev.tasks.setup_kotlin import (
    _renderable_gradle_features,
    _uses_intellij_platform_gradle_plugin_v2,
    java_version_for_features,
    kotlin_jvm_target_for_version,
)


def test_java_version_for_features_uses_global_default_without_intellij_plugin() -> None:
    assert java_version_for_features(21, {"jvm-kotlin-library": object()}) == 21


def test_java_version_for_features_forces_17_for_intellij_plugin() -> None:
    assert java_version_for_features(21, {"intellij-plugin": object()}) == 17


def test_kotlin_jvm_target_for_version_handles_legacy_java_8_name() -> None:
    assert kotlin_jvm_target_for_version(8) == "JVM_1_8"
    assert kotlin_jvm_target_for_version(17) == "JVM_17"


def test_renderable_gradle_features_infers_intellij_bundled_plugins_from_depends() -> None:
    rendered = _renderable_gradle_features(
        {
            "intellij-plugin": IntellijPlugin(
                pluginName="Demo",
                depends=["com.intellij.modules.platform", "org.jetbrains.kotlin", "com.intellij.gradle"],
            )
        }
    )

    feature = rendered["intellij-plugin"]
    assert isinstance(feature, IntellijPlugin)
    assert feature.bundledPlugins == ["org.jetbrains.kotlin", "com.intellij.gradle"]


def test_renderable_gradle_features_preserves_explicit_intellij_bundled_plugins() -> None:
    rendered = _renderable_gradle_features(
        {
            "intellij-plugin": IntellijPlugin(
                pluginName="Demo",
                depends=["com.intellij.modules.platform", "org.jetbrains.kotlin"],
                bundledPlugins=["com.intellij.java"],
            )
        }
    )

    feature = rendered["intellij-plugin"]
    assert isinstance(feature, IntellijPlugin)
    assert feature.bundledPlugins == ["com.intellij.java"]


def test_uses_intellij_platform_gradle_plugin_v2_for_2025_3_targets() -> None:
    assert _uses_intellij_platform_gradle_plugin_v2(
        IntellijPlugin(
            pluginName="Demo",
            ideaVersion="2025.3",
            sinceBuild="253",
        )
    )


def test_uses_intellij_platform_gradle_plugin_v2_keeps_older_targets_on_legacy_plugin() -> None:
    assert not _uses_intellij_platform_gradle_plugin_v2(
        IntellijPlugin(
            pluginName="Demo",
            ideaVersion="2023.2",
            sinceBuild="232",
        )
    )
