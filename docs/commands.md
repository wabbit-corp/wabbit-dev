# Command Reference

## Global Usage

```bash
wabbit-dev <command> [options]
python3 dev.py <command> [options]
```

The command set is configuration-driven. Most commands expect to run from the
workspace root so `root.clj` and `root.private.clj` can be loaded.

The CLI suggests close matches for mistyped commands, project IDs, checks, and
path-or-project targets when it can infer what you meant.

## Target Model

Many commands now share the same target conventions.

- Project-oriented commands such as `setup`, `build`, `publish`, `clean`,
  `commit`, `dep graph`, `project show`, and `project deps` accept:
  - a configured project ID
  - a configured repo ID
  - a path inside a configured project or configured repo
- Repo-oriented commands such as `status`, `push`, and `project repo` accept:
  - a configured repo ID
  - a configured project ID
  - a path inside a git repository
- Check-oriented commands such as `check`, `spdx headers`, and `secrets scan`
  accept:
  - a filesystem path
  - a bare project ID or repo ID
  - a project or repo ID prefixed with `:`
  - `:root` when you want every configured project path

When a repo target is supplied to a project-oriented command, it expands to the
configured projects that belong to that repo.

## Command Index

| Command | Summary |
| --- | --- |
| `completion bash` / `completion zsh` | Print shell completion scripts with dynamic command, target, and check-name completion. |
| `doctor [TARGET ...] [--only CHECK_OR_COMMAND] [--json]` | Diagnose workspace, toolchain, and credential readiness. |
| `config check` | Parse and validate `root.clj` and `root.private.clj`. |
| `setup [TARGET ...] [--json]` | Generate or refresh managed project files. |
| `llmcopy PATH ...` | Copy file contents to the clipboard in an LLM-friendly wrapper. |
| `dep graph [TARGET ...]` | Render an SVG dependency graph. |
| `dep updates` | Check configured Maven libraries for newer versions. |
| `publish [TARGET ...] [--dry-run]` | Publish configured projects in dependency order or print the publish plan. |
| `build [TARGET ...] [--json]` | Build Gradle projects or syntax-check Python projects. |
| `duplicates FOLDER ...` | Find duplicate files and duplicate directory trees. |
| `jitpack info GROUP ARTIFACT [VERSION]` | Show refs, commits, versions, and build info from JitPack. |
| `clean [TARGET ...]` | Remove generated build and cache directories. |
| `cloc [TARGET ...]` | Run `cloc` for configured targets or direct paths. |
| `status TARGET ... [--json]` | Show tracked working-tree changes for repo targets. |
| `commit [TARGET ...] [--dry-run]` | Run PROD setup, stage changes, and create commits, or print the commit plan. |
| `push [TARGET ...] [--dry-run]` | Push `origin/master` and tags, or print the push plan. |
| `project list` | List configured projects grouped by repository. |
| `project show TARGET ... [--json]` | Show detailed metadata for one or more configured projects. |
| `project deps TARGET ... [--json]` | Show resolved dependencies for one or more configured projects. |
| `project repo TARGET ... [--json]` | Show repo metadata for one or more configured targets. |
| `check --list [--json]` | List the loaded checks and what they do. |
| `check --describe CHECK [--json]` | Show issue IDs, config knobs, and suppression examples for one check. |
| `check [TARGET] [CHECK ...]` | Run the configured check suite. |
| `spdx headers [TARGET] [--fix]` | Run only the SPDX header check. |
| `secrets scan [TARGET]` | Run the internal high-entropy-string secret scan. |
| `contributors audit` | Audit contributor identity mismatches across configured repos. |

## Shell Completion

### `completion bash`

```bash
wabbit-dev completion bash
```

Prints a bash completion script. Source it directly:

```bash
source <(wabbit-dev completion bash)
```

### `completion zsh`

```bash
wabbit-dev completion zsh
```

Prints a zsh completion script. Initialize completion, then source it:

