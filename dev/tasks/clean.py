#!/usr/bin/env python3

import errno
import os
import shutil
import stat
import sys
from pathlib import Path

import dev.io
from dev.config import GradleProject, PythonProject, load_config

DRY_RUN = False


def delete_dir(path):
    import os

    if not os.path.exists(path):
        return

    if not os.path.isdir(path):
        print(f"Not a directory: {path}")
        return

    if DRY_RUN:
        print(f"Deleting {path}")
    else:

        def handleRemoveReadonly(func, path, exc):
            excvalue = exc[1]
            # print(func, path, exc, excvalue.errno, errno.EACCES)
            if func in (os.rmdir, os.unlink, os.remove) and excvalue.errno == errno.EACCES:
                os.chmod(path, stat.S_IRWXU)
                func(path)
            else:
                raise

        try:
            shutil.rmtree(path, ignore_errors=False, onerror=handleRemoveReadonly)
        except OSError:
            print(f"Please delete {path} manually")
            return
        print(f"Deleted {path}")


def clean_sbt_project(path):
    # print("Cleaning %s" % path)

    def go(dirpath):
        assert os.path.exists(dirpath) and os.path.isdir(dirpath)

        likely_project = (
            os.path.exists(os.path.join(dirpath, "build.sbt"))
            or os.path.exists(os.path.join(dirpath, "project/build.sbt"))
            or os.path.exists(os.path.join(dirpath, "src/main/scala"))
            or os.path.exists(os.path.join(dirpath, "src/main/java"))
            or os.path.exists(os.path.join(dirpath, "target/scala-2.12"))
            or os.path.exists(os.path.join(dirpath, "target/scala-2.13"))
            or os.path.exists(os.path.join(dirpath, "target/scala-2.11"))
        )

        if not likely_project:
            return

        delete_dir(os.path.join(dirpath, "target"))
        delete_dir(os.path.join(dirpath, "project/target"))
        delete_dir(os.path.join(dirpath, "project/project/target"))
        delete_dir(os.path.join(dirpath, ".bloop"))
        delete_dir(os.path.join(dirpath, ".metals"))

        for dirpath1 in os.listdir(dirpath):
            dirpath1 = os.path.join(dirpath, dirpath1)
            if not os.path.isdir(dirpath1):
                continue

            go(dirpath1)

    go(path)


def clean_gradle_project(path):
    # print("Cleaning %s" % path)

    def go(dirpath):
        assert os.path.exists(dirpath) and os.path.isdir(dirpath)

        likely_project = (
            os.path.exists(os.path.join(dirpath, "build.gradle"))
            or os.path.exists(os.path.join(dirpath, "build.gradle.kts"))
            or os.path.exists(os.path.join(dirpath, "settings.gradle"))
            or os.path.exists(os.path.join(dirpath, "settings.gradle.kts"))
            or os.path.exists(os.path.join(dirpath, "src/main/kotlin"))
            or os.path.exists(os.path.join(dirpath, "src/main/java"))
        )

        if not likely_project:
            return

        delete_dir(os.path.join(dirpath, "build"))
        delete_dir(os.path.join(dirpath, "out"))

        for dirpath1 in os.listdir(dirpath):
            dirpath1 = os.path.join(dirpath, dirpath1)
            if not os.path.isdir(dirpath1):
                continue

            go(dirpath1)

    go(path)


def clean_maven_project(path):
    # print("Cleaning %s" % path)

    def go(dirpath):
        assert os.path.exists(dirpath) and os.path.isdir(dirpath)

        likely_project = os.path.exists(os.path.join(dirpath, "pom.xml")) or os.path.exists(
            os.path.join(dirpath, "src/main/java")
        )

        if not likely_project:
            return

        delete_dir(os.path.join(dirpath, "target"))

        for dirpath1 in os.listdir(dirpath):
            dirpath1 = os.path.join(dirpath, dirpath1)
            if not os.path.isdir(dirpath1):
                continue

            go(dirpath1)

    go(path)


def clean_node_project(path):
    # print("Cleaning %s" % path)

    def go(dirpath):
        assert os.path.exists(dirpath) and os.path.isdir(dirpath)

        likely_project = os.path.exists(os.path.join(dirpath, "package.json")) or os.path.exists(
            os.path.join(dirpath, "node_modules")
        )

        if not likely_project:
            return

        delete_dir(os.path.join(dirpath, "node_modules"))

        for dirpath1 in os.listdir(dirpath):
            dirpath1 = os.path.join(dirpath, dirpath1)
            if not os.path.isdir(dirpath1):
                continue

            go(dirpath1)

    go(path)


def clean(paths):
    for path in paths:
        for dirpath, _dirnames, filenames in os.walk(path):
            if "build.sbt" in filenames:
                clean_sbt_project(dirpath)

            GRADLE_NAMES = [
                "gradle",
                "gradlew",
                "gradlew.bat",
                "gradle.properties",
                "build.gradle",
                "settings.gradle",
                "build.gradle.kts",
                "settings.gradle.kts",
            ]
            if any(name in filenames for name in GRADLE_NAMES):
                clean_gradle_project(dirpath)

            if "pom.xml" in filenames:
                clean_maven_project(dirpath)

            # if ('package.json' in filenames or 'package-lock.json' in filenames or 'yarn.lock' in filenames) and 'node_modules' in dirnames:
            #     print("Possible node project: %s" % dirpath)

            # if 'requirements.txt' in filenames:
            #     print("Possible python project: %s" % dirpath)

            # if 'Gemfile' in filenames:
            #     print("Possible ruby project: %s" % dirpath)

            # if 'Makefile' in filenames:
            #     print("Possible make project: %s" % dirpath)

            # if 'CMakeLists.txt' in filenames:
            #     print("Possible cmake project: %s" % dirpath)

            # if 'build.xml' in filenames:
            #     print("Possible ant project: %s" % dirpath)

            # if 'build.sh' in filenames:
            #     print("Possible build.sh project: %s" % dirpath)


if __name__ == "__main__":
    if sys.argv[1:]:
        clean(sys.argv[1:])
    else:
        print(f"Usage: {sys.argv[0]} <folder> [<folder>...]")


def clean(project_name: str | None) -> None:
    config = load_config()

    dev.io.delete_if_exists(Path("__pycache__"))
    dev.io.delete_if_exists(Path(".gradle"))
    dev.io.delete_if_exists(Path(".kotlin"))
    dev.io.delete_if_exists(Path(".mypy_cache"))
    dev.io.delete_if_exists(Path(".pytest_cache"))
    dev.io.delete_if_exists(Path("build"))

    for name, project in config.defined_projects.items():
        if project_name is not None and name != project_name:
            continue

        if isinstance(project, GradleProject):
            # FIXME: For now, we only support Gradle projects
            dev.io.delete_if_exists(project.path / "build")
            dev.io.delete_if_exists(project.path / "bin")
            dev.io.delete_if_exists(project.path / ".gradle")
            dev.io.delete_if_exists(project.path / ".kotlin")
            dev.io.delete_if_exists(project.path / ".mypy_cache")
            dev.io.delete_if_exists(project.path / "__pycache__")
        elif isinstance(project, PythonProject):
            # Find all __pycache__ directories and delete them
            for pycache in project.path.glob("**/__pycache__"):
                dev.io.delete_if_exists(pycache)
            dev.io.delete_if_exists(project.path / ".mypy_cache")
            dev.io.delete_if_exists(project.path / ".pytest_cache")
