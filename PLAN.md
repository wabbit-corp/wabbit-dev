# Plan

## Goal
- [ ] Publish all public Gradle/Kotlin repos to Maven Central through GitHub Actions using the Central Publisher Portal, not OSSRH.
- [x] Keep `setup`/config generation authoritative so publishing and docs workflows come from `root.clj` plus private config, not hand-edited repo files.
- [ ] Generate documentation workflows for public repos:
  - [x] Kotlin/Gradle repos: Dokka-based GitHub Pages publishing.
  - [x] Python repos: MkDocs-based GitHub Pages publishing, aligned with `python-lang-mu`.
- [x] Add workflow-testing coverage so generated GitHub Actions are validated before rollout.

## Constraints
- [x] Keep tracked repo state release-ready.
- [x] Use Sonatype Central Portal flow only. OSSRH is sunset as of June 30, 2025.
- [x] Do not hardcode secrets or repo-specific credentials in tracked files.
- [x] Public-repo docs and publishing should be generated from config and template defaults.
- [x] Private repos or quarantined repos must not get public publishing/docs workflows.
- [x] Preserve current local development UX; this task is about release/docs automation, not changing local dependency behavior again.
- [x] Release publishing must happen only from pushed annotated semver tags.
- [x] Snapshot publishing must happen only from branch/manual workflows, never from tags.

## Current Facts To Design Around
- [x] Central Portal now requires publisher namespaces/tokens through the new portal, not OSSRH.
- [x] There is still no official Gradle plugin for Central Portal publishing; Sonatype documents either the Portal OSSRH compatibility API or third-party Gradle integrations.
- [x] Central requires signed artifacts plus sources/javadoc jars and complete POM metadata.
- [x] Python already has a usable docs pattern in `python-lang-mu` with `docs-quality.yml` and `docs-deploy.yml`.
- [x] Gradle templates already generate Dokka config and source links; publishing/docs should build on that instead of reintroducing per-repo hand edits.

## Remaining Design Work
- [ ] Add first-class publishing metadata to config for public Gradle repos:
  - [ ] portal namespace / group ownership should derive from existing group/repo metadata where possible.
- [ ] Enforce version/source invariants in generated publish workflows:
  - [x] tag builds require a non-`-SNAPSHOT` version matching the tag
  - [x] snapshot builds require a `-SNAPSHOT` version
  - [x] snapshot workflows do not run on tag pushes
  - [x] repo-root release workflows are skipped when publishable nested modules do not share one version
  - [ ] decide whether monorepos should converge on one release version or support per-module release workflows

## Implementation Checklist

### 1. Inventory and Classification
- [ ] Enumerate all public repos from `root.clj`.
- [ ] Partition them into:
  - [ ] Gradle/Kotlin publish-to-Central candidates
  - [ ] Python docs-only candidates
  - [ ] IntelliJ plugins / JetBrains Marketplace-only candidates
  - [ ] repos that should stay unpublished or private
- [ ] Record which repos already have usable sources/javadoc/signing metadata and which do not.

### 2. Sonatype/Central Model in Config
- [x] Add typed/runtime config for Maven Central publishing.
- [x] Add private-config support for Central Portal credentials and signing secrets.
- [ ] Add validation rules:
  - [ ] public/publishable Gradle repos must have license, SCM URL, developer/org metadata, and description
  - [ ] public/publishable Gradle repos must generate sources + javadoc/dokka jars
  - [ ] group/namespace must be consistent with verified namespace ownership
- [x] Add config-driven opt-in for snapshot publishing only if we actually want it.

### 3. Gradle Publishing Generation
- [x] Generate `maven-publish` + signing configuration for publishable Gradle repos.
- [x] Generate Central Portal-compatible repository/publish configuration from one shared template path.
- [x] Ensure KMP projects publish all expected variants sanely.
- [x] Ensure JVM-only projects still publish correctly.
- [x] Ensure generated POM metadata is complete for Central requirements.
- [x] Ensure generated sources/javadoc artifacts satisfy Central requirements.
- [x] Ensure secrets are read only from environment variables injected by GitHub Actions.

### 3.5. CLI Publish Parity
- [x] Support `dev publish` for repo-managed Gradle projects, not just standalone repos.
- [x] Make repo-managed Maven Central CLI publish regenerate repo-root Gradle files/workflows before invoking Gradle.
- [x] Scope repo-managed Maven Central CLI publish to the selected nested module with explicit Gradle task selectors.
- [x] Cover standalone vs repo-managed Maven Central CLI publish command generation in tests.

### 4. GitHub Actions For Gradle Releases
- [x] Add a reusable/patterned workflow for release publishing on tags.
- [x] Restrict release workflow triggers to pushed annotated semver tags such as `v1.2.3`.
- [x] Add manual-dispatch support for dry-run/testing before first release.
- [ ] Add pre-publish verification steps:
  - [x] `./gradlew build`
  - [ ] publication artifact checks
  - [ ] signing sanity checks
  - [ ] publish dry run where supported
- [ ] Make workflow output clear failure diagnostics for missing secrets/metadata.
- [x] Add a separate snapshot workflow:
  - [x] trigger from the default branch and manual dispatch
  - [x] publish only `-SNAPSHOT` versions
  - [x] fail if invoked from a tag or if the version is not a snapshot

