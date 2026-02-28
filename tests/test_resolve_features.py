import pytest

from dev.config import Feature, Jvm, resolve_features


def test_resolve_features_is_transitive() -> None:
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
    class NeedsJvmJar(Feature):
        __feature_name__ = "needs-jvm-jar"

        def implied(self) -> list[Feature]:
            return [Jvm(jarName="service.jar")]

    resolved = resolve_features([Jvm(jarName=None), NeedsJvmJar()])

    assert "jvm" in resolved
    assert resolved["jvm"] == Jvm(jarName="service.jar")


def test_resolve_features_rejects_conflicting_optional_field_values() -> None:
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
