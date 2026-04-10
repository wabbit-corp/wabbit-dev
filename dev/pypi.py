from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from dev.caching import DEFAULT_CACHE_DB_PATH, cache
from dev.json_utils import as_dict


@dataclass
class PyPiProjectMetadata:
    latest_version: str | None
    releases: list[str]

    @classmethod
    def parse(cls, payload: object) -> PyPiProjectMetadata:
        payload_dict = as_dict(payload)
        if payload_dict is None:
            raise ValueError("PyPI metadata payload must be a JSON object.")

        info = as_dict(payload_dict.get("info"))
        releases_payload = as_dict(payload_dict.get("releases"))

        latest_version: str | None = None
        if info is not None:
            raw_latest = info.get("version")
            if isinstance(raw_latest, str) and raw_latest.strip():
                latest_version = raw_latest.strip()

        releases: list[str] = []
        if releases_payload is not None:
            for release_name in releases_payload.keys():
                if release_name.strip():
                    releases.append(release_name.strip())

        return cls(
            latest_version=latest_version,
            releases=sorted(set(releases)),
        )


def _fetch_raw_project_metadata_impl(project_name: str) -> object:
    import requests

    encoded_name = quote(project_name, safe="")
    url = f"https://pypi.org/pypi/{encoded_name}/json"  # check:ignore E_HARDCODED_URL value=https://pypi.org/pypi/
    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    payload: object = response.json()
    return payload


def _fetch_project_metadata_impl(project_name: str) -> PyPiProjectMetadata:
    return PyPiProjectMetadata.parse(fetch_raw_project_metadata(project_name))


fetch_raw_project_metadata: Callable[[str], object] = cache(path=DEFAULT_CACHE_DB_PATH)(
    _fetch_raw_project_metadata_impl
)
fetch_project_metadata: Callable[[str], PyPiProjectMetadata] = cache(path=DEFAULT_CACHE_DB_PATH)(
    _fetch_project_metadata_impl
)


__all__ = [
    "PyPiProjectMetadata",
    "fetch_project_metadata",
    "fetch_raw_project_metadata",
]
