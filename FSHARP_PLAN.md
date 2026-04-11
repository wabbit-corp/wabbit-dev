# C# / F# (.NET) Support Plan

## Goal

Add first-class `.NET` support to `dev` for SDK-style F# and C# projects, covering:

- `root.clj` modeling
- `dev setup` generation
- `dev build`
- `dev check` and fixers
- `dev docs check` and docs workflows
- `dev package verify`
- `dev project versions`
- publishing and release workflows
- release bundles and GitHub Releases

The end state should feel like existing Python and Gradle support, not like a collection of ad hoc dotnet shell-outs.

## Current State

- `app-wabbit-dev` has no first-class `.NET` project model today.
- The typed config model supports `python`, `gradle`, `purescript`, `premake`, and `data`, but not `fsharp`, `csharp`, or `dotnet`.
- `dev setup`, `dev build`, `dev release verify`, `dev release bundle`, `repo_docs.py`, and the docs verifier only branch for Python and Gradle right now.
- Existing support is incidental:
  - file classification knows `.fs`, `.fsi`, `.fsx`, `.cs`, `.fsproj`, `.csproj`, `.sln`
  - code linting has `csharpier` support
  - repo docs workflow planning already has a `needs_dotnet` field, but it is always `False`
  - release checklist content already includes `.NET`, `F#`, and `NuGet`
- The real target repos already exist:
  - `fsharp-lang-mu`
  - `fsharp-codec-nbt`
  - `fsharp-mc-fileformats`
  - `fsharp-vs-fileformats`
  - `dotnet-diff`
- Those repos are mostly SDK-style and simple:
  - `src/` and `tests/`
  - `global.json`
  - explicit `Compile Include` lists for F#
  - `GenerateDocumentationFile=true` on library projects
  - xUnit-based test projects
- One important dependency problem already exists:
  - `fsharp-mc-fileformats` currently uses a cross-repo `ProjectReference` to `fsharp-codec-nbt`
  - this is the wrong long-term shape for managed setup because it leaks outside the repo boundary and does not model prod packaging cleanly
- Those F# repos are not represented in `root.clj` today, so migration starts with onboarding them into the workspace model.

## Scope

### In Scope

- SDK-style F# and C# libraries
- SDK-style F# and C# console tools/apps
- SDK-style test projects
- repo-level `.sln`, `global.json`, `Directory.Build.props`, `NuGet.config`, and optional `Directory.Packages.props`
- NuGet package publishing
- repo docs, docs validation, and GitHub Pages deployment
- GitHub Release asset generation through the existing release-bundle flow

### Not In Initial Scope

- ASP.NET-specific project types
- WPF, WinForms, MAUI, Unity, Blazor
- legacy `packages.config`
- Paket
- Visual Studio solution behavior for old non-SDK projects
- deeply custom game-mod C# repos with large unmanaged `Directory.Build.props` policy surfaces

Those can be added later, but the first implementation should target the SDK-style library/tool/test repos we already have.

## Recommended Design

### 1. Use One Shared Internal Model

Internally, add a shared `DotnetProject` model with a `language` field:

- `language = "fsharp"`
- `language = "csharp"`

Externally, expose language-shaped config tags for ergonomics:

- `(fsharp ...)`
- `(csharp ...)`

Optional later:

- `(dotnet ... :language "fsharp")`
- `(dotnet ... :language "csharp")`

This keeps `root.clj` readable while avoiding duplicate implementation.

### 2. Standardize on SDK-Style Project Generation

Managed `.NET` projects should be generated from `root.clj` and follow a stable layout:

- repo root:
  - `.gitignore`
  - `global.json`
  - `NuGet.config`
  - `Directory.Build.props`
  - optional `Directory.Packages.props`
  - repo `.sln`
- project roots:
  - `src/<ProjectName>/<ProjectName>.fsproj` or `.csproj`
  - `tests/<ProjectName>.Tests/<ProjectName>.Tests.fsproj` or `.csproj`
  - optional `docs/`, `mkdocs.yml`, `scripts/`

Generated files should carry the existing managed-file integrity stamp wherever the file format allows it:

- XML files can use `<!-- ... -->`
- `.sln` likely can use `# ...`
- if a file format proves hostile to in-band stamping, add a generic managed sidecar manifest instead of leaving it unstamped

Special case:

