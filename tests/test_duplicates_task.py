from __future__ import annotations

import base64
import importlib
import io
import sys
import zipfile
from pathlib import Path

import pytest

from dev.tasks import duplicates as duplicates_task


ENCRYPTED_ZIP_BASE64 = (
    "UEsDBAoACQAAABaxh1yMsuviEwAAAAcAAAAIABwAZmlsZS50eHRVVAkAA6u41WmruNVpdXgLAAEE9QEAAAQUAAAAgK6VQC12"
    "EbPzEIwdiJ9sf/mjaVBLBwiMsuviEwAAAAcAAABQSwECHgMKAAkAAAAWsYdcjLLr4hMAAAAHAAAACAAYAAAAAAABAAAApIEA"
    "AAAAZmlsZS50eHRVVAUAA6u41Wl1eAsAAQT1AQAABBQAAABQSwUGAAAAAAEAAQBOAAAAZQAAAAAA"
)


def write_encrypted_zip(path: Path) -> None:
    path.write_bytes(base64.b64decode(ENCRYPTED_ZIP_BASE64))


def test_importing_duplicates_module_does_not_replace_sys_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStdout:
        def __init__(self) -> None:
            self.buffer = io.BytesIO()

    fake_stdout = FakeStdout()
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    reloaded = importlib.reload(duplicates_task)

    assert sys.stdout is fake_stdout
    assert reloaded is duplicates_task


