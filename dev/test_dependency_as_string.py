from pathlib import Path, PureWindowsPath
import sys


def _dependency_types():
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    from dev.config import Dependency, DependencyTarget

    return Dependency, DependencyTarget


def test_dependency_as_string_jarfile_defaults_modifier_and_dir() -> None:
    Dependency, DependencyTarget = _dependency_types()

    dep = Dependency(scope=None, target=DependencyTarget.JarFile(path=Path("app.jar")))

    assert dep.as_string() == 'implementation(fileTree(mapOf("dir" to ".", "include" to listOf("app.jar"))))'


def test_dependency_as_string_jarfile_normalizes_windows_path() -> None:
    Dependency, DependencyTarget = _dependency_types()

    dep = Dependency(
        scope="runtimeOnly",
        target=DependencyTarget.JarFile(path=PureWindowsPath(r"C:\libs\agent.jar")),
    )

    assert dep.as_string() == 'runtimeOnly(fileTree(mapOf("dir" to "C:/libs", "include" to listOf("agent.jar"))))'


def test_dependency_as_string_jarfile_escapes_quotes() -> None:
    Dependency, DependencyTarget = _dependency_types()

    dep = Dependency(
        scope="implementation",
        target=DependencyTarget.JarFile(path=Path('lib"dir') / 'agent"core.jar'),
    )

    assert (
        dep.as_string()
        == 'implementation(fileTree(mapOf("dir" to "lib\\"dir", "include" to listOf("agent\\"core.jar"))))'
    )
