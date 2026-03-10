from __future__ import annotations

import os
import sys
from inspect import signature
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from dev.config import Config


def _load_from_temp_root(
    tmp_path: Path,
    root_clj: str,
    root_private_clj: str = '(github-token "dummy")\n',
) -> Config:
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


def test_maven_version_variable_is_resolved_from_define(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(define ktor-version "3.3.0")',
                "(" 'define-maven-library "ktor-client-core" ' '"io.ktor:ktor-client-core:${ktor-version}")',
                "",
            ]
        ),
    )

    library = config.libraries["ktor-client-core"]
    assert library.maven_urn.group_id == "io.ktor"
    assert library.maven_urn.artifact_id == "ktor-client-core"
    assert library.maven_urn.version == "3.3.0"


def test_undefined_maven_version_variable_fails_with_path_and_span(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError) as exc:
        _load_from_temp_root(
            tmp_path,
            "(" 'define-maven-library "ktor-client-core" ' '"io.ktor:ktor-client-core:${ktor-version}")\n',
        )

    assert exc.value.path == "root[0]"
    assert exc.value.span is not None
    assert "Undefined variable referenced in maven version" in str(exc.value)


def test_forward_maven_version_variable_reference_is_rejected(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError) as exc:
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    "(" 'define-maven-library "ktor-client-core" ' '"io.ktor:ktor-client-core:${ktor-version}")',
                    '(define ktor-version "3.3.0")',
                    "",
                ]
            ),
        )

    assert exc.value.path == "root[0]"


def test_module_typed_commands_are_loaded_and_applied(tmp_path: Path) -> None:
    from dev.checks.code_stale import StaleCodeCheck

    config = _load_from_temp_root(
        tmp_path,
        "(checks/stale-todo/age-days 30)\n",
    )

    stale_check = next(module for module in config.modules.values() if isinstance(module, StaleCodeCheck))
    assert stale_check.todo_age_days == 30


def test_dep_call_in_gradle_dependencies_is_resolved(tmp_path: Path) -> None:
    from dev.config import MavenDependencyTarget

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(define-maven-library "kotlin-stdlib" "org.jetbrains.kotlin:kotlin-stdlib:2.0.0")',
                "("
                'gradle "demo" '
                ':version "0.1.0" '
                ":features [(jvm-kotlin-library)] "
                ':dependencies [(dep "kotlin-stdlib" "api")])',
                "",
            ]
        ),
    )

    project = config.defined_projects["demo"]
    assert any(
        dep.scope == "api"
        and isinstance(dep.target, MavenDependencyTarget)
        and dep.target.artifact == "org.jetbrains.kotlin:kotlin-stdlib:2.0.0"
        for dep in project.resolved_dependencies
    )


def test_default_company_email_is_loaded(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        '(default-company-email "legal@example.com")\n',
    )

    assert config.default_company_email == "legal@example.com"


def test_default_company_names_are_loaded(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-company-legal-name "Example Legal Co")',
                '(default-company-short-name "Example Co")',
                "",
            ]
        ),
    )

    assert config.default_company_legal_name == "Example Legal Co"
    assert config.default_company_short_name == "Example Co"


def test_purescript_project_is_loaded_with_explicit_license(tmp_path: Path) -> None:
    from dev.config import PurescriptProject

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(purescript "demo-purescript" :version "0.1.0" :license "MIT" :repo "wabbit-corp/demo-purescript")',
                "",
            ]
        ),
    )

    project = config.defined_projects["demo-purescript"]
    assert isinstance(project, PurescriptProject)
    assert project.license == "MIT"


def test_purescript_project_loads_explicit_copyright_metadata(tmp_path: Path) -> None:
    from dev.config import PurescriptProject

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                "("
                'purescript "demo-purescript" '
                ':version "0.1.0" '
                ':license "MIT" '
                ':copyright-holder "Wabbit Consulting Corporation" '
                ":copyright-year-start 2019 "
                ':repo "wabbit-corp/demo-purescript")',
                "",
            ]
        ),
    )

    project = config.defined_projects["demo-purescript"]
    assert isinstance(project, PurescriptProject)
    assert project.copyright_holder == "Wabbit Consulting Corporation"
    assert project.copyright_year_start == 2019


def test_unknown_top_level_tag_fails_decode(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError):
        _load_from_temp_root(tmp_path, '(unknown-cmd "x")\n')


