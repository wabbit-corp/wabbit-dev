#!/usr/bin/env python3

import os
import stat
import argparse
import sys # Added for stderr

# --- Configuration ---

# --- Helper Functions ---

def has_shebang(filepath):
    """
    Checks if a file starts with a shebang ('#!').
    Returns False if the file can't be read or is empty.
    """
    try:
        with open(filepath, 'rb') as f:
            return f.read(2) == b'#!'
    except (IOError, OSError):
        # print(f"Warning: Could not read {filepath} to check for shebang.", file=sys.stderr)
        return False
    except Exception as e:
        # print(f"Warning: Error reading {filepath}: {e}", file=sys.stderr)
        return False
    
def is_elf_exe_mach(filepath):
    """
    Checks if a file is an ELF, a Windows EXE, or a Mach-O (Darwin) executable
    by examining the first few bytes (the file "magic numbers").

    Returns a string among {"elf", "exe", "mach-o"} if recognized,
    or None if it does not match these known file types.
    """
    try:
        with open(filepath, 'rb') as f:
            # Read first 4 bytes
            magic = f.read(4)

        # -- Check ELF --
        # ELF files start with 0x7F, 'E', 'L', 'F'
        if magic == b'\x7fELF':
            return "elf"

        # -- Check Windows EXE (PE) --
        # Windows EXEs normally start with 'MZ' (0x4D, 0x5A)
        # Usually followed by other header bytes, but 'MZ' is the key signature
        if magic.startswith(b'MZ'):
            return "exe"

        # -- Check Mach-O (Darwin) --
        # 32-bit Mach-O: 0xFEEDFACE (little-endian: 0xCEFAEDFE)
        # 64-bit Mach-O: 0xFEEDFACF (little-endian: 0xCFFAEDFE)
        # On arm64 Macs, you’ll typically see the 64-bit Mach-O magic (0xFEEDFACF).
        # We can check for any known Mach-O “magic” or “fat” magic.
        mach_o_signatures = {
            b'\xFE\xED\xFA\xCE',  # 0xFEEDFACE  (32-bit big-endian)
            b'\xCE\xFA\xED\xFE',  # 0xCEFAEDFE  (32-bit little-endian)
            b'\xFE\xED\xFA\xCF',  # 0xFEEDFACF  (64-bit big-endian)
            b'\xCF\xFA\xED\xFE',  # 0xCFFAEDFE  (64-bit little-endian)
            b'\xCA\xFE\xBA\xBE',  # Fat/universal binaries
            b'\xBE\xBA\xFE\xCA',
        }
        if magic in mach_o_signatures:
            return "mach-o"

        return None
    except (IOError, OSError):
        return None
    except Exception:
        return None
    
assert is_elf_exe_mach("trufflehog")

def is_executable(filepath):
    """
    Checks if the file has execute permission for user, group, or others.
    """
    try:
        mode = os.stat(filepath).st_mode
        return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except OSError:
        return False

def remove_execute_permission(filepath):
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
            print(f"FIXED: Removed execute permission from {filepath}")
            return True
        else:
            # No execute permission was set initially
            return True # Considered success as the state is correct
    except OSError as e:
        print(f"Error: Could not change permissions for {filepath}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error: Unexpected error fixing {filepath}: {e}", file=sys.stderr)
        return False


def find_and_process_files(root_dir, fix_files=False):
    """
    Walks the directory tree, finds suspicious files, and optionally fixes them.
    Returns a list of files that were identified as suspicious.
    """
    suspicious_files_found = []
    fixed_count = 0
    error_count = 0

    print(f"Scanning directory: {os.path.abspath(root_dir)}")
    if fix_files:
        print("Fix mode enabled: Attempting to remove execute permissions from suspicious files.")
    print("-" * 30)

    # trufflehog git file://./kotlin-base58

    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True):
        # Optional: Skip directories like .git, venv, etc.
        dirnames[:] = [d for d in dirnames if d not in ['.git', '.svn', 'venv', '__pycache__', 'node_modules']]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)

            if filename == '.DS_Store':
                os.remove(filepath)
                print(f"Removed: {filepath} (macOS system file)")
                continue

            try:
                # Process only regular files (skip symlinks, etc.)
                if not os.path.islink(filepath) and os.path.isfile(filepath):
                    if is_executable(filepath):
                        _, ext = os.path.splitext(filename)
                        ext_lower = ext.lower()

                        # Check if extension is non-executable and file lacks shebang
                        # (filename in NON_EXECUTABLE_EXTENSIONS or ext_lower in NON_EXECUTABLE_EXTENSIONS) and
                        if not (has_shebang(filepath) or is_elf_exe_mach(filepath) is not None or ext_lower in EXECUTABLE_EXTENSIONS):
                            suspicious_files_found.append(filepath)
                            print(f"Suspicious: {filepath} (Extension: {ext}, Executable, No Shebang)")

                            # If fix mode is enabled, attempt to remove execute permission
                            if fix_files:
                                if remove_execute_permission(filepath):
                                    fixed_count += 1
                                else:
                                    error_count += 1
                        # Optional: Check for executable files with NO extension and no shebang
                        # elif not ext and not has_shebang(filepath):
                        #     suspicious_files_found.append(filepath)
                        #     print(f"Suspicious: {filepath} (No Extension, Executable, No Shebang)")
                        #     if fix_files:
                        #         if remove_execute_permission(filepath):
                        #             fixed_count += 1
                        #         else:
                        #             error_count += 1

            except OSError as e:
                print(f"Warning: Could not access {filepath}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Unexpected error processing {filepath}: {e}", file=sys.stderr)

    print("-" * 30)
    return suspicious_files_found, fixed_count, error_count

# --- Main Execution ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Find and optionally fix files with suspicious execute permissions."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="The directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--fix",
        action="store_true", # Makes it a boolean flag
        help="Attempt to remove execute permissions from suspicious files.",
    )
    args = parser.parse_args()

    target_directory = args.directory

    if not os.path.isdir(target_directory):
        print(f"Error: Directory not found: {target_directory}", file=sys.stderr)
        sys.exit(1)

    suspicious_files, fixed_count, error_count = find_and_process_files(
        target_directory,
        fix_files=args.fix
    )

    print("\n--- Summary ---")
    if suspicious_files:
        print(f"Found {len(suspicious_files)} potentially suspicious file(s).")
        if args.fix:
            print(f"Attempted to fix permissions:")
            print(f"  - Successfully fixed: {fixed_count}")
            print(f"  - Errors encountered: {error_count}")
            if error_count > 0:
                 print("  (Check error messages above for details)")
    else:
        print("No suspicious files found.")

    print("\nScan complete.")
