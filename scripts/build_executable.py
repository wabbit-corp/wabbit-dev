#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        from PyInstaller.__main__ import run as pyinstaller_run
    except ImportError:
        print(
            "PyInstaller is not installed. Install with: pip install -r requirements-dev.txt",
            file=sys.stderr,
        )
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    entrypoint = repo_root / "dev.py"

    if not entrypoint.exists():
        print(f"Entrypoint not found: {entrypoint}", file=sys.stderr)
        return 1

    # Build from a stable module list used by runtime module loading.
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from dev.base import CHECK_MODULE_IMPORTS

    dist_dir = repo_root / "dist"
    work_dir = repo_root / "build" / "pyinstaller"
    spec_dir = repo_root / "build" / "pyinstaller-spec"

    args = [
        "--name",
        "wabbit-dev",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--collect-submodules",
        "dev.tasks",
    ]
    for module_name in CHECK_MODULE_IMPORTS:
        args.extend(["--hidden-import", module_name])
    args.append(str(entrypoint))
    pyinstaller_run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
