# Changelog

## Unreleased (2026-02-17)
- Enforce `Semver Impact: ...` in suggested and edited commit messages.
- Add repository-level `AGENTS.md` workflow and commit message policy guidance.
- Add JVM version config parsing (`jvm-version`, `jvm-defaults`) and propagate Java/Kotlin JVM target values to setup rendering.
- Align root project metadata and dependency constraints in `pyproject.toml` and requirements files.
- Add PyInstaller build script and README packaging instructions for producing a single executable.
- Ignore temporary setup cache artifacts (`.dev.cache.db`, `test/tmp-setup-*`, `*.bak`).
- Split CLI entrypoint into `dev/cli.py` and add `setup --local` mode marker handling.
- Normalize Python config keywords to kebab-case and drop legacy `python_*` keyword forms.
- Simplify `PythonProject` internals by removing redundant `python_` field prefixes.
- Ensure project directories are created/validated before per-project setup writes files.
- Fix Python target-version derivation to use the minimum supported version from `requires-python` specifiers.
- Stop deriving import-linter root packages from layer definitions; fall back to source sets/packages only.
- Guard setup-time license/dependency lookups and emit errors for unknown keys instead of raising `KeyError`.
- Normalize setup task typing annotations to built-in generics (`list`/`dict`/`tuple`) for Python 3.10 style consistency.
- Remove `github` module/client name shadowing in setup context creation by renaming the GitHub client handle.
- Deduplicate WABBIT legal/docs file generation with a shared setup helper used by Python and Gradle project setup.
- Deduplicate setup banner generation with a shared helper used by Python and Gradle setup flows.
- Use `parents=True, exist_ok=True` for setup-time commit message parent directory creation.
