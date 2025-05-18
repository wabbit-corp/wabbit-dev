from typing import List, Callable, TypeAlias
from dataclasses import dataclass
from dev.messages import error
import traceback
from types import TracebackType
import enum


class Callback:
    pass


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
        self.deferred: List[Callback] = []

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
