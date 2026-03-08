from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dev.jvms import InstalledJvm, parse_macos_java_home_listing, resolve_project_jvm_policy, select_jvm


def test_parse_macos_java_home_listing_extracts_version_implementor_and_path() -> None:
    listing = """
Matching Java Virtual Machines (3):
    21.0.10 (arm64) "GraalVM Community" - "GraalVM CE 21" /Library/Java/JavaVirtualMachines/graalvm-21.jdk/Contents/Home
    21.0.9 (arm64) "Amazon Corretto" - "Corretto 21.0.9" /Users/test/Library/Java/JavaVirtualMachines/corretto-21.0.9/Contents/Home
    17.0.13 (arm64) "Eclipse Adoptium" - "Temurin 17" /Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home
""".strip()

    jvms = parse_macos_java_home_listing(listing)

    assert [jvm.version for jvm in jvms] == [(21, 0, 10), (21, 0, 9), (17, 0, 13)]
    assert jvms[0].implementor == "GraalVM Community"
    assert jvms[1].implementor == "Amazon Corretto"
    assert jvms[1].architecture == "arm64"
    assert jvms[2].home == Path("/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home")


def test_android_agp_policy_prefers_corretto_over_graalvm_for_java_21() -> None:
    installed = [
        InstalledJvm(
            home=Path("/Library/Java/JavaVirtualMachines/graalvm-21.jdk/Contents/Home"),
            version=(21, 0, 10),
            implementor="GraalVM Community",
        ),
        InstalledJvm(
            home=Path("/Users/test/Library/Java/JavaVirtualMachines/corretto-21.0.9/Contents/Home"),
            version=(21, 0, 9),
            implementor="Amazon Corretto",
        ),
    ]

    selected = select_jvm(installed, policy_name="android-agp-21")

    assert selected is not None
    assert selected.implementor == "Amazon Corretto"


def test_generic_jvm_policy_prefers_latest_matching_version() -> None:
    installed = [
        InstalledJvm(home=Path("/jdk-21.0.5"), version=(21, 0, 5), implementor="Amazon Corretto"),
        InstalledJvm(home=Path("/jdk-21.0.10"), version=(21, 0, 10), implementor="GraalVM Community"),
        InstalledJvm(home=Path("/jdk-17.0.13"), version=(17, 0, 13), implementor="Eclipse Adoptium"),
    ]

    selected = select_jvm(installed, policy_name="jvm-21")

    assert selected is not None
    assert selected.home == Path("/jdk-21.0.10")


def test_resolve_project_jvm_policy_uses_task_override_then_module_then_repo_then_global() -> None:
    project = SimpleNamespace(
        jvm_policy="jvm-17",
        jvm_task_policies={
            "*Android*": "android-agp-21",
            "compileKotlinJvm": "jvm-21",
        },
    )

    assert (
        resolve_project_jvm_policy(
            project,
            task_name="compileDebugKotlinAndroid",
            repo_policy="jvm-11",
            global_jvm_version=8,
        )
        == "android-agp-21"
    )
    assert (
        resolve_project_jvm_policy(
            project,
            task_name="compileKotlinJvm",
            repo_policy="jvm-11",
            global_jvm_version=8,
        )
        == "jvm-21"
    )
    assert (
        resolve_project_jvm_policy(
            SimpleNamespace(jvm_policy="jvm-17", jvm_task_policies={}),
            task_name=None,
            repo_policy="jvm-11",
            global_jvm_version=8,
        )
        == "jvm-17"
    )
    assert (
        resolve_project_jvm_policy(
            SimpleNamespace(jvm_policy=None, jvm_task_policies={}),
            task_name=None,
            repo_policy="jvm-11",
            global_jvm_version=8,
        )
        == "jvm-11"
    )
    assert (
        resolve_project_jvm_policy(
            SimpleNamespace(jvm_policy=None, jvm_task_policies={}),
            task_name=None,
            repo_policy=None,
            global_jvm_version=8,
        )
        == "jvm-8"
    )
