from __future__ import annotations

from pathlib import Path

import pathspec


def read_ignore_patterns(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


class IgnoreMatcher:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._specs_by_dir: dict[Path, pathspec.PathSpec | None] = {}

    def _spec_for_dir(self, directory: Path) -> pathspec.PathSpec | None:
        resolved_dir = directory.resolve()
        cached = self._specs_by_dir.get(resolved_dir)
        if cached is not None or resolved_dir in self._specs_by_dir:
            return cached

        patterns: list[str] = []
        if resolved_dir == self.root:
            patterns.append("/.git")
        patterns.extend(read_ignore_patterns(resolved_dir / ".gitignore"))
        patterns.extend(read_ignore_patterns(resolved_dir / ".checkignore"))

        if not patterns:
            self._specs_by_dir[resolved_dir] = None
            return None

        spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.gitwildmatch.GitWildMatchPattern,
            patterns,
        )
        self._specs_by_dir[resolved_dir] = spec
        return spec

    def matches(self, path: Path | str, *, is_dir: bool) -> bool:
        absolute_path = Path(path)
        if not absolute_path.is_absolute():
            absolute_path = absolute_path.absolute()
        try:
            absolute_path.relative_to(self.root)
        except ValueError:
            return False

        if absolute_path == self.root:
            return False

        ignored = False
        current_dir = absolute_path.parent

        while True:
            try:
                current_dir.relative_to(self.root)
            except ValueError:
                break
            spec = self._spec_for_dir(current_dir)
            if spec is not None:
                relative = absolute_path.relative_to(current_dir).as_posix()
                candidate = relative + "/" if is_dir and not relative.endswith("/") else relative
                result = spec.check_file(candidate)
                if result.index is not None:
                    ignored = bool(result.include)
            if current_dir == self.root:
                break
            current_dir = current_dir.parent

        return ignored

    def __call__(self, path: str, is_dir: bool) -> bool:
        return self.matches(path, is_dir=is_dir)