def test_gradle_kmp_platforms_and_source_set_dependencies_are_loaded(tmp_path: Path) -> None:
    from dev.config import GradleProject

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(define-maven-library "kotlin-stdlib" "org.jetbrains.kotlin:kotlin-stdlib:2.2.20")',
                "("
                'gradle "demo-kmp" '
                ':version "0.1.0" '
                ':targets [{"kind": "jvm"} {"kind": "android-kmp-library" "namespace": "one.wabbit.demo" "compileSdk": 34 "minSdk": 26}] '
                ':sourceSetDependencies {"commonMain": ["kotlin-stdlib"] "androidMain": ["kotlin-stdlib"]})',
                "",
            ]
        ),
    )

    project = config.defined_projects["demo-kmp"]
    assert isinstance(project, GradleProject)
    assert project.platforms == ["jvm", "android"]
    assert set(project.source_set_dependencies.keys()) == {"commonMain", "androidMain"}
    assert len(project.source_set_dependencies["commonMain"]) == 1
    assert len(project.source_set_dependencies["androidMain"]) == 1


def test_gradle_kmp_allows_default_hierarchy_without_explicit_source_sets(tmp_path: Path) -> None:
    from dev.config import GradleProject

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-kmp" '
                ':version "0.1.0" '
                ':targets [{"kind": "jvm"} {"kind": "iosArm64"}])',
                "",
            ]
        ),
    )

    project = config.defined_projects["demo-kmp"]
    assert isinstance(project, GradleProject)
    assert project.platforms == ["jvm", "iosArm64"]
    assert project.source_sets == {}
    assert project.source_set_dependencies == {}


def test_gradle_kmp_legacy_android_feature_still_backfills_targets(tmp_path: Path) -> None:
    from dev.config import GradleProject

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "demo-kmp" '
                ':version "0.1.0" '
                ':platforms ["jvm" "android"] '
                ":features ["
                '(kmp-android-library :namespace "one.wabbit.demo" :compileSdk 34 :minSdk 26)'
                "])",
                "",
            ]
        ),
    )

    project = config.defined_projects["demo-kmp"]
    assert isinstance(project, GradleProject)
    assert [target.kind for target in project.targets] == ["jvm", "android-kmp-library"]


def test_gradle_kmp_rejects_legacy_dependencies_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must use :sourceSetDependencies instead of :dependencies"):
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    '(default-maven-project-group "one.wabbit")',
                    '(define-maven-library "kotlin-stdlib" "org.jetbrains.kotlin:kotlin-stdlib:2.2.20")',
                    "("
                    'gradle "demo-kmp" '
                    ':version "0.1.0" '
                    ':targets [{"kind": "jvm"} {"kind": "android-kmp-library" "namespace": "one.wabbit.demo" "compileSdk": 34 "minSdk": 26}] '
                    ':dependencies ["kotlin-stdlib"])',
                    "",
                ]
            ),
        )


def test_gradle_kmp_rejects_source_set_key_not_supported_by_platforms(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not support it"):
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    '(default-maven-project-group "one.wabbit")',
                    '(define-maven-library "kotlin-stdlib" "org.jetbrains.kotlin:kotlin-stdlib:2.2.20")',
                    "("
                    'gradle "demo-kmp" '
                    ':version "0.1.0" '
                    ':targets [{"kind": "jvm"} {"kind": "android-kmp-library" "namespace": "one.wabbit.demo" "compileSdk": 34 "minSdk": 26}] '
                    ':sourceSetDependencies {"iosArm64Main": ["kotlin-stdlib"]})',
                    "",
                ]
            ),
        )


def test_kmp_source_set_validation_allows_jvm_main_to_depend_on_jvm_only_project(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(gradle "lib-jvm" :version "0.1.0" :features [(jvm-kotlin-library)])',
                "("
                'gradle "app-kmp" '
                ':version "0.1.0" '
                ':targets [{"kind": "jvm"} {"kind": "android-kmp-library" "namespace": "one.wabbit.app" "compileSdk": 34 "minSdk": 26}] '
                ':sourceSetDependencies {"jvmMain": [":lib-jvm"]})',
                "",
            ]
        ),
    )

    assert "app-kmp" in config.defined_projects


def test_kmp_source_set_validation_rejects_common_main_to_jvm_only_dependency(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="common compatibility"):
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    '(default-maven-project-group "one.wabbit")',
                    '(gradle "lib-jvm" :version "0.1.0" :features [(jvm-kotlin-library)])',
                    "("
                    'gradle "app-kmp" '
                    ':version "0.1.0" '
                    ':targets [{"kind": "jvm"} {"kind": "android-kmp-library" "namespace": "one.wabbit.app" "compileSdk": 34 "minSdk": 26}] '
                    ':sourceSetDependencies {"commonMain": [":lib-jvm"]})',
                    "",
                ]
            ),
        )


