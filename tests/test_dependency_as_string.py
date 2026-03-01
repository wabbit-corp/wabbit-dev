from pathlib import Path, PureWindowsPath
from typing import cast

from dev.config import Dependency, DependencyTarget


def test_dependency_as_string_jarfile_defaults_modifier_and_dir() -> None:
    dep = Dependency(scope=None, target=DependencyTarget.JarFile(path=Path("app.jar")))

    assert dep.as_string() == 'implementation(fileTree(mapOf("dir" to ".", "include" to listOf("app.jar"))))'


def test_dependency_as_string_jarfile_normalizes_windows_path() -> None:
    dep = Dependency(
        scope="runtimeOnly",
        target=DependencyTarget.JarFile(path=cast(Path, PureWindowsPath(r"C:\libs\agent.jar"))),
    )

    assert dep.as_string() == 'runtimeOnly(fileTree(mapOf("dir" to "C:/libs", "include" to listOf("agent.jar"))))'


def test_dependency_as_string_jarfile_escapes_quotes() -> None:
    dep = Dependency(
        scope="implementation",
        target=DependencyTarget.JarFile(path=Path('lib"dir') / 'agent"core.jar'),
    )

    assert (
        dep.as_string()
        == 'implementation(fileTree(mapOf("dir" to "lib\\"dir", "include" to listOf("agent\\"core.jar"))))'
    )
