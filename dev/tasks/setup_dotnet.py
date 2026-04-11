from __future__ import annotations

import json
import os
import uuid
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import Protocol

import jinja2

import dev.io
import dev.repo_docs
from dev.config import (
    Config,
    Dependency,
    DependencyTarget,
    DotnetProject,
    NugetDependencyTarget,
    Project,
    ProjectDependencyTarget,
    RepoDefinition,
)
from dev.dotnet import NUGET_V3_INDEX_URL, dotnet_project_file, fsharp_compile_entries, workspace_local_nuget_feed
from dev.generated_files import is_setup_managed_file, prepend_generated_comment
from dev.licenses import canonicalize_license_key
from dev.tasks.setup_common import RepoSetupMode, clean_text, render_template, write_banner, write_wabbit_legal_files

_F_SHARP_PROJECT_TYPE_GUID = "{F2A71F9B-5D33-465A-A702-920D77279786}"
_C_SHARP_PROJECT_TYPE_GUID = "{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}"
_DEFAULT_DOTNET_SDK_VERSION = "10.0.100"
_DEFAULT_TEST_PACKAGES: tuple[tuple[str, str], ...] = (
    ("coverlet.collector", "6.0.0"),
    ("Microsoft.NET.Test.Sdk", "17.8.0"),
    ("xunit", "2.5.3"),
    ("xunit.runner.visualstudio", "2.5.3"),
)


class DotnetSetupContext(Protocol):
    config: Config
    default_company_legal_name: str | None
    default_git_user_name: str | None
    gitignore_template: jinja2.Template
    dotnet_gitignore_template: jinja2.Template
    dotnet_global_json_template: jinja2.Template
    dotnet_nuget_config_template: jinja2.Template
    dotnet_directory_build_props_template: jinja2.Template
    dotnet_docs_quality_workflow_template: jinja2.Template
    dotnet_docs_deploy_workflow_template: jinja2.Template
    dotnet_release_publish_workflow_template: jinja2.Template
    python_mkdocs_template: jinja2.Template
    python_docs_index_template: jinja2.Template
    python_docs_installation_template: jinja2.Template
    python_docs_development_template: jinja2.Template
    python_contributing_template: jinja2.Template
    mode: RepoSetupMode


def _merge_gitignore_content(generated_content: str, existing_content: str | None) -> str:
    generated_lines = generated_content.rstrip("\n").splitlines()
    if not existing_content:
        return "\n".join(generated_lines).rstrip("\n") + "\n"

    merged_lines = list(generated_lines)
    seen = set(generated_lines)
    extra_lines = [line for line in existing_content.rstrip("\n").splitlines() if line not in seen]
    if extra_lines:
        if merged_lines and merged_lines[-1] != "":
            merged_lines.append("")
        merged_lines.extend(extra_lines)
    return "\n".join(merged_lines).rstrip("\n") + "\n"


def _xml_escape(value: str) -> str:
    return escape(value, quote=True)


def _generated_xml(text: str, *, body_lines: Sequence[str]) -> str:
    return prepend_generated_comment(
        clean_text(text),
        comment_prefix="<!--",
        comment_suffix="-->",
        body_lines=body_lines,
    )


def _generated_hash(text: str, *, body_lines: Sequence[str]) -> str:
    return prepend_generated_comment(
        clean_text(text),
        comment_prefix="#",
        body_lines=body_lines,
    )


def _repo_url(project: Project) -> str | None:
    if project.github_repo is None:
        return None
    return f"https://github.com/{project.github_repo}"


def _should_emit_spdx_expression(license_key: str | None) -> str | None:
    normalized = canonicalize_license_key(license_key)
    if normalized is None:
        return None
    if normalized.startswith("LicenseRef-"):
        return None
    return normalized


def _bool_xml(value: bool) -> str:
    if value:
        return "true"
    return "false"


def _nullable_xml(project: DotnetProject) -> str | None:
    if project.language != "csharp":
        return None
    if project.nullable is None:
        return "enable"
    return "enable" if project.nullable else "disable"


def _implicit_usings_xml(project: DotnetProject) -> str | None:
    if project.language != "csharp":
        return None
    if project.implicit_usings is None:
        return "enable"
    return "enable" if project.implicit_usings else "disable"


