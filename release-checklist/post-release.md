# Post-Release Verification Checklist

Use this immediately after a public release is published and before the release is announced broadly.

## 1. Registry Or Store Visibility

- [ ] The release appears in the destination's public index, catalog, store page, or search flow.
- [ ] The published version, metadata, and status match the intended release.
- [ ] The release notes shown publicly are the intended ones.

## 2. Fresh Consumer Verification

- [ ] A fresh external consumer can resolve, install, or download the released artifact through the real public path.
- [ ] If the release spans multiple destinations, the downstream destinations that depend on the upstream artifact still work.
- [ ] If exact version pinning matters, the pinned version resolves correctly.

## 3. Integrity Verification

- [ ] Checksums, signatures, or provenance data are present and verifiable where the destination supports them.
- [ ] The published artifact contents match what we intended to ship.
- [ ] The artifact version and metadata match the release tag and changelog.

## 4. Docs And Links

- [ ] README snippets, install instructions, and public docs all point at the newly released version where appropriate.
- [ ] Source repository links, homepage links, and package-page links are live and correct.
- [ ] Changelog, GitHub Release notes, and destination-specific release notes are consistent.

## 5. Rollout Decision

- [ ] We have a clear answer to "announce now" versus "pause and fix first".
- [ ] If something is wrong, we know whether the next step is yank, unlist, hotfix release, phased halt, or another destination-specific action.
