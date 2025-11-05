from typing import List
import io, os
from pathlib import Path
from dev.messages import error, success, info
import pyperclip

IGNORE_FILES = set(
    [
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
    ]
)

IGNORE_DIRS = set([".git", ".idea", "__pycache__"])


def llmcopy(paths: List[str]) -> None:
    added_paths = set()
    buf = io.StringIO()

    def go(p: Path) -> None:
        if p.is_dir():
            if p.name in IGNORE_DIRS:
                info(f"Ignoring directory {p}")
                return
            for item in p.iterdir():
                go(item)
        else:
            if p.name in IGNORE_FILES:
                info(f"Ignoring file {p}")
                return
            if p in added_paths:
                info(f"Already added {p}, skipping")
                return
            added_paths.add(p)
            info(f"Adding {p}")
            buf.write(f'<contents path="{p}">\n')
            with open(p, "rt", encoding="utf-8") as f:
                data = f.read()
                buf.write(data)
                if not data.endswith("\n"):
                    buf.write("\n")
            buf.write(f"</contents> (end of {p})\n")
            buf.write("\n\n")

    for path in paths:
        if "*" not in path:
            go(Path(path))
        else:
            # Use rglob to handle wildcards
            for p in Path(".").rglob(path):
                go(p)

    # copy to clipboard
    pyperclip.copy(buf.getvalue())
    success("Copied to clipboard")
