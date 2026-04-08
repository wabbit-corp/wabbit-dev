# GitHub Releases Checklist

Use this when the public release artifact is distributed through GitHub Releases, or when other destinations such as Homebrew or Chocolatey depend on GitHub Release assets.

## Release Structure

- [ ] The release tag is correct, stable, and points at the exact commit we intend to ship.
- [ ] Tag naming is consistent with the versioning scheme used elsewhere in the project.
- [ ] We have explicitly decided whether the release is a draft, pre-release, or final release.
- [ ] The GitHub Release title and notes match the actual release version and status.

## Asset Naming And Content

- [ ] Asset filenames are stable, predictable, and suitable for downstream automation.
- [ ] Checksums are published for the release artifacts if downstream consumers rely on them.
- [ ] Release assets do not accidentally include test outputs, local files, debug builds, or unrelated repo contents.
- [ ] Platform-specific binaries are named clearly enough that users and package managers can select the right one.

## Consumer And Downstream Validation

- [ ] A fresh external user can download the intended asset and use it successfully.
- [ ] If Homebrew, Chocolatey, or other package managers depend on these assets, the asset URLs and checksums work for those downstream consumers.
- [ ] If this is not the first release, upgrade expectations from the previous GitHub Release are understood.

## Publication Hygiene

- [ ] The release notes or changelog entries attached to the GitHub Release are complete and consistent with the chosen changelog source of truth.
- [ ] The release is not announced until the intended assets are uploaded and verified.
