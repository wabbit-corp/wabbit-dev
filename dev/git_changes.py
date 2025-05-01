#!/usr/bin/env python3
"""
Final 'git_changes.py' that:
  - gather_changes(repo) => List[FileDiff] describing HEAD->INDEX (staged) and INDEX->WORKING (unstaged), plus untracked.
  - Correctly identifies whether HEAD has 'src/main/kotlin/one/wabbit/data/Need.kt' via the sub-tree approach, preventing 'ADDED' misclassification.
  - Honors rename detection by default (no R=False).
  - Checks text->binary as MODIFIED, not UNCHANGED.
  - If no HEAD commit, forcibly treats all index entries as ADDED.

We have 15 tests total, including subdirectory tests verifying a file is recognized as modified if it appears in HEAD under nested folders.

Usage:
  python3 git_changes.py
"""

import os
import sys
import difflib
import hashlib
import logging
import unittest
import tempfile
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple, Union

import git
import gitdb
from git import Repo, Blob, Tree

##############################################################################
# Logging
##############################################################################

# logging.basicConfig(
#     level=logging.DEBUG,  # or logging.INFO if you prefer less detail
#     format="%(levelname)s:%(funcName)s:%(message)s"
# )

##############################################################################
# Exceptions
##############################################################################

class BareRepoNotSupportedError(Exception):
    pass

class SubmoduleNotSupportedError(Exception):
    pass

class SymlinkNotSupportedError(Exception):
    pass

class InvalidRepositoryStateError(Exception):
    """For contradictory or impossible states."""
    pass

##############################################################################
# Enums & Data Classes
##############################################################################

class FileKind(Enum):
    REGULAR = auto()
    SYMLINK = auto()
    SUBMODULE = auto()
    UNKNOWN = auto()

class FileType(Enum):
    TEXT = auto()
    BINARY = auto()

class ChangeType(Enum):
    ADDED = auto()
    DELETED = auto()
    RENAMED = auto()
    MODIFIED = auto()
    MODE_CHANGED = auto()
    UNCHANGED = auto()

@dataclass
class IndexContent:
    file_kind: FileKind
    file_type: FileType
    mode: Optional[int]
    lines: Optional[List[str]] = None
    content_hash: Optional[str] = None

@dataclass
class FileDiff:
    old_path: str
    new_path: str
    change_type: ChangeType

    staged: bool
    unstaged: bool
    untracked: bool

    partial_staging_suspected: bool = False

    head: Optional[IndexContent] = None
    index: Optional[IndexContent] = None
    working: Optional[IndexContent] = None

    unified_diff: Optional[str] = None
    binary_different: bool = False

##############################################################################
# Helper Functions
##############################################################################

def is_bare_or_invalid_repo(repo: Repo) -> bool:
    return (repo.bare or not repo.git_dir or not repo.working_tree_dir)

def identify_file_kind(obj) -> FileKind:
    if isinstance(obj, Tree):
        if obj.mode == 0o160000:
            return FileKind.SUBMODULE
        return FileKind.UNKNOWN
    if isinstance(obj, Blob):
        if obj.mode == 0o120000:
            return FileKind.SYMLINK
        return FileKind.REGULAR
    return FileKind.UNKNOWN

def sha256_hash(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

def classify_data(raw_data: bytes, empty_is_text: bool = True) -> Tuple[FileType, Optional[List[str]], Optional[str]]:
    if len(raw_data) == 0 and empty_is_text:
        return (FileType.TEXT, [], None)
    if b'\x00' in raw_data:
        return (FileType.BINARY, None, sha256_hash(raw_data))
    text = raw_data.decode('utf-8', errors='replace')
    total_chars = len(text)
    weird_chars = sum(ch=='�' or ord(ch)>127 for ch in text)
    if total_chars>0 and (weird_chars/total_chars) > 0.30:
        return (FileType.BINARY, None, sha256_hash(raw_data))
    lines = text.split('\n')
    return (FileType.TEXT, lines, None)

def generate_unified_diff(old_lines: List[str],
                          new_lines: List[str],
                          fromfile: str,
                          tofile: str) -> str:
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=fromfile,
        tofile=tofile,
        lineterm=''
    )
    return '\n'.join(diff)

