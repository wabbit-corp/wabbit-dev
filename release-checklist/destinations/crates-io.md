# crates.io Checklist

Use this together with the general checklist and [`languages/rust.md`](../languages/rust.md).

## Registry Metadata

- [ ] `cargo package` and `cargo publish --dry-run` succeed from a clean checkout.
- [ ] crates.io metadata such as description, keywords, categories, license, and readme are correct.
- [ ] The crate name is available and the one we actually want permanently.
- [ ] Repository and documentation links point at the real public locations.

## Package Contents

- [ ] The packaged crate contains only the intended source, docs, build scripts, and assets.
- [ ] No tests, local fixtures, large generated blobs, or unrelated repo files are accidentally included.
- [ ] Checksums or other downstream integrity expectations are documented if consumers rely on release assets elsewhere.

## Consumer Validation

- [ ] A fresh external Rust project can depend on the published crate and build successfully.
- [ ] If the crate exposes feature flags, at least the default feature set and the documented important combinations are validated.
- [ ] If the crate is also shipped as a binary elsewhere, the docs make the distinction between library and binary paths clear.

## Release Verification

- [ ] We verify that the crate appears on crates.io with the correct metadata after release.
- [ ] We verify that a fresh `cargo add` or equivalent consumer flow can resolve the released version.

## Rollback Semantics

- [ ] We understand that `cargo yank` removes a version from new resolution without deleting the crate contents.
- [ ] We know when to publish a semver-compatible hotfix before yanking a bad version.
- [ ] We know how to undo a yank if that becomes necessary.
