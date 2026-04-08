# Kotlin Release Checklist

Use this for Kotlin, JVM, or KMP projects, including Kotlin libraries, Gradle plugins, and compiler plugins.

## Kotlin And KMP Basics

- [ ] The published Kotlin version policy is intentional and documented.
- [ ] Supported Kotlin versions are based on actual tests, not just aspiration.
- [ ] Kotlin metadata compatibility expectations are explicit, especially if we expect consumers on older Kotlin compilers.
- [ ] `commonMain` and `commonTest` are actually common and do not rely on `java.*` or other host-only APIs by accident.
- [ ] The target set is intentional, and we are not publishing surprise targets just because the generator can.
- [ ] The published variants and `.module` metadata are sane for KMP consumers.
- [ ] Any host-specific caveats for native, JS, Wasm, Android, or iOS are documented.

## Gradle And IDE Behavior

- [ ] IntelliJ and Rider can import the generated project successfully.
- [ ] Gradle sync works without manual script edits or local-only hacks.
- [ ] The supported JDK and Gradle version floor is known and documented.
- [ ] Configuration-time behavior is sane and does not do surprising network or filesystem work.
- [ ] Incremental compilation behavior has not obviously regressed.

## Dependency And Metadata Sanity

- [ ] Published metadata does not leak `settings.local.gradle.kts`, local included-build names, or other monorepo-only wiring.
- [ ] Dependency metadata is correct for each source set and target.
- [ ] We are not leaking host-only or test-only dependencies into published variants.
- [ ] Source jars and docs reflect the actual published API shape.

## Kotlin Library Quality

- [ ] Public types and extension functions are intentionally named and scoped.
- [ ] If JVM consumers matter, the Java interop surface has been reviewed for `@JvmOverloads`, `@JvmStatic`, `@JvmField`, and other Java-facing ergonomics.
- [ ] Public serialization formats, parsers, and codecs are stable enough for release.
- [ ] Platform-specific implementations match the documented behavior of the common API.

## Gradle Plugin Checks

- [ ] If this is a Gradle plugin, a fresh consumer build can resolve and apply it by plugin ID and version.
- [ ] We have explicitly decided whether the official public path is Maven Central only, Plugin Portal, or both.
- [ ] The plugin behaves sanely during IDE sync and incremental builds.
- [ ] The plugin does not silently depend on workspace-only generated files or local repositories.

## Compiler Plugin Checks

- [ ] If this is a compiler plugin, the public Gradle path for enabling it is documented and tested.
- [ ] The Gradle bridge plugin points at the exact compiler-plugin coordinates we intend to publish.
- [ ] Compiler-plugin versioning across supported Kotlin versions is intentional and documented.
- [ ] Claimed Kotlin version support is backed by actual consumer-side tests for those Kotlin versions.
- [ ] The plugin produces useful diagnostics and does not expose internal-only stack traces in normal failure modes.
