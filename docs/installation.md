# Installation

## Requirements

- Python 3.12 or newer
- a shell environment where `python3` is available
- workspace access if you plan to use commands that load `root.clj`

## Install the Published Package

```bash
python3 -m pip install wabbit-dev
```

This installs both `dev` and `wabbit-dev`.

After installation:

```bash
dev --help
dev doctor
```

Enable shell completion:

```bash
dev install completions
```

This writes completion scripts for both `dev` and `wabbit-dev` and registers
managed shell rc snippets. Use `dev install completions --no-rc` if you only
want the scripts written.

## Install from a Checkout

Create and activate a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
```

Install the package in editable mode:

```bash
python3 -m pip install -e .
```

Optional development and packaging tools:

```bash
python3 -m pip install -r requirements.txt -r requirements-dev.txt
```

Optional docs toolchain:

```bash
python3 -m pip install "mkdocs>=1.6,<2.0" "mkdocs-material>=9.6,<9.7" "pymdown-extensions>=10,<11"
```

Run it from the repo:

```bash
dev --help
```

The editable install also provides `wabbit-dev --help` as an explicit alias.

For a checkout-local install that stays tied to this workspace, run:

```bash
dev install app
dev install completions
```

## Workspace Expectations

Config-driven commands can run from the workspace root or any nested
subdirectory inside it. The CLI walks upward until it finds the workspace
configuration files:

- `root.clj`
- `root.private.clj`

If those files are missing, only the commands that do not require workspace
metadata will work reliably.
