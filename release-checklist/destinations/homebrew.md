# Homebrew Checklist

Use this for CLI or desktop tooling distributed through Homebrew.

## Formula Readiness

- [ ] The formula points at a stable public source tarball, bottle, or release artifact.
- [ ] Checksums are correct for the exact release artifact.
- [ ] Runtime dependencies are declared correctly.
- [ ] Executable names are stable and intentional.

## Install And Upgrade Validation

- [ ] Install works on a clean macOS environment.
- [ ] If we intend to support Linux through Homebrew or Linuxbrew, install works there too.
- [ ] The installed command-line experience matches the docs.
- [ ] Upgrade from the previous release works cleanly if this is not the first release.
- [ ] Uninstall does not leave surprising junk behind.

## Packaging Hygiene

- [ ] No hardcoded local paths or workspace assumptions leak into the formula or installed artifact.
- [ ] If we promise completions, manpages, or shell integrations, they are actually installed and working.
