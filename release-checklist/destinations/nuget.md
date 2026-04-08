# NuGet Checklist

Use this together with the general checklist and the relevant .NET language checklist.

## Package Metadata

- [ ] Package ID, version, summary, license, repository URL, and tags are correct.
- [ ] Package README and icon are present if we want them surfaced in NuGet clients.
- [ ] The package metadata matches the exact public release we are cutting.

## Artifacts

- [ ] `dotnet pack` produces the intended package contents.
- [ ] If we ship symbols or source-link support, those artifacts are present and correct.
- [ ] The package does not accidentally include local-only files, tests, or internal build outputs.

## Consumer Validation

- [ ] A fresh consumer project can add the package and build successfully.
- [ ] Target framework resolution behaves the way we expect.
- [ ] The package works without local feeds or repo-specific assumptions.

## Release Operations

- [ ] NuGet ownership, publishing credentials, and any package ID reservation expectations are set up correctly.

## Rollback Semantics

- [ ] We understand that nuget.org does not support permanent deletion for normal package mistakes.
- [ ] We know when to unlist a bad package version and when to deprecate it with guidance to a replacement.
- [ ] We know how to communicate exact-version restore behavior to users if an unlisted package is already in the wild.