def test_find_duplicate_file_groups_across_directories(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()

    duplicate_left = left / "a.txt"
    duplicate_right = right / "b.txt"
    duplicate_left.write_text("same\n", encoding="utf-8")
    duplicate_right.write_text("same\n", encoding="utf-8")
    (left / "unique.txt").write_text("different\n", encoding="utf-8")

    groups = duplicates_task.find_duplicate_file_groups([str(left), str(right)])

    assert groups == [
        duplicates_task.FileGroup(
            total_size=10,
            total_count=2,
            files=sorted([str(duplicate_left.resolve()), str(duplicate_right.resolve())]),
        )
    ]


def test_find_duplicate_directory_groups_across_directories_up_to_ignored_files(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    (left / "nested").mkdir(parents=True)
    (right / "nested").mkdir(parents=True)

    (left / "a.txt").write_text("alpha\n", encoding="utf-8")
    (right / "a.txt").write_text("alpha\n", encoding="utf-8")
    (left / "nested" / "b.txt").write_text("beta\n", encoding="utf-8")
    (right / "nested" / "b.txt").write_text("beta\n", encoding="utf-8")
    (left / ".DS_Store").write_text("ignored\n", encoding="utf-8")

    groups = duplicates_task.find_duplicate_directory_groups([str(left), str(right)])

    expected_paths = sorted([str(left.resolve()), str(right.resolve())])
    assert any(
        group.paths == expected_paths
        and group.tree_size == 11
        and group.file_count == 2
        and group.directory_count == 2
        for group in groups
    )


def test_find_duplicate_file_groups_use_sparse_medium_hash_to_skip_full_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    left = tmp_path / "left.bin"
    right = tmp_path / "right.bin"

    shared_prefix = b"a" * 4096
    left.write_bytes(shared_prefix + (b"b" * 4096) + (b"c" * 4096))
    right.write_bytes(shared_prefix + (b"d" * 4096) + (b"e" * 4096))

    original_get_hash = duplicates_task.get_hash
    calls: list[bool] = []

    def tracking_get_hash(filename: str, first_chunk_only: bool = False) -> bytes:
        calls.append(first_chunk_only)
        return original_get_hash(filename, first_chunk_only=first_chunk_only)

    monkeypatch.setattr(duplicates_task, "get_hash", tracking_get_hash)

    groups = duplicates_task.find_duplicate_file_groups([str(tmp_path)])

    assert groups == []
    assert calls == [True, True]


def test_duplicate_groups_are_sorted_by_reclaimable_space(tmp_path: Path) -> None:
    files_root = tmp_path / "files"
    trees_root = tmp_path / "trees"
    files_root.mkdir()
    trees_root.mkdir()

    for dirname in ["fa", "fb", "fc"]:
        path = files_root / dirname
        path.mkdir()
        (path / "small.txt").write_text("abcde", encoding="utf-8")

    for dirname in ["fd", "fe"]:
        path = files_root / dirname
        path.mkdir()
        (path / "big.txt").write_text("abcdefghij", encoding="utf-8")

    file_groups = duplicates_task.find_duplicate_file_groups([str(files_root)])

    assert [group.total_count for group in file_groups] == [2, 3]
    assert [group.total_size for group in file_groups] == [20, 15]

    for dirname in ["ta", "tb", "tc"]:
        path = trees_root / dirname
        path.mkdir()
        (path / "small.txt").write_text("abcd", encoding="utf-8")

    for dirname in ["td", "te"]:
        path = trees_root / dirname
        path.mkdir()
        (path / "big.txt").write_text("abcdefghij", encoding="utf-8")

    tree_groups = duplicates_task.find_duplicate_directory_groups([str(trees_root)])

    assert [group.total_count for group in tree_groups] == [2, 3]
    assert [group.tree_size for group in tree_groups] == [10, 4]


def test_redundant_file_groups_are_collapsed_under_duplicate_trees(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    other = tmp_path / "other"
    left.mkdir()
    right.mkdir()
    other.mkdir()

    (left / "x.txt").write_text("same\n", encoding="utf-8")
    (right / "x.txt").write_text("same\n", encoding="utf-8")
    (other / "x.txt").write_text("same\n", encoding="utf-8")
    (other / "extra.txt").write_text("different\n", encoding="utf-8")

    report = duplicates_task.find_duplicates([str(left), str(right), str(other)])

    assert report.file_groups == [
        duplicates_task.FileGroup(
            total_size=10,
            total_count=2,
            files=sorted([str(left.resolve() / "x.txt"), str(other.resolve() / "x.txt")]),
        )
    ]
    assert any(group.paths == sorted([str(left.resolve()), str(right.resolve())]) for group in report.tree_groups)


def test_redundant_nested_tree_groups_are_pruned_after_parent_match(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    (left / "nested").mkdir(parents=True)
    (right / "nested").mkdir(parents=True)

    (left / "top.txt").write_text("alpha\n", encoding="utf-8")
    (right / "top.txt").write_text("alpha\n", encoding="utf-8")
    (left / "nested" / "child.txt").write_text("beta\n", encoding="utf-8")
    (right / "nested" / "child.txt").write_text("beta\n", encoding="utf-8")

    groups = duplicates_task.find_duplicate_directory_groups([str(left), str(right)])

    root_paths = sorted([str(left.resolve()), str(right.resolve())])
    nested_paths = sorted([str((left / "nested").resolve()), str((right / "nested").resolve())])

    assert any(group.paths == root_paths for group in groups)
    assert all(group.paths != nested_paths for group in groups)


def test_find_duplicate_directory_groups_ignores_same_real_directory_from_overlapping_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "only.txt").write_text("once\n", encoding="utf-8")

    groups = duplicates_task.find_duplicate_directory_groups([str(root), str(nested)])

    assert groups == []


def test_directory_stage_skips_hashing_when_tree_shape_differs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()

    (left / "a.txt").write_text("x\n", encoding="utf-8")
    (right / "a.txt").write_text("yy\n", encoding="utf-8")

    calls: list[tuple[str, bool]] = []

    def fake_get_hash(filename: str, first_chunk_only: bool = False) -> bytes:
        calls.append((filename, first_chunk_only))
        raise AssertionError("Hashing should not occur when weak tree fingerprints differ")

    monkeypatch.setattr(duplicates_task, "get_hash", fake_get_hash)

    groups = duplicates_task.find_duplicate_directory_groups([str(left), str(right)])

    assert groups == []
    assert calls == []


def test_directory_stage_stops_before_full_hash_when_first_chunk_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()

    (left / "a.txt").write_text("aa\n", encoding="utf-8")
    (right / "a.txt").write_text("bb\n", encoding="utf-8")

    original_get_hash = duplicates_task.get_hash
    calls: list[bool] = []

    def tracking_get_hash(filename: str, first_chunk_only: bool = False) -> bytes:
        calls.append(first_chunk_only)
        return original_get_hash(filename, first_chunk_only=first_chunk_only)

    monkeypatch.setattr(duplicates_task, "get_hash", tracking_get_hash)

    groups = duplicates_task.find_duplicate_directory_groups([str(left), str(right)])

    assert groups == []
    assert calls == [True, True]


def test_zip_contents_can_match_directory_tree(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.txt").write_text("alpha\n", encoding="utf-8")
    (data_dir / "nested").mkdir()
    (data_dir / "nested" / "b.txt").write_text("beta\n", encoding="utf-8")

    archive_path = tmp_path / "data.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("a.txt", "alpha\n")
        zf.writestr("nested/b.txt", "beta\n")
        zf.writestr(".DS_Store", "ignored\n")

    report = duplicates_task.find_duplicates([str(tmp_path)], include_zip_contents=True)

    expected_paths = sorted([str(data_dir.resolve()), str(archive_path.resolve())])
    assert any(group.paths == expected_paths and group.tree_size == 11 for group in report.tree_groups)


def test_zip_only_candidates_use_metadata_before_member_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_a = tmp_path / "a.zip"
    archive_b = tmp_path / "b.zip"

    with zipfile.ZipFile(archive_a, "w") as zf:
        zf.writestr("same-size.txt", "aaaa")

    with zipfile.ZipFile(archive_b, "w") as zf:
        zf.writestr("same-size.txt", "bbbb")

    def fail_on_zip_member_read(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("zip member content should not be read when metadata already differs")

    monkeypatch.setattr(duplicates_task, "get_zip_member_hash", fail_on_zip_member_read)

    groups = duplicates_task.find_duplicate_directory_groups([str(tmp_path)], include_zip_contents=True)

    expected_paths = sorted([str(archive_a.resolve()), str(archive_b.resolve())])
    assert all(group.paths != expected_paths for group in groups)


def test_encrypted_zip_contents_are_skipped_by_default(tmp_path: Path) -> None:
    archive_a = tmp_path / "a.zip"
    archive_b = tmp_path / "b.zip"
    write_encrypted_zip(archive_a)
    write_encrypted_zip(archive_b)

    groups = duplicates_task.find_duplicate_directory_groups([str(tmp_path)], include_zip_contents=True)

    expected_paths = sorted([str(archive_a.resolve()), str(archive_b.resolve())])
    assert all(group.paths != expected_paths for group in groups)


def test_weak_encrypted_zip_matching_uses_visible_metadata_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_a = tmp_path / "a.zip"
    archive_b = tmp_path / "b.zip"
    write_encrypted_zip(archive_a)
    write_encrypted_zip(archive_b)

    def fail_on_zip_member_read(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("encrypted zip matching should not read member contents")

    monkeypatch.setattr(duplicates_task, "get_zip_member_hash", fail_on_zip_member_read)

    groups = duplicates_task.find_duplicate_directory_groups(
        [str(tmp_path)],
        include_zip_contents=True,
        include_weak_encrypted_zip=True,
    )

    expected_paths = sorted([str(archive_a.resolve()), str(archive_b.resolve())])
    assert groups == [
        duplicates_task.TreeGroup(
            tree_size=7,
            total_count=2,
            file_count=1,
            directory_count=1,
            paths=expected_paths,
            match_kind=duplicates_task.TREE_MATCH_WEAK_ENCRYPTED_ZIP,
        )
    ]


def test_weak_encrypted_zip_matching_does_not_match_directories(tmp_path: Path) -> None:
    archive_path = tmp_path / "a.zip"
    write_encrypted_zip(archive_path)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file.txt").write_text("secret\n", encoding="utf-8")

    groups = duplicates_task.find_duplicate_directory_groups(
        [str(tmp_path)],
        include_zip_contents=True,
        include_weak_encrypted_zip=True,
    )

    expected_paths = sorted([str(data_dir.resolve()), str(archive_path.resolve())])
    assert all(group.paths != expected_paths for group in groups)


@pytest.mark.asyncio
async def test_cli_duplicates_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli

    captured: list[tuple[list[str], list[str], list[str], int, bool, bool, bool]] = []

    def fake_check_for_duplicates(
        folders: list[str],
        exclude_filters: list[str],
        include_filters: list[str],
        min_size: int,
        no_default_excludes: bool,
        include_zip_contents: bool = False,
        include_weak_encrypted_zip: bool = False,
    ) -> None:
        captured.append(
            (
                folders,
                exclude_filters,
                include_filters,
                min_size,
                no_default_excludes,
                include_zip_contents,
                include_weak_encrypted_zip,
            )
        )

    monkeypatch.setattr(duplicates_task, "check_for_duplicates", fake_check_for_duplicates)
    monkeypatch.setattr(
        "sys.argv",
        [
            "dev.py",
            "duplicates",
            "dir-a",
            "dir-b",
            "--exclude",
            "*.tmp",
            "--filter",
            "*.txt",
            "--size",
            "12",
            "--no-default-excludes",
            "--zip-contents",
            "--weak-encrypted-zip",
        ],
    )

    result = await cli.async_main()

    assert result == 0
    assert captured == [(["dir-a", "dir-b"], ["*.tmp"], ["*.txt"], 12, True, True, True)]
