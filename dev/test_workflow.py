import requests
import re
import csv
import dateparser
import datetime
import time
import yaml
import json
import os
import shutil
from typing import Callable, Generator, Any
from collections import namedtuple, defaultdict
from namedlist import namedlist


def digest(func, args, kwargs):
    import hashlib

    h = hashlib.sha256()
    data = [hex(id(func)), func.__name__, func.__module__, args, kwargs]
    h.update(repr(data).encode("utf-8"))
    return h.hexdigest()


def read_file(path):
    with open(path, "r") as f:
        return f.read()


def list_dir(path):
    return os.listdir(path)


# I/O Dependencies
DirList = namedtuple("DirList", "path")
LocalFile = namedtuple("LocalFile", "path")
RemoteFile = namedtuple("RemoteFile", "url path")

Call = namedtuple("Call", "func args kwargs")


def call(func, *args, **kwargs):
    return Call(func, args, kwargs)


class Context:
    def __init__(self):
        self.cache = {}
        self.dependencies = defaultdict(set)
        self.all_dependencies = set()
        pass

    def run(self, func, *args, **kwargs):
        key = digest(func, args, kwargs)
        if key in self.cache:
            return key, self.cache[key], self.dependencies[key]

        dependencies = set()

        gen = func(*args, **kwargs)

        if not isinstance(gen, Generator):
            return key, gen, dependencies

        last_value = None

        while True:
            try:
                step = gen.send(last_value)

                if isinstance(step, Call):
                    if step.func == read_file:
                        dependencies.add(LocalFile(step.args[0]))
                        last_value = read_file(*step.args, **step.kwargs)
                    elif step.func == list_dir:
                        dependencies.add(DirList(step.args[0]))
                        last_value = list_dir(*step.args, **step.kwargs)
                    else:
                        call_key, last_value, deps = self.run(step.func, *step.args)
                        if len(deps) > 0:
                            dependencies.update(deps)
                else:
                    print("Step is not a call:", step)
                    last_value = None

            except StopIteration as e:
                self.cache[key] = e.value
                self.dependencies[key] = dependencies
                self.all_dependencies.update(dependencies)
                return key, e.value, dependencies


def foo(i):
    s = yield call(read_file, "test.txt")
    print("foo", i)
    return i * i


def test():
    for i in range(10):
        x = yield call(foo, i)
        print(x)
    return "done"


if __name__ == "__main__":
    ctx = Context()
    print(ctx.run(test))
    print(ctx.run(test))
