# Development

## Local Verification

Run the project checks before opening a PR:

```bash
pytest -q
ruff check .
black --check .
mypy .
mkdocs build --strict
```

## Generated Files

`wabbit-dev` is intentionally configuration-driven. Changes to the config model,
template rendering, or setup behavior often require rerunning `setup` so the
generated files match the source of truth in `root.clj`.

Typical workflow:

```bash
dev config check
dev setup --local app-wabbit-dev
dev check app-wabbit-dev
```

## Docs Maintenance

The CLI help and docs should stay aligned:

- update `dev/typed_cli.py` when command behavior or syntax changes
- update [Command Reference](commands.md) when user-facing behavior changes
- update [Configuration Reference](configuration.md) when the config DSL changes
- rebuild docs with `mkdocs build --strict`

## Helpful Internal Entry Points

- `dev/cli.py`: main user-facing CLI
- `dev/config.py`: `root.clj` loader and config model
- `dev/config_typed.py`: typed DSL definitions and tagged config commands
- `dev/tasks/`: command implementations
- `tests/`: regression coverage for parsing, setup, publishing, and CLI behavior
