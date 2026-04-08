<!-- BANNERS START -->
<p align=center><img src=".banner.png"/></p>

<p align=center>
    <a href="https://github.com/wabbit-corp/wabbit-dev/blob/main/LICENSE.md"><img src="https://img.shields.io/github/license/wabbit-corp/wabbit-dev" alt="License"></a>
    <a href="https://github.com/wabbit-corp/wabbit-dev"><img src="https://img.shields.io/github/languages/top/wabbit-corp/wabbit-dev" alt="GitHub top language"></a>
</p>

---

# Wabbit Dev Toolkit

`wabbit-dev` is the workspace automation CLI used across the Wabbit repositories.
It reads project metadata from `root.clj` and `root.private.clj`, then uses that
configuration to:

- generate managed project files
- run repo and source checks
- inspect dependency graphs and updates
- build configured projects
- publish releases
- automate common git maintenance tasks

The main entrypoints are:

- `wabbit-dev ...` after installation
- `python3 dev.py ...` when running from this repository

## Installation

`wabbit-dev` requires Python 3.12 or newer.

Install the published package:

```bash
python3 -m pip install wabbit-dev
```

Install it from a checkout for local development:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
```

If you also want the test and packaging toolchain:

```bash
python3 -m pip install -r requirements.txt -r requirements-dev.txt
```

Docs dependencies live outside `requirements-dev.txt`. Install them separately:

```bash
python3 -m pip install "mkdocs>=1.6,<2.0" "mkdocs-material>=9.6,<9.7" "pymdown-extensions>=10,<11"
```

## Quick Start

Validate the workspace configuration:

```bash
python3 dev.py config check
```

Inspect the configured project inventory:

```bash
python3 dev.py project list
```

Generate managed files for a project and its dependencies:

```bash
python3 dev.py setup --local app-datatron
```

Run checks:

```bash
python3 dev.py check :root
python3 dev.py spdx headers . --fix
```

Build a configured project:

```bash
python3 dev.py build app-datatron
```

## Command Reference

Every command is documented here and in the MkDocs reference under
[docs/commands.md](docs/commands.md).

| Command | What it does |
| --- | --- |
| `doctor` | Diagnoses workspace, toolchain, and credential readiness. |
| `config check` | Parses and validates `root.clj` and `root.private.clj`. |
| `setup [PROJECT ...]` | Generates or refreshes managed project files from configuration. |
| `llmcopy PATH ...` | Copies file contents to the clipboard in an LLM-friendly wrapper. |
| `dep graph [PROJECT]` | Renders an SVG dependency graph for all projects or one project. |
| `dep updates` | Checks configured Maven libraries for newer upstream versions. |
| `publish [PROJECT]` | Publishes configured projects in dependency order. |
| `build [PROJECT ...]` | Builds configured Gradle projects or syntax-checks Python projects. |
| `duplicates FOLDER ...` | Finds duplicate files and duplicate directory trees. |
| `jitpack info GROUP ARTIFACT [VERSION]` | Shows refs, commits, versions, and build info for a JitPack artifact. |
| `clean [PROJECT]` | Deletes generated build and cache directories for configured projects. |
| `cloc [TARGET]` | Runs `cloc` for a configured project or an arbitrary filesystem path. |
| `status TARGET` | Shows tracked working-tree changes for a configured project or git path. |
| `commit [PROJECT]` | Runs PROD setup, stages changes, and creates commits with AI-generated messages. |
| `push [TARGET]` | Pushes `origin/master` and tags for one repo or all configured repos. |
| `project list` | Lists configured projects grouped by repository. |
| `project show PROJECT` | Shows detailed metadata for one configured project. |
| `check --list` | Lists the loaded checks with scope, auto-fix support, and summaries. |
| `check --describe CHECK` | Shows issue IDs, config knobs, and suppression examples for one check. |
| `check [TARGET] [CHECK ...]` | Runs the loaded check suite against a project, path, or file. |
| `spdx headers [TARGET] [--fix]` | Runs only the SPDX header check. |
| `secrets scan [TARGET]` | Runs the internal high-entropy-string secret scan. |
| `contributors audit` | Audits contributor identity mismatches across configured repos. |

Additional helper:

| Helper | What it does |
| --- | --- |
| `dev/tasks/choose-jvm.py` | Selects the best installed JVM for a named policy, project, or legacy query. |

## Configuration Overview

The CLI is driven by two files at the workspace root:

- `root.clj`: public workspace metadata, project definitions, dependency aliases,
  build defaults, check suppressions, and repository layout
- `root.private.clj`: private credentials and local secrets such as API tokens,
  publish credentials, and default git identity

Common `root.clj` forms include:

```clojure
(checks/disable "E_HARDCODED_URL" "**/LICENSE.md")
(define-maven-repo "repo:jitpack" "https://jitpack.io")
(define-maven-library "kotlin-stdlib" "org.jetbrains.kotlin:kotlin-stdlib:2.3.10")

