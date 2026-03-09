# Plan

## Goal
- [ ] Publish all public Gradle/Kotlin repos to Maven Central through GitHub Actions using the Central Publisher Portal, not OSSRH.
- [ ] Keep `setup`/config generation authoritative so publishing and docs workflows come from `root.clj` plus private config, not hand-edited repo files.
- [ ] Generate documentation workflows for public repos:
  - [ ] Kotlin/Gradle repos: Dokka-based GitHub Pages publishing.
  - [ ] Python repos: MkDocs-based GitHub Pages publishing, aligned with `python-lang-mu`.
- [ ] Add workflow-testing coverage so generated GitHub Actions are validated before rollout.

## Constraints
- [ ] Keep tracked repo state release-ready.
- [ ] Use Sonatype Central Portal flow only. OSSRH is sunset as of June 30, 2025.
- [ ] Do not hardcode secrets or repo-specific credentials in tracked files.
- [ ] Public-repo docs and publishing should be generated from config and template defaults.
- [ ] Private repos or quarantined repos must not get public publishing/docs workflows.
- [ ] Preserve current local development UX; this task is about release/docs automation, not changing local dependency behavior again.

## Current Facts To Design Around
- [ ] Central Portal now requires publisher namespaces/tokens through the new portal, not OSSRH.
- [ ] There is still no official Gradle plugin for Central Portal publishing; Sonatype documents either the Portal OSSRH compatibility API or third-party Gradle integrations.
- [ ] Central requires signed artifacts plus sources/javadoc jars and complete POM metadata.
- [ ] Python already has a usable docs pattern in `python-lang-mu` with `docs-quality.yml` and `docs-deploy.yml`.
- [ ] Gradle templates already generate Dokka config and source links; publishing/docs should build on that instead of reintroducing per-repo hand edits.

## Design Decisions To Implement
- [ ] Add first-class publishing metadata to config for public Gradle repos:
  - [ ] `:publish "maven-central"` or equivalent explicit mode.
  - [ ] portal namespace / group ownership should derive from existing group/repo metadata where possible.
  - [ ] signing and token secret names should be configurable but convention-driven.
- [ ] Add first-class docs metadata to config:
  - [ ] docs enabled/disabled
  - [ ] docs system (`dokka` for Gradle, `mkdocs` for Python)
  - [ ] site URL / Pages path defaults
- [ ] Split generated workflow logic by concern:
  - [ ] release publish workflow
  - [ ] docs quality workflow
  - [ ] docs deploy workflow
  - [ ] workflow-validation tests in `app-wabbit-dev`
- [ ] For Gradle publishing, standardize on one supported path across public repos.
  - [ ] Prefer a single generator-backed integration path rather than repo-by-repo custom plugins.
  - [ ] Decide whether to target Central Portal via the OSSRH compatibility endpoint or a vetted community Gradle plugin.
  - [ ] Bake that choice into templates and tests.
- [ ] For Kotlin docs, publish Dokka HTML to GitHub Pages.
- [ ] For Python docs, keep the `python-lang-mu` MkDocs pattern and generate it from setup.

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
- [ ] Add typed/runtime config for Maven Central publishing.
- [ ] Add private-config support for Central Portal credentials and signing secrets.
- [ ] Add validation rules:
  - [ ] public/publishable Gradle repos must have license, SCM URL, developer/org metadata, and description
  - [ ] public/publishable Gradle repos must generate sources + javadoc/dokka jars
  - [ ] group/namespace must be consistent with verified namespace ownership
- [ ] Add config-driven opt-in for snapshot publishing only if we actually want it.

### 3. Gradle Publishing Generation
- [ ] Generate `maven-publish` + signing configuration for publishable Gradle repos.
- [ ] Generate Central Portal-compatible repository/publish configuration from one shared template path.
- [ ] Ensure KMP projects publish all expected variants sanely.
- [ ] Ensure JVM-only projects still publish correctly.
- [ ] Ensure generated POM metadata is complete for Central requirements.
- [ ] Ensure generated sources/javadoc artifacts satisfy Central requirements.
- [ ] Ensure secrets are read only from environment variables injected by GitHub Actions.

### 4. GitHub Actions For Gradle Releases
- [ ] Add a reusable/patterned workflow for release publishing on tags.
- [ ] Add manual-dispatch support for dry-run/testing before first release.
- [ ] Add pre-publish verification steps:
  - [ ] `./gradlew build`
  - [ ] publication artifact checks
  - [ ] signing sanity checks
  - [ ] publish dry run where supported
- [ ] Make workflow output clear failure diagnostics for missing secrets/metadata.