def test_kmp_source_set_validation_rejects_ios_arm64_to_non_ios_project(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="iosArm64 compatibility"):
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    '(default-maven-project-group "one.wabbit")',
                    "("
                    'gradle "lib-kmp" '
                    ':version "0.1.0" '
                    ':targets [{"kind": "jvm"} {"kind": "android-kmp-library" "namespace": "one.wabbit.lib" "compileSdk": 34 "minSdk": 26}] '
                    ':sourceSetDependencies {"commonMain": ["org.jetbrains.kotlin:kotlin-stdlib:2.2.20"]})',
                    "("
                    'gradle "app-kmp" '
                    ':version "0.1.0" '
                    ':platforms ["jvm" "iosArm64"] '
                    ':sourceSetDependencies {"iosArm64Main": [":lib-kmp"]})',
                    "",
                ]
            ),
        )


def test_kmp_source_set_validation_allows_apple_main_to_depend_on_apple_capable_project(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "lib-apple" '
                ':version "0.1.0" '
                ':platforms ["jvm" "iosArm64"] '
                ':sourceSetDependencies {"commonMain": ["org.jetbrains.kotlin:kotlin-stdlib:2.2.20"]})',
                "("
                'gradle "app-kmp" '
                ':version "0.1.0" '
                ':platforms ["jvm" "iosArm64" "iosSimulatorArm64"] '
                ':sourceSetDependencies {"appleMain": [":lib-apple"]})',
                "",
            ]
        ),
    )

    assert "app-kmp" in config.defined_projects


def test_strict_kebab_case_rejects_legacy_python_keyword_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    "(" 'python "pkg" ' ':version "0.1.0" ' ':python_version ">=3.10" ' ':dev_dependencies ["pytest"])',
                    "",
                ]
            ),
        )


def test_checks_ignore_finding_is_loaded(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        '(checks/ignore-finding "E_HARDCODED_INTERNAL_HOSTNAME_IP" "**/*.py" "10.0.0.0")\n',
    )

    assert (
        "E_HARDCODED_INTERNAL_HOSTNAME_IP",
        "**/*.py",
        "10.0.0.0",
    ) in config.ignored_findings


def test_checks_ignore_finding_rejects_invalid_issue_id(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError):
        _load_from_temp_root(
            tmp_path,
            '(checks/ignore-finding "bad_issue" "**/*.py" "10.0.0.0")\n',
        )


def test_checks_ignore_finding_rejects_missing_args(tmp_path: Path) -> None:
    from mu.typed import DecodeError

    with pytest.raises(DecodeError):
        _load_from_temp_root(
            tmp_path,
            '(checks/ignore-finding "E_HARDCODED_INTERNAL_HOSTNAME_IP" "**/*.py")\n',
        )


def test_python_application_feature_is_loaded(tmp_path: Path) -> None:
    from dev.config import PythonProject

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                "("
                'python "app-demo" '
                ':version "0.1.0" '
                ":features ["
                '(python-application :script "demo" :entry "demo.cli:main" :path "demo/cli.py" :aliases ["d"])'
                "]"
                ")",
                "",
            ]
        ),
    )

    project = config.defined_projects["app-demo"]
    assert isinstance(project, PythonProject)
    assert project.application is not None
    assert project.application.script == "demo"
    assert project.application.entry == "demo.cli:main"
    assert project.application.path == "demo/cli.py"
    assert project.application.aliases == ["d"]


def test_python_application_feature_conflicts_with_legacy_scripts(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    "("
                    'python "app-demo" '
                    ':version "0.1.0" '
                    ':scripts ["demo=demo.cli:main"] '
                    ":features ["
                    '(python-application :script "demo" :entry "demo.cli:main" :path "demo/cli.py")'
                    "]"
                    ")",
                    "",
                ]
            ),
        )


def test_project_identifier_uses_directory_name_when_name_is_overridden(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                "(" 'python "python-lang-mu" ' ':name "lang-mu" ' ':version "0.4.0")',
                "",
            ]
        ),
    )

    assert "python-lang-mu" in config.defined_projects
    assert "lang-mu" not in config.defined_projects
    assert config.defined_projects["python-lang-mu"].name == "lang-mu"


