# Rust Release Checklist

Use this for Rust libraries, CLIs, or tools intended for public release.

## Cargo And Package Identity

- [ ] `Cargo.toml` metadata is complete and suitable for public release.
- [ ] The crate name is final, intentional, and the one we want to support publicly.
- [ ] The package version is correct and matches the release tag and changelog.
- [ ] License metadata is correct and matches the actual license files.
- [ ] Repository, homepage, documentation, and readme metadata point at the real public URLs.

## Toolchain And Compatibility

- [ ] The MSRV policy is explicit and documented.
- [ ] The release has been tested on the claimed stable Rust toolchain range.
- [ ] If nightly features are used anywhere, that support story is explicit and intentional.

## Feature Flags And API Surface

- [ ] Feature flags are intentional, documented, and tested in meaningful combinations.
- [ ] Default features are safe and represent what we actually want most users to get.
- [ ] Public APIs exposed behind feature flags are documented clearly enough for consumers.
- [ ] `#[doc(cfg(...))]`, docs, and feature-gated examples match the actual feature graph.

## Package Contents And Docs

- [ ] `cargo package --list` looks intentional and does not include junk.
- [ ] Docs build successfully for the intended public surface.
- [ ] README examples compile or are otherwise exercised.
- [ ] Build scripts and proc macros do not rely on local paths or repo-only assumptions.
