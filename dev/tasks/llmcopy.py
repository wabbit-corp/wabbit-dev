import io, os
from pathlib import Path
from dev.messages import error, success, info
import pyperclip

IGNORE_FILES = set([
    '.DS_Store',
    'Thumbs.db',
    'desktop.ini',
])

IGNORE_DIRS = set([
    '.git',
    '.idea',
    '__pycache__'
])

def llmcopy(path: Path) -> None:
    buf = io.StringIO()

    # walk all files, ignoring files and directories in IGNORE_FILES and IGNORE_DIRS
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            if file in IGNORE_FILES:
                continue

            path = Path(f"{root}/{file}")

            info(f"Adding {path}")
            
            # print(path)
            buf.write(f'<contents path="{path}">\n')
            with open(path, 'rt', encoding='utf-8') as f:
                data = f.read()
                buf.write(data)
                if not data.endswith('\n'):
                    buf.write('\n')
            buf.write(f'</contents> (end of {path})\n')
            buf.write("\n\n")
    
    # copy to clipboard
    pyperclip.copy(buf.getvalue())
    success("Copied to clipboard")