#!/usr/bin/env python3

"""
Fast duplicate file and directory finder.
Usage: duplicates.py <folder> [<folder>...]
Based on a staged fingerprinting approach to minimize I/O.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import posixpath
import sys
import time
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import BinaryIO, NamedTuple, Protocol, cast

type IgnorePathPredicate = Callable[[str, bool], bool]


IGNORE_DIRS = {".git", ".svn", ".hg", ".idea", ".vscode", "__pycache__"}
IGNORE_FILES = {"Thumbs.db", "desktop.ini", ".DS_Store"}

DIR_FINGERPRINT_WEAK = 0
DIR_FINGERPRINT_ZIP_METADATA = 1
DIR_FINGERPRINT_MEDIUM_COMPAT = 2
DIR_FINGERPRINT_MEDIUM_FAST = 3
DIR_FINGERPRINT_STRONG = 4

ZIP_ROOT_PREFIX = "zip::"
HASH_READ_CHUNK_SIZE = 1024 * 1024
HEAD_HASH_CHUNK_SIZE = 1024
SPARSE_HASH_CHUNK_SIZE = 4096
ZIP_FLAG_ENCRYPTED = 0x1

TREE_MATCH_STRONG = "strong"
TREE_MATCH_WEAK_ENCRYPTED_ZIP = "weak-encrypted-zip"


class FileGroup(NamedTuple):
    total_size: int
    total_count: int
    files: list[str]


class TreeGroup(NamedTuple):
    tree_size: int
    total_count: int
    file_count: int
    directory_count: int
    paths: list[str]
    match_kind: str = TREE_MATCH_STRONG


class DuplicateReport(NamedTuple):
    file_groups: list[FileGroup]
    tree_groups: list[TreeGroup]


@dataclass
class FileRecord:
    path: str
    size: int
    head_hash: bytes | None = None
    small_hash: bytes | None = None
    full_hash: bytes | None = None


@dataclass(frozen=True)
class TreeStats:
    total_size: int
    file_count: int
    directory_count: int


class NullProgress:
    def update(self, count: int = 1) -> None:
        pass

    def close(self) -> None:
        pass


class ProgressReporter(Protocol):
    def update(self, count: int = 1) -> None: ...

    def close(self) -> None: ...


class SimpleProgress:
    def __init__(self, desc: str, total: int | None, unit: str) -> None:
        self.desc = desc
        self.total = total
        self.unit = unit
        self.count = 0
        self.start = time.monotonic()
        self.last_render = 0.0

    def update(self, count: int = 1) -> None:
        self.count += count
        now = time.monotonic()
        if now - self.last_render >= 0.1:
            self.last_render = now
            self.render()

    def close(self) -> None:
        self.render(final=True)

    def render(self, final: bool = False) -> None:
        elapsed = max(time.monotonic() - self.start, 0.001)
        rate = self.count / elapsed
        if self.total is None:
            line = f"\r{self.desc}: {self.count} {self.unit} [{format_seconds(elapsed)}, {rate:0.1f} {self.unit}/s]"
        else:
            total = max(self.total, 1)
            ratio = min(self.count / total, 1.0)
            width = 24
            complete = int(width * ratio)
            remaining = width - complete
            eta = (self.total - self.count) / rate if rate > 0 and self.count < self.total else 0.0
            bar = "#" * complete + "-" * remaining
            line = (
                f"\r{self.desc}: {ratio:>6.1%}|{bar}| "
                f"{self.count}/{self.total} [{format_seconds(elapsed)}<{format_seconds(eta)}]"
            )
        end = "\n" if final else ""
        print(line, end=end, file=sys.stderr, flush=True)


def format_seconds(value: float) -> str:
    seconds = max(int(value), 0)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(value)

    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0

    return f"{value} B"


def duplicate_space_savings(size_per_item: int, total_count: int) -> int:
    return size_per_item * max(total_count - 1, 0)


def file_group_sort_key(group: FileGroup) -> tuple[int, int, int, list[str]]:
    per_file_size = group.total_size // max(group.total_count, 1)
    return (
        -duplicate_space_savings(per_file_size, group.total_count),
        -per_file_size,
        -group.total_count,
        group.files,
    )


def tree_group_sort_key(group: TreeGroup) -> tuple[int, int, int, int, int, list[str]]:
    return (
        -duplicate_space_savings(group.tree_size, group.total_count),
        -group.tree_size,
        -group.total_count,
        -group.file_count,
        0 if group.match_kind == TREE_MATCH_STRONG else 1,
        group.paths,
    )


def should_render_progress() -> bool:
    isatty = getattr(sys.stderr, "isatty", None)
    if isatty is None or not sys.stderr.isatty():
        return False
    return os.environ.get("TERM", "") != "dumb"


def create_progress(desc: str, *, total: int | None, unit: str) -> ProgressReporter:
    if not should_render_progress():
        return NullProgress()
    try:
        from tqdm import tqdm
    except ImportError:
        return SimpleProgress(desc, total, unit)
    return cast(
        ProgressReporter,
        tqdm(total=total, desc=desc, unit=unit, dynamic_ncols=True, file=sys.stderr, leave=False),
    )


@dataclass
class FilesystemTreeIndex:
    file_records: dict[str, FileRecord]
    directory_paths: list[str]
    directory_path_set: set[str]
    file_children: dict[str, list[tuple[str, str]]]
    directory_children: dict[str, list[tuple[str, str]]]
    directory_stats_cache: dict[str, TreeStats] = field(default_factory=dict)
    directory_fingerprint_cache: dict[tuple[str, int], bytes] = field(default_factory=dict)

    def get_file_head_hash(self, path: str) -> bytes:
        record = self.file_records[path]
        if record.head_hash is None:
            record.head_hash = get_head_hash(record.path)
        return record.head_hash

    def get_file_small_hash(self, path: str) -> bytes:
        record = self.file_records[path]
        if record.small_hash is None:
            record.small_hash = self._read_file_hash(record.path, first_chunk_only=True)
        return record.small_hash

    def get_file_full_hash(self, path: str) -> bytes:
        record = self.file_records[path]
        if record.full_hash is None:
            record.full_hash = self._read_file_hash(record.path, first_chunk_only=False)
        return record.full_hash

    def _read_file_hash(self, path: str, *, first_chunk_only: bool) -> bytes:
        try:
            return get_hash(path, first_chunk_only=first_chunk_only)
        except OSError:
            marker = "UNREADABLE-SMALL" if first_chunk_only else "UNREADABLE-FULL"
            hashobj = hashlib.sha256()
            hashobj.update(marker.encode("ascii"))
            hashobj.update(b"\0")
            hashobj.update(path.encode("utf-8", errors="surrogateescape"))
            return hashobj.digest()

    def get_directory_stats(self, path: str) -> TreeStats:
        cached = self.directory_stats_cache.get(path)
        if cached is not None:
            return cached

        total_size = 0
        file_count = 0
        directory_count = 1

        for _, child_file in self.file_children.get(path, []):
            record = self.file_records[child_file]
            total_size += record.size
            file_count += 1

        for _, child_dir in self.directory_children.get(path, []):
            child_stats = self.get_directory_stats(child_dir)
            total_size += child_stats.total_size
            file_count += child_stats.file_count
            directory_count += child_stats.directory_count

        stats = TreeStats(total_size=total_size, file_count=file_count, directory_count=directory_count)
        self.directory_stats_cache[path] = stats
        return stats

    def get_directory_fingerprint(self, path: str, stage: int) -> bytes:
        cache_key = (path, stage)
        cached = self.directory_fingerprint_cache.get(cache_key)
        if cached is not None:
            return cached

        hashobj = hashlib.sha256()

        for name, child_file in self.file_children.get(path, []):
            record = self.file_records[child_file]
            hashobj.update(b"F")
            update_hash_part(hashobj, name.encode("utf-8", errors="surrogateescape"))
            hashobj.update(encode_int(record.size))
            if stage == DIR_FINGERPRINT_MEDIUM_COMPAT:
                update_hash_part(hashobj, self.get_file_head_hash(child_file))
            elif stage == DIR_FINGERPRINT_MEDIUM_FAST:
                update_hash_part(hashobj, self.get_file_small_hash(child_file))
            elif stage == DIR_FINGERPRINT_STRONG:
                update_hash_part(hashobj, self.get_file_full_hash(child_file))

        for name, child_dir in self.directory_children.get(path, []):
            hashobj.update(b"D")
            update_hash_part(hashobj, name.encode("utf-8", errors="surrogateescape"))
            update_hash_part(hashobj, self.get_directory_fingerprint(child_dir, stage))

        digest = hashobj.digest()
        self.directory_fingerprint_cache[cache_key] = digest
        return digest


@dataclass
class ZipEntryRecord:
    archive_path: str
    member_name: str
    size: int
    crc32: int
    small_hash: bytes | None = None
    full_hash: bytes | None = None


@dataclass(frozen=True)
class ArchiveSummary:
    archive_path: str
    weak_fingerprint: bytes
    metadata_fingerprint: bytes
    stats: TreeStats
    is_encrypted: bool


@dataclass
class ArchiveTree:
    archive_path: str
    is_encrypted: bool
    file_records: dict[str, ZipEntryRecord]
    file_children: dict[str, list[tuple[str, str]]]
    directory_children: dict[str, list[tuple[str, str]]]
    stats_cache: dict[str, TreeStats] = field(default_factory=dict)
    fingerprint_cache: dict[tuple[str, int], bytes] = field(default_factory=dict)

    def get_root_stats(self) -> TreeStats:
        return self.get_directory_stats("")

    def get_root_fingerprint(self, stage: int) -> bytes:
        return self.get_directory_fingerprint("", stage)

    def get_directory_stats(self, node_id: str) -> TreeStats:
        cached = self.stats_cache.get(node_id)
        if cached is not None:
            return cached

        total_size = 0
        file_count = 0
        directory_count = 1

        for _, child_file in self.file_children.get(node_id, []):
            record = self.file_records[child_file]
            total_size += record.size
            file_count += 1

        for _, child_dir in self.directory_children.get(node_id, []):
            child_stats = self.get_directory_stats(child_dir)
            total_size += child_stats.total_size
            file_count += child_stats.file_count
            directory_count += child_stats.directory_count

        stats = TreeStats(total_size=total_size, file_count=file_count, directory_count=directory_count)
        self.stats_cache[node_id] = stats
        return stats

    def get_directory_fingerprint(self, node_id: str, stage: int) -> bytes:
        cache_key = (node_id, stage)
        cached = self.fingerprint_cache.get(cache_key)
        if cached is not None:
            return cached

        hashobj = hashlib.sha256()

        for name, child_file in self.file_children.get(node_id, []):
            record = self.file_records[child_file]
            hashobj.update(b"F")
            update_hash_part(hashobj, name.encode("utf-8", errors="surrogateescape"))
            hashobj.update(encode_int(record.size))
            if stage == DIR_FINGERPRINT_ZIP_METADATA:
                hashobj.update(encode_int(record.crc32))
            elif stage == DIR_FINGERPRINT_MEDIUM_COMPAT:
                update_hash_part(hashobj, self.get_file_small_hash(child_file))
            elif stage == DIR_FINGERPRINT_STRONG:
                update_hash_part(hashobj, self.get_file_full_hash(child_file))

        for name, child_dir in self.directory_children.get(node_id, []):
            hashobj.update(b"D")
            update_hash_part(hashobj, name.encode("utf-8", errors="surrogateescape"))
            update_hash_part(hashobj, self.get_directory_fingerprint(child_dir, stage))

        digest = hashobj.digest()
        self.fingerprint_cache[cache_key] = digest
        return digest

    def get_file_small_hash(self, entry_id: str) -> bytes:
        record = self.file_records[entry_id]
        if record.small_hash is None:
            self.populate_missing_small_hashes([entry_id])
        assert record.small_hash is not None
        return record.small_hash

    def get_file_full_hash(self, entry_id: str) -> bytes:
        record = self.file_records[entry_id]
        if record.full_hash is None:
            self.populate_missing_full_hashes([entry_id])
        assert record.full_hash is not None
        return record.full_hash

    def populate_missing_small_hashes(self, entry_ids: Iterable[str] | None = None) -> None:
        self._populate_missing_hashes(entry_ids, first_chunk_only=True)

    def populate_missing_full_hashes(self, entry_ids: Iterable[str] | None = None) -> None:
        self._populate_missing_hashes(entry_ids, first_chunk_only=False)

    def _read_member_hash(self, fobj: BinaryIO, *, first_chunk_only: bool) -> bytes:
        if first_chunk_only:
            return get_head_stream_hash(fobj)
        return get_stream_hash(fobj)

    def _get_unreadable_member_hash(self, member_name: str, *, first_chunk_only: bool) -> bytes:
        marker = "UNREADABLE-ZIP-SMALL" if first_chunk_only else "UNREADABLE-ZIP-FULL"
        hashobj = hashlib.sha256()
        hashobj.update(marker.encode("ascii"))
        hashobj.update(b"\0")
        hashobj.update(self.archive_path.encode("utf-8", errors="surrogateescape"))
        hashobj.update(b"\0")
        hashobj.update(member_name.encode("utf-8", errors="surrogateescape"))
        return hashobj.digest()

    def _populate_missing_hashes(self, entry_ids: Iterable[str] | None, *, first_chunk_only: bool) -> None:
        target_ids = sorted(
            set(entry_ids or self.file_records), key=lambda entry_id: self.file_records[entry_id].member_name
        )
        if first_chunk_only:
            missing_ids = [entry_id for entry_id in target_ids if self.file_records[entry_id].small_hash is None]
        else:
            missing_ids = [entry_id for entry_id in target_ids if self.file_records[entry_id].full_hash is None]

        if not missing_ids:
            return

        try:
            with zipfile.ZipFile(self.archive_path) as zf:
                for entry_id in missing_ids:
                    record = self.file_records[entry_id]
                    try:
                        with zf.open(record.member_name) as f:
                            digest = self._read_member_hash(cast(BinaryIO, f), first_chunk_only=first_chunk_only)
                    except (OSError, KeyError, RuntimeError, zipfile.BadZipFile):
                        digest = self._get_unreadable_member_hash(
                            record.member_name,
                            first_chunk_only=first_chunk_only,
                        )

                    if first_chunk_only:
                        record.small_hash = digest
                    else:
                        record.full_hash = digest
        except (OSError, RuntimeError, zipfile.BadZipFile):
            for entry_id in missing_ids:
                record = self.file_records[entry_id]
                digest = self._get_unreadable_member_hash(
                    record.member_name,
                    first_chunk_only=first_chunk_only,
                )
                if first_chunk_only:
                    record.small_hash = digest
                else:
                    record.full_hash = digest


def is_ignored_dir(path: str) -> bool:
    for component in os.path.normpath(path).split(os.path.sep):
        if component in IGNORE_DIRS:
            return True
    return False


def is_ignored_zip_path(path: str) -> bool:
    for component in path.split("/"):
        if component in IGNORE_DIRS:
            return True
    return False


def chunk_reader(fobj: BinaryIO, chunk_size: int = HASH_READ_CHUNK_SIZE) -> Iterator[bytes]:
    while True:
        chunk = fobj.read(chunk_size)
        if not chunk:
            return
        yield chunk


def get_head_stream_hash(fobj: BinaryIO) -> bytes:
    hashobj = hashlib.sha256()
    hashobj.update(fobj.read(HEAD_HASH_CHUNK_SIZE))
    return hashobj.digest()


def get_sparse_offsets(size: int, chunk_size: int = SPARSE_HASH_CHUNK_SIZE) -> list[int]:
    if size <= 0:
        return [0]

    max_offset = max(size - chunk_size, 0)
    offsets = {
        0,
        max(min((size // 2) - (chunk_size // 2), max_offset), 0),
        max_offset,
    }
    return sorted(offsets)


def get_sparse_stream_hash(fobj: BinaryIO, size: int) -> bytes:
    hashobj = hashlib.sha256()
    hashobj.update(b"SPARSE")
    hashobj.update(encode_int(size))

    for offset in get_sparse_offsets(size):
        fobj.seek(offset)
        chunk = fobj.read(SPARSE_HASH_CHUNK_SIZE)
        hashobj.update(encode_int(offset))
        update_hash_part(hashobj, chunk)

    return hashobj.digest()


def get_stream_hash(fobj: BinaryIO) -> bytes:
    hashobj = hashlib.sha256()
    for chunk in chunk_reader(fobj):
        hashobj.update(chunk)
    return hashobj.digest()


def get_hash(filename: str, first_chunk_only: bool = False) -> bytes:
    with open(filename, "rb") as f:
        if first_chunk_only:
            return get_sparse_stream_hash(f, os.fstat(f.fileno()).st_size)
        return get_stream_hash(f)


def get_head_hash(filename: str) -> bytes:
    with open(filename, "rb") as f:
        return get_head_stream_hash(f)


def get_zip_member_hash(archive_path: str, member_name: str, first_chunk_only: bool = False) -> bytes:
    with zipfile.ZipFile(archive_path) as zf, zf.open(member_name) as f:
        if first_chunk_only:
            return get_head_stream_hash(cast(BinaryIO, f))
        return get_stream_hash(cast(BinaryIO, f))


def zip_info_is_encrypted(info: zipfile.ZipInfo) -> bool:
    return bool(info.flag_bits & ZIP_FLAG_ENCRYPTED)


def should_include_file(
    *,
    filename: str,
    exclude_filters: Iterable[str],
    include_filters: Iterable[str],
) -> bool:
    if any(fnmatch.fnmatch(filename, pattern) for pattern in exclude_filters):
        return False
    if include_filters and not any(fnmatch.fnmatch(filename, pattern) for pattern in include_filters):
        return False
    return True


def encode_int(value: int) -> bytes:
    return value.to_bytes(16, "big", signed=False)


class HashUpdater(Protocol):
    def update(self, data: bytes, /) -> object: ...


def update_hash_part(hashobj: HashUpdater, data: bytes) -> None:
    hashobj.update(encode_int(len(data)))
    hashobj.update(data)


def group_duplicate_paths(
    paths: Iterable[str],
    key_fn: Callable[[str], bytes],
    *,
    progress: NullProgress | SimpleProgress | object | None = None,
) -> list[list[str]]:
    groups: defaultdict[bytes, list[str]] = defaultdict(list)
    for path in paths:
        groups[key_fn(path)].append(path)
        if progress is not None:
            progress.update(1)  # type: ignore[attr-defined]

    duplicate_groups = [sorted(group) for group in groups.values() if len(group) > 1]
    duplicate_groups.sort(key=lambda group: (-len(group), group[0]))
    return duplicate_groups


def flatten_groups(groups: Iterable[Iterable[str]]) -> list[str]:
    return sorted({path for group in groups for path in group})


def path_is_within(path: str, parent: str) -> bool:
    try:
        return os.path.commonpath([path, parent]) == parent
    except ValueError:
        return False


def zip_root_id(path: str) -> str:
    return f"{ZIP_ROOT_PREFIX}{path}"


def is_zip_root(path: str) -> bool:
    return path.startswith(ZIP_ROOT_PREFIX)


def display_tree_path(path: str) -> str:
    if is_zip_root(path):
        return path.removeprefix(ZIP_ROOT_PREFIX)
    return path


def build_filesystem_index(
    paths: list[str],
    exclude_filters: list[str] | None = None,
    include_filters: list[str] | None = None,
    no_default_excludes: bool = False,
    ignore_path: IgnorePathPredicate | None = None,
) -> FilesystemTreeIndex:
    file_records: dict[str, FileRecord] = {}
    directory_paths: set[str] = set()
    file_children: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
    directory_children: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)

    exclude_filters = exclude_filters or []
    include_filters = include_filters or []
    seen_directories: set[str] = set()
    progress = create_progress("Scanning", total=None, unit="files")

    try:
        for path in paths:
            root_path = os.path.realpath(path)
            if root_path in seen_directories:
                continue
            if ignore_path is not None and ignore_path(root_path, True):
                continue
            if not no_default_excludes and is_ignored_dir(root_path):
                continue

            pending_directories: list[tuple[str, str | None, str | None]] = [(root_path, None, None)]

            while pending_directories:
                dirpath, parent_dirpath, entry_name = pending_directories.pop()
                if dirpath in seen_directories:
                    continue

                try:
                    with os.scandir(dirpath) as entries:
                        seen_directories.add(dirpath)
                        directory_paths.add(dirpath)
                        if parent_dirpath is not None and entry_name is not None:
                            directory_children[parent_dirpath].append((entry_name, dirpath))

                        for entry in entries:
                            entry_name = entry.name

                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    if ignore_path is not None and ignore_path(entry.path, True):
                                        continue
                                    if not no_default_excludes and entry_name in IGNORE_DIRS:
                                        continue

                                    child_dirpath = entry.path
                                    if child_dirpath in seen_directories:
                                        continue

                                    pending_directories.append((child_dirpath, dirpath, entry_name))
                                    continue

                                if ignore_path is not None and ignore_path(entry.path, False):
                                    continue
                                if not no_default_excludes and entry_name in IGNORE_FILES:
                                    continue
                                if not should_include_file(
                                    filename=entry_name,
                                    exclude_filters=exclude_filters,
                                    include_filters=include_filters,
                                ):
                                    continue

                                if entry.is_file(follow_symlinks=False):
                                    canonical_path = entry.path
                                    file_size = entry.stat(follow_symlinks=False).st_size
                                elif entry.is_symlink() and entry.is_file(follow_symlinks=True):
                                    canonical_path = os.path.realpath(entry.path)
                                    if canonical_path in file_records:
                                        continue
                                    file_size = entry.stat(follow_symlinks=True).st_size
                                else:
                                    continue
                            except OSError:
                                continue

                            if canonical_path in file_records:
                                continue

                            file_records[canonical_path] = FileRecord(path=canonical_path, size=file_size)
                            progress.update(1)
                except OSError:
                    continue
    finally:
        progress.close()

    sorted_directory_paths = sorted(directory_paths, key=lambda path: (path.count(os.path.sep), path))

    for file_path in sorted(file_records):
        parent_path = os.path.dirname(file_path)
        if parent_path in directory_paths:
            file_children[parent_path].append((os.path.basename(file_path), file_path))

    for children in directory_children.values():
        children.sort()
    for children in file_children.values():
        children.sort()

    return FilesystemTreeIndex(
        file_records=file_records,
        directory_paths=sorted_directory_paths,
        directory_path_set=set(sorted_directory_paths),
        file_children=dict(file_children),
        directory_children=dict(directory_children),
    )


def normalize_zip_member_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.strip("/")
    return normalized


def build_archive_tree(
    archive_path: str,
    exclude_filters: list[str] | None = None,
    include_filters: list[str] | None = None,
    no_default_excludes: bool = False,
    allow_encrypted: bool = False,
) -> ArchiveTree | None:
    exclude_filters = exclude_filters or []
    include_filters = include_filters or []

    is_encrypted = False
    file_records: dict[str, ZipEntryRecord] = {}
    file_children: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
    directory_children: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
    seen_directory_edges: set[tuple[str, str]] = set()
    seen_member_paths: set[str] = set()

    try:
        with zipfile.ZipFile(archive_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue

                member_path = normalize_zip_member_path(info.filename)
                if not member_path or member_path in seen_member_paths:
                    continue
                if not no_default_excludes and is_ignored_zip_path(member_path):
                    continue

                filename = posixpath.basename(member_path)
                if not no_default_excludes and filename in IGNORE_FILES:
                    continue
                if not should_include_file(
                    filename=filename,
                    exclude_filters=exclude_filters,
                    include_filters=include_filters,
                ):
                    continue
                if zip_info_is_encrypted(info):
                    is_encrypted = True
                    if not allow_encrypted:
                        return None

                seen_member_paths.add(member_path)

                parent = ""
                components = member_path.split("/")
                for component in components[:-1]:
                    next_parent = component if not parent else f"{parent}/{component}"
                    edge = (parent, next_parent)
                    if edge not in seen_directory_edges:
                        directory_children[parent].append((component, next_parent))
                        seen_directory_edges.add(edge)
                    parent = next_parent

                file_children[parent].append((components[-1], member_path))
                file_records[member_path] = ZipEntryRecord(
                    archive_path=archive_path,
                    member_name=member_path,
                    size=info.file_size,
                    crc32=info.CRC,
                )
    except (OSError, zipfile.BadZipFile):
        return None

    for children in directory_children.values():
        children.sort()
    for children in file_children.values():
        children.sort()

    return ArchiveTree(
        archive_path=archive_path,
        is_encrypted=is_encrypted,
        file_records=file_records,
        file_children=dict(file_children),
        directory_children=dict(directory_children),
    )


def build_archive_summary(
    archive_path: str,
    exclude_filters: list[str] | None = None,
    include_filters: list[str] | None = None,
    no_default_excludes: bool = False,
    allow_encrypted: bool = False,
) -> ArchiveSummary | None:
    archive_tree = build_archive_tree(
        archive_path,
        exclude_filters=exclude_filters,
        include_filters=include_filters,
        no_default_excludes=no_default_excludes,
        allow_encrypted=allow_encrypted,
    )
    if archive_tree is None:
        return None
    return ArchiveSummary(
        archive_path=archive_path,
        weak_fingerprint=archive_tree.get_root_fingerprint(DIR_FINGERPRINT_WEAK),
        metadata_fingerprint=archive_tree.get_root_fingerprint(DIR_FINGERPRINT_ZIP_METADATA),
        stats=archive_tree.get_root_stats(),
        is_encrypted=archive_tree.is_encrypted,
    )


def iter_zip_archives(index: FilesystemTreeIndex) -> list[str]:
    archive_paths = sorted(path for path in index.file_records if os.path.basename(path).lower().endswith(".zip"))
    return archive_paths


def build_archive_summaries(
    archive_paths: list[str],
    exclude_filters: list[str] | None = None,
    include_filters: list[str] | None = None,
    no_default_excludes: bool = False,
    allow_encrypted: bool = False,
) -> dict[str, ArchiveSummary]:
    progress = create_progress("Indexing zip trees", total=len(archive_paths), unit="archives")
    archives: dict[str, ArchiveSummary] = {}

    try:
        for archive_path in archive_paths:
            archive_summary = build_archive_summary(
                archive_path,
                exclude_filters=exclude_filters,
                include_filters=include_filters,
                no_default_excludes=no_default_excludes,
                allow_encrypted=allow_encrypted,
            )
            if archive_summary is not None:
                archives[archive_path] = archive_summary
            progress.update(1)
    finally:
        progress.close()

    return archives


def build_archive_trees_for_paths(
    archive_paths: Iterable[str],
    exclude_filters: list[str] | None = None,
    include_filters: list[str] | None = None,
    no_default_excludes: bool = False,
) -> dict[str, ArchiveTree]:
    archive_path_list = sorted(set(archive_paths))
    progress = create_progress("Loading zip candidates", total=len(archive_path_list), unit="archives")
    archives: dict[str, ArchiveTree] = {}

    try:
        for archive_path in archive_path_list:
            archive_tree = build_archive_tree(
                archive_path,
                exclude_filters=exclude_filters,
                include_filters=include_filters,
                no_default_excludes=no_default_excludes,
            )
            if archive_tree is not None:
                archives[archive_path] = archive_tree
            progress.update(1)
    finally:
        progress.close()

    return archives


def find_duplicate_file_groups_in_index(index: FilesystemTreeIndex, min_size: int = 1) -> list[FileGroup]:
    files_by_size: defaultdict[int, list[str]] = defaultdict(list)
    files_by_small_hash: defaultdict[tuple[int, bytes], list[str]] = defaultdict(list)
    files_by_full_hash: defaultdict[bytes, list[str]] = defaultdict(list)

    for path, record in index.file_records.items():
        if record.size < min_size:
            continue
        files_by_size[record.size].append(path)

    small_hash_candidates = sum(len(files) for files in files_by_size.values() if len(files) > 1)
    progress = create_progress("Hashing duplicate-file candidates", total=small_hash_candidates, unit="files")

    try:
        for file_size, files in files_by_size.items():
            if len(files) < 2:
                continue

            for filename in files:
                files_by_small_hash[(file_size, index.get_file_small_hash(filename))].append(filename)
                progress.update(1)
    finally:
        progress.close()

    full_hash_candidates = sum(len(files) for files in files_by_small_hash.values() if len(files) > 1)
    progress = create_progress("Confirming duplicate files", total=full_hash_candidates, unit="files")

    try:
        for files in files_by_small_hash.values():
            if len(files) < 2:
                continue

            for filename in files:
                files_by_full_hash[index.get_file_full_hash(filename)].append(filename)
                progress.update(1)
    finally:
        progress.close()

    file_groups: list[FileGroup] = []

    for files in files_by_full_hash.values():
        if len(files) <= 1:
            continue

        sorted_files = sorted(files)
        file_groups.append(
            FileGroup(
                total_size=sum(index.file_records[filename].size for filename in sorted_files),
                total_count=len(sorted_files),
                files=sorted_files,
            )
        )

    file_groups.sort(key=file_group_sort_key)
    return file_groups


def get_tree_fingerprint(
    root_id: str,
    stage: int,
    index: FilesystemTreeIndex,
    archive_summaries: dict[str, ArchiveSummary],
    archive_trees: dict[str, ArchiveTree],
) -> bytes:
    if is_zip_root(root_id):
        archive_path = display_tree_path(root_id)
        if stage == DIR_FINGERPRINT_WEAK:
            return archive_summaries[archive_path].weak_fingerprint
        return archive_trees[archive_path].get_root_fingerprint(stage)
    return index.get_directory_fingerprint(root_id, stage)


def get_tree_stats(
    root_id: str,
    index: FilesystemTreeIndex,
    archive_summaries: dict[str, ArchiveSummary],
    archive_trees: dict[str, ArchiveTree],
) -> TreeStats:
    if is_zip_root(root_id):
        archive_path = display_tree_path(root_id)
        archive_tree = archive_trees.get(archive_path)
        if archive_tree is not None:
            return archive_tree.get_root_stats()
        return archive_summaries[archive_path].stats
    return index.get_directory_stats(root_id)


def tree_depth(root_id: str) -> int:
    if is_zip_root(root_id):
        return 0
    return root_id.count(os.path.sep)


def group_contains_zip_roots(group: Iterable[str]) -> bool:
    return any(is_zip_root(path) for path in group)


def is_encrypted_zip_root(root_id: str, archive_summaries: dict[str, ArchiveSummary]) -> bool:
    return is_zip_root(root_id) and archive_summaries[display_tree_path(root_id)].is_encrypted


def group_is_zip_only(group: Iterable[str]) -> bool:
    has_paths = False
    for path in group:
        has_paths = True
        if not is_zip_root(path):
            return False
    return has_paths


def build_groups_by_key(
    groups: Iterable[Iterable[str]],
    key_fn: Callable[[str], bytes],
) -> list[list[str]]:
    refined_groups: list[list[str]] = []
    for group in groups:
        refined_groups.extend(group_duplicate_paths(group, key_fn))
    return refined_groups


def split_weak_groups_for_encrypted_zips(
    weak_groups: Iterable[Iterable[str]],
    archive_summaries: dict[str, ArchiveSummary],
    *,
    include_weak_encrypted_zip: bool,
) -> tuple[list[list[str]], list[list[str]]]:
    strong_eligible_groups: list[list[str]] = []
    weak_encrypted_zip_groups: list[list[str]] = []

    for group in weak_groups:
        sorted_group = sorted(group)
        encrypted_zip_paths = [path for path in sorted_group if is_encrypted_zip_root(path, archive_summaries)]
        if not encrypted_zip_paths:
            strong_eligible_groups.append(sorted_group)
            continue

        if include_weak_encrypted_zip:
            zip_paths = [path for path in sorted_group if is_zip_root(path)]
            if len(zip_paths) > 1:
                weak_encrypted_zip_groups.append(zip_paths)

        strong_eligible_group = [path for path in sorted_group if path not in encrypted_zip_paths]
        if len(strong_eligible_group) > 1:
            strong_eligible_groups.append(strong_eligible_group)

    return strong_eligible_groups, weak_encrypted_zip_groups


def preload_zip_tree_hashes(
    group: Iterable[str],
    archive_trees: dict[str, ArchiveTree],
    *,
    first_chunk_only: bool,
) -> None:
    for path in group:
        if not is_zip_root(path):
            continue
        archive_tree = archive_trees.get(display_tree_path(path))
        if archive_tree is None:
            continue
        if first_chunk_only:
            archive_tree.populate_missing_small_hashes()
        else:
            archive_tree.populate_missing_full_hashes()


def find_covering_duplicate_root(
    path: str,
    confirmed_duplicate_roots: dict[str, tuple[int, str, str]],
) -> tuple[int, str, str] | None:
    current = os.path.dirname(path)
    while current and current != path:
        match = confirmed_duplicate_roots.get(current)
        if match is not None:
            return match
        path = current
        current = os.path.dirname(current)
    return confirmed_duplicate_roots.get(path)


def tree_group_is_redundant(
    group: Iterable[str],
    confirmed_duplicate_roots: dict[str, tuple[int, str, str]],
) -> bool:
    coverage: list[tuple[int, str]] = []
    for path in group:
        if is_zip_root(path):
            return False

        covered = find_covering_duplicate_root(path, confirmed_duplicate_roots)
        if covered is None:
            return False

        group_index, _representative, matched_root = covered
        coverage.append((group_index, os.path.relpath(path, matched_root)))

    if not coverage:
        return False

    first_coverage = coverage[0]
    return all(item == first_coverage for item in coverage[1:])


def register_confirmed_tree_group(
    group_index: int,
    group: Iterable[str],
    confirmed_duplicate_roots: dict[str, tuple[int, str, str]],
) -> None:
    directory_paths = sorted(path for path in group if not is_zip_root(path))
    if len(directory_paths) < 2:
        return

    representative = directory_paths[0]
    for directory_path in directory_paths:
        confirmed_duplicate_roots[directory_path] = (group_index, representative, directory_path)


def build_tree_group(
    group: Iterable[str],
    *,
    index: FilesystemTreeIndex,
    archive_summaries: dict[str, ArchiveSummary],
    archive_trees: dict[str, ArchiveTree],
    match_kind: str = TREE_MATCH_STRONG,
) -> TreeGroup:
    sorted_group = sorted(group)
    stats = get_tree_stats(sorted_group[0], index, archive_summaries, archive_trees)
    return TreeGroup(
        tree_size=stats.total_size,
        total_count=len(sorted_group),
        file_count=stats.file_count,
        directory_count=stats.directory_count,
        paths=sorted(display_tree_path(path) for path in sorted_group),
        match_kind=match_kind,
    )


def find_duplicate_tree_groups_in_index(
    index: FilesystemTreeIndex,
    *,
    include_zip_contents: bool,
    include_weak_encrypted_zip: bool = False,
    exclude_filters: list[str] | None = None,
    include_filters: list[str] | None = None,
    no_default_excludes: bool = False,
) -> list[TreeGroup]:
    archive_summaries = (
        build_archive_summaries(
            iter_zip_archives(index),
            exclude_filters=exclude_filters,
            include_filters=include_filters,
            no_default_excludes=no_default_excludes,
            allow_encrypted=include_weak_encrypted_zip,
        )
        if include_zip_contents
        else {}
    )
    archive_trees: dict[str, ArchiveTree] = {}

    root_ids = index.directory_paths + [zip_root_id(path) for path in sorted(archive_summaries)]

    progress = create_progress("Grouping trees", total=len(root_ids), unit="trees")
    try:
        weak_groups = group_duplicate_paths(
            root_ids,
            lambda path: get_tree_fingerprint(path, DIR_FINGERPRINT_WEAK, index, archive_summaries, archive_trees),
            progress=progress,
        )
    finally:
        progress.close()

    weak_groups, weak_encrypted_zip_seed_groups = split_weak_groups_for_encrypted_zips(
        weak_groups,
        archive_summaries,
        include_weak_encrypted_zip=include_weak_encrypted_zip,
    )

    zip_only_weak_groups = [group for group in weak_groups if group_is_zip_only(group)]
    dir_only_weak_groups = [group for group in weak_groups if not group_contains_zip_roots(group)]
    mixed_weak_groups = [
        group for group in weak_groups if not group_is_zip_only(group) and group_contains_zip_roots(group)
    ]

    zip_metadata_groups: list[list[str]] = []
    zip_metadata_candidates = flatten_groups(zip_only_weak_groups)
    progress = create_progress(
        "Hashing zip tree candidates (metadata)", total=len(zip_metadata_candidates), unit="trees"
    )
    try:
        zip_metadata_groups = build_groups_by_key(
            zip_only_weak_groups,
            lambda path: archive_summaries[display_tree_path(path)].metadata_fingerprint,
        )
        progress.update(len(zip_metadata_candidates))
    finally:
        progress.close()

    weak_encrypted_zip_groups: list[list[str]] = []
    weak_encrypted_zip_candidates = flatten_groups(weak_encrypted_zip_seed_groups)
    progress = create_progress(
        "Matching encrypted zip candidates (metadata)",
        total=len(weak_encrypted_zip_candidates),
        unit="trees",
    )
    try:
        weak_encrypted_zip_groups = build_groups_by_key(
            weak_encrypted_zip_seed_groups,
            lambda path: archive_summaries[display_tree_path(path)].metadata_fingerprint,
        )
        weak_encrypted_zip_groups = [
            group
            for group in weak_encrypted_zip_groups
            if any(is_encrypted_zip_root(path, archive_summaries) for path in group)
        ]
        progress.update(len(weak_encrypted_zip_candidates))
    finally:
        progress.close()

    dir_only_candidates = flatten_groups(dir_only_weak_groups)
    progress = create_progress("Hashing tree candidates (sparse)", total=len(dir_only_candidates), unit="trees")
    try:
        dir_only_medium_groups = group_duplicate_paths(
            dir_only_candidates,
            lambda path: get_tree_fingerprint(
                path,
                DIR_FINGERPRINT_MEDIUM_FAST,
                index,
                archive_summaries,
                archive_trees,
            ),
            progress=progress,
        )
    finally:
        progress.close()

    mixed_candidates = flatten_groups(mixed_weak_groups)
    archive_trees = build_archive_trees_for_paths(
        (display_tree_path(path) for path in mixed_candidates if is_zip_root(path)),
        exclude_filters=exclude_filters,
        include_filters=include_filters,
        no_default_excludes=no_default_excludes,
    )
    progress = create_progress("Hashing tree candidates (head)", total=len(mixed_candidates), unit="trees")
    try:
        for group in mixed_weak_groups:
            preload_zip_tree_hashes(group, archive_trees, first_chunk_only=True)
        mixed_medium_groups = group_duplicate_paths(
            mixed_candidates,
            lambda path: get_tree_fingerprint(
                path,
                DIR_FINGERPRINT_MEDIUM_COMPAT,
                index,
                archive_summaries,
                archive_trees,
            ),
            progress=progress,
        )
    finally:
        progress.close()

    strong_seed_groups = zip_metadata_groups + dir_only_medium_groups + mixed_medium_groups
    strong_seed_zip_paths = [
        display_tree_path(path)
        for path in flatten_groups(strong_seed_groups)
        if is_zip_root(path) and display_tree_path(path) not in archive_trees
    ]
    if strong_seed_zip_paths:
        archive_trees.update(
            build_archive_trees_for_paths(
                strong_seed_zip_paths,
                exclude_filters=exclude_filters,
                include_filters=include_filters,
                no_default_excludes=no_default_excludes,
            )
        )

    strong_groups: list[list[str]] = []
    confirmed_duplicate_roots: dict[str, tuple[int, str, str]] = {}
    next_confirmed_group_index = 0
    strong_candidate_count = sum(len(group) for group in strong_seed_groups)
    progress = create_progress("Hashing tree candidates (full)", total=strong_candidate_count, unit="trees")

    try:
        for group in sorted(strong_seed_groups, key=lambda item: (min(tree_depth(path) for path in item), item[0])):
            if tree_group_is_redundant(group, confirmed_duplicate_roots):
                progress.update(len(group))
                continue

            preload_zip_tree_hashes(group, archive_trees, first_chunk_only=False)
            confirmed_groups = group_duplicate_paths(
                group,
                lambda path: get_tree_fingerprint(
                    path, DIR_FINGERPRINT_STRONG, index, archive_summaries, archive_trees
                ),
                progress=progress,
            )
            for confirmed_group in confirmed_groups:
                if tree_group_is_redundant(confirmed_group, confirmed_duplicate_roots):
                    continue
                strong_groups.append(confirmed_group)
                register_confirmed_tree_group(
                    next_confirmed_group_index,
                    confirmed_group,
                    confirmed_duplicate_roots,
                )
                next_confirmed_group_index += 1
    finally:
        progress.close()

    tree_groups: list[TreeGroup] = []

    for group in strong_groups:
        tree_groups.append(
            build_tree_group(
                group,
                index=index,
                archive_summaries=archive_summaries,
                archive_trees=archive_trees,
            )
        )

    for group in weak_encrypted_zip_groups:
        tree_groups.append(
            build_tree_group(
                group,
                index=index,
                archive_summaries=archive_summaries,
                archive_trees=archive_trees,
                match_kind=TREE_MATCH_WEAK_ENCRYPTED_ZIP,
            )
        )

    tree_groups.sort(key=tree_group_sort_key)
    return tree_groups


def collapse_file_groups_under_duplicate_trees(
    file_groups: list[FileGroup],
    tree_groups: list[TreeGroup],
    index: FilesystemTreeIndex,
) -> list[FileGroup]:
    duplicate_directory_roots: dict[str, tuple[int, str, str]] = {}

    for group_index, tree_group in enumerate(tree_groups):
        directory_paths = [path for path in tree_group.paths if path in index.directory_path_set]
        if len(directory_paths) < 2:
            continue
        representative = directory_paths[0]
        for directory_path in directory_paths:
            duplicate_directory_roots[directory_path] = (group_index, representative, directory_path)

    inherited_duplicate_by_directory: dict[str, tuple[int, str, str] | None] = {}
    for directory_path in index.directory_paths:
        inherited_duplicate = duplicate_directory_roots.get(directory_path)
        if inherited_duplicate is None:
            inherited_duplicate = inherited_duplicate_by_directory.get(os.path.dirname(directory_path))
        inherited_duplicate_by_directory[directory_path] = inherited_duplicate

    collapsed_groups: list[FileGroup] = []
    total_group_files = sum(len(group.files) for group in file_groups)
    progress = create_progress("Collapsing file noise", total=total_group_files, unit="files")

    try:
        for group in file_groups:
            kept_by_key: dict[tuple[object, ...], str] = {}

            for file_path in group.files:
                key: tuple[object, ...] = ("file", file_path)
                display_path = file_path

                matched_duplicate = inherited_duplicate_by_directory.get(os.path.dirname(file_path))
                if matched_duplicate is not None:
                    group_index, representative, matched_root = matched_duplicate
                    relative_path = os.path.relpath(file_path, matched_root)
                    representative_path = os.path.join(representative, relative_path)
                    if representative_path in index.file_records:
                        key = ("tree", group_index, relative_path)
                        display_path = representative_path

                kept_by_key.setdefault(key, display_path)
                progress.update(1)

            collapsed_files = sorted(set(kept_by_key.values()))
            if len(collapsed_files) <= 1:
                continue

            collapsed_groups.append(
                FileGroup(
                    total_size=sum(index.file_records[path].size for path in collapsed_files),
                    total_count=len(collapsed_files),
                    files=collapsed_files,
                )
            )
    finally:
        progress.close()

    collapsed_groups.sort(key=file_group_sort_key)
    return collapsed_groups


def find_duplicate_file_groups(
    paths: list[str],
    exclude_filters: list[str] | None = None,
    include_filters: list[str] | None = None,
    min_size: int = 1,
    no_default_excludes: bool = False,
    ignore_path: IgnorePathPredicate | None = None,
) -> list[FileGroup]:
    index = build_filesystem_index(
        paths,
        exclude_filters=exclude_filters,
        include_filters=include_filters,
        no_default_excludes=no_default_excludes,
        ignore_path=ignore_path,
    )
    return find_duplicate_file_groups_in_index(index, min_size=min_size)


def find_duplicate_directory_groups(
    paths: list[str],
    exclude_filters: list[str] | None = None,
    include_filters: list[str] | None = None,
    no_default_excludes: bool = False,
    include_zip_contents: bool = False,
    include_weak_encrypted_zip: bool = False,
    ignore_path: IgnorePathPredicate | None = None,
) -> list[TreeGroup]:
    index = build_filesystem_index(
        paths,
        exclude_filters=exclude_filters,
        include_filters=include_filters,
        no_default_excludes=no_default_excludes,
        ignore_path=ignore_path,
    )
    return find_duplicate_tree_groups_in_index(
        index,
        include_zip_contents=include_zip_contents,
        include_weak_encrypted_zip=include_weak_encrypted_zip,
        exclude_filters=exclude_filters,
        include_filters=include_filters,
        no_default_excludes=no_default_excludes,
    )


def find_duplicates(
    paths: list[str],
    exclude_filters: list[str] | None = None,
    include_filters: list[str] | None = None,
    min_size: int = 1,
    no_default_excludes: bool = False,
    include_zip_contents: bool = False,
    include_weak_encrypted_zip: bool = False,
    ignore_path: IgnorePathPredicate | None = None,
) -> DuplicateReport:
    index = build_filesystem_index(
        paths,
        exclude_filters=exclude_filters,
        include_filters=include_filters,
        no_default_excludes=no_default_excludes,
        ignore_path=ignore_path,
    )
    tree_groups = find_duplicate_tree_groups_in_index(
        index,
        include_zip_contents=include_zip_contents,
        include_weak_encrypted_zip=include_weak_encrypted_zip,
        exclude_filters=exclude_filters,
        include_filters=include_filters,
        no_default_excludes=no_default_excludes,
    )
    file_groups = collapse_file_groups_under_duplicate_trees(
        find_duplicate_file_groups_in_index(index, min_size=min_size),
        tree_groups,
        index,
    )
    return DuplicateReport(file_groups=file_groups, tree_groups=tree_groups)


def print_duplicate_report(report: DuplicateReport) -> None:
    wrote_section = False

    if report.tree_groups:
        print("Duplicate trees:")
        for tree_group in report.tree_groups:
            match_suffix = ""
            if tree_group.match_kind == TREE_MATCH_WEAK_ENCRYPTED_ZIP:
                match_suffix = ", Match: weak encrypted zip metadata only"
            print(
                "Tree size: "
                f"{tree_group.tree_size} bytes ({format_bytes(tree_group.tree_size)}), "
                f"Total count: {tree_group.total_count}, "
                f"File count: {tree_group.file_count}, "
                f"Directory count: {tree_group.directory_count}"
                f"{match_suffix}"
            )
            for path in tree_group.paths:
                print("  ", path)
            print()
        wrote_section = True

    if report.file_groups:
        if wrote_section:
            print()
        print("Duplicate files:")
        for file_group in report.file_groups:
            print(
                f"Total size: {file_group.total_size} bytes ({format_bytes(file_group.total_size)}), "
                f"Total count: {file_group.total_count}"
            )
            for filename in file_group.files:
                print("  ", filename)
            print()


def check_for_duplicates(
    paths: list[str],
    exclude_filters: list[str],
    include_filters: list[str],
    min_size: int,
    no_default_excludes: bool,
    include_zip_contents: bool = False,
    include_weak_encrypted_zip: bool = False,
) -> None:
    report = find_duplicates(
        paths,
        exclude_filters=exclude_filters,
        include_filters=include_filters,
        min_size=min_size,
        no_default_excludes=no_default_excludes,
        include_zip_contents=include_zip_contents,
        include_weak_encrypted_zip=include_weak_encrypted_zip,
    )
    print_duplicate_report(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Find duplicate files and duplicate directory trees using staged "
            "fingerprinting to reduce unnecessary reads."
        ),
        epilog=(
            "Examples:\n"
            "  duplicates.py folder-a folder-b\n"
            "  duplicates.py . --exclude '*.png' '*.jpg' --size 4096\n"
            "  duplicates.py archives --zip-contents --weak-encrypted-zip"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("folders", nargs="+", help="Folders to check for duplicate files and directories")
    parser.add_argument(
        "-e",
        "--exclude",
        type=str,
        default=[],
        help="Exclude files matching the filter",
        nargs="+",
    )
    parser.add_argument(
        "-f",
        "--filter",
        type=str,
        default=[],
        help="Include only files matching the filter",
        nargs="+",
    )
    parser.add_argument(
        "-s",
        "--size",
        type=int,
        default=1,
        help="Minimum file size to consider for duplicate file reporting",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Do not exclude common files and directories",
    )
    parser.add_argument(
        "--zip-contents",
        action="store_true",
        help="Also compare directory trees against zip file contents",
    )
    parser.add_argument(
        "--weak-encrypted-zip",
        action="store_true",
        help="Weakly compare encrypted zip contents using visible zip metadata only",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(stdout_reconfigure):
        stdout_reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    check_for_duplicates(
        args.folders,
        args.exclude,
        args.filter,
        args.size,
        args.no_default_excludes,
        include_zip_contents=args.zip_contents,
        include_weak_encrypted_zip=args.weak_encrypted_zip,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
