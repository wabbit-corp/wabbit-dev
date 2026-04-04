from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jinja2
import pytest
from mu.types import Document

from dev.config import (
    Config,
    Dependency,
    DependencyTarget,
    GradlePluginApplication,
    GradlePlugins,
    GradleProject,
    GradleSourceSet,
    GradleTargetSpec,
    Jvm,
    JvmKotlinLibrary,
    KmpCompose,
    KmpJvmRunEntry,
    KmpJvmRuns,
    Kotlin,
    KotlinPluginDefinition,
    MavenLibraryDefinition,
    MavenRepositoryDefinition,
    NpmDependencyTarget,
    OwnershipType,
    PaperPlugin,
    ProjectDependencyTarget,
    RepoDefinition,
    ShadowJar,
    Version,
)
from dev.maven import MavenCoordinate
from dev.tasks.setup_common import RepoSetupMode
from dev.tasks.setup_kotlin import _render_dependency_for_mode, _write_gradle_repo_root_workflows, setup_gradle_project


@dataclass
class _Context:
    config: Config
    mode: RepoSetupMode
    repo_template: Path
    licenses: dict[str, str]
    coc: jinja2.Template
    cla: jinja2.Template
    cla_explanations: jinja2.Template
    contributor_privacy_policy: jinja2.Template
    subproject_build_template: jinja2.Template
    subproject_build_kmp_template: jinja2.Template
    gradle_release_publish_workflow_template: jinja2.Template
    gradle_snapshot_publish_workflow_template: jinja2.Template
    gradle_docs_quality_workflow_template: jinja2.Template
    gradle_docs_deploy_workflow_template: jinja2.Template
    settings_template: jinja2.Template
    subproject_settings_template: jinja2.Template
    gitignore_template: jinja2.Template
    gradle_gitignore_template: jinja2.Template
    gradle_properties_template: jinja2.Template


def _make_context(
    tmp_path: Path,
    *,
    jvm_template: str,
    kmp_template: str,
) -> _Context:
    config = Config(raw=Document([]))
    config.jvm_version = 21
    config.default_company_legal_name = "Example Legal Co"
    config.default_company_short_name = "Example Co"
    config.plugins.update(
        {
            "kotlin-jvm": KotlinPluginDefinition(plugin_id="org.jetbrains.kotlin.jvm", version="2.2.20"),
            "kotlin-mp": KotlinPluginDefinition(plugin_id="org.jetbrains.kotlin.multiplatform", version="2.2.20"),
            "kotlin-serialization": KotlinPluginDefinition(
                plugin_id="org.jetbrains.kotlin.plugin.serialization",
                version="2.2.20",
            ),
            "shadow": KotlinPluginDefinition(plugin_id="com.gradleup.shadow", version="8.3.0"),
        }
    )
    config.libraries.update(
        {
            "kotlinx-serialization-core": MavenLibraryDefinition(
                name="kotlinx-serialization-core",
                maven_urn=MavenCoordinate.parse("org.jetbrains.kotlinx:kotlinx-serialization-core:1.9.0"),
                repo=None,
            )
        }
    )
    return _Context(
        config=config,
        mode=RepoSetupMode.LOCAL,
        repo_template=tmp_path / "repo-template",
        licenses={},
        coc=jinja2.Template(""),
        cla=jinja2.Template(""),
        cla_explanations=jinja2.Template(""),
        contributor_privacy_policy=jinja2.Template(""),
        subproject_build_template=jinja2.Template(jvm_template),
        subproject_build_kmp_template=jinja2.Template(kmp_template),
        gradle_release_publish_workflow_template=jinja2.Template("release {{ project_name }} android={{ needs_android }}"),
        gradle_snapshot_publish_workflow_template=jinja2.Template(
            "snapshot {{ project_name }} android={{ needs_android }}"
        ),
        gradle_docs_quality_workflow_template=jinja2.Template("docs-quality {{ project_name }}"),
        gradle_docs_deploy_workflow_template=jinja2.Template("docs-deploy {{ docs_output_dir }}"),
        settings_template=jinja2.Template(""),
        subproject_settings_template=jinja2.Template(""),
        gitignore_template=jinja2.Template("# base"),
        gradle_gitignore_template=jinja2.Template("# gradle"),
        gradle_properties_template=jinja2.Template("org.gradle.caching=true"),
    )


def _make_project(path: Path, *, platforms: list[str]) -> GradleProject:
    return GradleProject(
        path=path,
        group_name="one.wabbit",
        name=path.name,
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo=None,
        ownership=OwnershipType.IMPORTED,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        platforms=platforms,
        source_set_dependencies={},
    )


def _make_repo_gradle_project(
    path: Path,
    *,
    project_id: str,
    repo_root: Path,
    gradle_project_name: str,
    github_repo: str,
    artifact_id: str | None = None,
) -> GradleProject:
    project = _make_project(path, platforms=["jvm"])
    project.project_id = project_id
    project.repo_id = project_id.split("/", 1)[0] if "/" in project_id else None
    project.repo_root = repo_root
    project.gradle_root = repo_root
    project.gradle_project_name = gradle_project_name
    project.github_repo = github_repo
    project.artifact_id = artifact_id
    return project


def _patch_setup_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    import dev.io as dev_io
    import dev.tasks.setup_kotlin as setup_kotlin_module

    monkeypatch.setattr(setup_kotlin_module, "write_wabbit_legal_files", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_kotlin_module, "write_banner", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dev_io, "copy", lambda *_args, **_kwargs: None)


