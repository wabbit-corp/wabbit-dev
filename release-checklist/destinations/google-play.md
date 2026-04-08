# Google Play Checklist

Use this for Android app releases.

## Identity And Signing

- [ ] The application ID is final and permanent.
- [ ] Signing keys and Play App Signing setup are correct and safely managed.
- [ ] `versionCode` and `versionName` are correct for this release.

## Store Readiness

- [ ] Store listing text, screenshots, icon, feature graphic, and other required assets are ready.
- [ ] Privacy policy, data safety, permission disclosures, and ads disclosures are accurate.
- [ ] Release notes are ready for the Play track we are using.

## App Quality

- [ ] The release build is not debuggable and does not expose test-only logging, secrets, or internal endpoints.
- [ ] Upgrade from the previous release has been tested if this is not the first release.
- [ ] Crash, ANR, and startup smoke checks are acceptable for release.
- [ ] Billing, subscriptions, sign-in, push, and other store-relevant integrations are configured correctly if used.

## Release Operations

- [ ] The intended rollout path is clear: internal, closed, open, staged, or production.
- [ ] We know how to verify the published build on-device after rollout starts.