### 5. GitHub Docs Generation
- [ ] Kotlin repos:
  - [ ] generate docs-quality workflow (`dokkaHtml`, link checks if applicable, changelog/docs guards if we want them)
  - [ ] generate docs-deploy workflow to GitHub Pages
  - [ ] standardize Pages URL pattern in README/docs metadata
- [ ] Python repos:
  - [ ] reuse the `python-lang-mu` MkDocs model through templates
  - [ ] ensure `mkdocs build --strict` runs in CI
  - [ ] ensure API docs generation/check hooks are generated where relevant
- [ ] Add setup generation rules so existing custom docs files are preserved when appropriate.

### 6. GitHub Action Testing
- [ ] Add template-level tests in `app-wabbit-dev` to validate generated workflow YAML structure.
- [ ] Add smoke tests for representative repos:
  - [ ] one JVM-only Kotlin repo
  - [ ] one KMP Kotlin repo
  - [ ] one Python repo using MkDocs
- [ ] Optionally add local `act` compatibility checks if practical, but do not make rollout depend on `act` fidelity.
- [ ] Validate that generated workflows do not reference missing secrets/steps for private repos.

### 7. Rollout Sequence
- [ ] Start with one small public JVM repo.
- [ ] Then one public KMP repo.
- [ ] Then roll out docs workflows broadly.
- [ ] Only after successful smoke releases, fan out to the rest of the public repos.
- [ ] Keep commits small and grouped by generator/template/runtime-model changes vs generated repo changes.

## User Actions Required

### Sonatype Central Portal
- [ ] Log in to the Central Publisher Portal: https://central.sonatype.com/publishing
- [ ] Check whether the publishing namespace for Wabbit is already present.
  - [ ] If `one.wabbit` is already available there, note that we can reuse it.
  - [ ] If it is missing, verify the namespace using the Central Portal namespace flow: https://central.sonatype.org/register/namespace/
  - [ ] If the namespace was previously managed in OSSRH and is still missing in Portal, contact Central Support per Sonatype guidance: https://central.sonatype.org/pages/ossrh-eol/
- [ ] Generate a Central Portal user token and store the issued username/password pair securely: https://central.sonatype.org/publish/generate-portal-token/
- [ ] Decide whether we want release-only publishing first, or release + snapshot publishing.

### Signing Material
- [ ] Create or designate a dedicated release GPG key for Wabbit releases.
- [ ] Export the ASCII-armored private key for GitHub Actions use.
- [ ] Record the key fingerprint / key ID.
- [ ] Record the passphrase.
- [ ] Keep the revocation certificate offline.

### GitHub Secrets / Org Settings
- [ ] Add organization or repository secrets for:
  - [ ] Central Portal username
  - [ ] Central Portal password/token
  - [ ] GPG private key
  - [ ] GPG passphrase
  - [ ] optional signing key ID if the Gradle path needs it explicitly
- [ ] Decide whether secrets will live at org scope or per-repo scope.
- [ ] Confirm GitHub Actions are enabled for all target public repos.

### GitHub Pages / Docs
- [ ] Decide the canonical docs URL pattern, likely `https://wabbit-corp.github.io/<repo-name>/`.
- [ ] Enable GitHub Pages for the repos that should publish docs.
- [ ] Decide whether we want Pages deployed from a `gh-pages` branch or from GitHub Actions artifacts/workflows.

## Acceptance Criteria
- [ ] A generated public JVM repo can publish a signed release to Maven Central from GitHub Actions.
- [ ] A generated public KMP repo can publish a signed release to Maven Central from GitHub Actions.
- [ ] Generated GitHub workflows are covered by tests in `app-wabbit-dev`.
- [ ] Public Python repos can generate and deploy docs in the same style as `python-lang-mu`.
- [ ] Public Kotlin repos can generate and deploy Dokka docs to GitHub Pages.
- [ ] Private/unpublished repos do not receive public publishing workflows.
- [ ] The required user-managed secrets and external setup steps are documented precisely enough that rollout does not depend on memory.

## References
- [ ] Sonatype Central requirements: https://central.sonatype.org/publish/requirements/
- [ ] Central Portal token generation: https://central.sonatype.org/publish/generate-portal-token/
- [ ] Namespace registration/verification: https://central.sonatype.org/register/namespace/
- [ ] OSSRH sunset / Portal migration: https://central.sonatype.org/pages/ossrh-eol/
- [ ] Gradle publishing guidance: https://central.sonatype.org/publish/publish-portal-gradle/
- [ ] `python-lang-mu` reference workflows:
  - [ ] `/Users/wabbit/ws/datatron/python-lang-mu/.github/workflows/docs-quality.yml`
  - [ ] `/Users/wabbit/ws/datatron/python-lang-mu/.github/workflows/docs-deploy.yml`
