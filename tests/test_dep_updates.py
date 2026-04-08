from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from dev.config import Config, OwnershipType, PythonProject
from dev.pypi import PyPiProjectMetadata
from dev.tasks import dep_updates as dep_updates_task


def _python_project(
    *,
    name: str = "demo",
    dependencies: list[str] | None = None,
    dev_dependencies: list[str] | None = None,
) -> PythonProject:
    return PythonProject(
        path=Path(f"/tmp/{name}"),
        name=name,
        version=None,
        description=None,
        authors=[],
        license=None,
        github_repo=None,
        requires_python=None,
        dependencies=dependencies or [],
        dev_dependencies=dev_dependencies or [],
        scripts=[],
        application=None,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=False,
        ownership=OwnershipType.WABBIT,
    )


def test_check_for_updates_reports_pinned_pypi_dependency_updates(
    monkeypatch,
    capsys,
) -> None:
    config = Config(
        raw=None,
        libraries=OrderedDict(),
        repositories=OrderedDict(),
        defined_projects=OrderedDict(
            {
                "demo": _python_project(
                    name="demo",
                    dependencies=["requests==2.31.0"],
                    dev_dependencies=["pytest==8.0.0"],
                )
            }
        ),
    )
    monkeypatch.setattr(dep_updates_task, "load_config", lambda: config)
    monkeypatch.setattr(dep_updates_task, "fetch_project_metadata", lambda name: {
        "requests": PyPiProjectMetadata(latest_version="2.32.3", releases=["2.31.0", "2.32.3"]),
        "pytest": PyPiProjectMetadata(latest_version="8.3.5", releases=["8.0.0", "8.3.5"]),
    }[name])

    dep_updates_task.check_for_updates()

    output = capsys.readouterr().out.strip().splitlines()
    assert output == [
        "demo: requests 2.31.0 < 2.32.3",
        "demo [dev]: pytest 8.0.0 < 8.3.5",
    ]


def test_check_for_updates_skips_unpinned_direct_url_and_prerelease_only_updates(
    monkeypatch,
    capsys,
) -> None:
    config = Config(
        raw=None,
        libraries=OrderedDict(),
        repositories=OrderedDict(),
        defined_projects=OrderedDict(
            {
                "demo": _python_project(
                    dependencies=[
                        "urllib3>=2.0,<3.0",
                        "demo-pkg @ https://example.com/demo-pkg-1.0.0.tar.gz",
                        "rich==13.7.0",
                    ]
                )
            }
        ),
    )
    monkeypatch.setattr(dep_updates_task, "load_config", lambda: config)
    monkeypatch.setattr(
        dep_updates_task,
        "fetch_project_metadata",
        lambda name: PyPiProjectMetadata(
            latest_version="13.8.0rc1",
            releases=["13.7.0", "13.8.0rc1"],
        ),
    )

    dep_updates_task.check_for_updates()

    assert capsys.readouterr().out == ""