def test_repo_command_loads_nested_projects_and_repo_metadata(tmp_path: Path) -> None:
    from dev.config import GradleProject, PythonProject

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'repo "jeeves" '
                ':repo "wabbit-corp/jeeves" '
                ':gradleRootProjectName "one.wabbit" '
                ':jvmPolicy "jvm-21" '
                ":projects ["
                '(gradle "api" :version "0.1.0" :buildModel "jvm" :features [(jvm-kotlin-library)]) '
                '(python "audio-backend" :version "0.1.0")'
                "])",
                "",
            ]
        ),
    )

    repo_definition = config.defined_repos["jeeves"]
    assert repo_definition.repo_id == "jeeves"
    assert repo_definition.path == Path("./jeeves")
    assert repo_definition.github_repo == "wabbit-corp/jeeves"
    assert repo_definition.gradle_root_project_name == "one.wabbit"
    assert repo_definition.jvm_policy == "jvm-21"
    assert repo_definition.project_ids == ["jeeves/api", "jeeves/audio-backend"]

    api_project = config.defined_projects["jeeves/api"]
    assert isinstance(api_project, GradleProject)
    assert api_project.project_id == "jeeves/api"
    assert api_project.repo_id == "jeeves"
    assert api_project.repo_root == Path("./jeeves")
    assert api_project.path == Path("./jeeves/api")
    assert api_project.managed_by_setup is False
    assert api_project.effective_gradle_project_name == "jeeves-api"
    assert api_project.github_repo == "wabbit-corp/jeeves"

    audio_project = config.defined_projects["jeeves/audio-backend"]
    assert isinstance(audio_project, PythonProject)
    assert audio_project.repo_id == "jeeves"
    assert audio_project.repo_root == Path("./jeeves")
    assert audio_project.path == Path("./jeeves/audio-backend")
    assert audio_project.managed_by_setup is False
    assert audio_project.github_repo == "wabbit-corp/jeeves"


def test_repo_local_dependency_shorthand_resolves_with_repo_prefix(tmp_path: Path) -> None:
    from dev.config import GradleProject, ProjectDependencyTarget

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'repo "jeeves" '
                ':repo "wabbit-corp/jeeves" '
                ":projects ["
                '(gradle "api" :version "0.1.0" :buildModel "jvm" :features [(jvm-kotlin-library)]) '
                '(gradle "server" :version "0.1.0" :buildModel "jvm" :features [(jvm-kotlin-library)] :dependencies [":api"])'
                "])",
                "",
            ]
        ),
    )

    server_project = config.defined_projects["jeeves/server"]
    assert isinstance(server_project, GradleProject)
    project_dependencies = [
        dependency.target.project
        for dependency in server_project.resolved_dependencies
        if isinstance(dependency.target, ProjectDependencyTarget)
    ]
    assert project_dependencies == ["jeeves/api"]


def test_load_config_supports_preserve_spans_parser_signature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import mu.parser as mu_parser

    import dev.config as config_module

    mu_parse_params = signature(mu_parser.parse).parameters

    def parse_with_preserve_spans(text: str, preserve_spans: bool = False) -> object:
        if "preserve_spans" in mu_parse_params:
            return mu_parser.parse(text, **{"preserve_spans": preserve_spans})
        if "no_spans" in mu_parse_params:
            return mu_parser.parse(text, **{"no_spans": not preserve_spans})
        return mu_parser.parse(text)

    monkeypatch.setattr(config_module, "parse", parse_with_preserve_spans)

    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "root.clj").write_text('(python "pkg" :version "0.1.0")\n', encoding="utf-8")
    (tmp_path / "root.private.clj").write_text("", encoding="utf-8")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        config = config_module.load_config()
    finally:
        os.chdir(cwd)

    assert "pkg" in config.defined_projects


