# Apple App Store Checklist

Use this for iPhone, iPad, or other Apple platform app releases through App Store Connect.

## Identity And Signing

- [ ] The bundle identifier is final and permanent.
- [ ] Signing certificates, provisioning profiles, and App Store Connect setup are correct.
- [ ] Version and build numbers are correct for this release.

## Store Readiness

- [ ] App Store Connect metadata, screenshots, icon, and promotional text are ready.
- [ ] Privacy nutrition labels, permission descriptions, and any required policy disclosures are accurate.
- [ ] Review notes are ready if the app needs explanation for login, gated flows, or unusual functionality.

## App Quality

- [ ] The release build does not contain debug-only code, internal endpoints, or local-development assumptions.
- [ ] Upgrade from the previous release has been tested if this is not the first release.
- [ ] TestFlight or equivalent pre-release install has been validated on real devices.
- [ ] Entitlements, push, sign-in, purchases, background modes, and other Apple-managed capabilities are configured correctly if used.
- [ ] We are not knowingly using private APIs or review-hostile behavior.

## Release Operations

- [ ] The intended release path is clear: manual release, scheduled release, or phased rollout.
- [ ] We know how to verify the published build after App Review approval.
