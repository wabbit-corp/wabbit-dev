from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_from_temp_root(
    tmp_path: Path,
    root_clj: str,
    root_private_clj: str = '(github-token "dummy")\n',
):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from dev.config import load_config

    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "root.clj").write_text(root_clj, encoding="utf-8")
    (tmp_path / "root.private.clj").write_text(root_private_clj, encoding="utf-8")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return load_config()
    finally:
        os.chdir(cwd)


def test_kmp_source_layout_drift_check_reports_requested_drift_cases(tmp_path: Path) -> None:
    from dev.checks.layout_drift import KmpSourceLayoutDriftCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-kmp" '
                ':version "0.1.0" '
                ':buildModel "kmp" '
                ':targets [{"kind": "jvm"} {"kind": "js"}] '
                ":sourceSets {"
                '"jsMain": {"kotlinSrcDirs": ["src/webShared/kotlin"]} '
                '"declaredMain": {"kotlinSrcDirs": ["src/emptyShared/kotlin"]}'
                "})",
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-kmp"]
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "src" / "rogueShared" / "kotlin").mkdir(parents=True)
    (project.path / "src" / "rogueShared" / "kotlin" / "Rogue.kt").write_text("class Rogue\n", encoding="utf-8")
    (project.path / "src" / "emptyShared" / "kotlin").mkdir(parents=True)
    (project.path / "src" / "compilerV2Main" / "kotlin").mkdir(parents=True)
    (project.path / "src" / "compilerV2Main" / "kotlin" / "Compat.kt").write_text("class Compat\n", encoding="utf-8")
    (project.path / "src" / "linuxX64Main" / "kotlin").mkdir(parents=True)
    (project.path / "src" / "linuxX64Main" / "kotlin" / "Linux.kt").write_text("class Linux\n", encoding="utf-8")

    issues = KmpSourceLayoutDriftCheck().check(project.path, project)
    issue_ids = {issue.issue_type.id for issue in issues}

    assert "E_KMP_CUSTOM_SOURCE_ROOT_UNDECLARED" in issue_ids
    assert "E_KMP_DECLARED_SOURCE_ROOT_MISSING" in issue_ids
    assert "E_KMP_DECLARED_SOURCE_ROOT_EMPTY" in issue_ids
    assert "E_KMP_SOURCE_SET_DIRECTORY_UNDECLARED" in issue_ids
    assert "E_KMP_PLATFORM_SOURCE_SET_WITHOUT_TARGET" in issue_ids


def test_kmp_source_set_naming_style_check_flags_ambiguous_native_aliases_only(tmp_path: Path) -> None:
    from dev.checks.layout_drift import KmpSourceSetNamingStyleCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-native-names" '
                ':version "0.1.0" '
                ':buildModel "kmp" '
                ':targets [{"kind": "iosArm64"} {"kind": "macosArm64" "name": "clientNative"} {"kind": "linuxX64"}] '
                ":sourceSets {"
                '"clientNativeTest": {"dependsOn": ["commonTest"]} '
                '"posixNativeMain": {"dependsOn": ["commonMain"]}'
                "})",
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-native-names"]
    (project.path / "src" / "clientNativeMain" / "kotlin").mkdir(parents=True, exist_ok=True)
    (project.path / "src" / "clientNativeMain" / "kotlin" / "Demo.kt").write_text("class Demo\n", encoding="utf-8")
    (project.path / "src" / "posixNativeMain" / "kotlin").mkdir(parents=True, exist_ok=True)
    (project.path / "src" / "posixNativeMain" / "kotlin" / "Posix.kt").write_text("class Posix\n", encoding="utf-8")

    issues = KmpSourceSetNamingStyleCheck().check(project.path, project)

    assert [issue.issue_type.id for issue in issues] == ["E_KMP_AMBIGUOUS_NATIVE_NAME"]
    assert issues[0].issue_type.severity.value == "warning"
    assert issues[0].data == {
        "name": "clientNative",
        "variants": "clientNative, clientNativeMain, clientNativeTest",
        "target_suffix": "; target kind(s): macosArm64",
    }


