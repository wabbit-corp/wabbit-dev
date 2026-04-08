# Scala Release Checklist

Use this for Scala libraries intended for public JVM release.

## Scala Versioning

- [ ] Supported Scala versions are intentional and tested.
- [ ] Cross-built artifact naming is correct and stable.
- [ ] The supported JDK floor is known and documented.
- [ ] The Scala 2 and Scala 3 support story is explicit, including whether the project supports both or only one line.

## Build And Publish Flow

- [ ] The actual release toolchain, whether sbt, Gradle, Mill, or another tool, can build and publish from a clean checkout.
- [ ] If the project is cross-built, the full cross-build matrix succeeds in the publish-like path, not just one Scala line.
- [ ] The published metadata and artifact suffixes for each Scala line match what consumers expect.

## Binary And Source Compatibility

- [ ] We know whether binary compatibility matters for this library.
- [ ] If binary compatibility matters, we have checked for accidental breakage.
- [ ] If macros, compiler hooks, or Scala-version-specific features are used, their support policy is documented.
- [ ] If Scala 2 and Scala 3 are both supported, source compatibility expectations between those lines are explicit.

## Consumer Experience

- [ ] A fresh consumer project can resolve and use the published artifact for each supported Scala line we claim.
- [ ] Dependency metadata is correct and does not drag in accidental or test-only artifacts.
- [ ] Public APIs, implicits, givens, and extension methods look intentional and supportable.
- [ ] Public docs and examples reflect the actual cross-build story consumers will encounter.
