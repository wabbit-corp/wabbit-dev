# Python Release Checklist

Use this for Python libraries, CLI tools, or SDKs.

## Packaging Basics

- [ ] `pyproject.toml` metadata is correct and complete.
- [ ] The package name and import name are both intentional and documented if they differ.
- [ ] Supported Python versions are documented and actually tested.
- [ ] Dependencies, extras, and optional features are intentional and minimal.

## Build Artifacts

- [ ] Both `sdist` and wheel build successfully from a clean checkout.
- [ ] The installed wheel works outside the source tree.
- [ ] Package data, templates, native artifacts, and CLI entry points are actually included in the built distribution.
- [ ] README or long description renders correctly for package consumers.

## Runtime Behavior

- [ ] Importing the package does not have surprising side effects.
- [ ] CLI entry points are smoke-tested from an installed package, not only from the repo checkout.
- [ ] Version reporting is consistent between package metadata and runtime APIs, if applicable.
- [ ] The package does not depend on local paths, editable-install assumptions, or untracked generated files.
