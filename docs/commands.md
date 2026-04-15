# Command Reference

## Global Usage

```bash
dev <command> [options]
wabbit-dev <command> [options]
```

The command set is configuration-driven. Commands walk upward from the current
directory until `root.clj` and `root.private.clj` can be loaded.

The CLI suggests close matches for mistyped commands, project IDs, checks, and
path-or-project targets when it can infer what you meant.

Use `dev where` to inspect the exact workspace, project, and repo context
the CLI inferred from the current directory.

This reference covers both the visible command tree from `dev --help` and the
supported compatibility paths that stay hidden from the top-level help output,
such as `docs check`, `release verify`, `security scan`, and `check describe`.

## Target Model

Many commands now share the same target conventions.

- Project-oriented commands such as `setup`, `release verify`, `build`, `publish`, `clean`,
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

When you omit targets from inside a configured project or repo, many commands
default to that current project or repo instead of widening to the full
workspace. The workspace-wide behavior remains the default when you invoke those
commands from the workspace root.

## Command Index

| Command | Summary |
| --- | --- |
| `install app [--bin-dir DIR]` | Install or refresh global `dev` and `wabbit-dev` launcher wrappers. |
| `install completions [--shell all\|bash\|zsh] [--no-rc]` | Install completion scripts and register managed shell rc snippets. |
| `install tools [--tool TOOL] [--force] [--json]` | Install optional local scanners, QA tools, and formatters. |
| `completion bash` / `completion zsh` | Print shell completion scripts with dynamic command, target, and check-name completion. |
| `doctor [TARGET ...] [--only CHECK_OR_COMMAND] [--json]` | Diagnose workspace, toolchain, and credential readiness. |
| `docs check [TARGET ...] [--semantic] [--json]` | Validate docs links, sections, snippets, hooks, and optional semantic quality. |
| `docs snippets [TARGET ...] [--verify] [--json]` | Validate fenced docs snippets with optional deeper project-specific verification. |
| `where [--json]` | Show the workspace, repo, and project context inferred from the current directory. |
| `config check` | Parse and validate `root.clj` and `root.private.clj`. |
| `setup [TARGET ...] [--commit-if-setup-only] [--json]` | Generate or refresh managed project files, with an optional safe post-setup auto-commit. |
| `llmcopy PATH ...` | Copy file contents to the clipboard in an LLM-friendly wrapper and report GPT-5.4 token totals. |
| `dep graph [TARGET ...]` | Render an SVG dependency graph. |
| `dep updates` | Check configured Maven libraries for newer versions. |
| `publish [TARGET ...] [--dry-run]` | Publish configured projects in dependency order or print the publish plan. |
| `release verify [TARGET ...] [--json]` | Verify publishable Python and Gradle projects without uploading them. |
| `security scan [TARGET ...] [--tool TOOL] [--json]` | Run opt-in external security scanners when available and applicable. |
| `build [TARGET ...] [--json]` | Build Gradle projects or syntax-check Python projects. |
| `duplicates FOLDER ...` | Find duplicate files and duplicate directory trees. |
| `jitpack info GROUP ARTIFACT [VERSION]` | Show refs, commits, versions, and build info from JitPack. |
| `clean [TARGET ...]` | Remove generated build and cache directories. |
| `cloc [TARGET ...]` | Run `cloc` for configured targets or direct paths. |
| `status [TARGET ...] [--json]` | Show staged, unstaged, and untracked status for the current or selected repo targets. |
| `commit [TARGET ...] [--dry-run]` | Run PROD setup, stage changes, and create commits, or print the commit plan. |
| `push [TARGET ...] [--dry-run]` | Push the current branch to its configured upstream when it can fast-forward, or print the push plan. |
| `project list` | List configured projects grouped by repository. |
| `project show [TARGET ...] [--json]` | Show detailed metadata for one or more configured projects. |
| `project deps [TARGET ...] [--json]` | Show resolved dependencies for one or more configured projects. |
| `project repo [TARGET ...] [--json]` | Show repo metadata for one or more configured targets. |
| `project targets [TARGET ...] [--json]` | Show Kotlin Multiplatform target platforms for matching configured projects. |
| `check list [--json]` | List the loaded checks and what they do. |
| `check describe CHECK [--json]` | Show issue IDs, config knobs, and suppression examples for one check. |
| `check [TARGET] [CHECK ...]` | Run the configured check suite. |
| `spdx headers [TARGET] [--fix]` | Run only the SPDX header check. |
| `secrets scan [TARGET]` | Run the internal high-entropy-string secret scan. |
| `contributors audit` | Audit contributor identity mismatches across configured repos. |

