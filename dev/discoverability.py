from __future__ import annotations

from collections.abc import Iterable, Sequence
from difflib import get_close_matches
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dev.config import Config, Project


def suggest_matches(
    value: str,
    choices: Iterable[str],
    *,
    limit: int = 3,
    cutoff: float = 0.45,
) -> list[str]:
    options = [choice for choice in choices if choice]
    if not value or not options:
        return []

    direct = get_close_matches(value, options, n=limit, cutoff=cutoff)
    if direct:
        return direct

    lower_to_original: dict[str, str] = {}
    for choice in options:
        lower_to_original.setdefault(choice.lower(), choice)
    lowered = get_close_matches(value.lower(), list(lower_to_original), n=limit, cutoff=cutoff)
    return [lower_to_original[match] for match in lowered]


def _format_choice(choice: str) -> str:
    return repr(choice)


def format_suggestions(suggestions: Sequence[str]) -> str:
    quoted = [_format_choice(suggestion) for suggestion in suggestions]
    if not quoted:
        return ""
    if len(quoted) == 1:
        return quoted[0]
    if len(quoted) == 2:
        return f"{quoted[0]} or {quoted[1]}"
    return f"{', '.join(quoted[:-1])}, or {quoted[-1]}"


def did_you_mean_suffix(
    value: str,
    choices: Iterable[str],
    *,
    limit: int = 3,
    cutoff: float = 0.45,
) -> str:
    suggestions = suggest_matches(value, choices, limit=limit, cutoff=cutoff)
    if not suggestions:
        return ""
    return f" Did you mean {format_suggestions(suggestions)}?"


def unknown_name_message(
    kind: str,
    value: str,
    choices: Iterable[str],
    *,
    prefix: str = "Unknown",
    limit: int = 3,
    cutoff: float = 0.45,
) -> str:
    return f"{prefix} {kind}: {value!r}.{did_you_mean_suffix(value, choices, limit=limit, cutoff=cutoff)}"


def require_project(config: Config, project_id: str, *, kind: str = "project") -> Project:
    project = config.defined_projects.get(project_id)
    if project is None:
        raise ValueError(unknown_name_message(kind, project_id, config.defined_projects))
    return project


__all__ = [
    "did_you_mean_suffix",
    "format_suggestions",
    "require_project",
    "suggest_matches",
    "unknown_name_message",
]
