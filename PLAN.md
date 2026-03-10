# Library Deployment Plan

## Goal
- [ ] Continue rolling out public Kotlin libraries to Maven Central and GitHub Pages one repo at a time.
- [ ] Write real user-facing documentation for each newly deployed library.
- [ ] Keep generated files generator-owned: README/docs content may be handwritten, but `build.gradle.kts` and workflows must come from `setup`.
- [ ] Respect dependency order when a useful library depends on unpublished Wabbit artifacts.
- [ ] Prefer libraries that already look publishable: useful functionality, sane API surface, active tests, and little or no commented-out dead code / TODO / FIXME debt.

## Repeatable Checklist For Each Library
- [ ] Review the public API and tests to understand the actual use cases.
- [ ] Write or refresh `README.md` with:
  - intro
  - installation from Maven Central
  - realistic usage examples
  - edge cases / error handling
  - link to published API docs
- [ ] Add `docs/dokka-module.md` when the repo should have a richer Dokka landing page than raw symbol docs.
- [ ] Run scoped `setup <name>` so generated Gradle/workflow files match template output.
- [ ] Run local validation:
  - JVM repo: `./gradlew test dokkaGeneratePublicationHtml --no-daemon`
  - KMP repo: `ANDROID_HOME=... ./gradlew jvmTest dokkaGeneratePublicationHtml --no-daemon`
- [ ] Commit and push docs + generated config/workflow changes.
- [ ] Verify GitHub Actions:
  - Docs Quality
  - Docs Deploy
  - Snapshot Publish
- [ ] Verify live Pages content.
- [ ] Do one tagged release verification when the repo is ready:
  - push annotated tag `vX.Y.Z`
  - confirm Central publish workflow succeeds
  - confirm artifact resolves from `repo.maven.apache.org`

## Completed
- [x] `kotlin-base58`: docs written, generated Dokka config aligned, GitHub Pages live, tagged Maven Central release verified.
- [x] `kotlin-envformat`: docs written, generated Dokka config aligned, GitHub Pages live, docs/snapshot workflows verified.

## In Progress
- [ ] `kotlin-java-escape`: docs and automation are live; fix final code-quality/runtime issues, then do tagged Maven Central release verification.

## Queue Selection Rules
- [ ] Finish the current repo fully before starting the next one.
- [ ] Favor standalone libraries with low dependency fan-out before higher-level libraries.
- [ ] Skip repos with obvious unfinished code, large TODO/FIXME debt, or unstable public APIs until the cleaner utility layer is published.

## Dependency Notes
- [ ] `kotlin-dotenv-parser` is blocked on unpublished Wabbit dependencies: `kotlin-parsing-charset`, `kotlin-parsing-charinput`, and `kotlin-exec`.
- [ ] `kotlin-shlex` is blocked on unpublished `kotlin-parsing-charinput`.
- [ ] Deploy low-level libraries before the libraries that consume them.

## Priority 1: Clean Core Utility Libraries
- [ ] `kotlin-java-escape`
- [ ] `kotlin-throwable-policy`
- [ ] `kotlin-termcolor`
- [ ] `kotlin-fnmatch`
- [ ] `kotlin-filetypes`
- [ ] `kotlin-parsing-charset`
- [ ] `kotlin-parsing-charinput`
- [ ] `kotlin-exec`
- [ ] `kotlin-dotenv-parser`
- [ ] `kotlin-dotenv`
- [ ] `kotlin-shlex`

## Priority 2: Parsing And Text Infrastructure
- [ ] `kotlin-parsing-parsers`
- [ ] `kotlin-textwrap`
- [ ] `kotlin-junidecode`
- [ ] `kotlin-levenshtein`
- [ ] `kotlin-base91`

## Priority 3: Data / Serialization / Reflection Utilities
- [ ] `kotlin-extra-serializers`
- [ ] `kotlin-data`
- [ ] `kotlin-data-ref`
- [ ] `kotlin-data-need`
- [ ] `kotlin-extra-io`
- [ ] `kotlin-extra-reflection`
- [ ] `kotlin-exception-serialization`
- [ ] `kotlin-pprint`
- [ ] `kotlin-doc`

## Priority 4: Specialized Libraries To Triage Later
- [ ] `kotlin-inetaddr`
- [ ] `kotlin-network-context`
- [ ] `kotlin-roman-numerals`
- [ ] `kotlin-ref-walker`
- [ ] `kotlin-openai-schemas`
- [ ] `kotlin-clipboard`
- [ ] `kotlin-notation`
- [ ] `kotlin-logic`
- [ ] `kotlin-lang-json`
- [ ] `kotlin-lang-xml`
- [ ] `kotlin-lang-xmlpath`
- [ ] `kotlin-lang-bibtex`
- [ ] `kotlin-lang-md`
- [ ] `kotlin-lang-jinjer`
- [ ] `kotlin-lang-calc`
- [ ] `kotlin-lang-mu`
- [ ] `kotlin-lang-rho`
- [ ] `kotlin-lang-alpha`
- [ ] `kotlin-lang-kappa`

## Explicitly Not In This Wave
- [ ] Applications (`app-*`) are not part of this library rollout.
- [ ] IntelliJ plugins (`ij-*`) stay on the JetBrains Marketplace path.
- [ ] Jeeves monorepo modules are handled separately.
- [ ] Web-client repos (`kotlin-web-*`) will be triaged after the core utility libraries.

## Immediate Next Step
- [ ] Finish `kotlin-java-escape`, then reassess the next clean standalone utility library before moving on.