def test_intellij_plugin_metadata_and_private_publish_tokens_are_loaded(tmp_path: Path) -> None:
    from dev.config import GradleProject, IntellijPlugin

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                "("
                'gradle "ij-diff-paste" '
                ':version "0.0.1" '
                ":features ["
                '(intellij-plugin "DiffPaste" '
                ':pluginId "one.wabbit.diffpaste" '
                ':ideaVersion "2023.2" '
                ':sinceBuild "232" '
                ':vendorName "Wabbit Consulting Corporation" '
                ':vendorEmail "wabbit@wabbit.one" '
                ':vendorUrl "https://wabbit.one" '
                ':pluginDescription "Applies clipboard diff patches directly to your open file." '
                ':pluginChangeNotes "Initial release." '
                ':depends ["com.intellij.modules.platform"] '
                ':bundledPlugins ["com.intellij.java"] '
                ':publishChannel "default" '
                ':marketplaceTokenEnv "JETBRAINS_MARKETPLACE_TOKEN")]'
                ")",
                "",
            ]
        ),
        "\n".join(
            [
                '(github-token "dummy")',
                '(jetbrains-marketplace-token "jb-token")',
                '(pypi-token "pypi-token")',
                "",
            ]
        ),
    )

    assert config.jetbrains_marketplace_token == "jb-token"
    assert config.pypi_token == "pypi-token"

    project = config.defined_projects["ij-diff-paste"]
    assert isinstance(project, GradleProject)
    feature = project.resolved_features["intellij-plugin"]
    assert isinstance(feature, IntellijPlugin)
    assert feature.pluginName == "DiffPaste"
    assert feature.pluginId == "one.wabbit.diffpaste"
    assert feature.ideaVersion == "2023.2"
    assert feature.sinceBuild == "232"
    assert feature.untilBuild is None
    assert feature.vendorName == "Wabbit Consulting Corporation"
    assert feature.vendorEmail == "wabbit@wabbit.one"
    assert feature.vendorUrl == "https://wabbit.one"
    assert feature.pluginDescription == "Applies clipboard diff patches directly to your open file."
    assert feature.pluginChangeNotes == "Initial release."
    assert feature.depends == ["com.intellij.modules.platform"]
    assert feature.bundledPlugins == ["com.intellij.java"]
    assert feature.publishChannel == "default"
    assert feature.marketplaceTokenEnv == "JETBRAINS_MARKETPLACE_TOKEN"


def test_intellij_plugin_rejects_nonexistent_until_build_branch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        _load_from_temp_root(
            tmp_path,
            "\n".join(
                [
                    '(default-maven-project-group "one.wabbit")',
                    "("
                    'gradle "ij-diff-paste" '
                    ':version "0.0.1" '
                    ":features ["
                    '(intellij-plugin "DiffPaste" :sinceBuild "232" :untilBuild "255.*")]'
                    ")",
                    "",
                ]
            ),
        )


def test_publish_target_routing(tmp_path: Path) -> None:
    from dev.tasks.publish import determine_publish_target

    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(gradle "kotlin-base58" :version "1.0.0" :features [(jvm-kotlin-library)])',
                '(gradle "kotlin-legacy" :version "1.0.0" :publishTarget "jitpack" :features [(jvm-kotlin-library)])',
                '(gradle "ij-diff-paste" :version "0.0.1" :features [(intellij-plugin "DiffPaste")])',
                '(python "python-lang-mu" :version "0.4.0")',
                "",
            ]
        ),
    )

    assert determine_publish_target(config.defined_projects["kotlin-base58"]) == "maven-central"
    assert determine_publish_target(config.defined_projects["kotlin-legacy"]) == "jitpack"
    assert determine_publish_target(config.defined_projects["ij-diff-paste"]) == "intellij-marketplace"
    assert determine_publish_target(config.defined_projects["python-lang-mu"]) == "pypi"


def test_loads_maven_central_secret_config_and_repo_docs_project(tmp_path: Path) -> None:
    config = _load_from_temp_root(
        tmp_path,
        "\n".join(
            [
                '(default-maven-project-group "one.wabbit")',
                '(repo "jeeves" :repo "wabbit-corp/jeeves" :docsProject "api" :projects [',
                '  (gradle "api" :version "0.0.1" :features [(jvm-kotlin-library)])',
                '  (python "audio-backend" :version "0.0.1")',
                '])',
                "",
            ]
        ),
        root_private_clj="\n".join(
            [
                '(maven-username "portal-user")',
                '(maven-password "portal-password")',
                '(maven-gpg-private-key "armored-key")',
                '(maven-gpg-passphrase "secret-passphrase")',
                '(maven-gpg-key-id "ABC123")',
                "",
            ]
        ),
    )

    assert config.maven_username == "portal-user"
    assert config.maven_password == "portal-password"
    assert config.maven_gpg_private_key == "armored-key"
    assert config.maven_gpg_passphrase == "secret-passphrase"
    assert config.maven_gpg_key_id == "ABC123"
    assert config.defined_repos["jeeves"].docs_project_id == "jeeves/api"