- F# `.fsproj` files should be treated as hybrid-owned rather than fully generated
- the checked-in `.fsproj` remains authoritative for `<Compile Include>` membership and order
- `root.clj` remains authoritative for everything else we can sanely model: target frameworks, package metadata, dependencies, publish/docs flags, and repo wiring
- setup should therefore preserve or merge the compile item list instead of treating the whole file as generator-owned text

### 3. Use Repo-Local `ProjectReference`, Cross-Repo `PackageReference`

Dependency policy should be:

- same repo dependency: generate `ProjectReference`
- cross-repo dependency: generate `PackageReference`

For local development, do not keep cross-repo `ProjectReference` edges in committed project files.

Recommended local-dev story:

- `dev setup --local` generates a workspace-local NuGet feed configuration via `NuGet.config`
- `dev build` or `dev package verify` can pre-pack upstream cross-repo `.NET` dependencies into that local feed before building the dependent project
- `dev setup --prod` keeps restore pointed at public feeds only

This mirrors the existing Gradle local-vs-prod overlay idea while preserving production package semantics.

### 4. Default to High-Quality Written Docs, Not Auto-API Output Alone

For `.NET`, the default docs system should be `mkdocs`, not a raw API-doc tool alone.

Reason:

- the repo-wide docs tooling already standardizes on written docs plus validation
- a generated API reference is useful, but it is not the same thing as good docs
- this aligns with the existing direction for Python docs and your stated quality bar

Recommended docs shape for docs-enabled `.NET` projects:

- `README.md`
- `mkdocs.yml`
- `docs/index.md`
- `docs/installation.md`
- `docs/development.md`
- at least one example page or example section
- `scripts/check_docs_links.py`
- `tests/test_docs_snippets.py`
- optional `scripts/generate_api_docs.py` later

Package-level XML docs should still be enabled by default for publishable libraries.

### 5. Treat `.fsproj` Compile Order as Authoritative

F# is the main place where naive generation will fail.

For F# libraries and tests, compile order must be explicit, but it does not need to live in `root.clj`.

Recommended approach:

- treat the checked-in `.fsproj` as the source of truth for `<Compile Include="...">`
- parse and preserve that ordered list during setup
- let `root.clj` drive the rest of the project model
- add checks that compare `.fsproj` compile entries against files on disk
- if an `.fsproj` does not exist yet, seed it deterministically on first generation and then treat it as authoritative after that

Do not try to infer F# compile order from filesystem order or lexicographic order.

C# can use default SDK globs in the common case.

## Proposed Config Surface

Naming convention:

- keep the existing external `root.clj` style
- simple fields stay lowercase single-word where they already are, like `:name`, `:version`, `:repo`
- multi-word fields use lowerCamelCase, like `:publishTarget`, `:docsSystem`, `:testLicense`, `:buildModel`
- do not introduce kebab-case for `.NET` fields only; consistency with the existing workspace schema is more important here

### Project-Level Fields

Shared fields:

- `dir_name`
- `version`
- `name`
- `description`
- `authors`
- `license`
- `copyright_holder`
- `copyright_year_start`
- `quarantine`
- `publish`
- `publishTarget`
- `publishSnapshots`
- `docs`
- `docsSystem`
- `repo`
- `ownership`
- `testLicense`

Dotnet-specific fields:

- `projectKind`
  - `library`
  - `exe`
  - `test`
  - `tool`
- `targetFramework`
  - single string for the common case
- `targetFrameworks`
  - multi-target list when needed
- `sdk`
  - default `Microsoft.NET.Sdk`
- `assemblyName`
- `rootNamespace`
- `packageId`
- `packageTags`
- `generateDocumentationFile`
- `nullable`
- `implicitUsings`
- `langVersion`
- `dependencies`
  - project refs and package refs
- `sourceRoots`
- `testProject`
- `packable`

F#-specific fields:

- none required for file order
- file order lives in the checked-in `.fsproj`
- optional later: an escape hatch only if we discover cases where `.fsproj` parsing is insufficient

C#-specific fields:

- optional `compileGlobs` only if we actually need to override SDK defaults later

### Repo-Level Fields

Add repo-level `.NET` defaults so multi-project repos stay coherent:

- `dotnetSdkVersion`
- `defaultTargetFramework`
- `solutionName`
- `useCentralPackageManagement`

Optional later:

- `nugetFeedName`
- repo-wide analyzer policy

### Example Shapes

F# library:

