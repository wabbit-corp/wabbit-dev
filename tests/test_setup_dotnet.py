from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import jinja2
from mu.parser import parse


def test_setup_dotnet_project_preserves_fsharp_compile_order_and_writes_repo_root(tmp_path: Path) -> None:
    import dev.tasks.setup_dotnet as setup_dotnet
    from dev.config import Config, DotnetProject, OwnershipType, Version
    from dev.tasks.setup_common import RepoSetupMode

    project_path = tmp_path / "alpha"
    project_file_dir = project_path / "src" / "Alpha"
    project_file_dir.mkdir(parents=True)
    project_file = project_file_dir / "Alpha.fsproj"
    project_file.write_text(
        "\n".join(
            [
                '<Project Sdk="Microsoft.NET.Sdk">',
                "  <ItemGroup>",
                '    <Compile Include="Prelude.fs" />',
                '    <Compile Include="Program.fs" />',
                "  </ItemGroup>",
                "</Project>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_path / "README.md").write_text("# Alpha\n", encoding="utf-8")
    (project_path / "LICENSE.md").write_text("# License\n", encoding="utf-8")

    project = DotnetProject(
        path=project_path,
        name="alpha",
        version=Version.parse("0.1.0"),
        description="Alpha project",
        authors=["Dev"],
        license="AGPL",
        quarantine=False,
        publish=True,
        github_repo="wabbit-corp/alpha",
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
        language="fsharp",
        project_kind="library",
        sdk="Microsoft.NET.Sdk",
        target_framework="net10.0",
        project_id="alpha",
        publish_target="nuget",
        packable=True,
    )

    config = Config(raw=parse("()"))
    config.workspace_root = tmp_path
    config.default_company_legal_name = "Wabbit Corp"
    config.default_git_user_name = "Test User"
    config.defined_projects["alpha"] = project

    ctx = SimpleNamespace(
        config=config,
        repo_template=tmp_path,
        gitignore_template=jinja2.Template("# base\n"),
        dotnet_gitignore_template=jinja2.Template("# dotnet\n"),
        dotnet_global_json_template=jinja2.Template('{"sdk": {"version": "{{ dotnet_sdk_version }}"}}\n'),
        dotnet_nuget_config_template=jinja2.Template("<configuration />\n"),
        dotnet_directory_build_props_template=jinja2.Template("<Project />\n"),
        dotnet_docs_quality_workflow_template=jinja2.Template(""),
        dotnet_docs_deploy_workflow_template=jinja2.Template(""),
        dotnet_release_publish_workflow_template=jinja2.Template("name: Release Publish\n"),
        python_mkdocs_template=jinja2.Template(""),
        python_docs_index_template=jinja2.Template(""),
        python_docs_installation_template=jinja2.Template(""),
        python_docs_development_template=jinja2.Template(""),
        python_contributing_template=jinja2.Template(""),
        mode=RepoSetupMode.LOCAL,
    )

    setup_dotnet.write_wabbit_legal_files = lambda _ctx, _project: None
    setup_dotnet.write_banner = lambda _ctx, _project: None

    setup_dotnet.setup_dotnet_project(ctx, project)

    project_text = project_file.read_text(encoding="utf-8")
    assert 'Compile Include="Prelude.fs"' in project_text
    assert 'Compile Include="Program.fs"' in project_text
    assert project_text.index('Compile Include="Prelude.fs"') < project_text.index('Compile Include="Program.fs"')
    assert "<Version>0.1.0</Version>" in project_text
    assert "<PackageId>alpha</PackageId>" in project_text

    assert (project_path / "global.json").is_file()
    assert (project_path / "NuGet.config").is_file()
    assert (project_path / "Directory.Build.props").is_file()
    assert (project_path / "Alpha.sln").is_file()


def test_setup_dotnet_test_project_uses_relative_project_reference_for_sibling_library(tmp_path: Path) -> None:
    import dev.tasks.setup_dotnet as setup_dotnet
    from dev.config import Config, DotnetProject, OwnershipType, Version
    from dev.tasks.setup_common import RepoSetupMode

    repo_path = tmp_path / "codec-repo"
    library_dir = repo_path / "src" / "Wabbit.Codec.NBT"
    library_dir.mkdir(parents=True)
    library_file = library_dir / "Wabbit.Codec.NBT.fsproj"
    library_file.write_text(
        "\n".join(
            [
                '<Project Sdk="Microsoft.NET.Sdk">',
                "  <ItemGroup>",
                '    <Compile Include="NBT.fs" />',
                "  </ItemGroup>",
                "</Project>",
                "",
            ]
        ),
        encoding="utf-8",
    )

    tests_dir = repo_path / "tests" / "Wabbit.Codec.NBT.Tests"
    tests_dir.mkdir(parents=True)
    tests_file = tests_dir / "Wabbit.Codec.NBT.Tests.fsproj"
    tests_file.write_text(
        "\n".join(
            [
                '<Project Sdk="Microsoft.NET.Sdk">',
                "  <ItemGroup>",
                '    <Compile Include="Tests.fs" />',
                "  </ItemGroup>",
                "</Project>",
                "",
            ]
        ),
        encoding="utf-8",
    )

    library_project = DotnetProject(
        path=library_dir,
        name="codec-nbt",
        version=Version.parse("0.1.0"),
        description="NBT library",
        authors=["Dev"],
        license="AGPL",
        quarantine=False,
        publish=True,
        github_repo="wabbit-corp/codec-repo",
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
        language="fsharp",
        project_kind="library",
        sdk="Microsoft.NET.Sdk",
        target_framework="net10.0",
        project_id="codec-repo/src/Wabbit.Codec.NBT",
        repo_id="codec-repo",
        repo_root=repo_path,
        managed_by_setup=False,
        assembly_name="Wabbit.Codec.NBT",
        package_id="Wabbit.Codec.NBT",
        publish_target="nuget",
        packable=True,
    )

    test_project = DotnetProject(
        path=tests_dir,
        name="codec-nbt-tests",
        version=Version.parse("0.1.0"),
        description=None,
        authors=[],
        license="AGPL",
        quarantine=False,
        publish=False,
        github_repo="wabbit-corp/codec-repo",
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
        language="fsharp",
        project_kind="test",
        sdk="Microsoft.NET.Sdk",
        target_framework="net10.0",
        project_id="codec-repo/tests/Wabbit.Codec.NBT.Tests",
        repo_id="codec-repo",
        repo_root=repo_path,
        managed_by_setup=False,
        assembly_name="Wabbit.Codec.NBT.Tests",
        publish_target=None,
        packable=False,
    )

    from dev.config import Dependency, ProjectDependencyTarget

    test_project.resolved_dependencies.append(
        Dependency(scope=None, target=ProjectDependencyTarget(project="codec-repo/src/Wabbit.Codec.NBT"))
    )

    config = Config(raw=parse("()"))
    config.workspace_root = tmp_path
    config.defined_projects[library_project.project_id] = library_project
    config.defined_projects[test_project.project_id] = test_project

    ctx = SimpleNamespace(
        config=config,
        repo_template=tmp_path,
        gitignore_template=jinja2.Template("# base\n"),
        dotnet_gitignore_template=jinja2.Template("# dotnet\n"),
        dotnet_global_json_template=jinja2.Template('{"sdk": {"version": "{{ dotnet_sdk_version }}"}}\n'),
        dotnet_nuget_config_template=jinja2.Template("<configuration />\n"),
        dotnet_directory_build_props_template=jinja2.Template("<Project />\n"),
        dotnet_docs_quality_workflow_template=jinja2.Template(""),
        dotnet_docs_deploy_workflow_template=jinja2.Template(""),
        dotnet_release_publish_workflow_template=jinja2.Template(""),
        python_mkdocs_template=jinja2.Template(""),
        python_docs_index_template=jinja2.Template(""),
        python_docs_installation_template=jinja2.Template(""),
        python_docs_development_template=jinja2.Template(""),
        python_contributing_template=jinja2.Template(""),
        mode=RepoSetupMode.LOCAL,
    )

    setup_dotnet.write_wabbit_legal_files = lambda _ctx, _project: None
    setup_dotnet.write_banner = lambda _ctx, _project: None

    setup_dotnet.setup_dotnet_project(ctx, test_project)

    project_text = tests_file.read_text(encoding="utf-8")
    assert 'ProjectReference Include="../../src/Wabbit.Codec.NBT/Wabbit.Codec.NBT.fsproj"' in project_text