def test_setup_gradle_project_uses_jvm_template_for_jvm_only_platforms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "jvm-proj", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template="KMP_TEMPLATE",
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "JVM_TEMPLATE" in build_text
    assert "KMP_TEMPLATE" not in build_text


def test_setup_gradle_project_inlines_optional_build_inline_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "inline-proj", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "build.inline.gradle.kts").write_text(
        'println("inline build logic")\n',
        encoding="utf-8",
    )
    ctx = _make_context(
        tmp_path,
        jvm_template="before\n{{ inline_extra_build_script }}\nafter",
        kmp_template="KMP_TEMPLATE",
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert 'println("inline build logic")' in build_text
    assert "before" in build_text
    assert "after" in build_text


def test_setup_gradle_project_cleans_stale_standalone_legal_files_for_nested_repo_modules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    repo_root = tmp_path / "repo"
    project = _make_repo_gradle_project(
        repo_root / "library",
        project_id="repo/library",
        repo_root=repo_root,
        gradle_project_name="library",
        github_repo="org/repo",
        artifact_id="library",
    )
    project.path.mkdir(parents=True, exist_ok=True)

    stale_paths = [
        project.path / ".banner.png",
        project.path / "LICENSE.md",
        project.path / "CLA.md",
        project.path / "CLA_EXPLANATIONS.md",
        project.path / "CONTRIBUTOR_PRIVACY.md",
        project.path / "CODE_OF_CONDUCT.md",
        project.path / "settings.gradle.kts",
        project.path / "settings.local.gradle.kts",
        project.path / "gradlew",
        project.path / "gradlew.bat",
        project.path / "gradle.properties",
    ]
    for stale_path in stale_paths:
        stale_path.parent.mkdir(parents=True, exist_ok=True)
        stale_path.write_text("stale\n", encoding="utf-8")
    (project.path / "gradle" / "wrapper").mkdir(parents=True, exist_ok=True)
    (project.path / "gradle" / "wrapper" / "gradle-wrapper.properties").write_text("stale\n", encoding="utf-8")

    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template="KMP_TEMPLATE",
    )
    ctx.config.defined_projects["repo/library"] = project
    ctx.config.defined_repos["repo"] = RepoDefinition(
        repo_id="repo",
        path=repo_root,
        github_repo="org/repo",
        gradle_root_project_name="repo",
        jvm_policy=None,
        project_ids=["repo/library"],
    )

    setup_gradle_project(ctx, project, interactive=False)

    for stale_path in stale_paths:
        assert not stale_path.exists()
    assert not (project.path / "gradle").exists()
    assert (project.path / "build.gradle.kts").is_file()


def test_setup_gradle_project_keeps_module_license_when_repo_licenses_differ(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    repo_root = tmp_path / "repo"
    project = _make_repo_gradle_project(
        repo_root / "library",
        project_id="repo/library",
        repo_root=repo_root,
        gradle_project_name="library",
        github_repo="org/repo",
        artifact_id="library",
    )
    sibling = _make_repo_gradle_project(
        repo_root / "compiler-plugin",
        project_id="repo/compiler-plugin",
        repo_root=repo_root,
        gradle_project_name="compiler-plugin",
        github_repo="org/repo",
        artifact_id="compiler-plugin",
    )
    sibling.license = "MIT"
    project.path.mkdir(parents=True, exist_ok=True)
    (project.path / "LICENSE.md").write_text("stale\n", encoding="utf-8")
    (project.path / "CLA.md").write_text("stale\n", encoding="utf-8")

    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template="KMP_TEMPLATE",
    )
    ctx.config.defined_projects.update(
        {
            "repo/library": project,
            "repo/compiler-plugin": sibling,
        }
    )
    ctx.config.defined_repos["repo"] = RepoDefinition(
        repo_id="repo",
        path=repo_root,
        github_repo="org/repo",
        gradle_root_project_name="repo",
        jvm_policy=None,
        project_ids=["repo/library", "repo/compiler-plugin"],
    )

    setup_gradle_project(ctx, project, interactive=False)

    assert (project.path / "LICENSE.md").is_file()
    assert not (project.path / "CLA.md").exists()


def test_setup_gradle_project_uses_kmp_template_and_renders_source_set_deps_and_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kmp-proj", platforms=["jvm", "android"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.source_set_dependencies = {
        "commonMain": [
            Dependency(
                scope=None,
                target=DependencyTarget.Maven(artifact="org.jetbrains.kotlin:kotlin-stdlib:2.2.20"),
            )
        ],
        "jvmMain": [
            Dependency(
                scope=None,
                target=DependencyTarget.Maven(artifact="io.ktor:ktor-client-core:3.3.0"),
            )
        ],
    }
    project.resolved_features = {
        "kmp-jvm-runs": KmpJvmRuns(
            entries=[
                KmpJvmRunEntry(
                    taskName="runServerJvm",
                    mainClass="one.wabbit.demo.MainKt",
                    description="Run demo",
                )
            ]
        ),
    }

    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template=(
            "KMP_TEMPLATE {{ platforms|join(',') }} "
            "{% for source_set, deps in source_set_dependencies.items() %}"
            "[{{ source_set }}={{ deps|join('|') }}]"
            "{% endfor %}"
            "{% if kmp_jvm_runs %} RUN={{ kmp_jvm_runs[0].taskName }}{% endif %}"
        ),
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "KMP_TEMPLATE jvm,android" in build_text
    assert 'commonMain=implementation("org.jetbrains.kotlin:kotlin-stdlib:2.2.20")' in build_text
    assert 'jvmMain=implementation("io.ktor:ktor-client-core:3.3.0")' in build_text
    assert "RUN=runServerJvm" in build_text


