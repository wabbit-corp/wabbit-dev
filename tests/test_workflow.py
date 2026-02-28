# mypy: disable-error-code=explicit-any

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from collections.abc import Generator
from typing import Callable, NamedTuple, TypeGuard


class DirList(NamedTuple):
    path: str


class LocalFile(NamedTuple):
    path: str


class RemoteFile(NamedTuple):
    url: str
    path: str


Dependency = DirList | LocalFile | RemoteFile
WorkflowValue = object
WorkflowGenerator = Generator["Call", WorkflowValue | None, WorkflowValue]
WorkflowResult = WorkflowValue | WorkflowGenerator
WorkflowCallable = Callable[..., WorkflowResult]


class Call(NamedTuple):
    func: WorkflowCallable
    args: tuple[object, ...]
    kwargs: dict[str, object]


def digest(
    func: WorkflowCallable,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> str:
    hasher = hashlib.sha256()
    data = [hex(id(func)), func.__name__, func.__module__, args, kwargs]
    hasher.update(repr(data).encode("utf-8"))
    return hasher.hexdigest()


def read_file(path: str) -> str:
    with open(path, encoding="utf-8") as file_obj:
        return file_obj.read()


def list_dir(path: str) -> list[str]:
    return os.listdir(path)


def call(func: WorkflowCallable, *args: object, **kwargs: object) -> Call:
    return Call(func=func, args=args, kwargs=kwargs)


def is_workflow_generator(value: WorkflowResult) -> TypeGuard[WorkflowGenerator]:
    return isinstance(value, Generator)


class Context:
    def __init__(self) -> None:
        self.cache: dict[str, WorkflowValue] = {}
        self.dependencies: defaultdict[str, set[Dependency]] = defaultdict(set)
        self.all_dependencies: set[Dependency] = set()

    def run(
        self,
        func: WorkflowCallable,
        *args: object,
        **kwargs: object,
    ) -> tuple[str, WorkflowValue, set[Dependency]]:
        key = digest(func, args, kwargs)
        if key in self.cache:
            return key, self.cache[key], self.dependencies[key]

        dependencies: set[Dependency] = set()
        generated = func(*args, **kwargs)
        if not is_workflow_generator(generated):
            return key, generated, dependencies

        last_value: WorkflowValue | None = None
        while True:
            try:
                step = generated.send(last_value)
            except StopIteration as stop_exc:
                self.cache[key] = stop_exc.value
                self.dependencies[key] = dependencies
                self.all_dependencies.update(dependencies)
                return key, stop_exc.value, dependencies

            if step.func is read_file:
                if not step.args or not isinstance(step.args[0], str):
                    raise TypeError("read_file call requires a string path")
                path = step.args[0]
                dependencies.add(LocalFile(path))
                last_value = read_file(path)
                continue

            if step.func is list_dir:
                if not step.args or not isinstance(step.args[0], str):
                    raise TypeError("list_dir call requires a string path")
                path = step.args[0]
                dependencies.add(DirList(path))
                last_value = list_dir(path)
                continue

            _, nested_value, nested_dependencies = self.run(step.func, *step.args, **step.kwargs)
            if nested_dependencies:
                dependencies.update(nested_dependencies)
            last_value = nested_value


def foo(i: int) -> Generator[Call, WorkflowValue | None, int]:
    _ = yield call(read_file, "test.txt")
    return i * i


def run_workflow_demo() -> Generator[Call, WorkflowValue | None, str]:
    for i in range(10):
        _ = yield call(foo, i)
    return "done"


if __name__ == "__main__":
    context = Context()
    print(context.run(run_workflow_demo))
    print(context.run(run_workflow_demo))