```clojure
(fsharp "fsharp-lang-mu"
    :name "lang-mu"
    :version "0.1.0"
    :repo ":sem"
    :publishTarget "nuget"
    :projectKind "library"
    :targetFramework "net10.0"
    :docs true
    :docsSystem "mkdocs")
```

C# tool:

```clojure
(csharp "dotnet-diff"
    :name "dotnet-diff"
    :version "0.1.0"
    :publishTarget "nuget"
    :projectKind "exe"
    :targetFramework "net10.0"
    :docs true
    :docsSystem "mkdocs")
```

## Workstreams

## 1. Config And Typed Model

- [ ] Add typed config commands for `fsharp` and `csharp`
- [ ] Add a shared internal `DotnetProject` dataclass
- [ ] Extend config loading, validation, and publish-target inference
- [ ] Add repo-level `.NET` defaults to `RepoCommand`
- [ ] Add `nuget-api-key` private config support
- [ ] Decide the canonical publish target name
  - recommendation: `nuget`

## 2. Setup Generation And Templates

- [ ] Add `data-repo-template/dotnet-files/`
- [ ] Add templates for:
  - `global.json`
  - `NuGet.config`
  - `Directory.Build.props`
  - optional `Directory.Packages.props`
  - `.gitignore`
  - F# library `.fsproj`
  - F# test `.fsproj`
  - F# exe/tool `.fsproj`
  - C# library `.csproj`
  - C# test `.csproj`
  - C# exe/tool `.csproj`
  - repo `.sln`
  - docs workflows
  - release workflows
- [ ] Generate repo `.sln` deterministically
- [ ] Generate stable solution-folder and project GUIDs from normalized paths
- [ ] Stamp managed generated `.xml` and `.sln` files with integrity markers
- [ ] Add repo-level `.NET` setup flow alongside existing Gradle/Python flows
- [ ] Keep setup idempotent
- [ ] Make F# `.fsproj` updates structure-aware:
  - preserve `<Compile Include>` entries and order from the checked-in file
  - regenerate managed metadata, dependency, and property sections from `root.clj`
  - seed new F# project files deterministically only when no `.fsproj` exists yet

### `.sln` Generation Notes

Recommended approach:

- do not rely on `dotnet sln add` as the primary implementation
- generate solution text directly for deterministic output and easier drift checking
- reflect repo structure with solution folders like `src`, `tests`, and `examples`

## 3. Build And Local Dependency Resolution

- [ ] Extend `dev build` to support `DotnetProject`
- [ ] Build command should use:
  - `dotnet restore`
  - `dotnet build`
- [ ] For test targets, decide whether `build` remains build-only or also runs tests
  - recommendation: keep `build` build-only
  - put tests in `package verify` and `release verify`
- [ ] Add workspace-local NuGet feed support for `--local`
- [ ] Pre-pack cross-repo local dependencies into that feed before dependent builds
- [ ] Replace the current cross-repo `ProjectReference` pattern during migration

## 4. Package Verification

Add `.NET` support to `dev package verify`.

Proposed verification flow:

- [ ] `dotnet restore`
- [ ] `dotnet build -c Release`
- [ ] `dotnet test -c Release --no-build` when tests exist
- [ ] `dotnet pack -c Release --no-build -o <temp>`
- [ ] inspect produced `.nupkg` and optional `.snupkg`
- [ ] validate nuspec/package metadata:
  - package ID
  - version
  - authors
  - description
  - license expression or license file
  - repository URL
  - tags
  - README linkage
- [ ] validate package contents:
  - main assembly
  - XML docs for libraries when enabled
  - README
  - LICENSE
  - icon if declared
  - no accidental `obj/`, `bin/`, tests, or local-only junk
- [ ] run a consumer smoke test from a temp project against the just-packed artifact

Consumer smoke-test policy:

- F# library: F# consumer required
- C# library: C# consumer required
- optional later: cross-language consumer smoke tests when interop matters

## 5. Docs And Repo Docs Workflows

- [ ] Add `.NET` support to `repo_docs.py`
- [ ] Set `needs_dotnet=True` when repo docs require a dotnet toolchain
- [ ] Make docs-enabled `.NET` projects participate in repo docs planning
- [ ] Support `mkdocs` as the initial docs system for `.NET`
- [ ] Generate:
  - `mkdocs.yml`
  - `docs/index.md`
  - `docs/installation.md`
  - `docs/development.md`
  - optional API reference hook