def test_setup_kmp_includes_implicit_default_parent_source_sets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kmp-proj", platforms=["jvm", "android"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.source_sets = {
        "commonTest": GradleSourceSet(
            name="commonTest",
            dependencies=[
                Dependency(
                    scope=None,
                    target=DependencyTarget.Maven(artifact="org.jetbrains.kotlin:kotlin-test:2.2.20"),
                )
            ],
        ),
        "jvmAndAndroidMain": GradleSourceSet(name="jvmAndAndroidMain", depends_on=["commonMain"]),
        "jvmMain": GradleSourceSet(name="jvmMain", depends_on=["jvmAndAndroidMain"]),
        "androidMain": GradleSourceSet(name="androidMain", depends_on=["jvmAndAndroidMain"]),
    }
    project.source_set_dependencies = {
        "commonTest": [
            Dependency(
                scope=None,
                target=DependencyTarget.Maven(artifact="org.jetbrains.kotlin:kotlin-test:2.2.20"),
            )
        ]
    }

    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template=(
            "{% for source_set in source_set_entries %}"
            "[{{ source_set.name }}|{{ source_set.accessor }}|{{ source_set.depends_on|join(',') }}"
            "|{{ source_set.dependencies|join(',') }}]"
            "{% endfor %}"
        ),
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "[commonMain|getting||]" in build_text
    assert "[commonTest|getting||implementation(\"org.jetbrains.kotlin:kotlin-test:2.2.20\")]" in build_text
    assert "[jvmAndAndroidMain|creating|commonMain|]" in build_text
    assert "[jvmMain|getting|jvmAndAndroidMain|]" in build_text
    assert "[androidMain|getting|jvmAndAndroidMain|]" in build_text


def test_setup_kmp_template_conditionals_include_android_and_compose_only_when_features_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    kmp_template = (
        "{% if android_kmp_library_target %}ANDROID{% endif %}"
        "{% if 'kmp-compose' in features %}COMPOSE{% endif %}"
    )
    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template=kmp_template,
    )

    no_feature_project = _make_project(tmp_path / "kmp-no-feature", platforms=["jvm", "iosArm64"])
    no_feature_project.path.mkdir(parents=True, exist_ok=True)
    setup_gradle_project(ctx, no_feature_project, interactive=False)
    no_feature_text = (no_feature_project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "ANDROID" not in no_feature_text
    assert "COMPOSE" not in no_feature_text

    feature_project = _make_project(tmp_path / "kmp-with-feature", platforms=["jvm", "android"])
    feature_project.path.mkdir(parents=True, exist_ok=True)
    feature_project.resolved_features = {
        "kmp-compose": KmpCompose(publicResClass=True, resClassPackage="one.wabbit.demo.resources"),
    }
    feature_project.targets = [
        GradleTargetSpec(kind="jvm"),
        GradleTargetSpec(kind="android-kmp-library", namespace="one.wabbit.demo", compile_sdk=34, min_sdk=26),
    ]
    setup_gradle_project(ctx, feature_project, interactive=False)
    feature_text = (feature_project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "ANDROID" in feature_text
    assert "COMPOSE" in feature_text


def test_setup_gradle_project_always_renders_context_parameters_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    ctx = _make_context(
        tmp_path,
        jvm_template="FLAGS={{ kotlin_free_compiler_args|join(',') }}",
        kmp_template="KMP={{ kotlin_free_compiler_args|join(',') }}",
    )

    plain_project = _make_project(tmp_path / "plain-proj", platforms=["jvm"])
    plain_project.path.mkdir(parents=True, exist_ok=True)
    setup_gradle_project(ctx, plain_project, interactive=False)
    plain_text = (plain_project.path / "build.gradle.kts").read_text(encoding="utf-8").strip()
    assert plain_text == "FLAGS=-Xcontext-parameters"

    kmp_project = _make_project(tmp_path / "kmp-proj", platforms=["jvm", "iosArm64"])
    kmp_project.path.mkdir(parents=True, exist_ok=True)
    setup_gradle_project(ctx, kmp_project, interactive=False)
    kmp_text = (kmp_project.path / "build.gradle.kts").read_text(encoding="utf-8").strip()
    assert kmp_text == "KMP=-Xcontext-parameters"


def test_setup_gradle_project_renders_js_wasm_targets_and_custom_source_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kmp-web-proj", platforms=["jvm", "js", "wasmJs"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.targets = [
        GradleTargetSpec(kind="jvm"),
        GradleTargetSpec(kind="js", browser=True, browser_test="chromeHeadless"),
        GradleTargetSpec(kind="wasmJs", browser=True, browser_test="chromeHeadless", executable=True),
    ]
    project.kotlin_free_compiler_args = ["-Xexpect-actual-classes"]
    project.dokka_suppress_source_sets = ["wasmJsMain"]
    project.source_sets = {
        "jsMain": GradleSourceSet(name="jsMain", kotlin_src_dirs=["src/webShared/kotlin"]),
        "wasmJsMain": GradleSourceSet(name="wasmJsMain", kotlin_src_dirs=["src/webShared/kotlin"]),
    }
    project.source_set_dependencies = {
        "jsMain": [Dependency(scope=None, target=NpmDependencyTarget(package="onnxruntime-web", version="1.24.3"))],
        "wasmJsMain": [Dependency(scope=None, target=NpmDependencyTarget(package="onnxruntime-web", version="1.24.3"))],
    }

    repo_root = Path(__file__).resolve().parents[2]
    kmp_template = (
        repo_root / "data-repo-template" / "gradle-files" / "subproject-build-kmp.gradle.kts.jinja2"
    ).read_text(encoding="utf-8")
    ctx = _make_context(tmp_path, jvm_template="JVM_TEMPLATE", kmp_template=kmp_template)

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "import org.jetbrains.kotlin.gradle.ExperimentalWasmDsl" in build_text
    assert 'freeCompilerArgs.add("-Xexpect-actual-classes")' in build_text
    assert "js {" in build_text
    assert "wasmJs {" in build_text
    assert "binaries.executable()" in build_text
    assert build_text.count("useChromeHeadless()") == 2
    assert build_text.count('kotlin.srcDir("src/webShared/kotlin")') == 2
    assert build_text.count('implementation(npm("onnxruntime-web", "1.24.3"))') == 2
    assert 'if (name == "wasmJsMain")' in build_text


def test_setup_gradle_project_renders_depends_on_parents_via_source_set_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kmp-native-proj", platforms=["jvm", "linuxX64"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.targets = [
        GradleTargetSpec(kind="jvm"),
        GradleTargetSpec(kind="linuxX64"),
    ]
    project.source_sets = {
        "ortNativeMain": GradleSourceSet(name="ortNativeMain", depends_on=["nativeMain"]),
        "linuxX64Main": GradleSourceSet(name="linuxX64Main", depends_on=["ortNativeMain"]),
    }

    repo_root = Path(__file__).resolve().parents[2]
    kmp_template = (
        repo_root / "data-repo-template" / "gradle-files" / "subproject-build-kmp.gradle.kts.jinja2"
    ).read_text(encoding="utf-8")
    ctx = _make_context(tmp_path, jvm_template="JVM_TEMPLATE", kmp_template=kmp_template)

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert 'dependsOn(sourceSets.getByName("nativeMain"))' in build_text
    assert 'dependsOn(sourceSets.getByName("ortNativeMain"))' in build_text
    assert build_text.index("val nativeMain by getting") < build_text.index("val ortNativeMain by creating")