def _output_type(project: DotnetProject) -> str | None:
    if project.project_kind in ("exe", "tool", "test"):
        return "Exe"
    return None


def _package_id_for_project(project: DotnetProject) -> str:
    return project.effective_package_id


def _project_reference_dependencies(
    config: Config,
    project: DotnetProject,
) -> tuple[list[DotnetProject], list[tuple[str, str]]]:
    local_project_dependencies: list[DotnetProject] = []
    package_references: list[tuple[str, str]] = []

    for dependency in project.resolved_dependencies:
        target = dependency.target
        if isinstance(target, NugetDependencyTarget):
            package_references.append((target.package, target.version))
            continue
        if not isinstance(target, ProjectDependencyTarget):
            raise ValueError(f"Unsupported .NET dependency target for {project.name}: {type(target).__name__}")

        dependency_project = config.defined_projects[target.project]
        if not isinstance(dependency_project, DotnetProject):
            raise ValueError(
                f".NET project {project.name} depends on non-.NET project {dependency_project.name}"
            )
        if dependency_project.effective_repo_root.resolve() == project.effective_repo_root.resolve():
            local_project_dependencies.append(dependency_project)
            continue
        dependency_version = dependency_project.version
        if dependency_version is None:
            raise ValueError(f"Cross-repo .NET dependency {dependency_project.name} is missing a version")
        package_references.append((_package_id_for_project(dependency_project), str(dependency_version)))

    if project.project_kind == "test":
        for package_name, version in _DEFAULT_TEST_PACKAGES:
            package_references.append((package_name, version))

    unique_packages: list[tuple[str, str]] = []
    seen_packages: set[tuple[str, str]] = set()
    for package_reference in package_references:
        if package_reference in seen_packages:
            continue
        seen_packages.add(package_reference)
        unique_packages.append(package_reference)

    unique_projects: list[DotnetProject] = []
    seen_projects: set[str] = set()
    for dependency_project in local_project_dependencies:
        dependency_key = dependency_project.project_id or dependency_project.name
        if dependency_key in seen_projects:
            continue
        seen_projects.add(dependency_key)
        unique_projects.append(dependency_project)
    return unique_projects, unique_packages


def _compile_entries_for_fsharp(project: DotnetProject) -> list[str]:
    project_file = dotnet_project_file(project)
    existing_entries = fsharp_compile_entries(project_file)
    if existing_entries:
        return existing_entries

    base_dir = project_file.parent
    if not base_dir.exists():
        return []

    entries = [
        path.relative_to(base_dir).as_posix()
        for path in sorted(base_dir.rglob("*.fs"))
        if all(part not in {"bin", "obj"} for part in path.parts)
    ]
    return entries


def _project_item_group_xml(project: DotnetProject, compile_entries: list[str]) -> list[str]:
    item_group_lines: list[str] = []
    if project.language == "fsharp" and compile_entries:
        item_group_lines.extend(["  <ItemGroup>"])
        for entry in compile_entries:
            item_group_lines.append(f'    <Compile Include="{_xml_escape(entry)}" />')
        item_group_lines.append("  </ItemGroup>")
    return item_group_lines


def _package_metadata_items(project: DotnetProject, project_file: Path) -> list[str]:
    metadata_items: list[str] = []
    repo_root = project.effective_repo_root
    readme_path = repo_root / "README.md"
    if readme_path.is_file():
        relative_readme = Path(os.path.relpath(readme_path, project_file.parent)).as_posix()
        metadata_items.append(
            f'    <None Include="{_xml_escape(relative_readme)}" Pack="true" PackagePath="\\\\" />'
        )

    license_path = repo_root / "LICENSE.md"
    if license_path.is_file():
        relative_license = Path(os.path.relpath(license_path, project_file.parent)).as_posix()
        metadata_items.append(
            f'    <None Include="{_xml_escape(relative_license)}" Pack="true" PackagePath="LICENSE.md" />'
        )
    return metadata_items


