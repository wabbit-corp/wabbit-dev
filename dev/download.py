import os
import time
from datetime import datetime
from pathlib import Path

import dateparser
import requests

REQUEST_TIMEOUT_SECONDS = 10.0


def _parse_http_datetime(raw_value: str | None) -> float | None:
    if raw_value is None:
        return None

    parsed = dateparser.parse(raw_value)
    if not isinstance(parsed, datetime):
        return None
    return time.mktime(parsed.timetuple())


def save_uri(uri: str, path: str) -> None:
    target_path = Path(path)
    etag_path = target_path.with_name(target_path.name + ".etag")
    needs_download = True

    if target_path.exists():
        if target_path.is_dir():
            raise Exception(f"{path} is a directory.")

        # Get the old modification time.
        old_mtime = target_path.stat().st_mtime
        print(f"Old file modification time: {old_mtime}")

        # Get the old ETag.
        old_etag = None
        if etag_path.exists():
            if etag_path.is_dir():
                print(f"{etag_path} is a directory.")
            else:
                with etag_path.open(encoding="utf-8") as fin:
                    old_etag = fin.read().strip()
                print(f"Old ETag: {old_etag}")

        head_mtime: float | None = None
        head_etag = None
        head_status = None

        try:
            response = requests.head(
                uri,
                headers={"If-Modified-Since": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(old_mtime))},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            head_status = response.status_code

            # Parse Last-Modified if it exists
            head_mtime = _parse_http_datetime(response.headers.get("Last-Modified"))
            if head_mtime is not None:
                print(f"Last modification time: {head_mtime}")

            head_etag = response.headers.get("ETag", None)
            if head_etag is not None:
                head_etag = head_etag.strip()
                print(f"New ETag: {head_etag}")
        except Exception as e:
            print(e)
            print("Failed to query HEAD.")

        if head_status == 304:
            print("Server responded with 304.")
            needs_download = False

        if head_etag == old_etag:
            print("Same ETag.")
            needs_download = False

        if head_mtime == old_mtime or (head_mtime is not None and head_mtime <= old_mtime):
            print("Modified at an earlier date.")
            needs_download = False

    if not needs_download:
        print(f"No need to download {uri} to {path}.")
        return

    print(f"Downloading {uri} to {path}.")
    response = requests.get(uri, timeout=REQUEST_TIMEOUT_SECONDS)
    assert response.status_code == 200
    body = response.content
    target_path.write_bytes(body)

    try:
        last_modified = _parse_http_datetime(response.headers.get("Last-Modified"))
    except Exception as e:
        print(e)
        print("Could not get last-modified date.")
        last_modified = None

    response_etag = response.headers.get("ETag")
    if response_etag is not None:
        etag_path.write_text(response_etag.strip(), encoding="utf-8")

    if last_modified is not None:
        os.utime(target_path, (last_modified, last_modified))


__all__ = ["REQUEST_TIMEOUT_SECONDS", "save_uri"]
