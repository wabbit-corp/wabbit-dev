# Maven Central Checklist

Use this together with the general checklist and the relevant language checklist.

## Sonatype Central Setup

- [ ] The publishing namespace is verified in the Sonatype Central Portal and is owned by the correct organization or maintainer.
- [ ] We have a working Central Portal publishing token for CI and for emergency manual release work.
- [ ] The intended `groupId` is final, publicly acceptable, and matches the verified namespace.
- [ ] The public source repository URL is final and stable.
- [ ] The signing subkey used for release is not expired.
- [ ] The signing key architecture is understood and documented well enough that we can rotate subkeys without chaos.
- [ ] A revocation certificate or equivalent key-recovery plan exists and is stored safely.
- [ ] The public signing key is published somewhere consumers can actually find it.

## Required Published Artifacts

- [ ] Every published non-`pom` artifact includes a `-sources.jar`.
- [ ] Every published non-`pom` artifact includes a `-javadoc.jar`.
- [ ] Every published file is signed with GPG or PGP and has a matching `.asc` signature.
- [ ] The publishing flow emits the required checksums for uploaded files.
- [ ] We are only publishing modules we actually want to support publicly.
- [ ] No internal-only helper module, sample app, scratch project, or test fixture is accidentally included in publication.

## Required POM Metadata

- [ ] Every publication has correct coordinates: `groupId`, `artifactId`, `version`, and packaging where needed.
- [ ] Every publication has a human-readable `name`.
- [ ] Every publication has a meaningful `description`.
- [ ] Every publication has a stable project `url`.
- [ ] Every publication declares at least one real distribution license.
- [ ] Every publication includes developer or maintainer metadata.
- [ ] Every publication includes SCM metadata: `connection`, `developerConnection`, and `url`.
- [ ] Published POMs do not contain private repository URLs, local filesystem paths, or other junk metadata.
- [ ] Published dependency metadata is correct and complete enough for consumers to resolve transitives cleanly.

## Verification

- [ ] We have manually inspected at least one generated POM and one generated module publication for correctness.
- [ ] The Central upload path works from CI, not just from one local machine.
- [ ] We verify that the release appears in Central search or the equivalent public index before announcing it.
- [ ] We verify that a fresh Maven or Gradle consumer can resolve the public coordinates after release.
- [ ] We verify that signature verification passes from the consumer side with the published public key.

## Rollback Semantics

- [ ] We understand that Maven Central components are immutable once published.
- [ ] We know that the normal recovery path is a follow-up release plus communication, not modification or deletion.
- [ ] We know what escalation path exists for the rare legal or policy exception cases.

## Official References

- Sonatype Central requirements: [central.sonatype.org/publish/requirements](https://central.sonatype.org/publish/requirements/)
- Sonatype Central Portal token setup: [central.sonatype.org/publish/generate-portal-token](https://central.sonatype.org/publish/generate-portal-token/)
- OSSRH sunset and Central Portal migration: [central.sonatype.org/pages/ossrh-eol](https://central.sonatype.org/pages/ossrh-eol/)