def _render_project_xml(ctx: DotnetSetupContext, project: DotnetProject) -> str:
    project_file = dotnet_project_file(project)
    compile_entries = _compile_entries_for_fsharp(project)
    local_project_dependencies, package_references = _project_reference_dependencies(ctx.config, project)
    target_frameworks = project.effective_target_frameworks

    property_lines = ["  <PropertyGroup>"]
    if len(target_frameworks) == 1:
        property_lines.append(f"    <TargetFramework>{_xml_escape(target_frameworks[0])}</TargetFramework>")
    elif len(target_frameworks) > 1:
        property_lines.append(
            f"    <TargetFrameworks>{_xml_escape(';'.join(target_frameworks))}</TargetFrameworks>"
        )
    output_type = _output_type(project)
    if output_type is not None:
        property_lines.append(f"    <OutputType>{output_type}</OutputType>")
    property_lines.append(f"    <AssemblyName>{_xml_escape(project.effective_assembly_name)}</AssemblyName>")
    property_lines.append(f"    <RootNamespace>{_xml_escape(project.effective_root_namespace)}</RootNamespace>")
    property_lines.append(f"    <Version>{_xml_escape(str(project.version) if project.version is not None else '0.0.0')}</Version>")
    property_lines.append(f"    <PackageId>{_xml_escape(project.effective_package_id)}</PackageId>")
    if project.description:
        property_lines.append(f"    <Description>{_xml_escape(project.description)}</Description>")
    if project.authors:
        property_lines.append(f"    <Authors>{_xml_escape(', '.join(project.authors))}</Authors>")
    if project.package_tags:
        property_lines.append(f"    <PackageTags>{_xml_escape(' '.join(project.package_tags))}</PackageTags>")
    repository_url = _repo_url(project)
    if repository_url is not None:
        property_lines.append(f"    <RepositoryUrl>{_xml_escape(repository_url)}</RepositoryUrl>")
        property_lines.append("    <RepositoryType>git</RepositoryType>")
    spdx_expression = _should_emit_spdx_expression(project.license)
    if spdx_expression is not None:
        property_lines.append(f"    <PackageLicenseExpression>{_xml_escape(spdx_expression)}</PackageLicenseExpression>")
    nullable = _nullable_xml(project)
    if nullable is not None:
        property_lines.append(f"    <Nullable>{nullable}</Nullable>")
    implicit_usings = _implicit_usings_xml(project)
    if implicit_usings is not None:
        property_lines.append(f"    <ImplicitUsings>{implicit_usings}</ImplicitUsings>")
    if project.lang_version is not None:
        property_lines.append(f"    <LangVersion>{_xml_escape(project.lang_version)}</LangVersion>")
    if project.project_kind == "test":
        property_lines.append("    <IsPackable>false</IsPackable>")
        property_lines.append("    <GenerateProgramFile>false</GenerateProgramFile>")
        property_lines.append("    <IsTestProject>true</IsTestProject>")
        property_lines.append("    <GenerateDocumentationFile>false</GenerateDocumentationFile>")
    else:
        property_lines.append(f"    <IsPackable>{_bool_xml(project.packable)}</IsPackable>")
        property_lines.append(
            f"    <GenerateDocumentationFile>{_bool_xml(project.generate_documentation_file)}</GenerateDocumentationFile>"
        )
    if project.project_kind == "tool":
        property_lines.append("    <PackAsTool>true</PackAsTool>")
        property_lines.append(f"    <ToolCommandName>{_xml_escape(project.name)}</ToolCommandName>")
    property_lines.append("  </PropertyGroup>")

    item_groups = _project_item_group_xml(project, compile_entries)

    if package_references:
        item_groups.append("  <ItemGroup>")
        for package_name, version in package_references:
            item_groups.append(
                f'    <PackageReference Include="{_xml_escape(package_name)}" Version="{_xml_escape(version)}" />'
            )
        item_groups.append("  </ItemGroup>")

    if local_project_dependencies:
        item_groups.append("  <ItemGroup>")
        for dependency_project in local_project_dependencies:
            relative_path = Path(
                os.path.relpath(
                    dotnet_project_file(dependency_project),
                    start=project_file.parent,
                )
            ).as_posix()
            item_groups.append(f'    <ProjectReference Include="{_xml_escape(relative_path)}" />')
        item_groups.append("  </ItemGroup>")

    metadata_items = _package_metadata_items(project, project_file)
    if metadata_items:
        item_groups.append("  <ItemGroup>")
        item_groups.extend(metadata_items)
        item_groups.append("  </ItemGroup>")

    xml_lines = [f'<Project Sdk="{_xml_escape(project.sdk)}">', *property_lines, *item_groups, "</Project>"]
    body_lines = [
        "This file is generated from workspace configuration in root.clj.",
        "To change managed project metadata or dependencies, update root.clj and regenerate with:",
        "  dev setup <project-or-repo>",
    ]
    if project.language == "fsharp":
        body_lines.extend(
            [
                "For F# projects, the ordered <Compile Include=...> list is preserved from the checked-in fsproj",
                "and remains the source of truth for compile order.",
            ]
        )
    return _generated_xml("\n".join(xml_lines) + "\n", body_lines=body_lines)


