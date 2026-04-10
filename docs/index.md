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
dev doctor
dev config check
```

List configured projects:

```bash
dev project list
```

Generate local development files for a project:

```bash
dev setup --local app-datatron
```

Run checks:

```bash
dev install tools
dev check :root
dev secrets scan .
dev security scan .
dev spdx headers . --fix
```

Build a configured project:

```bash
dev build app-datatron
```

## Read Next

- [Installation](installation.md)
- [Command Reference](commands.md)
- [Configuration Reference](configuration.md)
- [Development](development.md)
