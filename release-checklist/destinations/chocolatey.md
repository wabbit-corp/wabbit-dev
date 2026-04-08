# Chocolatey Checklist

Use this for Windows tooling distributed through Chocolatey.

## Package Readiness

- [ ] The package metadata is correct and suitable for public distribution.
- [ ] Install scripts reference stable public release artifacts.
- [ ] Checksums are correct for the exact release artifacts.
- [ ] Silent install and uninstall behavior is intentional and documented.

## Install And Upgrade Validation

- [ ] Install works on a clean Windows environment.
- [ ] Upgrade from the previous release works cleanly if this is not the first release.
- [ ] Uninstall works cleanly and does not leave surprising PATH or shell state behind.
- [ ] The installed command-line experience matches the docs.

## Packaging Hygiene

- [ ] No local paths, repo-only assumptions, or internal URLs leak into the package scripts.
- [ ] Any admin or reboot assumptions are documented and justified.