def _write_dotnet_docs(ctx: DotnetSetupContext, project: DotnetProject) -> None:
    site_url = dev.repo_docs.repo_docs_site_url(ctx.config, project)
    repository_url = _repo_url(project)
    repository_name = project.github_repo
    managed_mkdocs_text = prepend_generated_comment(
        clean_text(
            render_template(
                ctx.python_mkdocs_template,
                site_name=project.name,
                site_description=project.description or f"Documentation for {project.name}.",
                site_url=site_url,
                repo_url=repository_url,
                repo_name=repository_name,
            )
        ),
        comment_prefix="#",
        body_lines=[
            "This file is generated from workspace configuration in root.clj.",
            "To change it, update root.clj and rerun:",
            "  dev setup <project-or-repo>",
        ],
    )
    mkdocs_path = project.path / "mkdocs.yml"
    if not mkdocs_path.exists() or is_setup_managed_file(mkdocs_path):
        dev.io.write_text_file(mkdocs_path, managed_mkdocs_text)

    dev.io.write_text_file_if_missing(
        project.path / "docs" / "index.md",
        clean_text(
            render_template(
                ctx.python_docs_index_template,
                project_name=project.name,
                project_description=project.description or "",
            )
        ),
    )
    dev.io.write_text_file_if_missing(
        project.path / "docs" / "installation.md",
        clean_text(render_template(ctx.python_docs_installation_template, package_name=project.name)),
    )
    dev.io.write_text_file_if_missing(
        project.path / "docs" / "development.md",
        clean_text(render_template(ctx.python_docs_development_template, project_name=project.name)),
    )
    dev.io.write_text_file_if_missing(
        project.path / "CONTRIBUTING.md",
        clean_text(render_template(ctx.python_contributing_template, project_name=project.name)),
    )

    if dev.repo_docs.repo_docs_workflows_owned_by_repo(ctx.config, project):
        dev.io.delete_if_exists(project.path / ".github" / "workflows" / "docs-quality.yml")
        dev.io.delete_if_exists(project.path / ".github" / "workflows" / "docs-deploy.yml")
        return

    docs_workflow_context = {
        "dotnet_version": _DEFAULT_DOTNET_SDK_VERSION,
        "project_file": dotnet_project_file(project).relative_to(project.path).as_posix(),
        "has_docs_links_script": (project.path / "scripts" / "check_docs_links.py").is_file(),
        "has_docs_snippets_test": (project.path / "tests" / "test_docs_snippets.py").is_file(),
    }
    dev.io.write_text_file(
        project.path / ".github" / "workflows" / "docs-quality.yml",
        clean_text(render_template(ctx.dotnet_docs_quality_workflow_template, **docs_workflow_context)),
    )
    dev.io.write_text_file(
        project.path / ".github" / "workflows" / "docs-deploy.yml",
        clean_text(render_template(ctx.dotnet_docs_deploy_workflow_template, **docs_workflow_context)),
    )


def _release_bundle_projects_json(projects: Sequence[DotnetProject], *, root_path: Path) -> str:
    items = [
        {
            "projectId": project.project_id or project.name,
            "assetSlug": (project.project_id or project.name).replace("/", "-"),
            "sourceDir": str((root_path / "artifacts" / "packages" / (project.project_id or project.name).replace("/", "-")).resolve()),
            "archivePrefix": "packages",
            "bundleKind": "dotnet-nuget",
        }
        for project in projects
        if project.packable and project.publish
    ]
    return json.dumps(items)


