import sys
from pathlib import Path

import pytest


def _load_config_symbols():
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    from dev.config import Feature, Jvm, resolve_features

    return Feature, Jvm, resolve_features


def test_resolve_features_is_transitive() -> None:
    Feature, _Jvm, resolve_features = _load_config_symbols()

    class FeatureC(Feature):
        __feature_name__ = "feature-c"

    class FeatureB(Feature):
        __feature_name__ = "feature-b"

        def implied(self) -> list[Feature]:
            return [FeatureC()]

    class FeatureA(Feature):
        __feature_name__ = "feature-a"

        def implied(self) -> list[Feature]:
            return [FeatureB()]

    resolved = resolve_features([FeatureA()])

    assert set(resolved.keys()) == {"feature-a", "feature-b", "feature-c"}
    assert isinstance(resolved["feature-c"], FeatureC)


def test_resolve_features_merges_optional_fields() -> None:
    Feature, Jvm, resolve_features = _load_config_symbols()

    class NeedsJvmJar(Feature):
        __feature_name__ = "needs-jvm-jar"

        def implied(self) -> list[Feature]:
            return [Jvm(jarName="service.jar")]

    resolved = resolve_features([Jvm(jarName=None), NeedsJvmJar()])

    assert "jvm" in resolved
    assert resolved["jvm"] == Jvm(jarName="service.jar")


def test_resolve_features_rejects_conflicting_optional_field_values() -> None:
    Feature, Jvm, resolve_features = _load_config_symbols()

    class NeedsJvmJarA(Feature):
        __feature_name__ = "needs-jvm-jar-a"

        def implied(self) -> list[Feature]:
            return [Jvm(jarName="a.jar")]

    class NeedsJvmJarB(Feature):
        __feature_name__ = "needs-jvm-jar-b"

        def implied(self) -> list[Feature]:
            return [Jvm(jarName="b.jar")]

    with pytest.raises(ValueError):
        resolve_features([NeedsJvmJarA(), NeedsJvmJarB()])