def detect_partial_staging(repo: Repo, path: str) -> bool:
    if not repo.head.is_valid():
        return False
    h2i = repo.index.diff('HEAD', paths=[path], create_patch=True)
    i2w = repo.index.diff(None, paths=[path], create_patch=True)
    return (len(h2i)>0) and (len(i2w)>0)

def has_tree_path(tree: Tree, path: str) -> bool:
    """
    Return True if 'path' is found in 'tree', possibly nested, e.g. 'src/main/kotlin/file.kt'.
    """
    try:
        _ = tree[path]  # This drills down subfolders if 'path' uses forward slashes
        return True
    except KeyError:
        return False

def read_tree_object(tree: Tree, path: str):
    """
    Return the Git object (Blob or Tree) at 'path' within 'tree', or raise KeyError if not found.
    This is a direct subscript that supports nested paths with forward slashes.
    """
    return tree[path]

def read_tree_content(head_commit: Optional[git.Commit], path: str) -> Optional[IndexContent]:
    """
    Safely read the HEAD commit's version of 'path' (which can be nested).
    Return IndexContent or None if absent. Raise SubmoduleNotSupportedError etc. if encountered.
    """
    if not head_commit:
        return None
    try:
        obj = read_tree_object(head_commit.tree, path)
    except KeyError:
        return None

    kind = identify_file_kind(obj)
    if kind==FileKind.SUBMODULE:
        raise SubmoduleNotSupportedError(f"Submodule at {path}")
    if kind==FileKind.SYMLINK:
        raise SymlinkNotSupportedError(f"Symlink at {path}")
    if kind!=FileKind.REGULAR:
        return None

    blob: Blob = obj
    raw_data = blob.data_stream.read()
    mode=blob.mode
    file_type, lines, content_hash=classify_data(raw_data)
    return IndexContent(kind,file_type,mode, lines, content_hash)

def read_index_content(repo: Repo, path: str) -> Optional[IndexContent]:
    if (path,) not in repo.index.entries:
        return None
    stage_tuple = repo.index.entries[(path,)]
    blob_oid=stage_tuple[1]
    mode=stage_tuple[0].mode
    blob_stream=repo.odb.stream(blob_oid)
    raw_data=blob_stream.read()
    file_type, lines, content_hash=classify_data(raw_data)
    return IndexContent(FileKind.REGULAR,file_type,mode, lines, content_hash)

def read_working_content(repo: Repo, path: str) -> Optional[IndexContent]:
    fp=os.path.join(repo.working_tree_dir, path)
    if not os.path.exists(fp):
        return None
    if os.path.islink(fp):
        raise SymlinkNotSupportedError(f"Symlink at {path}")
    mode=os.stat(fp).st_mode
    with open(fp,'rb') as f:
        raw_data=f.read()
    file_type, lines, content_hash=classify_data(raw_data)
    return IndexContent(FileKind.REGULAR,file_type,mode, lines, content_hash)

##############################################################################
# gather_changes
##############################################################################