```bash
autoload -Uz compinit && compinit
source <(wabbit-dev completion zsh)
```

The generated completion scripts query the live workspace when you press tab, so
they can complete:

- top-level commands
- nested subcommands
- configured project IDs
- configured repo IDs
- loaded check names

## Environment Diagnostics

### `doctor`

```bash
wabbit-dev doctor
wabbit-dev doctor app-wabbit-dev
wabbit-dev doctor --only publish app-wabbit-dev
wabbit-dev doctor --json
```

Runs an environment and workspace readiness check covering:

- current working directory and workspace root detection
- `root.clj` and `root.private.clj`
- Python version
- virtual environment usage
- `git`, Gradle, and `cloc`
- config loading
- contributor audit baseline identity
- commit and publish credentials

The CLI also reuses a subset of these checks as preflight for commands such as
`setup`, `build`, `publish`, `commit`, `project ...`, `dep ...`, and
`contributors audit`.

Use `--json` when you want a machine-readable report for editor integrations,
scripts, or CI diagnostics.

Use `--only` to narrow the report to either:

- one or more raw check IDs such as `gradle`, `config`, or `publish-pypi`
- one or more command readiness groups such as `build`, `publish`, or `commit`

Optional targets scope project- and publish-related checks to the selected
project closure.

## Configuration and Inventory

### `config check`

```bash
wabbit-dev config check
```

Parses `root.clj` and `root.private.clj` and validates:

- top-level command forms
- project and repo definitions
- library and plugin aliases
- dependency references
- feature blocks and typed config fields

Use this first when changing the config DSL or debugging setup/build behavior.

### `project list`

```bash
wabbit-dev project list
```

Prints the configured projects in declaration order and groups nested repo
projects beneath their containing repository. Each entry is labeled with its
detected project type such as `python`, `kotlin/jvm`, or `kotlin/kmp`.

### `project show`

```bash
wabbit-dev project show TARGET ...
wabbit-dev project show TARGET ... --json
```

Prints the resolved metadata for one or more configured projects, including:

- project type
- path and repo root
- resolved dependencies
- publish target
- docs system
- JVM policy
- the main generated files managed by `setup`

Example:

```bash
wabbit-dev project show app-wabbit-dev
wabbit-dev project show jeeves
wabbit-dev project show app-wabbit-dev --json
```

### `project deps`

```bash
wabbit-dev project deps TARGET ...
wabbit-dev project deps TARGET ... --json
```

Prints just the resolved dependency list for one or more configured projects.
This is useful when `project show` is too verbose and you only want the
post-resolution dependency view.

Examples:

```bash
wabbit-dev project deps app-wabbit-dev
wabbit-dev project deps jeeves
wabbit-dev project deps jeeves --json
```

### `project repo`

```bash
wabbit-dev project repo TARGET ...
wabbit-dev project repo TARGET ... --json
```

Prints repo-level metadata for the repos associated with one or more configured
targets. The output is de-duplicated by repo, so multiple project targets inside
the same repo only print that repo once.

The output includes:

- repo path
- repo ID
- GitHub repo
- Gradle root project name when configured
- docs project when configured
- the configured projects that belong to that repo

Examples:

```bash
wabbit-dev project repo app-wabbit-dev
wabbit-dev project repo jeeves
wabbit-dev project repo jeeves --json
```

## Generation, Build, and Maintenance

### `setup`

```bash
wabbit-dev setup [--dev] [--local] [--json] [TARGET ...]
```

Generates or refreshes managed files from configuration.

Behavior:

- with no targets, processes every configured project
- each target can be a configured project ID, repo ID, or path inside a
  configured project or repo
- in default mode, runs PROD setup
- with `--dev`, switches to DEV mode
- with `--local`, switches to LOCAL mode and writes local dependency overlays
- with `--json`, emits a machine-readable summary while progress logs go to stderr

Typical uses:

