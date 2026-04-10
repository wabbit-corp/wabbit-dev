#!/usr/bin/env python3

"""
* [x] Check that there are no unnecessary executable file modes.
* [ ] Check that there are no executable files that lack a shebang line (i.e. a file is marked executable but probably shouldn't be, or it needs a shebang).
* [ ] Check that files that are supposed to be executable (e.g., scripts) have the correct executable permissions.
"""

from __future__ import annotations

import argparse
import logging
import os
import stat
import sys  # Added for stderr

from dev.checks.base import FileCheck, FileContext, IssueType

LOGGER = logging.getLogger(__name__)

# --- Configuration ---
EXECUTABLE_EXTENSIONS = {
    ".bat",
    ".bin",
    ".cmd",
    ".com",
    ".exe",
    ".ps1",
    ".run",
    ".sh",
}

E_SUSPICIOUS_EXECUTABLE_FILE_MODE = IssueType(
    "E_SUSPICIOUS_EXECUTABLE_FILE_MODE",
    "File is marked executable but does not appear to be an executable script or binary.",
)

# --- Helper Functions ---


def has_shebang(filepath: str) -> bool:
    """
    Checks if a file starts with a shebang ('#!').
    Returns False if the file can't be read or is empty.
    """
    try:
        with open(filepath, "rb") as f:
            return f.read(2) == b"#!"
    except OSError:
        # print(f"Warning: Could not read {filepath} to check for shebang.", file=sys.stderr)
        return False
    except Exception:
        # print(f"Warning: Error reading {filepath}: {e}", file=sys.stderr)
        return False


def is_elf_exe_mach(filepath: str) -> str | None:
    """
    Checks if a file is an ELF, a Windows EXE, or a Mach-O (Darwin) executable
    by examining the first few bytes (the file "magic numbers").

    Returns a string among {"elf", "exe", "mach-o"} if recognized,
    or None if it does not match these known file types.
    """
    try:
        with open(filepath, "rb") as f:
            # Read first 4 bytes
            magic = f.read(4)

        # -- Check ELF --
        # ELF files start with 0x7F, 'E', 'L', 'F'
        if magic == b"\x7fELF":
            return "elf"

        # -- Check Windows EXE (PE) --
        # Windows EXEs normally start with 'MZ' (0x4D, 0x5A)
        # Usually followed by other header bytes, but 'MZ' is the key signature
        if magic.startswith(b"MZ"):
            return "exe"

        # -- Check Mach-O (Darwin) --
        # 32-bit Mach-O: 0xFEEDFACE (little-endian: 0xCEFAEDFE)
        # 64-bit Mach-O: 0xFEEDFACF (little-endian: 0xCFFAEDFE)
        # On arm64 Macs, you’ll typically see the 64-bit Mach-O magic (0xFEEDFACF).
        # We can check for any known Mach-O “magic” or “fat” magic.
        mach_o_signatures = {
            b"\xfe\xed\xfa\xce",  # 0xFEEDFACE  (32-bit big-endian)
            b"\xce\xfa\xed\xfe",  # 0xCEFAEDFE  (32-bit little-endian)
            b"\xfe\xed\xfa\xcf",  # 0xFEEDFACF  (64-bit big-endian)
            b"\xcf\xfa\xed\xfe",  # 0xCFFAEDFE  (64-bit little-endian)
            b"\xca\xfe\xba\xbe",  # Fat/universal binaries
            b"\xbe\xba\xfe\xca",
        }
        if magic in mach_o_signatures:
            return "mach-o"

        return None
    except OSError:
        return None
    except Exception:
        return None


# assert is_elf_exe_mach("trufflehog")


def is_executable(filepath: str) -> bool:
    """
    Checks if the file has execute permission for user, group, or others.
    """
    try:
        mode = os.stat(filepath).st_mode
        return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except OSError:
        return False


def is_suspicious_executable(filepath: str) -> bool:
    """
    Returns True when a regular non-link file has execute bits set but does not
    look like a script or binary that should be executable.
    """
    if os.path.islink(filepath) or not os.path.isfile(filepath):
        return False
    if not is_executable(filepath):
        return False

    _, ext = os.path.splitext(filepath)
    ext_lower = ext.lower()
    return not (has_shebang(filepath) or is_elf_exe_mach(filepath) is not None or ext_lower in EXECUTABLE_EXTENSIONS)


