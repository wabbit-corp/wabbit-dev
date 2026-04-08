# Installation

## Requirements

- Python 3.12 or newer
- a shell environment where `python3` is available
- workspace access if you plan to use commands that load `root.clj`

## Install the Published Package

```bash
python3 -m pip install wabbit-dev
```

After installation:

```bash
wabbit-dev --help
wabbit-dev doctor
```

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
python3 dev.py --help
```

## Workspace Expectations

Most commands expect to run from the workspace root, because that is where the
configuration files live:

- `root.clj`
- `root.private.clj`

If those files are missing, only the commands that do not require workspace
metadata will work reliably.
