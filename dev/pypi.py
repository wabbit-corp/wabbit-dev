from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote

from dev.caching import DEFAULT_CACHE_DB_PATH, cache
from dev.json_utils import as_dict


@dataclass
class PyPiProjectMetadata:
    latest_version: str | None
    releases: list[str]
    home_page: str | None = None
    project_url: str | None = None
    project_urls: dict[str, str] = field(default_factory=dict)

    @classmethod
    def parse(cls, payload: object) -> PyPiProjectMetadata:
        payload_dict = as_dict(payload)
        if payload_dict is None:
            raise ValueError("PyPI metadata payload must be a JSON object.")

        info = as_dict(payload_dict.get("info"))
        releases_payload = as_dict(payload_dict.get("releases"))
        project_urls_payload = None if info is None else as_dict(info.get("project_urls"))

        latest_version: str | None = None
        home_page: str | None = None
        project_url: str | None = None
        if info is not None:
            raw_latest = info.get("version")
            if isinstance(raw_latest, str) and raw_latest.strip():
                latest_version = raw_latest.strip()
            raw_home_page = info.get("home_page")
            if isinstance(raw_home_page, str) and raw_home_page.strip():
                home_page = raw_home_page.strip()
            raw_project_url = info.get("project_url")
            if isinstance(raw_project_url, str) and raw_project_url.strip():
                project_url = raw_project_url.strip()

        releases: list[str] = []
        if releases_payload is not None:
            for release_name in releases_payload.keys():
                if release_name.strip():
                    releases.append(release_name.strip())

        project_urls: dict[str, str] = {}
        if project_urls_payload is not None:
            for key, value in project_urls_payload.items():
                if isinstance(key, str) and isinstance(value, str):
                    normalized_key = key.strip()
                    normalized_value = value.strip()
                    if normalized_key and normalized_value:
                        project_urls[normalized_key] = normalized_value

        return cls(
            latest_version=latest_version,
            releases=sorted(set(releases)),
            home_page=home_page,
            project_url=project_url,
            project_urls=project_urls,
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
