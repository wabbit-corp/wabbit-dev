from pathlib import Path

import dev.io
from dev.config import load_config, GradleProject


def clean(project_name: str | None) -> None:
    config = load_config()

    dev.io.delete_if_exists(Path('__pycache__'))
    dev.io.delete_if_exists(Path('.gradle'))
    dev.io.delete_if_exists(Path('.kotlin'))
    dev.io.delete_if_exists(Path('.mypy_cache'))
    dev.io.delete_if_exists(Path('build'))

    for name, project in config.defined_projects.items():
        if project_name is not None and name != project_name:
            continue

        assert isinstance(project, GradleProject) # FIXME: For now, we only support Gradle projects

        dev.io.delete_if_exists(project.path / 'build')
        dev.io.delete_if_exists(project.path / 'bin')
        dev.io.delete_if_exists(project.path / '.gradle')
        dev.io.delete_if_exists(project.path / '.kotlin')
        dev.io.delete_if_exists(project.path / '.mypy_cache')
        dev.io.delete_if_exists(project.path / '__pycache__')

