# wabbit-dev

`wabbit-dev` is the configuration-driven automation CLI used across the Wabbit
workspace.

It reads `root.clj` and `root.private.clj`, builds an internal model of the
workspace, and then uses that model to:

- generate managed Gradle, Python, legal, and workflow files
- run checks over repositories, projects, directories, and files
- inspect dependency graphs and available dependency updates
- build configured projects in dependency order
- publish releases to Maven Central, JitPack, JetBrains Marketplace, and PyPI
- automate common git maintenance tasks

## Quick Start

Validate configuration:

```bash
python3 dev.py doctor
python3 dev.py config check
```

List configured projects:

```bash
python3 dev.py project list
```

Generate local development files for a project:

```bash
python3 dev.py setup --local app-datatron
```

Run checks:

```bash
python3 dev.py check :root
python3 dev.py secrets scan .
python3 dev.py spdx headers . --fix
```

Build a configured project:

```bash
python3 dev.py build app-datatron
```

## Read Next

- [Installation](installation.md)
- [Command Reference](commands.md)
- [Configuration Reference](configuration.md)
- [Development](development.md)
