from pathlib import Path
import sys


def _load_config_symbols():
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    from dev.config import Feature, resolve_features

    return Feature, resolve_features


def test_resolve_features_is_transitive() -> None:
    Feature, resolve_features = _load_config_symbols()

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
