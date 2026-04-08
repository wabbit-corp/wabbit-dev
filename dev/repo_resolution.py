from pathlib import Path

from dev.config import load_config, project_repo_root
from dev.discoverability import did_you_mean_suffix


def resolve_repo_target(target: str) -> tuple[str, Path]:
    path = Path(target)
    if path.exists():
        return target, path

    if not Path("./root.clj").exists():
        return target, path

    try:
        config = load_config()
    except Exception:
        return target, path

    project = config.defined_projects.get(target)
    if project is None:
        raise ValueError(
            "Target does not exist as a path and is not a configured project: "
            f"{target!r}.{did_you_mean_suffix(target, config.defined_projects)}"
        )
    return target, project_repo_root(project)


__all__ = ["resolve_repo_target"]
