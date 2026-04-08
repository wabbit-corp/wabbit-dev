# Release Checklist

This directory is the release gate for public distribution.

Do not use a single checklist in isolation. For a real release, combine:

1. [`general.md`](general.md)
2. one language or ecosystem checklist from [`languages/`](languages/)
3. one or more destination checklists from [`destinations/`](destinations/)

## How To Use It

- Start with the general checklist.
- Add the language or ecosystem checklist that matches the project.
- Add every destination checklist for where the release will actually go.
- If a project spans multiple ecosystems or destinations, use all relevant overlays.
- If a project still needs repo-specific quirks to release, prefer modeling them in `root.clj` or the generator before shipping.
- Use [`pre-release.md`](pre-release.md) for alpha, beta, or RC releases.
- Use [`rollback.md`](rollback.md) whenever the destination is effectively immutable.
- Use [`post-release.md`](post-release.md) immediately after publishing, before announcing the release.

## Recommended Combinations

- Kotlin or KMP library to Maven Central:
  - [`general.md`](general.md)
  - [`languages/kotlin.md`](languages/kotlin.md)
  - [`destinations/maven-central.md`](destinations/maven-central.md)

- Rust crate to crates.io:
  - [`general.md`](general.md)
  - [`languages/rust.md`](languages/rust.md)
  - [`destinations/crates-io.md`](destinations/crates-io.md)

- Kotlin Gradle plugin to Plugin Portal:
  - [`general.md`](general.md)
  - [`languages/kotlin.md`](languages/kotlin.md)
  - [`destinations/gradle-plugin-portal.md`](destinations/gradle-plugin-portal.md)

- Binary or CLI release staged through GitHub Releases:
  - [`general.md`](general.md)
  - the relevant language checklist
  - [`destinations/github-releases.md`](destinations/github-releases.md)

- Python package to PyPI:
  - [`general.md`](general.md)
  - [`languages/python.md`](languages/python.md)
  - [`destinations/pypi.md`](destinations/pypi.md)

- .NET package to NuGet:
  - [`general.md`](general.md)
  - [`languages/dotnet.md`](languages/dotnet.md)
  - [`destinations/nuget.md`](destinations/nuget.md)

- F# package to NuGet:
  - [`general.md`](general.md)
  - [`languages/fsharp.md`](languages/fsharp.md)
  - [`destinations/nuget.md`](destinations/nuget.md)

- PureScript package to Pursuit:
  - [`general.md`](general.md)
  - [`languages/purescript.md`](languages/purescript.md)
  - [`destinations/pursuit.md`](destinations/pursuit.md)

- Scala library to Maven Central:
  - [`general.md`](general.md)
  - [`languages/scala.md`](languages/scala.md)
  - [`destinations/maven-central.md`](destinations/maven-central.md)

- CLI app for Homebrew and Chocolatey:
  - [`general.md`](general.md)
  - the relevant language checklist
  - [`destinations/github-releases.md`](destinations/github-releases.md)
  - [`destinations/homebrew.md`](destinations/homebrew.md)
  - [`destinations/chocolatey.md`](destinations/chocolatey.md)

- Mobile app release:
  - [`general.md`](general.md)
  - the relevant language checklist
  - [`destinations/google-play.md`](destinations/google-play.md)
  - [`destinations/apple-app-store.md`](destinations/apple-app-store.md)