### 5. GitHub Docs Generation
- [ ] Kotlin repos:
  - [x] generate docs-quality workflow (`dokkaHtml`, link checks if applicable, changelog/docs guards if we want them)
  - [x] generate docs-deploy workflow to GitHub Pages
  - [x] standardize Pages URL pattern in README/docs metadata
- [ ] Python repos:
  - [x] reuse the `python-lang-mu` MkDocs model through templates
  - [x] ensure `mkdocs build --strict` runs in CI
  - [x] ensure API docs generation/check hooks are generated where relevant
- [x] Add setup generation rules so existing custom docs files are preserved when appropriate.

### 6. GitHub Action Testing
- [x] Add template-level tests in `app-wabbit-dev` to validate generated workflow YAML structure.
- [x] Add smoke tests for representative repos:
  - [x] one JVM-only Kotlin repo
  - [x] one KMP Kotlin repo
  - [x] one Python repo using MkDocs
- [ ] Optionally add local `act` compatibility checks if practical, but do not make rollout depend on `act` fidelity.
- [ ] Validate that generated workflows do not reference missing secrets/steps for private repos.

### 7. Rollout Sequence
- [ ] Start with one small public JVM repo.
- [ ] Commit/push the generator/template changes needed for the rollout.
- [ ] Commit/push the first public JVM repo rollout after scoped regen and local verification.
- [ ] Then one public KMP repo.
- [ ] Then roll out docs workflows broadly.
- [ ] Only after successful smoke releases, fan out to the rest of the public repos.
- [ ] Keep commits small and grouped by generator/template/runtime-model changes vs generated repo changes.

## User Actions Required

### Sonatype Central Portal
- [x] Log in to the Central Publisher Portal: https://central.sonatype.com/publishing
- [x] Check whether the publishing namespace for Wabbit is already present.
  - [x] If `one.wabbit` is already available there, note that we can reuse it.
  - [x] If it is missing, verify the namespace using the Central Portal namespace flow: https://central.sonatype.org/register/namespace/
  - [x] If the namespace was previously managed in OSSRH and is still missing in Portal, contact Central Support per Sonatype guidance: https://central.sonatype.org/pages/ossrh-eol/
- [x] Generate a Central Portal user token and store the issued username/password pair securely: https://central.sonatype.org/publish/generate-portal-token/
      USER: it's in ../.maven-token.xml
- [x] Decide whether we want release-only publishing first, or release + snapshot publishing: release + snapshot publishing

### Signing Material
- [x] Create or designate a dedicated release GPG key for Wabbit releases.
- [x] Export the ASCII-armored private key for GitHub Actions use.
- [x] Record the key fingerprint / key ID: 2B8FF27A5452C366CF92B1BE46F7512F6BDF8F7C
- [x] Record the passphrase.
- [ ] Keep the revocation certificate offline.

### GitHub Secrets / Org Settings
- [ ] Add organization or repository secrets for:
  - [x] Central Portal username MAVEN_USERNAME
  - [x] Central Portal password/token MAVEN_PASSWORD
  - [x] GPG private key MAVEN_GPG_PRIVATE_KEY
  - [x] GPG passphrase MAVEN_GPG_PASSPHRASE
  - [ ] optional signing key ID if the Gradle path needs it explicitly
- [x] Decide whether secrets will live at org scope or per-repo scope: org scope
- [x] Confirm GitHub Actions are enabled for all target public repos.

### GitHub Pages / Docs
- [x] Decide the canonical docs URL pattern, likely `https://wabbit-corp.github.io/<repo-name>/`.
- [x] Enable GitHub Pages for the repos that should publish docs.
- [x] Decide whether we want Pages deployed from a `gh-pages` branch or from GitHub Actions artifacts/workflows.

## Acceptance Criteria
- [ ] A generated public JVM repo can publish a signed release to Maven Central from GitHub Actions.
- [ ] A generated public KMP repo can publish a signed release to Maven Central from GitHub Actions.
- [ ] Generated release workflows publish only from semver tags and fail on version/tag mismatches.
- [ ] Generated snapshot workflows publish only snapshot versions from branch/manual runs.
- [ ] Generated GitHub workflows are covered by tests in `app-wabbit-dev`.
- [ ] Public Python repos can generate and deploy docs in the same style as `python-lang-mu`.
- [ ] Public Kotlin repos can generate and deploy Dokka docs to GitHub Pages.
- [ ] Private/unpublished repos do not receive public publishing workflows.
- [ ] The required user-managed secrets and external setup steps are documented precisely enough that rollout does not depend on memory.

## Immediate Next Step
- [x] Finish repo-managed Maven Central CLI publish support.
- [ ] Roll out the generated GitHub Actions changes to one small public JVM repo (`kotlin-base58`) and push that repo.

## References
- [ ] Sonatype Central requirements: https://central.sonatype.org/publish/requirements/
- [ ] Central Portal token generation: https://central.sonatype.org/publish/generate-portal-token/
- [ ] Namespace registration/verification: https://central.sonatype.org/register/namespace/
- [ ] OSSRH sunset / Portal migration: https://central.sonatype.org/pages/ossrh-eol/
- [ ] Gradle publishing guidance: https://central.sonatype.org/publish/publish-portal-gradle/
- [ ] `python-lang-mu` reference workflows:
  - [ ] `/Users/wabbit/ws/datatron/python-lang-mu/.github/workflows/docs-quality.yml`
  - [ ] `/Users/wabbit/ws/datatron/python-lang-mu/.github/workflows/docs-deploy.yml`
