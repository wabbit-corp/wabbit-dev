import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from dev.config import JvmKotlinAgent, JvmKotlinApplication


def _load_feature_types() -> tuple[type["JvmKotlinApplication"], type["JvmKotlinAgent"]]:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.config import JvmKotlinAgent, JvmKotlinApplication

    return JvmKotlinApplication, JvmKotlinAgent


def test_jvm_kotlin_application_normalizes_jar_name() -> None:
    JvmKotlinApplication, _JvmKotlinAgent = _load_feature_types()

    feature = JvmKotlinApplication(main="com.example.Main", jarName="app.jar")

    assert feature.jarName == "app.jar"
    assert feature.shadedJarName == "app.jar"
    assert feature.unshadedJarName == "app-unshaded.jar"


def test_jvm_kotlin_application_normalizes_unshaded_input() -> None:
    JvmKotlinApplication, _JvmKotlinAgent = _load_feature_types()

    feature = JvmKotlinApplication(
        main="com.example.Main",
        unshadedJarName="agent-unshaded.jar",
    )

    assert feature.jarName == "agent-unshaded.jar"
    assert feature.shadedJarName == "agent-unshaded-shaded.jar"
    assert feature.unshadedJarName == "agent-unshaded.jar"


def test_jvm_kotlin_application_rejects_multiple_jar_inputs() -> None:
    JvmKotlinApplication, _JvmKotlinAgent = _load_feature_types()

    with pytest.raises(ValueError, match="Provide only one of jarName"):
        JvmKotlinApplication(
            main="com.example.Main",
            jarName="app.jar",
            shadedJarName="app-shaded.jar",
        )


def test_jvm_kotlin_agent_rejects_multiple_jar_inputs() -> None:
    _JvmKotlinApplication, JvmKotlinAgent = _load_feature_types()

    with pytest.raises(ValueError, match="Provide only one of jarName"):
        JvmKotlinAgent(
            main="com.example.Agent",
            jarName="agent.jar",
            unshadedJarName="agent-unshaded.jar",
        )


def test_jvm_kotlin_agent_rejects_non_jar_extension() -> None:
    _JvmKotlinApplication, JvmKotlinAgent = _load_feature_types()

    with pytest.raises(ValueError, match="Expected \\.jar file"):
        JvmKotlinAgent(main="com.example.Agent", shadedJarName="agent.zip")