- [ ] Reuse the repo-level GitHub Pages aggregation model already used for multi-project docs
- [ ] Add `.NET` docs-quality and docs-deploy workflow variants where needed

Recommended documentation bar:

- README explains what the project is and why it exists
- quickstart/install section
- one compelling example
- project status or maturity
- docs/support links
- changelog/release notes link

### API Docs Strategy

Phase 1:

- require XML docs in packable libraries
- standardize written docs plus package XML docs

Phase 2:

- add generated API-reference pages if the toolchain story is good enough
- keep that additive, not a replacement for written docs

## 6. Checks And Fixers

Add a dotnet-specific check module set.

### Layout / Config Drift

- [ ] `DotnetProjectRootsUndeclaredCheck`
- [ ] `DotnetDeclaredProjectRootsMissingCheck`
- [ ] `DotnetSolutionDriftCheck`
- [ ] `DotnetGlobalJsonDriftCheck`
- [ ] `DotnetDirectoryBuildPropsDriftCheck`
- [ ] `DotnetNuGetConfigDriftCheck`

### Project File Drift

- [ ] `DotnetTargetFrameworkDriftCheck`
- [ ] `DotnetProjectReferenceDriftCheck`
- [ ] `DotnetPackageReferenceDriftCheck`
- [ ] `DotnetPackageMetadataDriftCheck`
- [ ] `DotnetPackAssetMetadataCheck`
- [ ] `DotnetXmlDocsRequiredCheck`

### F#-Specific Checks

- [ ] `FSharpProjectFileMissingCompileEntryCheck`
- [ ] `FSharpCompileEntryMissingOnDiskCheck`
- [ ] `FSharpCompileEntryOrderingSanityCheck`
- [ ] `FSharpProjectFileVsRootConfigDriftCheck`
- [ ] `FSharpTestProjectShapeCheck`

### C#-Specific Checks

- [ ] `CSharpNullablePolicyCheck`
- [ ] `CSharpImplicitUsingsPolicyCheck`

### Docs Checks

- [ ] make `docs check` understand docs-enabled `.NET` projects
- [ ] require `mkdocs.yml` and `docs/index.md` when docs are enabled
- [ ] add `.NET` docs hook checks similar to the Python flow
- [ ] extend snippet checking to `fsharp`, `fs`, `csharp`, and `cs`

### Fixer Policy

Safe auto-fixers should exist for setup-converge issues:

- rerun setup for managed generated file drift
- regenerate `.sln`
- regenerate `global.json`, `NuGet.config`, `Directory.Build.props`
- regenerate managed docs/workflow files

Do not auto-fix files that look manually edited unless integrity verification says the file is still generator-owned and unmodified.

## 7. Version Diagnostics

Extend `dev project versions <project>` for `.NET`.

- [ ] query local tags
- [ ] query remote tags
- [ ] show current version from config
- [ ] show unpushed commit count and working tree state
- [ ] query NuGet-visible versions
- [ ] show current/local-tag/remote-tag/nuget state in the same table

This should integrate with the same report model already used for Maven Central, JitPack, and PyPI.

## 8. Publish And Release Workflows

### Publish Targets

- [ ] support `publishTarget = "nuget"`
- [ ] add credential plumbing for NuGet API key
- [ ] add publish task support for `dotnet nuget push`

### Release Verify

Extend `dev release verify` for `.NET`:

- [ ] package verification
- [ ] docs/readme/license presence
- [ ] feed visibility preflight where relevant
- [ ] NuGet package metadata sanity
- [ ] optional SourceLink or symbols checks

### Release Bundle

Extend `dev release bundle` for `.NET`:

- [ ] include `.nupkg`
- [ ] include `.snupkg` if produced
- [ ] include zipped published outputs for non-package tools when relevant
- [ ] include repo aggregate zip and checksums

### GitHub Releases

Use the repo-level GitHub Release flow already being standardized:

- attach per-project packaged artifacts
- attach repo aggregate artifact
- attach checksums

## 9. Tooling Install And Doctor

- [ ] add `.NET` support to `dev doctor`
- [ ] check for required `dotnet` SDK matching `global.json`
- [ ] check restore connectivity to NuGet
- [ ] check presence of NuGet auth when publishing is enabled
- [ ] check formatter availability when formatting checks are enabled

Recommended managed install targets:

