# AGENTS

Use .venv python venv.
Run tests (especially relevant tests) regularly while editing.
Always keep CHANGELOG.md up to date with meaningful entries.

Python coding rules:
1. Do not use casts unless absolutely necessary.
2. Do not use type: ignore comments unless absolutely necessary.
3. Prefer explicit imports over wildcard imports.
4. Prefer hypotheses / property-based tests where applicable.
5. Make your code as acyclic as possible (avoid circular imports).
6. Practice defensive programming (validate inputs using assertions or explicit checks, validate state).
7. Use logging with appropriate log levels instead of print statements.
8. Use explicit dependency injection (pass dependencies as parameters) where applicable.

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
