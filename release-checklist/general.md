# General Release Checklist

Use this for every public release, regardless of ecosystem or destination.

## Minimum Bar

- [ ] The project is something we actually want to support publicly, not just an app, demo, experiment, or internal tool.
- [ ] The README is clear, accurate, and shows the right package, artifact, or plugin information for the release being cut.
- [ ] The README includes at least one example that was actually exercised during this release cycle.
- [ ] A clean standalone checkout works the way an external user would expect.
- [ ] IntelliJ or Rider can import the project without manual patching if the project is Gradle-based.
- [ ] Regenerating from the current `root.clj` does not break the project or remove required release metadata.
- [ ] Every destination-specific consumer validation passes without monorepo-only tricks such as local composite builds or `mavenLocal()`.
- [ ] The public API, package names, artifact names, and plugin IDs are names we are willing to support for a long time.
- [ ] The release does not expose local paths, private repos, internal hostnames, or monorepo terminology without explanation.
- [ ] We know who will maintain the project after release and what level of support we are implicitly promising.

## Scope And Ownership

- [ ] We have explicitly decided that this project belongs in a public package registry or app store.
- [ ] The intended audience for the project is clear.
- [ ] The project version is a real release version and not a placeholder or temporary value.
- [ ] If this is a coordinated multi-module release, all published modules share the intended version and cross-module dependency versions are self-consistent.
- [ ] If we publish a BOM, platform, or umbrella package, it accurately reflects the released module set and versions.
- [ ] We know who owns the release, who approves it, and who handles follow-up support.
- [ ] The public support path is clear enough for users: issue tracker, security contact, or maintainer contact.

## Documentation And Onboarding

- [ ] The README explains what the project is for in one or two clear paragraphs.
- [ ] The setup instructions match the actual release path users will take.
- [ ] The README contains at least one minimal, copy-pastable usage example that actually works.
- [ ] The README contains at least one practical example that reflects real usage rather than only toy snippets.
- [ ] README examples are exercised by tests or by an explicit release-time smoke test, not just copied prose.
- [ ] Code snippets in docs use the current package names, class names, function names, and artifact names.
- [ ] Version numbers shown in docs match the release we are about to publish.
- [ ] README links, badges, source links, and homepage links point at the real public repo and not a placeholder or monorepo-only path.
- [ ] Migration docs, upgrade notes, and caveats are still accurate after the latest generator and `root.clj` changes.
- [ ] If the library has sharp edges, limitations, or platform caveats, they are documented.
- [ ] We have an explicit changelog source of truth, such as `CHANGELOG.md`, GitHub Releases, or both, and it is applied consistently.
- [ ] The changelog or release notes state what changed in this release.
- [ ] Breaking changes are called out explicitly.
- [ ] Upgrade steps are documented if users need to change code or configuration.

## Public API And Code Quality

- [ ] The public API surface looks intentional and not like an accidental dump of internal types.
- [ ] Experimental APIs are marked clearly and documented as such.
- [ ] Deprecated APIs are intentional and have a migration path.
- [ ] Default behavior is safe and reasonable for first-time users.
- [ ] Public failure paths produce useful errors instead of raw internal crashes or vague exceptions.
- [ ] Logging, diagnostics, or warnings do not expose internal-only assumptions or confusing workspace-specific details.
- [ ] Release builds are warning-free, or every remaining warning is explicitly understood and accepted.
- [ ] A human has reviewed the public API surface for accidental leaks of internal types, odd names, or unstable-looking APIs.
- [ ] Mutable state, caches, registries, and lazy initialization have been reviewed for thread-safety and proper scoping.
- [ ] Public serialization, parsing, hashing, and code-generation behavior is deterministic for the same input.
- [ ] Libraries do not perform surprising network, filesystem, temp-dir, or environment-dependent behavior unless clearly documented.
- [ ] Published dependency graphs are minimal and justified, without accidental heavy, platform-wrong, or internal transitive dependencies.
- [ ] Published artifacts have been inspected for accidental junk such as test resources, build scripts, `.git` data, or unrelated monorepo files.
- [ ] Performance for common use cases has been smoke-tested enough to catch obvious pathological regressions.
- [ ] Core public paths do not ship with unresolved `TODO`, `FIXME`, `HACK`, or temporary-workaround markers unless consciously accepted.

