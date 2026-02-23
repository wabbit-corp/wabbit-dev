import termcolor

from dev.jitpack import JitPackAPI


async def get_jitpack_info(group: str, artifact: str, target_version: str | None) -> None:
    async with JitPackAPI() as api:
        versions = await api.get_versions(group, artifact, "reload")
        refs = await api.get_refs(group, artifact)
        commits = await api.get_commits(group, artifact, "master")

        print("# Refs:")
        for ref in refs:
            print(f"* {ref}")
        print()

        print("# Commits (master):")
        for commit in commits:
            print(f"* {commit}")
        print()

        print("# Versions:")
        for version in versions:
            if target_version and version.version != target_version:
                continue
            print(f"* {version}")
            build = await api.get_build_info(group, artifact, version.version)
            if build is None:
                log = await api.get_build_log(group, artifact, version.version)
                for line in log.splitlines():
                    if line.startswith("e: "):
                        line = termcolor.colored(line[3:], "red")
                        print(f"  - {line}")

            print(f"  - Build: {build}")
        print()
