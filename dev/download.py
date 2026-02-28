import os
import time
from datetime import datetime

import dateparser
import requests


def save_uri(uri: str, path: str) -> None:
    needs_download = True

    if os.path.exists(path):
        if os.path.isdir(path):
            raise Exception(f"{path} is a directory.")

        # Get the old modification time.
        old_mtime = os.path.getmtime(path)
        print(f"Old file modification time: {old_mtime}")

        # Get the old ETag.
        old_etag = None
        if os.path.exists(path + ".etag"):
            if os.path.isdir(path + ".etag"):
                print(f"{path + '.etag'} is a directory.")
            else:
                with open(path + ".etag") as fin:
                    old_etag = fin.read().strip()
                print(f"Old ETag: {old_etag}")

        head_mtime: float | None = None
        head_etag = None
        head_status = None

        try:
            response = requests.head(
                uri,
                headers={"If-Modified-Since": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(old_mtime))},
            )

            head_status = response.status_code

            # Parse Last-Modified if it exists
            head_mtime_raw = response.headers.get("Last-Modified", None)
            if head_mtime_raw is not None:
                parsed_head_mtime = dateparser.parse(head_mtime_raw)
                if isinstance(parsed_head_mtime, datetime):
                    head_mtime = time.mktime(parsed_head_mtime.timetuple())
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

        if head_etag is not None and head_etag != old_etag:
            with open(path + ".etag", "w+") as fout:
                fout.write(head_etag)

    if not needs_download:
        print(f"No need to download {uri} to {path}.")
        return

    print(f"Downloading {uri} to {path}.")
    response = requests.get(uri)
    assert response.status_code == 200
    with open(path, "w+") as fout:
        fout.write(response.text)

    last_modified: float | None = None
    try:
        last_modified_raw = response.headers.get("Last-Modified", None)
        if last_modified_raw is not None:
            parsed_last_modified = dateparser.parse(last_modified_raw)
            if isinstance(parsed_last_modified, datetime):
                last_modified = time.mktime(parsed_last_modified.timetuple())
    except Exception as e:
        print(e)
        print("Could not get last-modified date.")

    if last_modified is not None:
        os.utime(path, (last_modified, last_modified))


__all__ = ["save_uri"]
