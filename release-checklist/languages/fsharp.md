# F# Release Checklist

Use this for F# libraries or tools intended for public .NET release.

## Package And Surface Area

- [ ] Package ID, assembly names, namespaces, and module names are stable enough for long-term support.
- [ ] The target framework set is intentional and documented.
- [ ] The public F# API shape is intentional, including modules, records, discriminated unions, and computation expressions where applicable.

## Compatibility And Runtime Behavior

- [ ] The package resolves against the intended `FSharp.Core` expectations without surprising version conflicts.
- [ ] The supported .NET and F# compiler/tooling floor is known and documented.
- [ ] Any `netstandard`, `netX.Y`, or runtime-specific behavioral differences are documented.
- [ ] Public async/task behavior and exception behavior are clear enough for consumers.

## Consumer Validation

- [ ] A fresh F# consumer project can reference the package and build successfully.
- [ ] If C# consumers matter, the interop surface is reviewed for usability from C# as well.
- [ ] XML docs or equivalent public docs are present if that is part of the support bar.
