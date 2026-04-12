from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from git import Repo
from git.exc import BadName, GitCommandError, InvalidGitRepositoryError, NoSuchPathError

LEGACY_GENERATED_GITIGNORE_LINES = frozenset(
    {
        "/.is-dev-mode",
        "/.is-local-mode",
        "/.is-ij-mode",
    }
)


def merge_gitignore_content(
    generated_content: str,
    existing_content: str | None,
    *,
    ignored_extra_lines: Collection[str] = LEGACY_GENERATED_GITIGNORE_LINES,
) -> str:
    generated_lines = generated_content.rstrip("\n").splitlines()
    if not existing_content:
        return "\n".join(generated_lines).rstrip("\n") + "\n"

    merged_lines = list(generated_lines)
    seen = set(generated_lines)
    extra_lines: list[str] = []
    for line in existing_content.rstrip("\n").splitlines():
        if line in ignored_extra_lines:
            continue
        if line in seen:
            continue
        extra_lines.append(line)
        seen.add(line)

    if extra_lines:
        if merged_lines and merged_lines[-1] != "":
            merged_lines.append("")
        merged_lines.extend(extra_lines)
    return "\n".join(merged_lines).rstrip("\n") + "\n"


def load_tracked_file_text(repo_root: Path, relative_path: str) -> str | None:
    if not (repo_root / ".git").exists():
        return None

    try:
        repo = Repo(repo_root)
    except (InvalidGitRepositoryError, NoSuchPathError, OSError, ValueError):
        return None

    try:
        if not repo.head.is_valid():
            return None
        tracked_text = repo.git.show(f"HEAD:{relative_path}")
        return tracked_text if isinstance(tracked_text, str) else None
    except (BadName, GitCommandError, OSError, ValueError):
        return None
    finally:
        repo.close()


def merged_gitignore_text(directory: Path, generated_content: str) -> str:
    gitignore_path = directory / ".gitignore"
    tracked_content = load_tracked_file_text(directory, ".gitignore")
    merged_tracked = merge_gitignore_content(generated_content, tracked_content)
    existing_content = gitignore_path.read_text(encoding="utf-8") if gitignore_path.is_file() else None
    return merge_gitignore_content(merged_tracked, existing_content)


__all__ = [
    "LEGACY_GENERATED_GITIGNORE_LINES",
    "load_tracked_file_text",
    "merge_gitignore_content",
    "merged_gitignore_text",
]
