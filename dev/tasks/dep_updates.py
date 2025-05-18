from dev.config import Config, load_config, MavenRepositoryDefinition

from dev.maven import fetch_metadata, MavenVersion

import time

MAVEN_CENTRAL = MavenRepositoryDefinition(
    name="Maven Central", url="https://repo1.maven.org/maven2/"
)


def check_for_updates():
    config = load_config()

    for _, library in config.libraries.items():
        if library.repo is None:
            repo = MAVEN_CENTRAL
        else:
            repo = config.repositories[library.repo]

        # print(f"Checking for updates for {library.name} from {repo.name}")

        group_id = library.maven_urn.group_id
        artifact_id = library.maven_urn.artifact_id
        current_version = library.maven_urn.version
        try:
            current_version_obj = MavenVersion.parse(current_version)
        except ValueError:
            # print(f"Skipping invalid version: {current_version}")
            continue

        try:
            metadata = fetch_metadata(repo.url, group_id, artifact_id)
        except Exception as e:
            # print(f"Failed to fetch metadata for {library.name}: {e}")
            continue

        newer_versions = []
        for version in metadata.versions:
            try:
                available_version = MavenVersion.parse(version)
                if available_version > current_version_obj:
                    newer_versions.append(version)
            except ValueError:
                # print(f"Skipping invalid version: {version}")
                pass

        if newer_versions:
            print(f"{library.name}: {current_version} < {newer_versions}")
