from __future__ import annotations

from typing import cast


def as_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def as_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast(list[object], value)


def as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def as_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default


def as_optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def as_string_list(value: object) -> list[str]:
    items = as_list(value)
    if items is None:
        return []
    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
    return out


def as_string_dict_list(value: object) -> list[dict[str, str]]:
    items = as_list(value)
    if items is None:
        return []
    out: list[dict[str, str]] = []
    for item in items:
        item_dict = as_dict(item)
        if item_dict is None:
            continue
        row: dict[str, str] = {}
        for key, row_value in item_dict.items():
            if isinstance(row_value, str):
                row[key] = row_value
        out.append(row)
    return out


__all__ = [
    "as_bool",
    "as_dict",
    "as_list",
    "as_optional_str",
    "as_str",
    "as_string_dict_list",
    "as_string_list",
]