- `fantomas`
- `csharpier`
- optional `dotnet-format`

## 10. Testing Strategy

Add test coverage before broad migration.

- [ ] typed config loading tests
- [ ] config validation tests
- [ ] setup generation golden tests for `.fsproj`, `.csproj`, `.sln`, `global.json`, `NuGet.config`
- [ ] `build` tests
- [ ] `package verify` tests
- [ ] `project versions` tests for NuGet visibility
- [ ] `docs check` tests
- [ ] check/fixer tests

Dogfood targets:

- `fsharp-lang-mu`
- `fsharp-codec-nbt`
- `fsharp-vs-fileformats`
- `fsharp-mc-fileformats`
- `dotnet-diff`

## Migration Order

### Phase 0: Foundation

- [ ] add config model
- [ ] add project dataclasses
- [ ] add publish target and secret handling
- [ ] add templates and setup scaffolding

### Phase 1: F# Library Happy Path

- [ ] onboard `fsharp-lang-mu`
- [ ] onboard `fsharp-codec-nbt`
- [ ] generate managed repo files
- [ ] make `dev build`, `dev check`, `dev docs check`, `dev package verify`, and `dev project versions` work

### Phase 2: F# Cross-Repo Dependency Happy Path

- [ ] onboard `fsharp-mc-fileformats`
- [ ] replace cross-repo `ProjectReference` with managed dependency modeling
- [ ] validate local-feed story

### Phase 3: Additional F# Repos

- [ ] onboard `fsharp-vs-fileformats`
- [ ] onboard `dotnet-diff`

### Phase 4: C# SDK-Style Happy Path

- [ ] onboard one small SDK-style C# tool or library
- [ ] validate shared `DotnetProject` design

### Phase 5: Complex Existing C# Repos

- [ ] assess `cc-vs`-style repos separately
- [ ] model repo-local `Directory.Build.props` overrides and external DLL path conventions
- [ ] do not block the core SDK-style support on this

## Acceptance Criteria

The work is done when all of the following are true for at least the initial F# repos:

- `root.clj` fully defines the projects
- F# compile order is preserved from the checked-in `.fsproj` rather than duplicated in `root.clj`
- `dev setup <project>` generates stable `.NET` files
- rerunning setup is idempotent
- managed-file integrity works on generated `.NET` artifacts
- `dev build <project>` succeeds
- `dev check <project>` reports meaningful `.NET` drift and can fix safe issues
- `dev docs check <project>` understands the project
- `dev package verify <project>` passes
- `dev project versions <project>` shows NuGet state
- `dev release bundle <project>` emits usable release artifacts
- GitHub workflows exist for docs and release/publish when enabled

## Risks And Open Questions

### 1. F# Compile Order Is the Main Ownership Risk

Recommendation:

- keep compile order authoritative in the checked-in `.fsproj`
- make setup do a structured merge instead of whole-file replacement for F# project files
- use structural checks instead of pretending file order belongs in `root.clj`

### 2. Cross-Repo Local Development Needs One Canonical Story

Recommendation:

- same repo: `ProjectReference`
- cross repo: `PackageReference`
- local mode: workspace-local NuGet feed

### 3. `.sln` Stamping Needs Verification

Recommendation:

- try in-band `#` stamping first
- if Visual Studio or `dotnet` rejects it, add a generic sidecar integrity manifest

### 4. Docs API Generation Tooling Should Not Dictate the Whole Docs Story

Recommendation:

- ship written docs and package XML docs first
- add generated API pages later only if the toolchain is stable and worth the complexity

### 5. Complex C# Repos Should Not Define the First-Cut Abstractions

Recommendation:

- first implement the SDK-style library/tool/test happy path
- then add extension points for complex repo-local props and external DLL references

## Immediate Implementation Order

If this plan is executed next, the best order is:

1. Add the shared `DotnetProject` model plus `fsharp` and `csharp` config tags.
2. Add setup generation for `global.json`, `.sln`, `Directory.Build.props`, `NuGet.config`, and F# project files.
3. Onboard `fsharp-lang-mu` and `fsharp-codec-nbt`.
4. Add `dev build`, `dev package verify`, and `dev project versions` support for `.NET`.
5. Add docs generation and docs verification for `.NET`.
6. Add dotnet-specific drift checks and safe fixers.
7. Migrate `fsharp-mc-fileformats` to the local-feed package dependency model.