def test_setup_gradle_project_renders_extra_gradle_plugin_in_jvm_build_and_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "jvm-proj", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.resolved_features = {
        "kotlin": Kotlin(),
        "jvm-kotlin-library": JvmKotlinLibrary(),
        "gradle-plugin": GradlePlugins(entries=[GradlePluginApplication(name="acyclic-gradle")]),
    }
    ctx = _make_context(
        tmp_path,
        jvm_template='{% for plugin in extra_gradle_plugins %}[{{ plugin.plugin_id }}]{% endfor %}',
        kmp_template="KMP_TEMPLATE",
    )
    ctx.config.plugins["acyclic-gradle"] = KotlinPluginDefinition(plugin_id="one.wabbit.acyclic", version="0.0.1")
    ctx.config.repositories["repo:company"] = MavenRepositoryDefinition(
        name="repo:company",
        url="https://repo.example.com/releases",
    )
    ctx.config.plugins["company-plugin"] = KotlinPluginDefinition(
        plugin_id="com.example.company",
        version="1.2.3",
        repo="repo:company",
    )
    project.resolved_features["gradle-plugin"] = GradlePlugins(
        entries=[
            GradlePluginApplication(name="acyclic-gradle"),
            GradlePluginApplication(name="company-plugin"),
        ]
    )
    ctx.subproject_settings_template = jinja2.Template(
        "{% for plugin in extra_gradle_plugins %}[{{ plugin.plugin_id }}={{ plugin.version }}]{% endfor %}"
        "{% for repo in extra_gradle_plugin_repositories %}[repo={{ repo.url }}]{% endfor %}"
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    settings_text = (project.path / "settings.gradle.kts").read_text(encoding="utf-8")
    assert "[one.wabbit.acyclic][com.example.company]" in build_text
    assert "[one.wabbit.acyclic=0.0.1][com.example.company=1.2.3]" in settings_text
    assert "[repo=https://repo.example.com/releases]" in settings_text


def test_setup_gradle_project_renders_extra_gradle_plugin_in_kmp_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kmp-proj", platforms=["jvm", "iosArm64"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.resolved_features = {
        "gradle-plugin": GradlePlugins(entries=[GradlePluginApplication(name="acyclic-gradle")]),
    }
    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template='{% for plugin in extra_gradle_plugins %}[{{ plugin.plugin_id }}]{% endfor %}',
    )
    ctx.config.plugins["acyclic-gradle"] = KotlinPluginDefinition(plugin_id="one.wabbit.acyclic", version="0.0.1")

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "[one.wabbit.acyclic]" in build_text


