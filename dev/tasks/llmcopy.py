import io
from pathlib import Path

import pyperclip

from dev.messages import info, success
from dev.tokens import count_text_tokens_for_gpt_5_4

IGNORE_FILES: set[str] = set(
    [
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
    ]
)

IGNORE_DIRS: set[str] = set([".git", ".idea", "__pycache__"])


def llmcopy(paths: list[str]) -> None:
    added_paths: set[Path] = set()
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
            with open(p, encoding="utf-8") as f:
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

    copied_text = buf.getvalue()
    token_count = count_text_tokens_for_gpt_5_4(copied_text)

    pyperclip.copy(copied_text)

    file_count = len(added_paths)
    file_label = "file" if file_count == 1 else "files"
    success(f"Copied to clipboard: {file_count:,} {file_label}, {token_count.total_tokens:,} GPT-5.4 tokens")
