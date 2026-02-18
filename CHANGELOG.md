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