def test_kmp_redundant_target_alias_check_flags_unused_aliases(tmp_path: Path) -> None:
    from dev.checks.layout_drift import KmpRedundantTargetAliasCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(gradle "demo-redundant-alias" :version "0.1.0" :buildModel "kmp" :targets [{"kind": "macosArm64" "name": "hostArm"}])',
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-redundant-alias"]
    project.path.mkdir(parents=True, exist_ok=True)

    issues = KmpRedundantTargetAliasCheck().check(project.path, project)

    assert [issue.issue_type.id for issue in issues] == ["E_KMP_REDUNDANT_TARGET_ALIAS"]


def test_kmp_single_target_and_pass_through_checks_flag_narrow_or_empty_custom_source_sets(tmp_path: Path) -> None:
    from dev.checks.layout_drift import KmpPassThroughSourceSetCheck, KmpSingleTargetAbstractionCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-abstractions" '
                ':version "0.1.0" '
                ':buildModel "kmp" '
                ':targets [{"kind": "macosArm64"}] '
                ":sourceSets {"
                '"hostMain": {"dependsOn": ["commonMain"]} '
                '"relayMain": {"dependsOn": ["commonMain"]} '
                '"macosArm64Main": {"dependsOn": ["hostMain"]}'
                "})",
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-abstractions"]
    (project.path / "src" / "hostMain" / "kotlin").mkdir(parents=True, exist_ok=True)
    (project.path / "src" / "hostMain" / "kotlin" / "Host.kt").write_text("class Host\n", encoding="utf-8")
    (project.path / "src" / "macosArm64Main" / "kotlin").mkdir(parents=True, exist_ok=True)
    (project.path / "src" / "macosArm64Main" / "kotlin" / "Platform.kt").write_text(
        "class Platform\n", encoding="utf-8"
    )

    single_target_issues = KmpSingleTargetAbstractionCheck().check(project.path, project)
    pass_through_issues = KmpPassThroughSourceSetCheck().check(project.path, project)

    assert {issue.data["source_set"] for issue in single_target_issues} == {"hostMain"}
    assert {issue.data["source_set"] for issue in pass_through_issues} == {"relayMain"}


def test_kmp_file_suffix_boundary_and_alias_meaning_mismatch_checks_flag_confusing_boundaries(tmp_path: Path) -> None:
    from dev.checks.layout_drift import KmpAliasMeaningMismatchCheck, KmpFileSuffixBoundaryCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-boundaries" '
                ':version "0.1.0" '
                ':buildModel "kmp" '
                ':targets [{"kind": "macosArm64"}] '
                ":sourceSets {"
                '"iosSupportMain": {"dependsOn": ["commonMain"]} '
                '"macosArm64Main": {"dependsOn": ["iosSupportMain"]}'
                "})",
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-boundaries"]
    (project.path / "src" / "iosSupportMain" / "kotlin").mkdir(parents=True, exist_ok=True)
    (project.path / "src" / "iosSupportMain" / "kotlin" / "Support.kt").write_text("class Support\n", encoding="utf-8")
    (project.path / "src" / "macosArm64Main" / "kotlin").mkdir(parents=True, exist_ok=True)
    (project.path / "src" / "macosArm64Main" / "kotlin" / "VoiceCapture.clientNative.kt").write_text(
        "class VoiceCapture\n",
        encoding="utf-8",
    )

    mismatch_issues = KmpAliasMeaningMismatchCheck().check(project.path, project)
    suffix_issues = KmpFileSuffixBoundaryCheck().check(project.path, project)

    assert [issue.issue_type.id for issue in mismatch_issues] == ["E_KMP_ALIAS_MEANING_MISMATCH"]
    assert mismatch_issues[0].data == {
        "name": "iosSupportMain",
        "implied": "iOS",
        "actual_scope": "macosArm64",
    }
    assert [issue.issue_type.id for issue in suffix_issues] == ["E_KMP_FILE_SUFFIX_BOUNDARY"]
    assert suffix_issues[0].data == {
        "suffix": "clientNative",
        "file_name": "VoiceCapture.clientNative.kt",
        "source_set": "macosArm64Main",
        "reason": "generic native suffix is too broad for macosArm64",
    }