```bash
wabbit-dev setup
wabbit-dev setup app-wabbit-dev
wabbit-dev setup jeeves
wabbit-dev setup --local app-datatron
wabbit-dev setup app-wabbit-dev --json
```

### `build`

```bash
wabbit-dev build [TARGET ...] [--json]
```

Builds configured projects in topological dependency order.

Project type behavior:

- Gradle projects: run `build`
- Python projects: syntax-check discovered `.py` files with `py_compile`

Only Gradle and Python projects are buildable through this command.

Use `--json` to emit the resolved targets, topological build order, per-project
results, and a summary count.

### `clean`

```bash
wabbit-dev clean [TARGET ...]
```

Removes generated build and cache directories such as:

- `build`
- `.gradle`
- `.kotlin`
- `.pytest_cache`
- `.mypy_cache`
- Python `__pycache__`

Targets can be configured project IDs, repo IDs, or paths inside configured
projects or repos.

### `cloc`

```bash
wabbit-dev cloc [TARGET ...]
```

Runs `cloc` and prints per-language totals.

Target behavior:

- no target: all configured projects
- configured project or repo ID: project-specific source roots
- path inside a configured project or repo: resolve to the matching configured target
- filesystem path outside the config model: run directly on that path

Project-specific scope:

- Gradle: `src/main` and `src/test`
- Premake: `src`
- Python: whole project root

### `duplicates`

```bash
wabbit-dev duplicates FOLDER ... [--exclude PATTERN ...] [--filter PATTERN ...] [--size BYTES] [--no-default-excludes] [--zip-contents] [--weak-encrypted-zip]
```

Finds duplicate files and duplicate directory trees using staged fingerprinting.

Useful options:

- `--exclude`: remove filename patterns from consideration
- `--filter`: restrict matching to selected filename patterns
- `--size`: minimum file size for duplicate-file reporting
- `--zip-contents`: compare directories against zip contents
- `--weak-encrypted-zip`: allow metadata-only comparison for encrypted zips

### `llmcopy`

```bash
wabbit-dev llmcopy PATH ...
```

Reads files, directories, or glob patterns and copies their contents to the
clipboard using a wrapper like:

```xml
<contents path="...">
...
</contents>
```

This is intended for prompt construction and other copy/paste workflows.

Ignored by default:

- `.git`
- `.idea`
- `__pycache__`
- `.DS_Store`
- `Thumbs.db`

## Dependency and Release Inspection

### `dep graph`

```bash
wabbit-dev dep graph [TARGET ...] [--artifacts]
```

Generates an SVG dependency graph.

- no target: graph the whole workspace
- `TARGET ...`: focus on one or more configured projects, repos, or matching paths
- `--artifacts`: include external artifacts as nodes instead of only project edges

Output is written as `dependency_graph.svg`.

### `dep updates`

```bash
wabbit-dev dep updates
```

Checks the named Maven libraries defined in `root.clj` against their configured
repositories and prints newer versions when found.

This command does not resolve project-to-project dependencies. It only checks
named library aliases.

### `jitpack info`

```bash
wabbit-dev jitpack info GROUP ARTIFACT [VERSION]
```

Prints JitPack metadata for an artifact, including:

- refs
- recent `master` commits
- published versions
- build metadata
- compiler-style build errors extracted from logs when a build record is missing

### `publish`

```bash
wabbit-dev publish [TARGET ...]
wabbit-dev publish [TARGET ...] --dry-run
```

Publishes configured projects in dependency order.

Supported targets:

- Maven Central
- JitPack
- JetBrains Marketplace
- PyPI

The publish target is inferred from project metadata and features. Credentials
are loaded from `root.private.clj` and, for some flows, supporting environment
variables.

Projects that do not declare a publish target are skipped.

Use `--dry-run` to inspect the topological publish order and resolved publish
targets without uploading artifacts or contacting remote publish services.

## Quality and Security

### `check`

```bash
wabbit-dev check --list
wabbit-dev check --list --json
wabbit-dev check --describe SpdxHeaderCheck
wabbit-dev check --describe SpdxHeaderCheck --json
wabbit-dev check [TARGET] [CHECK ...] [--fix]
```

