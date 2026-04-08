# Rollback And Hotfix Playbook

Use this for any public release to an immutable registry or store.

## Assumptions

- [ ] We understand whether the destination allows deletion, yanking, unlisting, phased halt, or none of the above.
- [ ] For immutable registries, rollback means a follow-up release plus communication, not deletion.

## Before Release

- [ ] The release owner and approval path for emergency follow-up releases are known.
- [ ] The time expectations for responding to a bad public release are explicit.
- [ ] We know how to pause rollout, unlist, yank, or halt promotion where the destination supports it.
- [ ] We know which communication channels will be used if the release is bad.

## If The Release Is Bad

- [ ] We can identify the bad version unambiguously by tag, version, and published coordinates.
- [ ] We can publish a fixed follow-up release without inventing a new process under pressure.
- [ ] We can tell users whether to stop upgrading, pin a previous version, or move to the hotfix release.
- [ ] We can update release notes, docs, and issue trackers quickly enough that users are not left guessing.

## Aftermath

- [ ] We capture the root cause and any checklist gap that allowed the bad release through.
- [ ] We update the relevant checklist file rather than relying on memory next time.