def _write_release_workflow(
    ctx: DotnetSetupContext,
    *,
    root_path: Path,
    projects: Sequence[DotnetProject],
    github_repo: str | None,
) -> None:
    workflow_path = root_path / ".github" / "workflows" / "release-publish.yml"
    publish_projects = [project for project in projects if project.publish and project.packable]
    if github_repo is None or not publish_projects:
        dev.io.delete_if_exists(workflow_path)
        return

    release_projects = [
        {
            "project_id": project.project_id or project.name,
            "project_file": dotnet_project_file(project).relative_to(root_path).as_posix(),
            "pack_output_dir": f"artifacts/packages/{(project.project_id or project.name).replace('/', '-')}",
        }
        for project in publish_projects
    ]
    dev.io.write_text_file(
        workflow_path,
        clean_text(
            render_template(
                ctx.dotnet_release_publish_workflow_template,
                dotnet_version=_DEFAULT_DOTNET_SDK_VERSION,
                release_versions_literal=repr([str(project.version) for project in publish_projects if project.version]),
                publish_projects=release_projects,
                release_bundle_projects_json=_release_bundle_projects_json(publish_projects, root_path=root_path),
            )
        ),
    )


def _project_guid(project: DotnetProject) -> str:
    identifier = project.project_id or project.name
    value = uuid.uuid5(uuid.NAMESPACE_URL, f"wabbit-dotnet:{identifier}")
    return "{" + str(value).upper() + "}"


def _project_type_guid(project: DotnetProject) -> str:
    if project.language == "fsharp":
        return _F_SHARP_PROJECT_TYPE_GUID
    return _C_SHARP_PROJECT_TYPE_GUID


def _render_solution_text(
    repo_definition: RepoDefinition,
    projects: Sequence[DotnetProject],
) -> str:
    root_path = repo_definition.path
    solution_lines = [
        "Microsoft Visual Studio Solution File, Format Version 12.00",
        "# Visual Studio Version 17",
        "VisualStudioVersion = 17.0.31903.59",
        "MinimumVisualStudioVersion = 10.0.40219.1",
    ]
    sorted_projects = sorted(projects, key=lambda item: item.project_id or item.name)
    for project in sorted_projects:
        relative_path = dotnet_project_file(project).relative_to(root_path).as_posix().replace("/", "\\")
        solution_lines.append(
            f'Project("{_project_type_guid(project)}") = "{project.effective_assembly_name}", "{relative_path}", "{_project_guid(project)}"'
        )
        solution_lines.append("EndProject")
    solution_lines.extend(
        [
            "Global",
            "\tGlobalSection(SolutionConfigurationPlatforms) = preSolution",
            "\t\tDebug|Any CPU = Debug|Any CPU",
            "\t\tRelease|Any CPU = Release|Any CPU",
            "\tEndGlobalSection",
            "\tGlobalSection(ProjectConfigurationPlatforms) = postSolution",
        ]
    )
    for project in sorted_projects:
        guid = _project_guid(project)
        solution_lines.append(f"\t\t{guid}.Debug|Any CPU.ActiveCfg = Debug|Any CPU")
        solution_lines.append(f"\t\t{guid}.Debug|Any CPU.Build.0 = Debug|Any CPU")
        solution_lines.append(f"\t\t{guid}.Release|Any CPU.ActiveCfg = Release|Any CPU")
        solution_lines.append(f"\t\t{guid}.Release|Any CPU.Build.0 = Release|Any CPU")
    solution_lines.extend(
        [
            "\tEndGlobalSection",
            "EndGlobal",
        ]
    )
    return _generated_hash(
        "\n".join(solution_lines) + "\n",
        body_lines=[
            "This file is generated from workspace configuration in root.clj.",
            "To change repo membership or project metadata, update root.clj and rerun:",
            "  dev setup <project-or-repo>",
        ],
    )