def remove_execute_permission(filepath: str) -> bool:
    """
    Removes execute permissions (user, group, other) from a file.
    Returns True on success, False on failure.
    """
    try:
        current_mode = os.stat(filepath).st_mode
        # Create a mask to remove all execute bits
        execute_mask = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        # Apply the mask using bitwise AND with the inverted mask
        new_mode = current_mode & ~execute_mask
        # Only apply if the mode actually changed
        if new_mode != current_mode:
            os.chmod(filepath, new_mode)
            LOGGER.info("Removed execute permission from %s", filepath)
            return True
        else:
            # No execute permission was set initially
            return True  # Considered success as the state is correct
    except OSError as e:
        LOGGER.error("Could not change permissions for %s: %s", filepath, e)
        return False
    except Exception as e:
        LOGGER.error("Unexpected error fixing %s: %s", filepath, e)
        return False


def remove_ds_store(filepath: str) -> bool:
    """
    Removes a macOS .DS_Store file.
    Returns True on success, False on failure.
    """
    try:
        os.remove(filepath)
        LOGGER.info("Removed macOS system file %s", filepath)
        return True
    except OSError as e:
        LOGGER.warning("Could not remove %s: %s", filepath, e)
        return False
    except Exception as e:
        LOGGER.warning("Unexpected error removing %s: %s", filepath, e)
        return False


def find_and_process_files(root_dir: str, fix_files: bool = False) -> tuple[list[str], int, int]:
    """
    Walks the directory tree, finds suspicious files, and optionally fixes them.
    Returns a list of files that were identified as suspicious.
    """
    suspicious_files_found: list[str] = []
    fixed_count = 0
    error_count = 0

    LOGGER.info("Scanning directory: %s", os.path.abspath(root_dir))
    if fix_files:
        LOGGER.info("Fix mode enabled: attempting to remove execute permissions from suspicious files.")

    # trufflehog git file://./kotlin-base58

    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True):
        # Optional: Skip directories like .git, venv, etc.
        dirnames[:] = [d for d in dirnames if d not in [".git", ".svn", "venv", "__pycache__", "node_modules"]]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)

            if filename == ".DS_Store":
                if fix_files and not remove_ds_store(filepath):
                    error_count += 1
                continue

            try:
                # Process only regular files (skip symlinks, etc.)
                if is_suspicious_executable(filepath):
                    _, ext = os.path.splitext(filename)
                    suspicious_files_found.append(filepath)
                    LOGGER.info("Suspicious executable file mode: %s (extension: %s)", filepath, ext)

                    # If fix mode is enabled, attempt to remove execute permission
                    if fix_files:
                        if remove_execute_permission(filepath):
                            fixed_count += 1
                        else:
                            error_count += 1

            except OSError as e:
                LOGGER.warning("Could not access %s: %s", filepath, e)
            except Exception as e:
                LOGGER.warning("Unexpected error processing %s: %s", filepath, e)

    return suspicious_files_found, fixed_count, error_count


class SuspiciousExecutableFileModeCheck(FileCheck):
    """Flags files with execute bits that do not look like scripts or binaries."""

    order = 85

    def check(self, ctx: FileContext) -> None:
        if ctx.path.is_symlink() or not ctx.is_file:
            return
        if not is_suspicious_executable(str(ctx.path)):
            return

        def clear_execute_permission() -> None:
            remove_execute_permission(str(ctx.path))

        ctx.add_issue(
            E_SUSPICIOUS_EXECUTABLE_FILE_MODE,
            fix=clear_execute_permission,
        )


# --- Main Execution ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find and optionally fix files with suspicious execute permissions.")
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="The directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--fix",
        action="store_true",  # Makes it a boolean flag
        help="Attempt to remove execute permissions from suspicious files.",
    )
    args = parser.parse_args()

    target_directory = args.directory

    if not os.path.isdir(target_directory):
        print(f"Error: Directory not found: {target_directory}", file=sys.stderr)
        sys.exit(1)

    suspicious_files, fixed_count, error_count = find_and_process_files(target_directory, fix_files=args.fix)

    print("\n--- Summary ---")
    if suspicious_files:
        print(f"Found {len(suspicious_files)} potentially suspicious file(s).")
        if args.fix:
            print("Attempted to fix permissions:")
            print(f"  - Successfully fixed: {fixed_count}")
            print(f"  - Errors encountered: {error_count}")
            if error_count > 0:
                print("  (Check error messages above for details)")
    else:
        print("No suspicious files found.")

    print("\nScan complete.")


__all__ = [
    "EXECUTABLE_EXTENSIONS",
    "E_SUSPICIOUS_EXECUTABLE_FILE_MODE",
    "SuspiciousExecutableFileModeCheck",
    "find_and_process_files",
    "has_shebang",
    "is_elf_exe_mach",
    "is_executable",
    "is_suspicious_executable",
    "remove_ds_store",
    "remove_execute_permission",
]
