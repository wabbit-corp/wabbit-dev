from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from dev.caching import DEFAULT_CACHE_DB_PATH, cache


@dataclass
class PyPiProjectMetadata:
    latest_version: str | None
    releases: list[str]

    @classmethod
    def parse(cls, payload: object) -> "PyPiProjectMetadata":
        if not isinstance(payload, dict):
            raise ValueError("PyPI metadata payload must be a JSON object.")

        info = payload.get("info")
        releases_payload = payload.get("releases")

        latest_version: str | None = None
        if isinstance(info, dict):
            raw_latest = info.get("version")
            if isinstance(raw_latest, str) and raw_latest.strip():
                latest_version = raw_latest.strip()

        releases: list[str] = []
        if isinstance(releases_payload, dict):
            for release_name in releases_payload.keys():
                if isinstance(release_name, str) and release_name.strip():
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
