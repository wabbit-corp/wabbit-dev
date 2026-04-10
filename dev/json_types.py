from __future__ import annotations

from collections.abc import Mapping, Sequence

type JSONPrimitive = None | bool | int | float | str
type JSONValue = JSONPrimitive | Sequence[JSONValue] | Mapping[str, JSONValue]
type JSONObject = dict[str, JSONValue]
type JSONArray = list[JSONValue]

__all__ = [
    "JSONArray",
    "JSONObject",
    "JSONPrimitive",
    "JSONValue",
]
