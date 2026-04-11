from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from dev.caching import DEFAULT_CACHE_DB_PATH, cache
from dev.dotnet import NUGET_V3_INDEX_URL
from dev.json_utils import as_dict, as_list


@dataclass(frozen=True)
class NuGetPackageMetadata:
    latest_version: str | None
    versions: tuple[str, ...]

    @classmethod
    def parse(cls, payload: object) -> NuGetPackageMetadata:
        payload_dict = as_dict(payload)
        if payload_dict is None:
            raise ValueError("NuGet metadata payload must be a JSON object.")

        versions_payload = as_list(payload_dict.get("versions"))
        versions: list[str] = []
        if versions_payload is not None:
            for item in versions_payload:
                if isinstance(item, str) and item.strip():
                    versions.append(item.strip())

        latest_version = versions[-1] if versions else None
        return cls(
            latest_version=latest_version,
            versions=tuple(sorted(set(versions))),
        )


def _flat_container_index_url(package_id: str) -> str:
    normalized = package_id.strip().lower()
    encoded_name = quote(normalized, safe="")
    return f"https://api.nuget.org/v3-flatcontainer/{encoded_name}/index.json"


def _fetch_raw_package_metadata_impl(package_id: str) -> object:
    import requests

    response = requests.get(
        _flat_container_index_url(package_id),
        headers={"Accept": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    payload: object = response.json()
    return payload


def _fetch_package_metadata_impl(package_id: str) -> NuGetPackageMetadata:
    return NuGetPackageMetadata.parse(fetch_raw_package_metadata(package_id))


fetch_raw_package_metadata: Callable[[str], object] = cache(path=DEFAULT_CACHE_DB_PATH)(
    _fetch_raw_package_metadata_impl
)
fetch_package_metadata: Callable[[str], NuGetPackageMetadata] = cache(path=DEFAULT_CACHE_DB_PATH)(
    _fetch_package_metadata_impl
)


__all__ = [
    "NUGET_V3_INDEX_URL",
    "NuGetPackageMetadata",
    "fetch_package_metadata",
    "fetch_raw_package_metadata",
]