## Build, Reproducibility, And Generator Hygiene

- [ ] A clean checkout builds successfully without relying on untracked files.
- [ ] A clean-room copy of the standalone repository works outside the monorepo root.
- [ ] Release tasks are deterministic enough that rerunning from a clean checkout produces the same output shape.
- [ ] If reproducibility is part of the support bar for this project, byte-for-byte reproducibility has been tested for the released artifacts.
- [ ] Dependency verification, lock files, or ecosystem-equivalent integrity checks are in place where the toolchain supports them.
- [ ] An SBOM is generated for the release artifact set.
- [ ] Right before release, regenerating from the current `root.clj` produces either no diff or only understood, intentional diff.
- [ ] The generated publication metadata comes from `root.clj` and not from handwritten one-off fixes unless there is a documented escape hatch.
- [ ] `root.clj` expresses the correct project type and release behavior for the project.
- [ ] Any special handling is modeled generically in the generator when it belongs to a whole class of projects.
- [ ] Generated metadata and docs do not leak monorepo-only paths or concepts.

## Consumer Validation

- [ ] Destination-specific overlays are the authoritative source for install, resolve, and consumer-flow validation.
- [ ] We have executed the relevant destination-specific consumer validation checklist for every destination in this release.
- [ ] We have at least one test that does not rely on workspace-local filesystem coupling.
- [ ] We have tested at least one realistic upgrade or mixed-version consumer scenario where that matters.

## Testing And Compatibility

- [ ] The test suite passes on a clean checkout.
- [ ] The tests meaningfully cover the main public usage paths, not just internal helpers.
- [ ] At least one integration-style test exercises the public entry point exactly the way an external user would.
- [ ] Known flaky tests are fixed, quarantined, or clearly excluded from the release decision.
- [ ] Generated code, codegen outputs, and checked-in generated files are up to date.
- [ ] The supported toolchain version floor is known and documented where relevant.
- [ ] Any ABI or source-compatibility promises are documented before release.
- [ ] If binary compatibility matters, we have checked for accidental API or ABI breakage.

## Legal And Public Metadata

- [ ] The repository has a top-level license file.
- [ ] We have the right to publish all bundled code, generated code, and assets.
- [ ] Third-party notices or attribution requirements are satisfied where applicable.
- [ ] No secret, token, private endpoint, internal hostname, or customer data is baked into sources, tests, docs, or published resources.

## Security And Supply Chain

- [ ] Dependency audit or ecosystem-equivalent vulnerability review has been run recently enough for this release.
- [ ] Dependency integrity protections such as verification metadata or lock files are in place where the toolchain supports them.
- [ ] If we claim provenance or build attestation, the attestation is actually produced and verifiable.
- [ ] If commit or tag signing is part of the repo's trust story, the release commit and tag follow that policy.

## Release Operations

- [ ] CI can build and publish the release without local machine assumptions.
- [ ] Release secrets are present, scoped correctly, and documented.
- [ ] The release workflow has an explicit version or tag source of truth.
- [ ] The release workflow fails fast on missing metadata or other required release artifacts.
- [ ] We have an explicit post-release verification procedure and know who performs it.
- [ ] We know how to prove that the published artifact can actually be resolved and used by a fresh external consumer after release.
- [ ] If the destination supports signatures, we know how to verify them from the consumer side after release.
- [ ] We know who is responsible for follow-up patches and post-release support.
- [ ] For immutable registries, rollback means a follow-up release and public guidance, not deletion; that plan is explicit.

## Final Go/No-Go

- [ ] The first release version is one we are comfortable leaving in public registries permanently.
- [ ] We have manually inspected at least one generated metadata file or package manifest for correctness.
- [ ] We are comfortable that an external user, with no access to this monorepo, can consume the published result successfully.