def test_kmp_alias_meaning_mismatch_understands_compound_boundaries(tmp_path: Path) -> None:
    from dev.checks.layout_drift import KmpAliasMeaningMismatchCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-compound-boundaries" '
                ':version "0.1.0" '
                ':buildModel "kmp" '
                ':targets [{"kind": "jvm"} {"kind": "android-kmp-library" "namespace": "one.wabbit.demo" "compileSdk": 34 "minSdk": 21}] '
                ":sourceSets {"
                '"jvmAndAndroidMain": {"dependsOn": ["commonMain"]} '
                '"jvmMain": {"dependsOn": ["jvmAndAndroidMain"]} '
                '"androidMain": {"dependsOn": ["jvmAndAndroidMain"]}'
                "})",
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-compound-boundaries"]

    issues = KmpAliasMeaningMismatchCheck().check(project.path, project)

    assert issues == []


def test_kmp_file_suffix_boundary_allows_js_suffix_under_wasmjs(tmp_path: Path) -> None:
    from dev.checks.layout_drift import KmpFileSuffixBoundaryCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(gradle "demo-wasm-js" :version "0.1.0" :buildModel "kmp" :targets [{"kind": "wasmJs"}])',
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-wasm-js"]
    (project.path / "src" / "wasmJsMain" / "kotlin").mkdir(parents=True, exist_ok=True)
    (project.path / "src" / "wasmJsMain" / "kotlin" / "Platform.js.kt").write_text("class Platform\n", encoding="utf-8")

    issues = KmpFileSuffixBoundaryCheck().check(project.path, project)

    assert issues == []


def test_gradle_manifest_and_resource_drift_check_reports_missing_and_stray_paths(tmp_path: Path) -> None:
    from dev.checks.layout_drift import GradleManifestResourceDriftCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-gradle" '
                ':version "0.1.0" '
                ':targets [{"kind": "jvm"} {"kind": "android-kmp-library" "namespace": "one.wabbit.demo" "compileSdk": 34 "minSdk": 21}])',
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-gradle"]
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "src" / "legacy").mkdir(parents=True)
    (project.path / "src" / "legacy" / "AndroidManifest.xml").write_text("<manifest/>\n", encoding="utf-8")
    (project.path / "src" / "legacy" / "resources").mkdir(parents=True)
    (project.path / "src" / "legacy" / "resources" / "data.txt").write_text("x\n", encoding="utf-8")

    issues = GradleManifestResourceDriftCheck().check(project.path, project)
    issue_ids = {issue.issue_type.id for issue in issues}

    assert "E_GRADLE_MANIFEST_PATH_MISSING" in issue_ids
    assert "E_GRADLE_UNDECLARED_MANIFEST_PATH" in issue_ids
    assert "E_GRADLE_UNDECLARED_RESOURCE_ROOT" in issue_ids


def test_gradle_publication_metadata_check_reports_missing_license_and_build_metadata(tmp_path: Path) -> None:
    from dev.checks.layout_drift import GradlePublicationMetadataDriftCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-company-legal-name "Example Legal Co")',
                '(default-company-email "legal@example.com")',
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-publish" '
                ':version "0.1.0" '
                ':description "Demo publishable lib" '
                ':repo "wabbit-corp/demo-publish" '
                ':license "MIT" '
                ":publish true "
                ':publishTarget "maven-central" '
                ":features [(jvm-kotlin-library)])",
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-publish"]
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "build.gradle.kts").write_text("plugins {}\n", encoding="utf-8")

    issues = GradlePublicationMetadataDriftCheck().check(project.path, project)
    issue_ids = {issue.issue_type.id for issue in issues}

    assert "E_GRADLE_PUBLICATION_LICENSE_FILE_MISSING" in issue_ids
    assert "E_GRADLE_PUBLICATION_METADATA_DRIFT" in issue_ids
    assert all(issue.fix is not None for issue in issues)


def test_gradle_publication_metadata_check_skips_intellij_marketplace_projects(tmp_path: Path) -> None:
    from dev.checks.layout_drift import GradlePublicationMetadataDriftCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-company-legal-name "Example Legal Co")',
                '(default-company-email "legal@example.com")',
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-ij" '
                ':version "0.1.0" '
                ':description "Demo IntelliJ plugin" '
                ':repo "wabbit-corp/demo-ij" '
                ':license "MIT" '
                ":publish true "
                ':publishTarget "jetbrains-marketplace" '
                ':features [(intellij-plugin "Demo IJ")])',
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-ij"]
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "build.gradle.kts").write_text("plugins {}\n", encoding="utf-8")

    issues = GradlePublicationMetadataDriftCheck().check(project.path, project)

    assert issues == []


