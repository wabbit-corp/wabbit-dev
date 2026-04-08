# Gradle Plugin Portal Checklist

Use this together with the general checklist, [`languages/kotlin.md`](../languages/kotlin.md), and any other destination checklist the plugin also uses.

## Portal Metadata

- [ ] The plugin has a clear display name and description suitable for public discovery.
- [ ] The plugin website URL is correct and public.
- [ ] The plugin VCS URL is correct and public.
- [ ] The Portal metadata fields such as display name, description, website, VCS URL, tags, and categories are all populated through the intended publish path.
- [ ] Tags, categories, and metadata shown in the Portal are intentional and useful.
- [ ] The Portal-facing metadata matches the actual plugin ID and the release we are publishing.

## Publish Path

- [ ] We have explicitly decided whether Plugin Portal is an official destination for this plugin or just Maven Central.
- [ ] The public installation instructions match the real Portal path users will take.
- [ ] A fresh consumer build can resolve and apply the plugin through the Plugin Portal path.
- [ ] If the plugin also depends on artifacts from Maven Central, that combined resolution path works in a clean consumer project.

## Verification

- [ ] We verify that the plugin appears correctly in the Gradle Plugin Portal after release.
- [ ] We verify that the published Portal metadata points at the correct website and source repository.