Runs the loaded check suite against:

- a filesystem path
- a bare configured project or repo ID
- a configured project or repo ID prefixed with `:`
- `:root` to walk every configured project path

Discovery helpers:

- `--list`: show every loaded check with its scope and whether it advertises auto-fix support
- `--describe CHECK`: show issue IDs, config commands, and suppression examples for one check
- `--json`: with `--list` or `--describe`, emit structured output instead of text

Examples:

```bash
wabbit-dev check .
wabbit-dev check app-wabbit-dev
wabbit-dev check jeeves
wabbit-dev check app-wabbit-dev/dev/cli.py
wabbit-dev check :app-wabbit-dev
wabbit-dev check :root --fix
wabbit-dev check . SpdxHeaderCheck
```

Important notes:

- explicit check names use the Python class names registered by the loaded check modules
- checks honor `.gitignore`, `.checkignore`, `checks/disable`, and `checks/ignore-finding`
- `--fix` only applies to checks that supply an automatic fix callback

### `spdx headers`

```bash
wabbit-dev spdx headers [TARGET] [--fix]
```

Runs only the SPDX header check. This is a focused shortcut for:

```bash
wabbit-dev check TARGET SpdxHeaderCheck
```

Use `--fix` to insert or normalize headers where the check supports it.

### `secrets scan`

```bash
wabbit-dev secrets scan [TARGET]
```

Runs the internal high-entropy-string check against a target path.

Examples:

```bash
wabbit-dev secrets scan .
wabbit-dev secrets scan :root
```

Targets can be:

- a filesystem path
- a bare configured project or repo ID
- a configured project or repo ID prefixed with `:`
- `:root` to walk every configured project path

### `contributors audit`

```bash
wabbit-dev contributors audit
```

Audits configured repositories for contributor identities that do not match the
default git user configured in the loaded workspace metadata.

The expected identity comes from `(git-user "Name" "email@example.com")` in the
loaded workspace config.

## Git Workflow Commands

### `status`

```bash
wabbit-dev status TARGET ... [--json]
```

Shows tracked working-tree changes for:

- a configured repo ID
- a configured project ID from `root.clj`
- any path inside a git repository

This command reports tracked files that differ between the index and working
tree. It does not list untracked files.

Use `--json` to emit a per-repo list of tracked changes for scripts or editor
integrations.

### `commit`

```bash
wabbit-dev commit [TARGET ...]
wabbit-dev commit [TARGET ...] --dry-run
```

Runs PROD setup for the selected projects, groups them by repository, stages
changes, and creates commits with AI-generated messages.

Requirements:

- valid workspace configuration
- an OpenAI key in `root.private.clj`

Use `--dry-run` to print the PROD setup order and repository commit plan without
modifying files or creating commits.

### `push`

```bash
wabbit-dev push [TARGET ...]
wabbit-dev push [TARGET ...] --dry-run
```

Pushes `origin/master` and tags.

Target behavior:

- no target or `.`: push every distinct configured repository once
- configured repo ID: push that repo
- configured project ID: resolve the repo for that project
- filesystem path: resolve the repo containing that path

Current caveat: the branch target is hard-coded to `master`.

Use `--dry-run` to print the resolved repositories before pushing branch or tag
updates.

## Standalone Helper

### `dev/tasks/choose-jvm.py`

```bash
python3 dev/tasks/choose-jvm.py --policy jvm-21
python3 dev/tasks/choose-jvm.py --project jeeves/client --task compileKotlinJvm
python3 dev/tasks/choose-jvm.py 21 latest amazon
```

This helper is not wired into the main `wabbit-dev` command tree, but it is part
of the toolkit. It chooses the best installed JVM for:

- a named policy
- a configured project and optional Gradle task
- a legacy free-form query

Use `--json` to emit machine-readable output instead of shell exports.