## Installation Helpers

### `install app`

```bash
dev install app
```

Installs or refreshes global `dev` and `wabbit-dev` wrappers tied to this
checkout. By default it chooses the first writable PATH directory, preferring
`/opt/homebrew/bin`, `/usr/local/bin`, then `~/.local/bin`.

Use a specific install directory when needed:

```bash
dev install app --bin-dir ~/.local/bin
```

### `install completions`

```bash
dev install completions
```

Writes bash and zsh completion scripts for both `dev` and `wabbit-dev`, then
updates managed blocks in `.bashrc` and `.zshrc` so new shells load them.

Install only one shell, or skip rc edits:

```bash
dev install completions --shell zsh
dev install completions --no-rc
```

### `install tools`

```bash
dev install tools
dev install tools --tool gitleaks --tool ktfmt
dev install tools --force
dev install tools --json
```

Installs optional developer tools used by checks and security scans. Python
tools such as `ruff`, `black`, `mypy`, `pyright`, `pytest`, `coverage`,
`diff-cover`, `deptry`, `import-linter`, `vulture`, `bandit`, `semgrep`, and
`pip-audit` install into the workspace/app Python environment. Standalone
release assets such as `gitleaks`, `trufflehog`, `shellcheck`, `osv-scanner`,
and `ktfmt` install under `.tools` with wrappers in `.tools/bin`. Formatter
tools backed by other ecosystems, currently `purs-tidy` and `csharpier`, use
local npm/dotnet tool installs when those system package managers are present.

Direct downloads are verified against SHA-256 release asset metadata before
being exposed in `.tools/bin`. Python-package signatures are not consistently
published upstream, so Python tools are installed through pip with PyPI/HTTPS
transport and reported separately in the install output.

### `install hooks`

```bash
dev install hooks
dev install hooks app-wabbit-dev
dev install hooks --json
```

Installs local Git hooks for the current repo or selected repos. Targets can be
repo IDs, project IDs, or paths inside a git repository.

Use `--json` when editor tooling or bootstrap scripts need a structured result.

## Shell Completion

### `completion bash`

```bash
dev completion bash
```

Prints a bash completion script. Source it directly:

```bash
source <(dev completion bash)
```

### `completion zsh`

```bash
dev completion zsh
```

Prints a zsh completion script. Initialize completion, then source it:

```bash
autoload -Uz compinit && compinit
source <(dev completion zsh)
```

The generated completion scripts query the live workspace when you press tab, so
they can complete:

- top-level commands
- nested subcommands
- configured project IDs
- configured repo IDs
- loaded check names

### `completion query`

```bash
dev completion query SHELL INDEX WORD ...
```

Internal compatibility protocol used by the generated completion scripts. You
normally do not call this directly, but it remains a supported command path and
is documented here because the completion scripts depend on it.

## Environment Diagnostics

### `doctor`

