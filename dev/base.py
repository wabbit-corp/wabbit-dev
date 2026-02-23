import abc
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from mu.exec import ExecutionContext

from dev.messages import error


class Callback:
    pass


@dataclass(frozen=True)
class TypedConfigCommandRegistration:
    command_type: type[Any]
    apply: Callable[[Any], None]


@dataclass
class OnExitCallback(Callback):
    value: Callable[[], None]


@dataclass
class OnFailureCallback(Callback):
    value: Callable[[BaseException], None]


@dataclass
class OnSuccessCallback(Callback):
    value: Callable[[], None]


class Scope:
    def __init__(self) -> None:
        self.deferred: list[Callback] = []

    def defer(self, fn: Callable[[], None]) -> None:
        self.deferred.append(OnExitCallback(fn))

    def on_exit(self, fn: Callable[[], None]) -> None:
        self.deferred.append(OnExitCallback(fn))

    def on_failure(self, fn: Callable[[BaseException], None]) -> None:
        self.deferred.append(OnFailureCallback(fn))

    def on_success(self, fn: Callable[[], None]) -> None:
        self.deferred.append(OnSuccessCallback(fn))

    def __enter__(self):
        assert len(self.deferred) == 0
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        for fn in self.deferred[::-1]:
            match fn:
                case OnExitCallback(fn):
                    try:
                        fn()
                    except Exception as e:
                        error(f"Error during deferred execution: {e}")
                case OnFailureCallback(fn):
                    if exc_type is None:
                        continue
                    try:
                        fn(exc_type)
                    except Exception as e:
                        error(f"Error during deferred execution: {e}")
                case OnSuccessCallback(fn):
                    if exc_type is not None:
                        continue
                    try:
                        fn()
                    except Exception as e:
                        error(f"Error during deferred execution: {e}")


class Module:

    def register_script_commands(self, ctx: ExecutionContext) -> None:
        pass

    def register_typed_config_commands(self) -> list[TypedConfigCommandRegistration]:
        return []

    @staticmethod
    def load_modules() -> dict[str, "Module"]:
        import inspect
        from importlib import import_module
        from pathlib import Path

        dev_dir = Path(__file__).parent

        packages = [("dev.checks", dev_dir / "checks")]

        # Get the file location of base.py to discover all checks
        modules: dict[str, Module] = {}

        for package, package_dir in packages:
            for path in package_dir.iterdir():
                if path.is_file() and path.suffix == ".py":
                    module = import_module(f"{package}.{path.stem}")
                    for name, obj in vars(module).items():
                        if isinstance(obj, type) and issubclass(obj, Module):
                            if inspect.isabstract(obj):
                                continue

                            # Check if it has an immediate abc.ABC parent
                            skip = False
                            for base in obj.__bases__:
                                if base is Module:
                                    continue
                                if base is abc.ABC:
                                    skip = True
                                    break
                            if skip:
                                continue

                            try:
                                # print(f"Loading module: {name}")
                                modules[name] = obj()  # assumes no-arg ctor
                            except TypeError:
                                # print(f"Skipping module (needs args): {name}")
                                # skip or handle modules that need args
                                pass

        return modules
