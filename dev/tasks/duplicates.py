#!/usr/bin/env python3

"""
Fast duplicate file finder.
Usage: duplicates.py <folder> [<folder>...]
Based on https://stackoverflow.com/a/36113168/300783
Modified for Python3 with some small code improvements.
"""

import os
import sys
import hashlib
from collections import defaultdict, namedtuple
import codecs

# reopen stdout with utf-8 support
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


IGNORE_DIRS = {".git", ".svn", ".hg", ".idea", ".vscode", "__pycache__"}
IGNORE_FILES = {"Thumbs.db", "desktop.ini", ".DS_Store"}

FileGroup = namedtuple("FileGroup", "total_size total_count files")


def is_ignored_dir(path):
    # check every path component, account for windows/unix path separators
    for component in os.path.normpath(path).split(os.path.sep):
        if component in IGNORE_DIRS:
            return True


def chunk_reader(fobj, chunk_size=1024):
    """Generator that reads a file in chunks of bytes"""
    while True:
        chunk = fobj.read(chunk_size)
        if not chunk:
            return
        yield chunk


def get_hash(filename, first_chunk_only=False, hash_algo=hashlib.sha1):
    hashobj = hash_algo()
    with open(filename, "rb") as f:
        if first_chunk_only:
            hashobj.update(f.read(1024))
        else:
            for chunk in chunk_reader(f):
                hashobj.update(chunk)
    return hashobj.digest()


def check_for_duplicates(
    paths, exclude_filters, include_filters, min_size, no_default_excludes
):
    files_by_size = defaultdict(list)
    files_by_small_hash = defaultdict(list)
    files_by_full_hash = defaultdict(list)

    processed = 0

    for path in paths:
        for dirpath, _, filenames in os.walk(path):
            # skip some common directories
            if is_ignored_dir(dirpath):
                continue

            for filename in filenames:
                # skip some common file names
                if filename in IGNORE_FILES:
                    continue

                processed += 1
                if processed % 1000 == 0:
                    print("Processed %d files" % processed)

                full_path = os.path.join(dirpath, filename)
                try:
                    # if the target is a symlink (soft one), this will
                    # dereference it - change the value to the actual target file
                    full_path = os.path.realpath(full_path)
                    file_size = os.path.getsize(full_path)
                except OSError:
                    # not accessible (permissions, etc) - pass on
                    continue
                files_by_size[file_size].append(full_path)

    # For all files with the same file size, get their hash on the first 1024 bytes
    for file_size, files in files_by_size.items():
        if len(files) < 2:
            continue  # this file size is unique, no need to spend cpu cycles on it

        for filename in files:
            try:
                small_hash = get_hash(filename, first_chunk_only=True)
            except OSError:
                # the file access might've changed till the exec point got here
                continue
            files_by_small_hash[(file_size, small_hash)].append(filename)

    del files_by_size

    # For all files with the hash on the first 1024 bytes, get their hash on the full
    # file - collisions will be duplicates
    for files in files_by_small_hash.values():
        if len(files) < 2:
            # the hash of the first 1k bytes is unique -> skip this file
            continue

        for filename in files:
            try:
                full_hash = get_hash(filename, first_chunk_only=False)
            except OSError:
                # the file access might've changed till the exec point got here
                continue

            files_by_full_hash[full_hash].append(filename)

    del files_by_small_hash

    file_groups = []

    # Print the duplicate files
    for files in files_by_full_hash.values():
        if len(files) > 1:
            total_size = 0
            total_count = len(files)
            for filename in files:
                try:
                    # if the target is a symlink (soft one), this will
                    # dereference it - change the value to the actual target file
                    full_path = os.path.realpath(filename)
                    file_size = os.path.getsize(filename)
                except OSError:
                    # not accessible (permissions, etc) - pass on
                    continue
                total_size += file_size

            file_groups.append(FileGroup(total_size, total_count, files))

    file_groups.sort(key=lambda x: x.total_size, reverse=True)
    for file_group in file_groups:
        print(
            f"Total size: {file_group.total_size} bytes, Total count: {file_group.total_count}"
        )
        for filename in file_group.files:
            print("  ", filename)
        print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", help="Folders to check for duplicates")

    # -e, --exclude <filter>  Exclude files matching the filter (-e '*.bak' -e '*.tmp')
    # -f, --filter <filter>   Include only files matching the filter (-f '*.txt' -f '*.doc')
    # -s, --size <size>       Minimum file size to consider (default: 1)
    # -no-default-excludes    Do not exclude common files and directories

    parser.add_argument(
        "-e",
        "--exclude",
        type=str,
        default="",
        help="Exclude files matching the filter",
        nargs="+",
    )
    parser.add_argument(
        "-f",
        "--filter",
        type=str,
        default="",
        help="Include only files matching the filter",
        nargs="+",
    )
    parser.add_argument(
        "-s", "--size", type=int, default=1, help="Minimum file size to consider"
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Do not exclude common files and directories",
    )

    args = parser.parse_args()

    check_for_duplicates(
        args.folders, args.exclude, args.filter, args.size, args.no_default_excludes
    )