```bash
dev doctor
dev doctor app-wabbit-dev
dev doctor --only publish app-wabbit-dev
dev doctor --json
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

For publish targets, `dev doctor` treats missing local credentials as advisory:
that is fine when publishing is handled by GitHub Actions. The same checks stay
strict when you actually run `dev publish` locally.

The CLI also reuses a subset of these checks as preflight for commands such as
`setup`, `release verify`, `build`, `publish`, `commit`, `project ...`, `dep ...`, and
`contributors audit`.

Use `--json` when you want a machine-readable report for editor integrations,
scripts, or CI diagnostics.

Use `--only` to narrow the report to either:

- one or more raw check IDs such as `gradle`, `config`, or `publish-pypi`
- one or more command readiness groups such as `build`, `publish`, or `commit`

Optional targets scope project- and publish-related checks to the selected
project closure.

## Documentation

### `verify`

```bash
dev verify
```

Lists the slower workflow-oriented verification entrypoints:

- `verify docs`
- `verify release`
- `verify security`
- `verify list`

These are the visible grouped verification commands shown by `dev --help`.
Compatibility entrypoints such as `docs check`, `release verify`, and
`security scan` remain supported and are documented below.

### `verify list`

```bash
dev verify list
dev verify list --json
```

Prints the available verification workflows and their summaries. Use `--json`
for editor tooling, wrappers, or CI helpers that want to discover the available
verification families programmatically.

### `verify docs` / `docs check`

```bash
dev verify docs [TARGET ...] [--semantic] [--json]
dev docs check [TARGET ...] [--semantic] [--json]
```

Runs documentation validation for the selected projects.

Deterministic checks cover:

- broken internal markdown links and anchors
- unreachable external links and badges
- missing project purpose, installation, quickstart, status, docs/support links, changelog links, and example-oriented README sections
- missing docs-generation hooks for supported docs systems
- invalid Python, shell, JSON, TOML, and YAML code snippets

Use `--semantic` to add an advisory LLM-based docs review for issues such as:

- a README that still does not explain the project's purpose or value clearly
- a quickstart that exists but is not actionable for a first-time user
- examples that do not show the core use case convincingly
- docs written for the wrong audience or overselling project maturity
- a fragmented docs journey from README to deeper guides/reference
- unclear support or escalation guidance

The semantic layer is opt-in, warning-level by design, and requires an OpenAI
key from `root.private.clj` or `OPENAI_API_KEY`. It can inspect the project
structure and a few relevant local text files with constrained repo-local tools
such as path listing, grep, and file reads.

Examples:

```bash
dev verify docs
dev verify docs app-wabbit-dev
dev verify docs --semantic app-wabbit-dev
dev docs check
dev docs check app-wabbit-dev
dev docs check --semantic app-wabbit-dev
dev docs check --json jeeves
```

### `docs snippets`

```bash
dev docs snippets [TARGET ...] [--verify] [--json]
```

Runs snippet-focused validation for fenced code blocks extracted from README and
docs markdown files.

Default behavior stays intentionally cheap:

- syntax-check Python snippets
- parse prompt-style shell snippets with `bash -n`
- parse JSON, TOML, and YAML snippets when supported
- report unsupported fenced languages without turning them into blocking errors

Optional deeper verification:

- `--verify`: enable project-specific deeper verification where the project
  type supports it, such as Python snippet hook tests or one coarse Gradle
  verification build

`--verify` is honest by design: for Gradle projects it validates the project
build or publication path as a whole, not each Kotlin snippet individually.

Examples:

```bash
dev docs snippets
dev docs snippets python-lang-mu
dev docs snippets --verify python-lang-mu
dev docs snippets --verify kotlin-data
dev docs snippets --json app-wabbit-dev
```

### `where`

```bash
dev where
dev where --json
```

Prints the cwd context the CLI inferred, including:

- resolved workspace root
- current configured project, if any
- current repo target, if any
- the commands that inherit project defaults from this directory
- the commands that inherit repo defaults from this directory

Use this when an AI agent or shell session is running from a nested directory
and you want to confirm what `build`, `check`, `project show`, `project repo`,
or `status` will target when you omit explicit arguments.

## Configuration and Inventory

### `config check`

```bash
dev config check
```

Parses `root.clj` and `root.private.clj` and validates:

- top-level command forms
- project and repo definitions
- library and plugin aliases
- dependency references
- feature blocks and typed config fields

Use this first when changing the config DSL or debugging setup/build behavior.

### `config cut`

```bash
dev config cut subset.clj app-wabbit-dev jeeves
```

Writes a reduced `root.clj`-style config file containing only the selected
projects and the transitive local project definitions they need.

Use this when you want a smaller extracted workspace config for debugging,
isolated builds, or handing a focused subset to another tool or agent.

### `project list`

```bash
dev project list
```

Prints the configured projects in declaration order and groups nested repo
projects beneath their containing repository. Each entry is labeled with its
detected project type such as `python`, `kotlin/jvm`, or `kotlin/kmp`.

### `project show`

```bash
dev project show [TARGET ...]
dev project show [TARGET ...] --json
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
dev project show
dev project show app-wabbit-dev
dev project show jeeves
dev project show app-wabbit-dev --json
```

With no targets from inside a configured project or repo, the command defaults
to that current project or repo. From the workspace root, pass an explicit
target to avoid dumping the full workspace.

### `project deps`

```bash
dev project deps [TARGET ...]
dev project deps [TARGET ...] --json
```

Prints just the resolved dependency list for one or more configured projects.
This is useful when `project show` is too verbose and you only want the
post-resolution dependency view.

Examples:

```bash
dev project deps
dev project deps app-wabbit-dev
dev project deps jeeves
dev project deps jeeves --json
```

With no targets from inside a configured project or repo, the command defaults
to that current project or repo. From the workspace root, pass an explicit
target to avoid dumping the full workspace.

### `project repo`

```bash
dev project repo [TARGET ...]
dev project repo [TARGET ...] --json
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
dev project repo
dev project repo app-wabbit-dev
dev project repo jeeves
dev project repo jeeves --json
```

With no targets from inside a configured project or repo, the command defaults
to that current repo. From the workspace root, omitting targets lists every
configured repo.

### `project targets`

```bash
dev project targets [TARGET ...]
dev project targets [TARGET ...] --json
```

Prints the declared Kotlin Multiplatform target platforms for matching
configured projects.

Behavior:

- with no targets from inside a configured project or repo, defaults to that current project or repo
- with no targets from the workspace root, lists every configured KMP project in declaration order
- with explicit targets, resolves project IDs, repo IDs, or paths inside configured projects or repos
- non-KMP projects are skipped rather than treated as errors

The human-readable output is grouped by project and styled similarly to
`project list`. The JSON output includes both the user-facing `platforms` list
and the raw Gradle `targetKinds`.

Examples:

```bash
dev project targets
dev project targets jeeves
dev project targets ./jeeves/client
dev project targets jeeves --json
```

### `project versions`

```bash
dev project versions PROJECT
dev project versions PROJECT --json
```

Shows release-state diagnostics for one configured project, including:

- current configured version
- reachable local tags
- remote tags when the git remote is configured
- commits after the latest version-like tag
- unpushed commit count and local dirty state
- registry visibility such as Maven Central, PyPI, NuGet, or JitPack when applicable

Use this when you need to answer “what is published, what is only tagged, and
what still exists only locally?”

## Generation, Build, and Maintenance

### `setup`

```bash
dev setup [--dev] [--local] [--commit-if-setup-only] [--json] [TARGET ...]
```

Generates or refreshes managed files from configuration.

This includes generated project files plus repo-root metadata such as
`.editorconfig` and the managed `.github` community templates for Wabbit-owned
repos.

Behavior:

- with no targets, processes every configured project
- each target can be a configured project ID, repo ID, or path inside a
  configured project or repo
- in default mode, runs PROD setup
- with `--dev`, switches to DEV mode
- with `--local`, switches to LOCAL mode and writes local dependency overlays
- with `--commit-if-setup-only`, after PROD setup finishes, auto-commits only
  when every affected repo remains on `master`, has no untracked files, and the
  remaining diffs are limited to `root.clj`, `.gitignore`, and setup-managed
  generated files
- with `--json`, emits a machine-readable summary while progress logs go to stderr

Typical uses:

```bash
dev setup
dev setup app-wabbit-dev
dev setup jeeves
dev setup --local app-datatron
dev setup --commit-if-setup-only app-wabbit-dev
dev setup app-wabbit-dev --json
```

### `build`

```bash
dev build [TARGET ...] [--json]
```

Builds configured projects in topological dependency order.

Project type behavior:

- Gradle projects: run `build`
- Python projects: syntax-check discovered `.py` files with `py_compile`

Only Gradle and Python projects are buildable through this command.

Use `--json` to emit the resolved targets, topological build order, per-project
results, and a summary count.

### `verify release` / `release verify`

```bash
dev verify release [TARGET ...] [--json]
dev release verify [TARGET ...] [--json]
```

Verifies release readiness for publishable projects in topological dependency
order without uploading artifacts.

Current backends:

- Python projects published to PyPI:
  - build wheel and sdist artifacts
  - run `twine check`
  - run `check-manifest`
  - inspect artifact metadata and packaged files
  - rely on the generated `pyproject.toml` sdist/check-manifest policy instead
    of a separate manual `MANIFEST.in`
- Gradle projects:
  - first check whether cross-repo project dependencies already exist on Maven Central
  - switch the touched Gradle root into PROD-style resolution for verification
  - Maven Central targets then run `build` and `publishToMavenLocal`
  - JetBrains Marketplace targets run `verifyPlugin` and `buildPlugin`
  - JitPack targets currently run `build`
  - restore the previous local overlay after verification when one was present

Projects that are quarantined, publish-disabled, or not yet supported by
release verification are reported explicitly instead of crashing the command.

Use `--json` to emit the resolved targets, topological verification order,
per-project results, and summary counts.

Examples:

```bash
dev verify release
dev verify release app-wabbit-dev
dev verify release jeeves
dev release verify
dev release verify app-wabbit-dev
dev release verify jeeves
dev release verify --json app-wabbit-dev
```

### `release bundle`

```bash
dev release bundle [TARGET ...] [--json]
```

Builds release artifacts suitable for GitHub Releases for publishable projects.
Use this when verification is not enough and you want the packaged output that a
release workflow would attach or upload later.

### `clean`

```bash
dev clean [TARGET ...]
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
dev cloc [TARGET ...]
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
dev duplicates FOLDER ... [--exclude PATTERN ...] [--filter PATTERN ...] [--size BYTES] [--no-default-excludes] [--zip-contents] [--weak-encrypted-zip]
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
dev llmcopy PATH ...
```

Reads files, directories, or glob patterns and copies their contents to the
clipboard using a wrapper like:

```xml
<contents path="...">
...
</contents>
```

This is intended for prompt construction and other copy/paste workflows.
After copying, it reports the total token count using GPT-5.4 tokenization.

Ignored by default:

- `.git`
- `.idea`
- `__pycache__`
- `.DS_Store`
- `Thumbs.db`

## Dependency and Release Inspection

### `dep graph`

```bash
dev dep graph [TARGET ...] [--artifacts]
```

Generates an SVG dependency graph.

- no target: graph the whole workspace
- `TARGET ...`: focus on one or more configured projects, repos, or matching paths
- `--artifacts`: include external artifacts as nodes instead of only project edges

Output is written as `dependency_graph.svg`.

### `dep updates`

```bash
dev dep updates
```

Checks the named Maven libraries defined in `root.clj` against their configured
repositories and prints newer versions when found.

This command does not resolve project-to-project dependencies. It only checks
named library aliases.

### `jitpack info`

```bash
dev jitpack info GROUP ARTIFACT [VERSION]
```

Prints JitPack metadata for an artifact, including:

- refs
- recent `master` commits
- published versions
- build metadata
- compiler-style build errors extracted from logs when a build record is missing

### `publish`

```bash
dev publish [TARGET ...]
dev publish [TARGET ...] --dry-run
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
dev check list
dev check list --json
dev check show SpdxHeaderCheck
dev check show SpdxHeaderCheck --json
dev check describe SpdxHeaderCheck
dev check [TARGET|BUNDLE|CHECK ...] [--fix]
dev check run [TARGET|BUNDLE|CHECK ...] [--fix]
```

Runs the loaded check suite against:

- a filesystem path
- a bare configured project or repo ID
- a configured project or repo ID prefixed with `:`
- `:root` to walk every configured project path

Discovery helpers:

- `check list`: show every loaded check with its scope and whether it advertises auto-fix support
- `check show CHECK`: show issue IDs, config commands, and suppression examples for one check
- `check describe CHECK`: hidden compatibility alias for `check show`
- `check config`: hidden compatibility shortcut for `config check`
- `--json`: with `check list` or `check show`, emit structured output instead of text

Run-form notes:

- one target can be provided as `.`, `:root`, a repo ID, a project ID, or a filesystem path
- bundle names such as `docs`, `security`, `kmp`, `gradle`, or `python` can appear positionally or through `--bundle`
- explicit check selectors can appear before or after the target
- these are equivalent:
  `dev check docs kotlin-base58`
  `dev check kotlin-base58 docs`
  `dev check --bundle docs kotlin-base58`

Examples:

```bash
dev check .
dev check app-wabbit-dev
dev check jeeves
dev check app-wabbit-dev/dev/cli.py
dev check :app-wabbit-dev
dev check :root --fix
dev check run . SpdxHeaderCheck
dev check show SpdxHeaderCheck
dev check . SpdxHeaderCheck
dev check docs .
dev check kotlin-base58 docs
```

Important notes:

- `dev check` and `dev check run` are equivalent
- explicit check selectors can use CLI IDs, issue IDs, or legacy Python class names
- checks honor `.gitignore`, `.checkignore`, `checks/disable`, and `checks/ignore-finding`
- `--fix` only applies to checks that supply an automatic fix callback

### `spdx headers`

```bash
dev spdx headers [TARGET] [--fix]
```

Runs only the SPDX header check. This is a focused shortcut for:

```bash
dev check TARGET SpdxHeaderCheck
```

Use `--fix` to insert or normalize headers where the check supports it.

### `secrets scan`

```bash
dev secrets scan [TARGET]
```

Runs the internal high-entropy-string check against a target path.

Examples:

```bash
dev secrets scan .
dev secrets scan :root
```

Targets can be:

- a filesystem path
- a bare configured project or repo ID
- a configured project or repo ID prefixed with `:`
- `:root` to walk every configured project path

### `verify security` / `security scan`

```bash
dev verify security [TARGET ...]
dev security scan [TARGET ...]
```

Runs external security scanners outside the normal `dev check` path. This is
opt-in because the tools can be slower, noisier, depend on local installation,
or query vulnerability databases.

Known tools:

- `gitleaks`
- `trufflehog`
- `semgrep`
- `bandit`
- `shellcheck`
- `osv-scanner`
- `pip-audit`
- `gradle-dependency-check`

Examples:

```bash
dev verify security .
dev verify security app-wabbit-dev
dev security scan .
dev security scan app-wabbit-dev
dev security scan --tool gitleaks --tool shellcheck .
dev security scan --json jeeves
```

Missing tools and non-applicable tools are reported as skipped. External command
output is written to a temp log directory and summarized on stdout. Use `--json`
for CI or scripted integrations.

### `contributors audit`

```bash
dev contributors audit
```

Audits configured repositories for contributor identities that do not match the
default git user configured in the loaded workspace metadata.

The expected identity comes from `(git-user "Name" "email@example.com")` in the
loaded workspace config.

## Git Workflow Commands

### `status`

```bash
dev status TARGET ... [--json]
```

Shows repo status for:

- a configured repo ID
- a configured project ID from `root.clj`
- any path inside a git repository

This command reports staged changes, unstaged changes, and untracked files.

Use `--json` to emit a per-repo status summary for scripts or editor
integrations.

### `commit`

```bash
dev commit [TARGET ...]
dev commit [TARGET ...] --dry-run
```

Runs PROD setup for the selected projects, groups them by repository, stages
changes, and creates commits with AI-generated messages.

Requirements:

- valid workspace configuration
- an OpenAI key in `root.private.clj`

Use `--dry-run` to print the PROD setup order and repository commit plan without
modifying files or creating commits.

### `commit verify`

```bash
dev commit verify --message-file .git/COMMIT_EDITMSG
dev commit verify --message "feat: tighten docs coverage"
dev commit verify --range origin/master..HEAD
dev commit verify --staged
dev commit verify --json
```

Validates commit messages against the commit policy, optionally including staged
diff context checks such as version/changelog coupling. This is intended for
hook integration, local preflight, and CI enforcement.

### `push`

```bash
dev push [TARGET ...]
dev push [TARGET ...] --dry-run
```

Pushes the current branch to its configured upstream when the remote can accept
the update as a fast-forward.

Target behavior:

- no target or `.`: push every distinct configured repository once
- configured repo ID: push that repo
- configured project ID: resolve the repo for that project
- filesystem path: resolve the repo containing that path

Behavior details:

- fetches the upstream remote first
- pushes only when the local branch is ahead and not behind
- refuses detached HEAD, missing-upstream, behind, or diverged states
- does not assume `master` or `origin`

Use `--dry-run` to print the resolved repositories and their pushability before
sending branch updates.

## Services and Backup

### `service`

```bash
dev service
dev service start
dev service stop
dev service status
dev service dashboard
```

Hosts the workspace monitoring surface:

- `service start`: start the macOS menubar monitor for this workspace
- `service stop`: stop the monitor and dashboard processes
- `service status`: show the current monitor and dashboard process state
- `service dashboard`: start or open the localhost dashboard

Use the optional `--interval-seconds` flag on `service start` and
`service dashboard` to tune the refresh cadence.

### `backup`

```bash
dev backup
dev backup push
dev backup restore
```

Hosts immutable restic-based repo backup commands configured through
`root.clj` backup policy and target definitions.

- `backup push`: snapshot selected repos, the current repo, or all configured repos from the workspace root
- `backup restore`: restore one repo snapshot into a destination directory

Examples:

```bash
dev backup push
dev backup push --target cold-storage app-wabbit-dev
dev backup push --dry-run
dev backup restore app-wabbit-dev --into /tmp/restore
dev backup restore --snapshot latest --json
```

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
