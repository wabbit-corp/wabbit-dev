from typing import List, Generator, Callable

import os
import shutil
from pathlib import Path
import fnmatch
import jinja2
import pathspec
import hashlib

from dev.messages import info, error

##################################################################################################
# File Reading/Writing
##################################################################################################

def copy(from_: Path, to: Path) -> None:
    assert isinstance(from_, Path), f"Expected Path, got {type(from_)}"
    assert isinstance(to, Path), f"Expected Path, got {type(to)}"
    assert from_.exists(), f"File {from_} does not exist"
    assert from_.is_file() or from_.is_dir(), f"Path {from_} is not a file or directory"

    if not to.parent.exists():
        info(f"Creating directory {to.parent}")
        to.parent.mkdir(parents=True)
    
    if to.exists():
        if from_.is_file() and not to.is_file():
            raise ValueError(f"Cannot copy file {from_} to non-file {to}")
        if from_.is_dir() and not to.is_dir():
            raise ValueError(f"Cannot copy directory {from_} to non-directory {to}")
        
        if from_.is_file():
            # Now we need to check if the files are the same
            from_hash = hashlib.sha256(from_.read_bytes()).hexdigest()
            to_hash = hashlib.sha256(to.read_bytes()).hexdigest()
            
            if from_hash == to_hash:
                return

            info(f"Overwriting {to} with {from_}")
            shutil.copyfile(from_, to)
        else:
            assert False, "Not implemented"
    else:
        if from_.is_file():
            info(f"Copying {from_} to {to}")
            shutil.copyfile(from_, to)
        else:
            info(f"Copying directory {from_} to {to}")
            shutil.copytree(from_, to)


def list_files(path: Path) -> List[Path]:
    assert isinstance(path, Path), f"Expected Path, got {type(path)}"
    assert path.exists(), f"Directory {path} does not exist"
    assert path.is_dir(), f"Path {path} is not a directory"
    return [Path(f) for f in os.listdir(path)]


def read_text_file(path: Path) -> str:
    assert isinstance(path, Path), f"Expected Path, got {type(path)}"
    assert path.exists(), f"File {path} does not exist"
    with open(path, 'rt', encoding='utf-8') as f:
        return f.read()


def read_template(path: Path) -> jinja2.Template:
    assert isinstance(path, Path), f"Expected Path, got {type(path)}"
    return jinja2.Template(read_text_file(path))


def delete_if_exists(path: Path) -> None:
    if path.exists():
        info(f"Deleting {path}")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def touch(path: Path) -> None:
    if not path.exists():
        info(f"Creating an empty file at {path}")
        path.touch()


def write_text_file(path: Path, content: str) -> None:
    assert isinstance(path, Path), f"Expected Path, got {type(path)}"

    if not path.parent.exists():
        info(f"Creating directory {path.parent}")
        path.parent.mkdir(parents=True)

    content_bytes = content.encode('utf-8')
    assert '\r\n' not in content, "Windows line endings detected"

    if path.exists():
        # if size is not the same, we are definitely overwriting
        old_content = path.read_text()
        assert '\r\n' not in old_content, "Windows line endings detected"

        # print("size: ", path.stat().st_size, len(content_bytes))
        old_content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        new_content_hash = hashlib.sha256(content_bytes).hexdigest()
        # print("hash: ", old_content_hash, new_content_hash)

        if (path.stat().st_size != len(content_bytes)) or (old_content_hash != new_content_hash):

            # Compute diff:
            from difflib import unified_diff
            diff = unified_diff(old_content.splitlines(), content.splitlines(), lineterm='')
            total_added = 0
            total_removed = 0
            for line in diff:
                if line.startswith('+'):
                    total_added += 1
                elif line.startswith('-'):
                    total_removed += 1

            info(f'Modifying {path}: {total_removed} lines removed, {total_added} lines added')
            with open(path, 'wb+') as f:
                f.write(content_bytes)
        else:
            return
    else:
        info(f'Writing to {path}')
        with open(path, 'wb+') as f:
            f.write(content_bytes)


def walk_files(path: Path, predicate: Callable[[Path], bool] | None = None) -> Generator[Path, None, None]:
    assert isinstance(path, Path), f"Expected Path, got {type(path)}"
    if predicate is not None and not predicate(path):
        return

    if os.path.isfile(path):
        yield path

    elif os.path.isdir(path):
        subfiles = os.listdir(path)

        for subfile in subfiles:
            yield from walk_files(path / subfile, predicate=predicate)
    else:
        raise ValueError(f"Unknown file type: {path}")


class FileSet:
    def __init__(self, base_path: Path, positive: List[str], negative: List[str]):
        self.base_path = base_path
        self.positive = positive
        self.negative = negative

        self.path_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, list(positive) + ['!' + n for n in negative])

    def __call__(self, path: Path) -> bool:
        # Use ignore list using globbing
        # files = [file for file in files if not any(fnmatch.fnmatch(file, pattern) for pattern in ignore)]

        # rel_path = path.relative_to(self.base_path).as_posix()
        # is_positive = any(fnmatch.fnmatch(rel_path, pattern) for pattern in self.positive)
        # is_negative = any(fnmatch.fnmatch(rel_path, pattern) for pattern in self.negative)

        # return is_positive and not is_negative

        rel_path = '/' + path.relative_to(self.base_path).as_posix()

        # print(f"Checking {rel_path} against {self.positive} and {self.negative}: {self.path_spec.match_file(rel_path)}")
        return self.path_spec.match_file(rel_path)

    def __add__(self, other: 'FileSet') -> 'FileSet':
        return FileSet(
            self.base_path,
            self.positive + other.positive,
            self.negative + other.negative)


def read_ignore_file(path: Path, extra_positive: List[str] | None = None) -> FileSet:
    assert isinstance(path, Path), f"Expected Path, got {type(path)}"

    if not path.exists():
        return FileSet(path.parent, [], [])

    with open(path, 'rt', encoding='utf-8') as f:
        ignore = f.readlines()
        ignore = [i.strip() for i in ignore]
        ignore = [i for i in ignore if not i.startswith("#")]
        ignore = [i for i in ignore if i != ""]

        positive = [i for i in ignore if not i.startswith("!")]
        negative = [i[1:] for i in ignore if i.startswith("!")]

        return FileSet(path.parent, positive + (extra_positive or []), negative)