(python "app-wabbit-dev"
  :version "1.1.0"
  :features [
    (python-application
      :script "wabbit-dev"
      :entry "dev.cli:main"
      :path "dev.py")])

(gradle "app-datatron"
  :version "1.0.0"
  :features [(jvm-kotlin-application :main "datatron.MainKt")]
  :dependencies [":kotlin-minilog" "sqlite-jdbc"])

(repo "jeeves"
  :repo "wabbit-corp/jeeves"
  :projects [
    (gradle "api" :version "0.0.1" :buildModel "kmp")
    (gradle "client" :version "0.0.1" :buildModel "kmp")])
```

Dependency inputs can reference:

- another configured project: `":kotlin-minilog"`
- a named library alias: `"sqlite-jdbc"`
- a direct Maven coordinate: `"org.jsoup:jsoup:1.21.2"`
- a modified dependency call: `(dep "kotlin-compiler-embeddable" "compileOnly")`
- an npm dependency: `"npm:react:18.3.1"`
- a jar path: `"./libs/custom-tooling.jar"`

Full configuration reference:

- [docs/configuration.md](docs/configuration.md)

## Checks and Suppressions

`check` honors:

- `.gitignore`
- `.checkignore`
- path-based suppressions in `root.clj` via `(checks/disable ...)`
- value-based suppressions in `root.clj` via `(checks/ignore-finding ...)`
- inline ignore pragmas such as:

```python
HOST = "10.0.0.0"  # check:ignore E_HARDCODED_INTERNAL_HOSTNAME_IP value=10.0.0.0
```

The main target forms are:

- `python3 dev.py doctor`
- `python3 dev.py check --list`
- `python3 dev.py check --describe SpdxHeaderCheck`
- `python3 dev.py check .`
- `python3 dev.py check path/to/file.py`
- `python3 dev.py check :app-wabbit-dev`
- `python3 dev.py check :root`
- `python3 dev.py secrets scan .`

Inventory commands:

- `python3 dev.py project list`
- `python3 dev.py project show app-wabbit-dev`
- `python3 dev.py contributors audit`

## Documentation

MkDocs pages live under `docs/`:

- [docs/index.md](docs/index.md)
- [docs/installation.md](docs/installation.md)
- [docs/commands.md](docs/commands.md)
- [docs/configuration.md](docs/configuration.md)
- [docs/development.md](docs/development.md)

Build the docs locally with:

```bash
mkdocs build --strict
```

## Packaging

Build a single-file executable with PyInstaller:

```bash
python3 scripts/build_executable.py
```

Artifacts are emitted under `dist/`.

Build a macOS installer:

```bash
scripts/build_macos_installer.sh --version 0.1.0
```

Artifacts:

- `dist/wabbit-dev-<version>.pkg`
- `dist/wabbit-dev-<version>.dmg`

Optional signing and notarization environment variables:

- `INSTALLER_SIGN_IDENTITY`
- `NOTARYTOOL_PROFILE`
- `NOTARYTOOL_APPLE_ID`
- `NOTARYTOOL_PASSWORD`
- `NOTARYTOOL_TEAM_ID`

## Development

Run the local verification suite before sending changes upstream:

```bash
pytest -q
ruff check .
black --check .
mypy .
mkdocs build --strict
```

This repository generates some managed files from `root.clj`. If you change the
configuration model or template behavior, run the relevant `setup` commands and
review the generated output before committing.

## Licensing

This project is licensed under the [AGPL](LICENSE.md) for open source use.

For commercial use, contact Wabbit Consulting Corporation at `wabbit@wabbit.one`.

## Contributing

Before contributions can be accepted, contributors must agree to the
[Contributor License Agreement](CLA.md).