def test_python_package_layout_drift_check_reports_undeclared_and_missing_paths(tmp_path: Path) -> None:
    from dev.checks.layout_drift import PythonPackageLayoutDriftCheck

    config = _load_from_temp_root(
        tmp_path,
        '(python "demo-py" :version "0.1.0" :repo "wabbit-corp/demo-py")\n',
    )
    project = config.defined_projects["demo-py"]
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.poetry]",
                'name = "demo-py"',
                'version = "0.1.0"',
                'packages = [{ include = "declaredpkg" }]',
                'include = [{ path = "missing.txt", format = ["sdist"] }]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project.path / "otherpkg").mkdir()
    (project.path / "otherpkg" / "__init__.py").write_text("", encoding="utf-8")

    issues = PythonPackageLayoutDriftCheck().check(project.path, project)
    issue_ids = {issue.issue_type.id for issue in issues}

    assert "E_PYTHON_PACKAGE_ROOT_UNDECLARED" in issue_ids
    assert "E_PYTHON_DECLARED_PACKAGE_ROOT_MISSING" in issue_ids
    assert "E_PYTHON_DECLARED_INCLUDE_PATH_MISSING" in issue_ids


def test_docs_layout_drift_check_reports_missing_nav_targets_and_unlisted_docs(tmp_path: Path) -> None:
    from dev.checks.layout_drift import DocsLayoutDriftCheck

    config = _load_from_temp_root(
        tmp_path,
        '(python "demo-docs" :version "0.1.0" :repo "wabbit-corp/demo-docs")\n',
    )
    project = config.defined_projects["demo-docs"]
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "mkdocs.yml").write_text(
        "\n".join(
            [
                "site_name: demo-docs",
                "docs_dir: docs",
                "nav:",
                "  - Home: index.md",
                "  - Missing: missing.md",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project.path / "docs").mkdir()
    (project.path / "docs" / "index.md").write_text("# Home\n", encoding="utf-8")
    (project.path / "docs" / "extra.md").write_text("# Extra\n", encoding="utf-8")

    issues = DocsLayoutDriftCheck().check(project.path, project)
    issue_ids = {issue.issue_type.id for issue in issues}

    assert "E_DOCS_NAV_PATH_MISSING" in issue_ids
    assert "E_DOCS_FILE_NOT_IN_NAV" in issue_ids


def test_repo_metadata_placement_drift_check_reports_wrong_locations(tmp_path: Path) -> None:
    from dev.checks.layout_drift import RepoMetadataPlacementDriftCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(code-owner "Sir Wabbit" "wabbit@wabbit.one")',
                '(python "demo-meta" :version "0.1.0" :repo "wabbit-corp/demo-meta")',
                "",
            ]
        ),
    )
    project = config.defined_projects["demo-meta"]
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "SECURITY.md").write_text("stale\n", encoding="utf-8")

    issues = RepoMetadataPlacementDriftCheck().check(project.path, None)

    assert {issue.issue_type.id for issue in issues} == {"E_MISPLACED_REPO_METADATA_FILE"}
    assert all(issue.fix is not None for issue in issues)


def test_test_license_coverage_check_reports_missing_and_stale_copies(tmp_path: Path) -> None:
    from dev.checks.layout_drift import TestLicenseCoverageCheck

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(python "demo-test-license" :version "0.1.0" :testLicense "LicenseRef-Wabbit-Public-Test-License-1.1")',
                '(python "demo-stale-license" :version "0.1.0")',
                "",
            ]
        ),
    )
    configured = config.defined_projects["demo-test-license"]
    stale = config.defined_projects["demo-stale-license"]
    (configured.path / "tests").mkdir(parents=True, exist_ok=True)
    (stale.path / "tests").mkdir(parents=True, exist_ok=True)
    (stale.path / "tests" / "LICENSE.md").write_text("stale\n", encoding="utf-8")

    configured_issues = TestLicenseCoverageCheck().check(configured.path, configured)
    stale_issues = TestLicenseCoverageCheck().check(stale.path, stale)

    assert {issue.issue_type.id for issue in configured_issues} == {"E_TEST_LICENSE_COPY_MISSING"}
    assert {issue.issue_type.id for issue in stale_issues} == {"E_STALE_TEST_LICENSE_COPY"}
    assert all(issue.fix is not None for issue in configured_issues)
    assert all(issue.fix is not None for issue in stale_issues)
