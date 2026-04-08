from __future__ import annotations

from dev.tasks.check import check_main


def spdx_headers(project_or_dir_or_file: str | None = None, fix: bool = False) -> int:
    return check_main(project_or_dir_or_file, ["SpdxHeaderCheck"], fix)


__all__ = ["spdx_headers"]