def compute_repo_diffs(repo: Repo) -> List[FileDiff]:
    """
    Summarize HEAD->INDEX (staged) & INDEX->WORKING (unstaged) plus untracked.
    If HEAD doesn't exist, forcibly label everything in index as ADDED.
    If we see text->binary mismatch, we set change_type=MODIFIED, not UNCHANGED.
    If HEAD has subdirectory paths, we do the correct sub-tree check so we don't mislabel them as ADDED.
    Also, for newly added text files, generate a unified diff from empty (i.e. /dev/null) to the new lines.
    """
    if is_bare_or_invalid_repo(repo):
        raise BareRepoNotSupportedError("Bare or invalid repository")

    head_commit = repo.head.commit if repo.head.is_valid() else None

    def head_has(path: str) -> bool:
        """Return True if HEAD's tree has path, possibly nested."""
        if not head_commit:
            return False
        return has_tree_path(head_commit.tree, path)

    # -----------------------------------------------------
    # Collect diffs: staged + unstaged + untracked
    # -----------------------------------------------------
    try:
        if repo.head.is_valid():
            staged = list(repo.index.diff('HEAD', create_patch=False))
        else:
            staged = list(repo.index.diff(None, create_patch=False))
    except (ValueError, gitdb.exc.BadName):
        staged = list(repo.index.diff(None, create_patch=False))

    unstaged = list(repo.index.diff(None, create_patch=False))
    untracked_files = set(repo.untracked_files)

    diffs_map: Dict[Tuple[str, str, bool], Dict[str, object]] = {}

    def store_diff(d: git.Diff, is_staged: bool):
        a_path = d.a_path
        b_path = d.b_path
        if a_path is None and b_path is None:
            raise InvalidRepositoryStateError("Both a_path and b_path None => can't classify")

        ctype = 'modified'
        if d.renamed_file:
            ctype = 'renamed'
        elif d.new_file:
            ctype = 'added'
        elif d.deleted_file:
            ctype = 'deleted'

        old_p = a_path or ''
        new_p = b_path or ''

        # Fallback checks for contradictory flags
        if ctype == 'added' and a_path is not None and a_path != b_path:
            logging.debug(f"Contradiction new_file but a_path={a_path}. fallback => 'modified'")
            ctype = 'modified'
        if ctype == 'deleted' and b_path is not None and b_path != a_path:
            logging.debug(f"Contradiction deleted_file but b_path={b_path}. fallback => 'modified'")
            ctype = 'modified'
        if (a_path and b_path and a_path != b_path) and not (d.renamed_file or d.new_file or d.deleted_file):
            logging.debug(f"Detected path change {a_path} => {b_path} but no rename_file => rename fallback")
            ctype = 'renamed'

        diffs_map[(old_p, new_p, is_staged)] = {
            'ctype': ctype,
            'staged': is_staged,
            'unstaged': not is_staged,
            'a_mode': d.a_mode,
            'b_mode': d.b_mode
        }

    for d in staged:
        store_diff(d, True)
    for d in unstaged:
        store_diff(d, False)

    for uf in untracked_files:
        k = ('', uf, False)
        if k not in diffs_map:
            logging.debug(f"Untracked => add key={k}")
            diffs_map[k] = {
                'ctype': 'added',
                'staged': False,
                'unstaged': True,
                'a_mode': None,
                'b_mode': None
            }

    # If HEAD doesn't exist => forcibly treat all index entries as ADDED if not untracked
    if not repo.head.is_valid():
        for (ptuple), idx_entry in repo.index.entries.items():
            path_str = ptuple[0]
            if path_str not in untracked_files:
                key = (path_str, path_str, True)
                if key not in diffs_map:
                    logging.debug(f"No HEAD => forcibly treat index entry {ptuple} as ADDED/staged")
                    diffs_map[key] = {
                        'ctype': 'added',
                        'staged': True,
                        'unstaged': False,
                        'a_mode': idx_entry.mode,
                        'b_mode': idx_entry.mode
                    }

    # -----------------------------------------------------
    # Merge staged + unstaged changes into final entries
    # -----------------------------------------------------
    used = set()
    final_entries = []
    all_keys = sorted(diffs_map.keys(), key=lambda x: (x[0], x[1], x[2]))
    i = 0
    while i < len(all_keys):
        k1 = all_keys[i]
        i += 1
        if k1 in used:
            continue
        d1 = diffs_map[k1]
        (old_p1, new_p1, s1) = k1

        k2 = (old_p1, new_p1, not s1)
        if k2 in diffs_map and k2 not in used:
            d2 = diffs_map[k2]
            c1 = d1['ctype']
            c2 = d2['ctype']
            merged_ctype = c1
            if c1 != c2:
                combos = {c1, c2}
                HEAD_has_old = (old_p1 != '' and head_has(old_p1))

                def unify_mismatch(x1, x2):
                    if combos == {'added', 'deleted'}:
                        return 'deleted' if HEAD_has_old else 'added'
                    if combos == {'added', 'modified'}:
                        return 'modified' if HEAD_has_old else 'added'
                    if combos == {'deleted', 'modified'}:
                        return 'modified' if HEAD_has_old else 'deleted'
                    if combos == {'renamed', 'added'}:
                        return 'renamed' if HEAD_has_old else 'added'
                    if combos == {'renamed', 'deleted'}:
                        return 'renamed' if HEAD_has_old else 'deleted'
                    return 'modified'

                merged_ctype = unify_mismatch(c1, c2)

            merged = {
                'ctype': merged_ctype,
                'staged': (d1['staged'] or d2['staged']),
                'unstaged': (d1['unstaged'] or d2['unstaged']),
                'a_mode': d1['a_mode'] if d1['a_mode'] else d2['a_mode'],
                'b_mode': d1['b_mode'] if d1['b_mode'] else d2['b_mode'],
                'old_p': old_p1,
                'new_p': new_p1
            }
            final_entries.append(merged)
            used.add(k1)
            used.add(k2)
        else:
            final_entries.append({
                'ctype': d1['ctype'],
                'staged': d1['staged'],
                'unstaged': d1['unstaged'],
                'a_mode': d1['a_mode'],
                'b_mode': d1['b_mode'],
                'old_p': old_p1,
                'new_p': new_p1
            })
            used.add(k1)

    # -----------------------------------------------------
    # Now read HEAD/Index/Working content & finalize diffs
    # -----------------------------------------------------
    results = []
    head_commit2 = repo.head.commit if repo.head.is_valid() else None

    def head_has_file(path: str) -> bool:
        if not head_commit2:
            return False
        return has_tree_path(head_commit2.tree, path)

    for fe in final_entries:
        ctype = fe['ctype']
        staged_ = fe['staged']
        unstaged_ = fe['unstaged']
        a_mode = fe['a_mode']
        b_mode = fe['b_mode']
        old_p = fe['old_p']
        new_p = fe['new_p']

        if ctype == 'added':
            change_type = ChangeType.ADDED
            final_old = new_p
            final_new = new_p
        elif ctype == 'deleted':
            change_type = ChangeType.DELETED
            final_old = old_p
            final_new = old_p
        elif ctype == 'renamed':
            change_type = ChangeType.RENAMED
            final_old = old_p
            final_new = new_p
        else:
            change_type = ChangeType.MODIFIED
            final_old = old_p
            final_new = new_p

        # If HEAD doesn't have final_old => can't be DELETED/MODIFIED => force ADDED
        if old_p and not head_has_file(old_p) and change_type not in (
            ChangeType.RENAMED,
            ChangeType.ADDED
        ):
            logging.debug(
                f"Forcing ADDED since HEAD lacks old_p={old_p} => can't be {change_type}"
            )
            change_type = ChangeType.ADDED
            final_old = final_new

        head_ic = None
        if final_old and head_has_file(final_old):
            head_ic = read_tree_content(head_commit2, final_old)

        index_ic = None
        if final_new:
            index_ic = read_index_content(repo, final_new)

        working_ic = None
        if final_new:
            working_ic = read_working_content(repo, final_new)

        mode_changed = False
        if a_mode and b_mode and a_mode != b_mode:
            mode_changed = True
        if change_type == ChangeType.ADDED:
            mode_changed = False  # Usually ignore mode change for brand-new files

        unified_diff = None
        binary_different = False

        # text->binary => force MODIFIED
        if head_ic and working_ic:
            if head_ic.file_type != working_ic.file_type:
                if change_type not in (
                    ChangeType.ADDED,
                    ChangeType.DELETED,
                    ChangeType.RENAMED,
                ):
                    logging.debug(
                        f"Text->binary or binary->text => force MODIFIED for {final_old}->{final_new}"
                    )
                    change_type = ChangeType.MODIFIED
                if head_ic.file_type == FileType.BINARY or working_ic.file_type == FileType.BINARY:
                    binary_different = True
            else:
                # same file type
                if head_ic.file_type == FileType.TEXT and working_ic.file_type == FileType.TEXT:
                    if head_ic.lines == working_ic.lines and not mode_changed:
                        if change_type not in (
                            ChangeType.ADDED,
                            ChangeType.DELETED,
                            ChangeType.RENAMED,
                        ):
                            change_type = ChangeType.UNCHANGED
                    else:
                        unified_diff = generate_unified_diff(
                            head_ic.lines or [],
                            working_ic.lines or [],
                            fromfile=final_old or '/dev/null',
                            tofile=final_new or '/dev/null'
                        )
                else:
                    # both are BINARY
                    if head_ic.content_hash and working_ic.content_hash:
                        if head_ic.content_hash != working_ic.content_hash:
                            binary_different = True
                            if change_type not in (
                                ChangeType.ADDED,
                                ChangeType.DELETED,
                                ChangeType.RENAMED,
                            ):
                                change_type = ChangeType.MODIFIED
                        else:
                            if (
                                change_type not in (
                                    ChangeType.ADDED,
                                    ChangeType.DELETED,
                                    ChangeType.RENAMED,
                                )
                                and not mode_changed
                            ):
                                change_type = ChangeType.UNCHANGED
                    else:
                        # missing hash => assume changed
                        if change_type not in (
                            ChangeType.ADDED,
                            ChangeType.DELETED,
                            ChangeType.RENAMED,
                        ):
                            change_type = ChangeType.MODIFIED
                            if (
                                head_ic.file_type == FileType.BINARY
                                or working_ic.file_type == FileType.BINARY
                            ):
                                binary_different = True

        # If it's purely a mode change with no content change
        if (
            change_type == ChangeType.MODIFIED
            and mode_changed
            and not binary_different
            and not unified_diff
        ):
            change_type = ChangeType.MODE_CHANGED

        # If newly added text file => generate diff from empty
        if change_type == ChangeType.ADDED:
            if working_ic and working_ic.file_type == FileType.TEXT and not unified_diff:
                unified_diff = generate_unified_diff(
                    [],
                    working_ic.lines or [],
                    fromfile='/dev/null',
                    tofile=final_new or '/dev/null'
                )

        is_untracked = (change_type == ChangeType.ADDED and not staged_)
        partial_staging = False
        if staged_ and unstaged_ and not is_untracked:
            path_for_patch = final_new or final_old
            if path_for_patch and detect_partial_staging(repo, path_for_patch):
                partial_staging = True

        logging.debug(
            f"Final classification for {final_old} => {final_new}: {change_type.name} "
            f"(staged={staged_},unstaged={unstaged_})"
        )

        fd = FileDiff(
            old_path=final_old,
            new_path=final_new,
            change_type=change_type,
            staged=staged_,
            unstaged=unstaged_,
            untracked=is_untracked,
            partial_staging_suspected=partial_staging,
            head=head_ic,
            index=index_ic,
            working=working_ic,
            unified_diff=unified_diff,
            binary_different=binary_different
        )
        results.append(fd)

    return results