def _write_repo_root_files(
    ctx: DotnetSetupContext,
    repo_definition: RepoDefinition,
    projects: Sequence[DotnetProject],
) -> None:
    root_path = repo_definition.path
    root_path.mkdir(parents=True, exist_ok=True)

    existing_gitignore = None
    gitignore_path = root_path / ".gitignore"
    if gitignore_path.is_file():
        existing_gitignore = gitignore_path.read_text(encoding="utf-8")
    generated_gitignore = clean_text(
        render_template(ctx.gitignore_template) + "\n" + render_template(ctx.dotnet_gitignore_template)
    )
    dev.io.write_text_file(gitignore_path, _merge_gitignore_content(generated_gitignore, existing_gitignore))

    global_json = clean_text(
        render_template(
            ctx.dotnet_global_json_template,
            dotnet_sdk_version=repo_definition.dotnet_sdk_version or _DEFAULT_DOTNET_SDK_VERSION,
        )
    )
    dev.io.write_text_file(root_path / "global.json", global_json)

    local_feed_path: str | None
    if ctx.mode == RepoSetupMode.LOCAL:
        workspace_root = ctx.config.workspace_root
        local_feed_path = None if workspace_root is None else str(workspace_local_nuget_feed(workspace_root))
    else:
        local_feed_path = None
    nuget_config_text = _generated_xml(
        render_template(
            ctx.dotnet_nuget_config_template,
            local_feed_path=local_feed_path,
        ),
        body_lines=[
            "This file is generated from workspace configuration in root.clj.",
            "To change package source policy, update root.clj and rerun:",
            "  dev setup <project-or-repo>",
        ],
    )
    dev.io.write_text_file(root_path / "NuGet.config", nuget_config_text)

    directory_build_props = _generated_xml(
        render_template(
            ctx.dotnet_directory_build_props_template,
            company_name=ctx.config.default_company_legal_name,
            authors=ctx.config.default_git_user_name,
            repository_url=f"https://github.com/{repo_definition.github_repo}" if repo_definition.github_repo else None,
        ),
        body_lines=[
            "This file is generated from workspace configuration in root.clj.",
            "To change repo-wide .NET build metadata, update root.clj and rerun:",
            "  dev setup <project-or-repo>",
        ],
    )
    dev.io.write_text_file(root_path / "Directory.Build.props", directory_build_props)

    solution_name = repo_definition.solution_name or repo_definition.repo_id
    solution_path = root_path / f"{solution_name}.sln"
    dev.io.write_text_file(solution_path, _render_solution_text(repo_definition, projects))


def setup_dotnet_repo_root(
    ctx: DotnetSetupContext,
    repo_definition: RepoDefinition,
    projects: Sequence[DotnetProject],
) -> None:
    _write_repo_root_files(ctx, repo_definition, projects)
    _write_release_workflow(
        ctx,
        root_path=repo_definition.path,
        projects=projects,
        github_repo=repo_definition.github_repo,
    )


def setup_dotnet_project(ctx: DotnetSetupContext, project: DotnetProject) -> None:
    existing_gitignore = None
    gitignore_path = project.path / ".gitignore"
    if gitignore_path.is_file():
        existing_gitignore = gitignore_path.read_text(encoding="utf-8")
    generated_gitignore = clean_text(
        render_template(ctx.gitignore_template) + "\n" + render_template(ctx.dotnet_gitignore_template)
    )
    dev.io.write_text_file(gitignore_path, _merge_gitignore_content(generated_gitignore, existing_gitignore))

    write_wabbit_legal_files(ctx, project)
    write_banner(ctx, project)

    project_file_path = dotnet_project_file(project)
    dev.io.write_text_file(project_file_path, _render_project_xml(ctx, project))

    if project.docs_enabled and project.docs_system == "mkdocs":
        _write_dotnet_docs(ctx, project)

    if project.repo_id is None:
        repo_definition = RepoDefinition(
            repo_id=project.project_id or project.name,
            path=project.path,
            github_repo=project.github_repo,
            gradle_root_project_name=None,
            jvm_policy=None,
            dotnet_sdk_version=_DEFAULT_DOTNET_SDK_VERSION,
            solution_name=project.effective_assembly_name,
            project_ids=[project.project_id or project.name],
        )
        _write_repo_root_files(ctx, repo_definition, [project])
        _write_release_workflow(
            ctx,
            root_path=project.path,
            projects=[project],
            github_repo=project.github_repo,
        )


__all__ = [
    "setup_dotnet_project",
    "setup_dotnet_repo_root",
]
