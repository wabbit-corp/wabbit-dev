from __future__ import annotations

from dev.tasks.setup_kotlin import java_version_for_features, kotlin_jvm_target_for_version


def test_java_version_for_features_uses_global_default_without_intellij_plugin() -> None:
    assert java_version_for_features(21, {"jvm-kotlin-library": object()}) == 21


def test_java_version_for_features_forces_17_for_intellij_plugin() -> None:
    assert java_version_for_features(21, {"intellij-plugin": object()}) == 17


def test_kotlin_jvm_target_for_version_handles_legacy_java_8_name() -> None:
    assert kotlin_jvm_target_for_version(8) == "JVM_1_8"
    assert kotlin_jvm_target_for_version(17) == "JVM_17"
