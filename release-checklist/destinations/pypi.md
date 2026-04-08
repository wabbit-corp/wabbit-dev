# PyPI Checklist

Use this together with the general checklist and [`languages/python.md`](../languages/python.md).

## Package Identity And Metadata

- [ ] The package name is correct, available, and the one we intend to support publicly.
- [ ] Core metadata such as summary, homepage, license, classifiers, and Python version range are correct.
- [ ] README or long description renders correctly for package consumers.

## Artifacts

- [ ] Both `sdist` and wheel build successfully from a clean checkout.
- [ ] The uploaded artifacts contain the files we expect and no internal-only junk.
- [ ] Console scripts, package data, and optional extras behave correctly from the installed distribution.

## Consumer Validation

- [ ] A fresh virtual environment can install the package and use it successfully.
- [ ] If we claim a CLI, the installed entry point works from the packaged artifact.
- [ ] If we claim support for multiple Python versions or platforms, that support is backed by tests or explicit validation.

## Release Operations

- [ ] PyPI publishing credentials and ownership are set up correctly.
- [ ] We know whether we are validating via TestPyPI, an internal dry run, or a real production publish flow before the first public release.
