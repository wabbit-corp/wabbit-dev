# Pre-Release And RC Policy

Use this when shipping `alpha`, `beta`, `rc`, preview, or otherwise non-final releases.

## Rules

- [ ] We have explicitly decided that this is a pre-release and labeled it consistently in version numbers, tags, and release notes.
- [ ] The release notes clearly state what is unstable, provisional, or still expected to change.
- [ ] Hard gates from [`general.md`](general.md) still apply unless this file explicitly says otherwise.
- [ ] We do not use a pre-release label as an excuse to skip correctness, packaging, or consumer validation.

## What May Be Softer Than Final Release

- [ ] Docs may be incomplete only where the incompleteness is clearly called out.
- [ ] Performance work may still be ongoing, but no known pathological regressions remain.
- [ ] Public API may still be marked experimental, but the experimental status is explicit.
- [ ] Changelog and release notes explicitly tell users that upgrade breakage is more likely than in a stable release.

## What Still Must Hold

- [ ] The package, artifact, or app must install and run through the real public path users are expected to take.
- [ ] Signing, metadata correctness, and destination-specific publication requirements still hold.
- [ ] No secrets, internal URLs, local paths, or monorepo-only assumptions leak into the released artifacts.
- [ ] A rollback or hotfix plan exists, because immutable public pre-releases are still public releases.
