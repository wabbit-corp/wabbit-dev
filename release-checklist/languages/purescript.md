# PureScript Release Checklist

Use this for PureScript libraries intended for the PureScript ecosystem and Pursuit.

## Package Basics

- [ ] Package name, module names, and public exports are stable enough for long-term support.
- [ ] The supported PureScript compiler version range is intentional and documented.
- [ ] Dependency bounds are intentional and have been tested against the package set or registry flow we expect users to use.

## Docs And Examples

- [ ] Public modules, types, and values have enough documentation to produce useful generated docs.
- [ ] Examples compile and reflect real usage rather than only toy snippets.
- [ ] Any FFI modules or JS-side behavior are documented where they affect consumers.

## Build And Consumer Checks

- [ ] A clean package build works with the expected tooling flow.
- [ ] A fresh consumer project can add the package and compile against it.
- [ ] Generated docs correspond to the exact version being released.
