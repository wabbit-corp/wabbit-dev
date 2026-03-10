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
    GradleProject,
    KmpAndroidLibrary,
    KmpCompose,
    KmpJvmRunEntry,
    KmpJvmRuns,
    KotlinPluginDefinition,
    MavenLibraryDefinition,
    OwnershipType,
    ProjectDependencyTarget,
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
            "kotlin-jvm": KotlinPluginDefinition(name="org.jetbrains.kotlin.jvm", version="2.2.20"),
            "kotlin-mp": KotlinPluginDefinition(name="org.jetbrains.kotlin.multiplatform", version="2.2.20"),
            "kotlin-serialization": KotlinPluginDefinition(
                name="org.jetbrains.kotlin.plugin.serialization",
                version="2.2.20",
            ),
            "shadow": KotlinPluginDefinition(name="com.gradleup.shadow", version="8.3.0"),
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
        "kmp-android-library": KmpAndroidLibrary(namespace="one.wabbit.demo", compileSdk=34, minSdk=26),
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


def test_setup_kmp_template_conditionals_include_android_and_compose_only_when_features_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup_side_effects(monkeypatch)
    kmp_template = (
        "{% if 'kmp-android-library' in features %}ANDROID{% endif %}"
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
        "kmp-android-library": KmpAndroidLibrary(namespace="one.wabbit.demo", compileSdk=34, minSdk=26),
        "kmp-compose": KmpCompose(publicResClass=True, resClassPackage="one.wabbit.demo.resources"),
    }
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
