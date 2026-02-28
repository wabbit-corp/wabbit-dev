# AGENTS

General Guidelines:
1. Never hardcode secrets, API keys, paths, or environment-specific values in the codebase.
2. Follow the DRY (Don't Repeat Yourself) principle. Refactor common code into reusable functions, data types, and modules.

## Python Coding Guidelines

Use .venv python venv.
Run tests (especially relevant tests) regularly while editing.
Always keep CHANGELOG.md up to date with meaningful entries.
Place pytest tests under `tests/` (not `dev/`).

Python coding rules:
* Do not use casts unless absolutely necessary.
* Do not use type: ignore comments unless absolutely necessary.
* Prefer explicit imports over wildcard imports.
* Prefer hypotheses / property-based tests where applicable.
* Make your code as acyclic as possible (avoid circular imports).
* Practice defensive programming (validate inputs using assertions or explicit checks, validate state).
* Use logging with appropriate log levels instead of print statements.
* Use explicit dependency injection (pass dependencies as parameters) where applicable.
* Use @dataclass for data and Union[...] for sum types as if you are writing in a functional programming style with algebraic data types.
* Prefer plain functions, and algebraic data types over classes and OOP.

## Commit Message Policy

When generating commit messages for this repository, use this structure:

1. A concise subject line.
2. Optional body lines with context that is directly inferable from the diff.
3. A trailing semantic-impact line in exactly this form:

```
Semver Impact: MAJOR
```

Allowed values are `MAJOR`, `MINOR`, `PATCH`, `NONE`.

### Semver impact rules

- Use `NONE` for docs/comments/readme/build config/test-only changes and dev/test dependency changes that do not affect published runtime behavior.
- If runtime/compile dependency versions change:
  - major version change => `MAJOR`
  - minor version change => `MINOR`
  - patch version change => `PATCH`
- If multiple changes exist, choose the highest impact.
- Use `MAJOR` for clearly backward-incompatible API changes.
- Use `MINOR` for backward-compatible new functionality.
- Use `PATCH` for bug fixes and patch-level runtime changes.
