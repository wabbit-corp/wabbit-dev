from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dev import download


def test_save_uri_writes_binary_content_and_etag_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "asset.bin"

    def fake_get(url: str, timeout: float) -> SimpleNamespace:
        assert url == "https://example.com/asset.bin"
        assert timeout == download.REQUEST_TIMEOUT_SECONDS
        return SimpleNamespace(
            status_code=200,
            content=b"\xff\x00\x01",
            headers={"ETag": '"etag-1"'},
        )

    monkeypatch.setattr(download.requests, "get", fake_get)

    download.save_uri("https://example.com/asset.bin", str(target))

    assert target.read_bytes() == b"\xff\x00\x01"
    assert target.with_name("asset.bin.etag").read_text(encoding="utf-8") == '"etag-1"'


def test_save_uri_does_not_update_etag_if_download_fails_after_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "asset.txt"
    target.write_text("old\n", encoding="utf-8")
    etag_path = target.with_name("asset.txt.etag")
    etag_path.write_text('"old-etag"', encoding="utf-8")

    def fake_head(url: str, headers: dict[str, str], timeout: float) -> SimpleNamespace:
        assert timeout == download.REQUEST_TIMEOUT_SECONDS
        return SimpleNamespace(
            status_code=200,
            headers={"ETag": '"new-etag"'},
        )

    def fake_get(url: str, timeout: float) -> SimpleNamespace:
        assert timeout == download.REQUEST_TIMEOUT_SECONDS
        return SimpleNamespace(
            status_code=500,
            content=b"",
            headers={},
        )

    monkeypatch.setattr(download.requests, "head", fake_head)
    monkeypatch.setattr(download.requests, "get", fake_get)

    with pytest.raises(AssertionError):
        download.save_uri("https://example.com/asset.txt", str(target))

    assert target.read_text(encoding="utf-8") == "old\n"
    assert etag_path.read_text(encoding="utf-8") == '"old-etag"'


def test_save_uri_passes_timeout_to_head_and_get(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "asset.txt"
    target.write_text("old\n", encoding="utf-8")

    observed: list[tuple[str, float]] = []

    def fake_head(url: str, headers: dict[str, str], timeout: float) -> SimpleNamespace:
        observed.append(("head", timeout))
        return SimpleNamespace(status_code=200, headers={"ETag": '"new-etag"'})

    def fake_get(url: str, timeout: float) -> SimpleNamespace:
        observed.append(("get", timeout))
        return SimpleNamespace(status_code=200, content=b"new\n", headers={})

    monkeypatch.setattr(download.requests, "head", fake_head)
    monkeypatch.setattr(download.requests, "get", fake_get)

    download.save_uri("https://example.com/asset.txt", str(target))

    assert observed == [
        ("head", download.REQUEST_TIMEOUT_SECONDS),
        ("get", download.REQUEST_TIMEOUT_SECONDS),
    ]
