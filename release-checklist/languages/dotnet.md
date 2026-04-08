# .NET Release Checklist

Use this for libraries or tools intended for NuGet and the wider .NET ecosystem.

## Package Identity

- [ ] Package ID, assembly names, namespaces, and public type names are stable enough for long-term support.
- [ ] Supported target frameworks are intentional and documented.
- [ ] The versioning strategy for package version, assembly version, and file version is intentional.

## Build And Packaging

- [ ] `dotnet build` and `dotnet pack` succeed from a clean checkout.
- [ ] The produced package installs cleanly into a fresh consumer project.
- [ ] Package contents are intentional: assemblies, XML docs, readme, icon, and any symbols package if we ship one.
- [ ] SourceLink or equivalent source mapping is configured if we claim debugging support.

## Consumer Experience

- [ ] Public APIs have meaningful XML docs or other discoverable documentation if that is part of the support bar.
- [ ] Target-framework-specific behavior is documented where it differs.
- [ ] Transitive dependencies and target framework assets resolve the way we expect in a clean consumer project.