def test_setup_gradle_project_renders_gradle_plugin_compiler_options_in_jvm_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "jvm-proj", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.resolved_features = {
        "kotlin": Kotlin(),
        "jvm-kotlin-library": JvmKotlinLibrary(),
        "gradle-plugin": GradlePlugins(
            entries=[
                GradlePluginApplication(
                    name="acyclic-gradle",
                    compilerOptions={
                        "compilationUnits": "enabled",
                        "declarations": "enabled",
                    },
                )
            ]
        ),
    }
    ctx = _make_context(
        tmp_path,
        jvm_template=(
            "{% for option in kotlin_compiler_plugin_options %}"
            "[{{ option.plugin_id }}:{{ option.option_name }}={{ option.option_value }}]"
            "{% endfor %}"
        ),
        kmp_template="KMP_TEMPLATE",
    )
    ctx.config.plugins["acyclic-gradle"] = KotlinPluginDefinition(
        plugin_id="one.wabbit.acyclic",
        version="0.0.1",
        compiler_plugin_id="one.wabbit.acyclic",
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "[one.wabbit.acyclic:compilationUnits=enabled]" in build_text
    assert "[one.wabbit.acyclic:declarations=enabled]" in build_text


def test_setup_gradle_project_renders_gradle_plugin_compiler_options_in_kmp_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kmp-proj", platforms=["jvm", "iosArm64"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.resolved_features = {
        "gradle-plugin": GradlePlugins(
            entries=[
                GradlePluginApplication(
                    name="acyclic-gradle",
                    compilerOptions={"declarationOrder": "bottom-up"},
                )
            ]
        ),
    }
    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template=(
            "{% for option in kotlin_compiler_plugin_options %}"
            "[{{ option.plugin_id }}:{{ option.option_name }}={{ option.option_value }}]"
            "{% endfor %}"
        ),
    )
    ctx.config.plugins["acyclic-gradle"] = KotlinPluginDefinition(
        plugin_id="one.wabbit.acyclic",
        version="0.0.1",
        compiler_plugin_id="one.wabbit.acyclic",
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "[one.wabbit.acyclic:declarationOrder=bottom-up]" in build_text


def test_setup_gradle_project_renders_desktop_native_targets_and_apple_framework_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(
        tmp_path / "kmp-native-proj",
        platforms=["jvm", "iosArm64", "linuxX64", "mingwX64", "macosX64", "macosArm64"],
    )
    project.path.mkdir(parents=True, exist_ok=True)
    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template=(
            "{% for target in targets %}[{{ target.kind }}:{{ target.name or '' }}]{% endfor %}"
            "|frameworks={% for target_name in apple_framework_target_names %}[{{ target_name }}]{% endfor %}"
        ),
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "[linuxX64:]" in build_text
    assert "[mingwX64:]" in build_text
    assert "[macosX64:]" in build_text
    assert "[macosArm64:clientNative]" in build_text
    assert "frameworks=[iosArm64][macosX64][clientNative]" in build_text


def test_render_dependency_keeps_same_repo_project_dependency_in_prod_mode(tmp_path: Path) -> None:
    ctx = _make_context(tmp_path, jvm_template="", kmp_template="")
    ctx.mode = RepoSetupMode.PROD

    repo_root = tmp_path / "jeeves"
    owner = _make_repo_gradle_project(
        repo_root / "server",
        project_id="jeeves/server",
        repo_root=repo_root,
        gradle_project_name="jeeves-server",
        github_repo="wabbit-corp/jeeves",
    )
    dependency_project = _make_repo_gradle_project(
        repo_root / "api",
        project_id="jeeves/api",
        repo_root=repo_root,
        gradle_project_name="jeeves-api",
        github_repo="wabbit-corp/jeeves",
    )
    ctx.config.defined_projects.update(
        {
            "jeeves/server": owner,
            "jeeves/api": dependency_project,
        }
    )

    dependency = Dependency(scope=None, target=ProjectDependencyTarget(project="jeeves/api"))
    rendered = _render_dependency_for_mode(ctx, owner, dependency)

    assert rendered == 'implementation(project(":jeeves-api")) // 0.0.1'


def test_render_dependency_uses_published_artifact_for_cross_repo_dependency_in_prod_mode(tmp_path: Path) -> None:
    ctx = _make_context(tmp_path, jvm_template="", kmp_template="")
    ctx.mode = RepoSetupMode.PROD

    owner = _make_repo_gradle_project(
        tmp_path / "jeeves" / "server",
        project_id="jeeves/server",
        repo_root=tmp_path / "jeeves",
        gradle_project_name="jeeves-server",
        github_repo="wabbit-corp/jeeves",
    )
    dependency_project = _make_repo_gradle_project(
        tmp_path / "kotlin-dotenv-parser",
        project_id="kotlin-dotenv-parser",
        repo_root=tmp_path / "kotlin-dotenv-parser",
        gradle_project_name="kotlin-dotenv-parser",
        artifact_id="kotlin-dotenv-parser",
        github_repo="wabbit-corp/kotlin-dotenv-parser",
    )
    ctx.config.defined_projects.update(
        {
            "jeeves/server": owner,
            "kotlin-dotenv-parser": dependency_project,
        }
    )

    dependency = Dependency(scope=None, target=ProjectDependencyTarget(project="kotlin-dotenv-parser"))
    rendered = _render_dependency_for_mode(ctx, owner, dependency)

    assert rendered == 'implementation("one.wabbit:kotlin-dotenv-parser:0.0.1")'


def test_render_dependency_uses_published_artifact_for_cross_repo_dependency_in_local_mode(tmp_path: Path) -> None:
    ctx = _make_context(tmp_path, jvm_template="", kmp_template="")
    ctx.mode = RepoSetupMode.LOCAL

    owner = _make_repo_gradle_project(
        tmp_path / "jeeves" / "server",
        project_id="jeeves/server",
        repo_root=tmp_path / "jeeves",
        gradle_project_name="jeeves-server",
        github_repo="wabbit-corp/jeeves",
    )
    dependency_project = _make_repo_gradle_project(
        tmp_path / "kotlin-dotenv-parser",
        project_id="kotlin-dotenv-parser",
        repo_root=tmp_path / "kotlin-dotenv-parser",
        gradle_project_name="kotlin-dotenv-parser",
        artifact_id="kotlin-dotenv-parser",
        github_repo="wabbit-corp/kotlin-dotenv-parser",
    )
    ctx.config.defined_projects.update(
        {
            "jeeves/server": owner,
            "kotlin-dotenv-parser": dependency_project,
        }
    )

    dependency = Dependency(scope=None, target=ProjectDependencyTarget(project="kotlin-dotenv-parser"))
    rendered = _render_dependency_for_mode(ctx, owner, dependency)

    assert rendered == 'implementation("one.wabbit:kotlin-dotenv-parser:0.0.1")'


def test_setup_gradle_project_writes_prod_shaped_settings_even_in_local_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kotlin-demo", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    ctx = _make_context(tmp_path, jvm_template="JVM_TEMPLATE", kmp_template="KMP_TEMPLATE")
    ctx.subproject_settings_template = jinja2.Template("SETTINGS={{ project_name }}")

    setup_gradle_project(ctx, project, interactive=False)

    settings_text = (project.path / "settings.gradle.kts").read_text(encoding="utf-8").strip()
    assert settings_text == "SETTINGS=kotlin-demo"
    assert not (project.path / ".is-local-mode").exists()
    assert not (project.path / ".is-dev-mode").exists()
    assert not (project.path / ".is-ij-mode").exists()


def test_setup_gradle_project_renders_dokka_source_link_for_standalone_jvm_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kotlin-demo", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.github_repo = "wabbit-corp/kotlin-demo"
    ctx = _make_context(
        tmp_path,
        jvm_template=(
            "{% if has_dokka_source_link %}{{ dokka_source_link_remote_url }}{% else %}NO_SOURCE_LINK{% endif %}"
        ),
        kmp_template="KMP_TEMPLATE",
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8").strip()
    assert build_text == "https://github.com/wabbit-corp/kotlin-demo/tree/master/src/main/kotlin"


def test_setup_gradle_project_renders_repo_relative_dokka_source_link_for_nested_kmp_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    repo_root = tmp_path / "jeeves"
    project = _make_project(repo_root / "client", platforms=["jvm", "iosArm64"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.repo_root = repo_root
    project.github_repo = "wabbit-corp/jeeves"
    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template=(
            "{% if has_dokka_source_link %}{{ dokka_source_link_remote_url }}{% else %}NO_SOURCE_LINK{% endif %}"
        ),
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8").strip()
    assert build_text == "https://github.com/wabbit-corp/jeeves/tree/master/client/src"


def test_setup_gradle_project_omits_dokka_source_link_without_github_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "standalone", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    ctx = _make_context(
        tmp_path,
        jvm_template=(
            "{% if has_dokka_source_link %}{{ dokka_source_link_remote_url }}{% else %}NO_SOURCE_LINK{% endif %}"
        ),
        kmp_template="KMP_TEMPLATE",
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8").strip()
    assert build_text == "NO_SOURCE_LINK"


def test_setup_gradle_project_generates_maven_central_and_docs_workflows_for_standalone_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kotlin-demo", platforms=["jvm", "android"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.github_repo = "wabbit-corp/kotlin-demo"
    project.publish = True
    project.publish_target = "maven-central"
    project.publish_snapshots = True
    project.docs_enabled = True
    project.docs_system = "dokka"
    project.description = "Demo library"
    project.ownership = OwnershipType.WABBIT
    ctx = _make_context(
        tmp_path,
        jvm_template="PUBLISH={{ publish_to_maven_central }} {{ pom_url }}",
        kmp_template="KMP={{ publish_to_maven_central }} {{ pom_url }}",
    )
    ctx.config.default_company_email = "oss@wabbit.one"

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "KMP=True https://github.com/wabbit-corp/kotlin-demo" in build_text
    assert (project.path / ".github" / "workflows" / "release-publish.yml").read_text(encoding="utf-8") == (
        "release kotlin-demo android=True\n"
    )
    assert (project.path / ".github" / "workflows" / "snapshot-publish.yml").read_text(encoding="utf-8") == (
        "snapshot kotlin-demo android=True\n"
    )
    assert (project.path / ".github" / "workflows" / "docs-quality.yml").read_text(encoding="utf-8") == (
        "docs-quality kotlin-demo\n"
    )
    assert (project.path / ".github" / "workflows" / "docs-deploy.yml").read_text(encoding="utf-8") == (
        "docs-deploy build/dokka/html\n"
    )


def test_setup_gradle_project_workflow_context_includes_release_and_docs_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "kotlin-demo", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.github_repo = "wabbit-corp/kotlin-demo"
    project.publish = True
    project.publish_target = "maven-central"
    project.publish_snapshots = True
    project.docs_enabled = True
    project.docs_system = "dokka"
    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template="KMP_TEMPLATE",
    )
    ctx.gradle_release_publish_workflow_template = jinja2.Template(
        "{{ version_print_command }}\n{{ release_validation_command }}\n"
        "{{ release_build_command }}\n{{ release_publish_command }}\n"
    )
    ctx.gradle_snapshot_publish_workflow_template = jinja2.Template(
        "{{ snapshot_version_print_command }}\n{{ snapshot_publish_command }}\n"
    )
    ctx.gradle_docs_quality_workflow_template = jinja2.Template("{{ docs_build_command }}\n")
    ctx.gradle_docs_deploy_workflow_template = jinja2.Template("{{ docs_output_dir }}\n")

    setup_gradle_project(ctx, project, interactive=False)

    assert (project.path / ".github" / "workflows" / "release-publish.yml").read_text(encoding="utf-8") == (
        "./gradlew --quiet --no-daemon printVersion\n"
        "./gradlew --no-daemon assertReleaseVersion\n"
        "./gradlew --no-daemon build\n"
        "./gradlew --no-daemon build publishAndReleaseToMavenCentral\n"
    )
    assert (project.path / ".github" / "workflows" / "snapshot-publish.yml").read_text(encoding="utf-8") == (
        "./gradlew --quiet --no-daemon printVersion\n"
        "./gradlew --no-daemon build assertSnapshotVersion publishToMavenCentral\n"
    )
    assert (project.path / ".github" / "workflows" / "docs-quality.yml").read_text(encoding="utf-8") == (
        "./gradlew --no-daemon build dokkaGeneratePublicationHtml\n"
    )
    assert (project.path / ".github" / "workflows" / "docs-deploy.yml").read_text(encoding="utf-8") == (
        "build/dokka/html\n"
    )


def test_write_gradle_repo_root_workflows_uses_nested_task_selectors_and_repo_relative_docs_output(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "jeeves"
    api_project = _make_repo_gradle_project(
        repo_root / "api",
        project_id="jeeves/api",
        repo_root=repo_root,
        gradle_project_name="jeeves-api",
        github_repo="wabbit-corp/jeeves",
    )
    client_project = _make_repo_gradle_project(
        repo_root / "client",
        project_id="jeeves/client",
        repo_root=repo_root,
        gradle_project_name="jeeves-client",
        github_repo="wabbit-corp/jeeves",
    )
    for project in (api_project, client_project):
        project.path.mkdir(parents=True, exist_ok=True)
        project.gradle_root = repo_root
        project.publish = True
        project.publish_target = "maven-central"
        project.publish_snapshots = True
        project.docs_enabled = True
        project.docs_system = "dokka"

    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template="KMP_TEMPLATE",
    )
    ctx.gradle_release_publish_workflow_template = jinja2.Template(
        "{{ version_print_command }}\n{{ release_validation_command }}\n{{ release_publish_command }}\n"
    )
    ctx.gradle_snapshot_publish_workflow_template = jinja2.Template("{{ snapshot_publish_command }}\n")
    ctx.gradle_docs_quality_workflow_template = jinja2.Template("{{ docs_build_command }}\n")
    ctx.gradle_docs_deploy_workflow_template = jinja2.Template("{{ docs_output_dir }}\n")

    _write_gradle_repo_root_workflows(
        ctx,
        root_path=repo_root,
        repo_github_repo="wabbit-corp/jeeves",
        projects=[api_project, client_project],
        docs_project=api_project,
        java_version=21,
    )

    assert (repo_root / ".github" / "workflows" / "release-publish.yml").read_text(encoding="utf-8") == (
        "./gradlew --quiet --no-daemon :jeeves-api:printVersion :jeeves-client:printVersion\n"
        "./gradlew --no-daemon :jeeves-api:assertReleaseVersion :jeeves-client:assertReleaseVersion\n"
        "./gradlew --no-daemon build :jeeves-api:publishAndReleaseToMavenCentral"
        " :jeeves-client:publishAndReleaseToMavenCentral\n"
    )
    assert (repo_root / ".github" / "workflows" / "snapshot-publish.yml").read_text(encoding="utf-8") == (
        "./gradlew --no-daemon build :jeeves-api:assertSnapshotVersion :jeeves-client:assertSnapshotVersion"
        " :jeeves-api:publishToMavenCentral :jeeves-client:publishToMavenCentral\n"
    )
    assert (repo_root / ".github" / "workflows" / "docs-quality.yml").read_text(encoding="utf-8") == (
        "./gradlew --no-daemon build :jeeves-api:dokkaGeneratePublicationHtml\n"
    )
    assert (repo_root / ".github" / "workflows" / "docs-deploy.yml").read_text(encoding="utf-8") == (
        "api/build/dokka/html\n"
    )


def test_write_gradle_repo_root_workflows_skips_release_publish_when_nested_versions_differ(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "jeeves"
    api_project = _make_repo_gradle_project(
        repo_root / "api",
        project_id="jeeves/api",
        repo_root=repo_root,
        gradle_project_name="jeeves-api",
        github_repo="wabbit-corp/jeeves",
    )
    client_project = _make_repo_gradle_project(
        repo_root / "client",
        project_id="jeeves/client",
        repo_root=repo_root,
        gradle_project_name="jeeves-client",
        github_repo="wabbit-corp/jeeves",
    )
    api_project.version = Version.parse("0.0.1")
    client_project.version = Version.parse("1.0.0")
    for project in (api_project, client_project):
        project.path.mkdir(parents=True, exist_ok=True)
        project.gradle_root = repo_root
        project.publish = True
        project.publish_target = "maven-central"
        project.publish_snapshots = True
        project.docs_enabled = True
        project.docs_system = "dokka"

    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template="KMP_TEMPLATE",
    )

    _write_gradle_repo_root_workflows(
        ctx,
        root_path=repo_root,
        repo_github_repo="wabbit-corp/jeeves",
        projects=[api_project, client_project],
        docs_project=api_project,
        java_version=21,
    )

    assert not (repo_root / ".github" / "workflows" / "release-publish.yml").exists()
    assert not (repo_root / ".github" / "workflows" / "snapshot-publish.yml").exists()
    assert (repo_root / ".github" / "workflows" / "docs-quality.yml").exists()
    assert (repo_root / ".github" / "workflows" / "docs-deploy.yml").exists()


def test_setup_gradle_project_skips_public_workflows_for_nested_repo_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    repo_root = tmp_path / "jeeves"
    project = _make_project(repo_root / "api", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.repo_root = repo_root
    project.gradle_root = repo_root
    project.gradle_project_name = "jeeves-api"
    project.github_repo = "wabbit-corp/jeeves"
    project.publish = True
    project.publish_target = "maven-central"
    project.publish_snapshots = True
    project.docs_enabled = True
    project.docs_system = "dokka"
    ctx = _make_context(
        tmp_path,
        jvm_template="JVM_TEMPLATE",
        kmp_template="KMP_TEMPLATE",
    )

    setup_gradle_project(ctx, project, interactive=False)

    assert not (project.path / ".github" / "workflows" / "release-publish.yml").exists()
    assert not (project.path / ".github" / "workflows" / "snapshot-publish.yml").exists()
    assert not (project.path / ".github" / "workflows" / "docs-quality.yml").exists()
    assert not (project.path / ".github" / "workflows" / "docs-deploy.yml").exists()


def test_setup_gradle_project_renders_gradle_plugin_project_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "typeclasses-gradle-plugin", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.gradle_plugin_id = "one.wabbit.typeclass"

    repo_root = Path(__file__).resolve().parents[2]
    jvm_template = (
        repo_root / "data-repo-template" / "gradle-files" / "subproject-build.gradle.kts.jinja2"
    ).read_text(encoding="utf-8")
    ctx = _make_context(
        tmp_path,
        jvm_template=jvm_template,
        kmp_template="KMP_TEMPLATE",
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8")
    assert "`java-gradle-plugin`" in build_text
    assert 'compileOnly("org.jetbrains.kotlin:kotlin-gradle-plugin-api:2.2.20")' in build_text
    assert 'testImplementation("org.jetbrains.kotlin:kotlin-gradle-plugin-api:2.2.20")' in build_text
    assert "testImplementation(gradleApi())" in build_text
    assert "testImplementation(gradleTestKit())" in build_text
    assert 'filesMatching("**/*gradle-plugin.properties")' in build_text
    assert "pluginUnderTestMetadata {" in build_text
    assert 'id = "one.wabbit.typeclass"' in build_text
    assert 'implementationClass = "one.wabbit.typeclass.gradle.TypeclassGradlePlugin"' in build_text
    assert 'displayName = "Typeclass Gradle plugin"' in build_text


def test_setup_gradle_project_uses_configured_paper_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "paper-proj", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.resolved_features = {
        "paper-plugin": PaperPlugin(main="cc.Main", name="CC", apiVersion="1.20"),
    }
    ctx = _make_context(
        tmp_path,
        jvm_template="BUNDLE={{ paper_dev_bundle_version }}",
        kmp_template="KMP_TEMPLATE",
    )
    ctx.subproject_settings_template = jinja2.Template("PLUGIN={{ paperweight_userdev_plugin_version }}")
    ctx.config.plugins["paperweight-userdev"] = KotlinPluginDefinition(
        plugin_id="io.papermc.paperweight.userdev",
        version="2.0.0-beta.19",
    )
    ctx.config.libraries["paper-api"] = MavenLibraryDefinition(
        name="paper-api",
        maven_urn=MavenCoordinate.parse("io.papermc.paper:paper-api:1.21.11-R0.1-SNAPSHOT"),
        repo="repo:papermc",
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8").strip()
    settings_text = (project.path / "settings.gradle.kts").read_text(encoding="utf-8").strip()
    assert build_text == "BUNDLE=1.21.11-R0.1-SNAPSHOT"
    assert settings_text == "PLUGIN=2.0.0-beta.19"


def test_setup_gradle_project_renders_paper_depend_shadow_jar_and_java_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    project = _make_project(tmp_path / "paper-proj", platforms=["jvm"])
    project.path.mkdir(parents=True, exist_ok=True)
    project.resolved_features = {
        "paper-plugin": PaperPlugin(
            main="cc.Main",
            name="CC",
            apiVersion="1.20",
            depend=["ProtocolLib", "Vault"],
        ),
        "shadow-jar": ShadowJar(jarName="cc-shadow.jar"),
        "kotlin": Kotlin(),
        "jvm": Jvm(),
    }
    ctx = _make_context(
        tmp_path,
        jvm_template=(
            "DEPEND={{ features['paper-plugin'].depend|join(',') }}\n"
            "JAR={{ features['shadow-jar'].jarName }}\n"
            "JAVA={{ java_version }}"
        ),
        kmp_template="KMP_TEMPLATE",
    )

    setup_gradle_project(ctx, project, interactive=False)

    build_text = (project.path / "build.gradle.kts").read_text(encoding="utf-8").strip()
    assert "DEPEND=ProtocolLib,Vault" in build_text
    assert "JAR=cc-shadow.jar" in build_text
    assert "JAVA=21" in build_text