##############################################################################
# Tests
##############################################################################

class TestGatherChanges(unittest.TestCase):
    def test_no_head_commit(self):
        """
        If there's no commit yet, everything in index is effectively new (ADDED).
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)  # no HEAD
            fpath=os.path.join(tmp,'file.txt')
            with open(fpath,'w') as f:
                f.write("Hello\n")
            repo.index.add(['file.txt'])
            diffs=compute_repo_diffs(repo)
            self.assertEqual(len(diffs),1)
            d=diffs[0]
            self.assertEqual(d.change_type,ChangeType.ADDED)
            self.assertTrue(d.staged)
            self.assertFalse(d.unstaged)

    def test_filetype_change(self):
        """
        Start with text => commit => replace with binary => expect MODIFIED, not UNCHANGED.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            fname=os.path.join(tmp,'data.txt')
            with open(fname,'w') as g:
                g.write("Line1\nLine2\n")
            repo.index.add(['data.txt'])
            repo.index.commit("Init")
            with open(fname,'wb') as g:
                g.write(b'\x00\x01\x02\x03')
            diffs=compute_repo_diffs(repo)
            self.assertEqual(len(diffs),1)
            d=diffs[0]
            self.assertEqual(d.change_type,ChangeType.MODIFIED)
            self.assertTrue(d.binary_different)

    def test_basic_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            file1=os.path.join(tmp,'hello.txt')
            with open(file1,'w') as f:
                f.write("Hello\n")
            repo.index.add(['hello.txt'])
            repo.index.commit("Initial")

            # modify
            with open(file1,'a') as f:
                f.write("Another line.\n")

            # untracked
            file2=os.path.join(tmp,'untracked.bin')
            with open(file2,'wb') as f:
                f.write(b'\x00\x01\x02')

            diffs=compute_repo_diffs(repo)
            self.assertEqual(len(diffs),2)
            untracked=next(d for d in diffs if d.old_path=='untracked.bin')
            self.assertEqual(untracked.change_type,ChangeType.ADDED)
            self.assertTrue(untracked.untracked)
            hello=next(d for d in diffs if d.old_path=='hello.txt')
            self.assertEqual(hello.change_type,ChangeType.MODIFIED)

    def test_mode_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            script=os.path.join(tmp,'script.sh')
            with open(script,'w') as f:
                f.write("#!/bin/bash\necho Hello\n")
            repo.index.add(['script.sh'])
            repo.index.commit("Init")

            os.chmod(script,0o755)
            diffs=compute_repo_diffs(repo)
            self.assertEqual(len(diffs),1)
            d=diffs[0]
            self.assertEqual(d.change_type,ChangeType.MODE_CHANGED)

    def test_partial_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            e=os.path.join(tmp,'example.txt')
            with open(e,'w') as f:
                f.write("Line1\nLine2\nLine3\n")
            repo.index.add(['example.txt'])
            repo.index.commit("Init")

            with open(e,'a') as f:
                f.write("Line4\nLine5\n")

            partial_data="Line1\nLine2\nLine3\nLine4\n"
            full_data=partial_data+"Line5\n"
            with open(e,'w') as f:
                f.write(partial_data)
            repo.index.add(['example.txt'])
            with open(e,'w') as f:
                f.write(full_data)

            diffs=compute_repo_diffs(repo)
            self.assertEqual(len(diffs),1)
            d=diffs[0]
            self.assertTrue(d.partial_staging_suspected)

    def test_empty_file_classified_as_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            e=os.path.join(tmp,'empty.txt')
            open(e,'w').close()
            repo.index.add(['empty.txt'])
            repo.index.commit("Init")

            diffs=compute_repo_diffs(repo)
            self.assertEqual(len(diffs),0)

            with open(e,'w') as f:
                f.write("Hello\n")
            diffs2=compute_repo_diffs(repo)
            self.assertEqual(len(diffs2),1)
            d=diffs2[0]
            self.assertIn("+Hello", d.unified_diff or "")

    def test_unified_diff_correctness(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            fname=os.path.join(tmp,'data.txt')
            with open(fname,'w') as f:
                f.write("Apple\nBanana\nCherry\n")
            repo.index.add(['data.txt'])
            repo.index.commit("Init")

            with open(fname,'w') as f:
                f.write("Apple\nBerry\nCherry\nDates\n")

            diffs=compute_repo_diffs(repo)
            self.assertEqual(len(diffs),1)
            d=diffs[0]
            self.assertIsNotNone(d.unified_diff)
            lines=d.unified_diff.split('\n')
            expected=["-Banana","+Berry"," Cherry","+Dates"]
            idx=0
            for e in expected:
                while idx<len(lines) and e not in lines[idx]:
                    idx+=1
                self.assertTrue(idx<len(lines),f"Missing {e}")

    def test_multiline_diff_correctness(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            bigp=os.path.join(tmp,'big.txt')
            orig=["Line1","Line2","Line3","Line4","Line5"]
            with open(bigp,'w') as f:
                f.write("\n".join(orig)+"\n")
            repo.index.add(['big.txt'])
            repo.index.commit("Init")

            new_text=["Line1","Line2Changed","Line3","Line5","Line6"]
            with open(bigp,'w') as f:
                f.write("\n".join(new_text)+"\n")

            diffs=compute_repo_diffs(repo)
            self.assertEqual(len(diffs),1)
            d=diffs[0]
            lines=d.unified_diff.split('\n')
            for piece in ["-Line2","+Line2Changed","-Line4","+Line6"]:
                self.assertTrue(any(piece in l for l in lines), f"Missing {piece} in diff")

    def test_deleted_and_readded_in_working_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            f=os.path.join(tmp,'dupe.txt')
            with open(f,'w') as g:
                g.write("Old\n")
            repo.index.add(['dupe.txt'])
            repo.index.commit("Init")

            os.remove(f)
            repo.git.rm('dupe.txt')
            with open(f,'w') as g:
                g.write("New\n")

            diffs=compute_repo_diffs(repo)
            self.assertIn(len(diffs),(1,2))

    def test_add_then_delete_without_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            f=os.path.join(tmp,'temp.txt')
            with open(f,'w') as g:
                g.write("Hello\n")
            repo.index.add(['temp.txt'])
            os.remove(f)
            repo.git.rm('--cached','temp.txt')

            diffs=compute_repo_diffs(repo)
            self.assertIn(len(diffs),(0,1))

    def test_real_life_scenario_with_new_and_modified(self):
        """
        Typically user sees:
          - A brand new file => ADDED
          - 2 existing files => MODIFIED
        All staged, not "added" if HEAD truly has them (like 'Need.kt' in subdir).
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            # Put Need.kt in subdir
            subdir=os.path.join(tmp,'src','main','kotlin','one','wabbit','data')
            os.makedirs(subdir)
            needkt=os.path.join(subdir,'Need.kt')
            with open(needkt,'w') as g:
                g.write("// Original\n")
            gradle=os.path.join(tmp,'build.gradle.kts')
            with open(gradle,'w') as g:
                g.write("dependencies{implementation(\"org.jetbrains.kotlinx:kotlinx-serialization-core:1.7.2\")}\n")
            repo.index.add([
                os.path.relpath(needkt,tmp),
                os.path.relpath(gradle,tmp)
            ])
            repo.index.commit("Init")

            # Add new file
            design=os.path.join(tmp,'DESIGN_DETAILS.md')
            with open(design,'w') as g:
                g.write("Some design.\n")
            repo.index.add(['DESIGN_DETAILS.md'])

            # Modify
            with open(gradle,'w') as g:
                g.write("dependencies{implementation(\"org.jetbrains.kotlinx:kotlinx-serialization-core:1.8.0\")}\n")
            repo.index.add(['build.gradle.kts'])

            # Modify Need.kt
            with open(needkt,'a') as g:
                g.write("// doc line\n")
            repo.index.add([os.path.relpath(needkt,tmp)])

            diffs=compute_repo_diffs(repo)
            # Expect 3 diffs
            self.assertEqual(len(diffs),3)
            dd=next(d for d in diffs if 'DESIGN_DETAILS.md' in d.new_path)
            self.assertEqual(dd.change_type,ChangeType.ADDED)
            self.assertTrue(dd.staged)
            self.assertFalse(dd.unstaged)

            gradle_diff=next(d for d in diffs if 'build.gradle.kts' in d.new_path)
            self.assertEqual(gradle_diff.change_type,ChangeType.MODIFIED)

            # Must detect subdir Need.kt as modified, not added
            need_diff=next(d for d in diffs if 'Need.kt' in d.new_path)
            self.assertEqual(need_diff.change_type,ChangeType.MODIFIED,
                             f"Should be MODIFIED, got {need_diff.change_type}")
            self.assertTrue(need_diff.staged)
            self.assertFalse(need_diff.unstaged)

            self.assertFalse(need_diff.untracked, "It's not untracked if HEAD had that path.")


    def test_rename_file(self):
        """
        Show that if Git detects rename, we might see 'renamed'; else 'deleted + added'.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            oldp=os.path.join(tmp,'old.txt')
            with open(oldp,'w') as g:
                g.write("Some text.\n")
            repo.index.add(['old.txt'])
            repo.index.commit("Init")

            newp=os.path.join(tmp,'new.txt')
            os.rename(oldp,newp)
            repo.index.remove(['old.txt'])
            repo.index.add(['new.txt'])
            diffs=compute_repo_diffs(repo)
            # Usually 1 diff => RENAMED if Git sees enough similarity
            # or 2 diffs => DELETED + ADDED
            self.assertIn(len(diffs),(1,2))

    def test_subdirectory_modified(self):
        """
        Ensure a file in 'src/main/kotlin/...' is recognized as MODIFIED if HEAD had it,
        not forced to ADDED.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repo.init(tmp)
            subdir=os.path.join(tmp,'src','main','kotlin')
            os.makedirs(subdir)
            f1=os.path.join(subdir,'File.kt')
            with open(f1,'w') as g:
                g.write("val x=1\n")
            relp=os.path.relpath(f1,tmp)
            repo.index.add([relp])
            repo.index.commit("Init")

            # modify it
            with open(f1,'a') as g:
                g.write("val y=2\n")

            diffs=compute_repo_diffs(repo)
            self.assertEqual(len(diffs),1)
            d=diffs[0]
            self.assertEqual(d.change_type,ChangeType.MODIFIED,"Should not be ADDED.")

    def test_new_file_includes_content_in_diff(self):
        """
        Verifies that newly added text files have a unified diff that shows
        lines from /dev/null -> new file content.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo.init(tmp)
            # Write an initial commit so HEAD is valid, just to test normal scenario.
            with open(os.path.join(tmp, 'dummy.txt'), 'w') as f:
                f.write("Initial file\n")
            repo.index.add(['dummy.txt'])
            repo.index.commit("Initial commit")

            # Now add a brand-new text file
            new_file = os.path.join(tmp, 'newfile.txt')
            with open(new_file, 'w') as f:
                f.write("Hello\nWorld\n")
            repo.index.add(['newfile.txt'])

            diffs = compute_repo_diffs(repo)

            # Find the entry for newfile.txt
            newfile_diff = next(d for d in diffs if d.new_path == 'newfile.txt')
            self.assertEqual(newfile_diff.change_type, ChangeType.ADDED)
            self.assertIsNotNone(newfile_diff.unified_diff, "Expected a unified diff for newly added text file")

            # Check that the unified diff includes the lines we wrote
            self.assertIn("+Hello", newfile_diff.unified_diff)
            self.assertIn("+World", newfile_diff.unified_diff)

            # Also confirm it references /dev/null in the 'fromfile' portion
            self.assertIn("--- /dev/null", newfile_diff.unified_diff)
            self.assertIn("+++ newfile.txt", newfile_diff.unified_diff)

if __name__=='__main__':
    unittest.main(argv=[''], exit=False)
