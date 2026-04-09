import abc
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

from dev.messages import error

CHECK_MODULE_IMPORTS: tuple[str, ...] = (
    "dev.checks.chinese_firewall",
    "dev.checks.code_linting",
    "dev.checks.code_stale",
    "dev.checks.dependencies",
    "dev.checks.file_duplicates",
    "dev.checks.file_headers",
    "dev.checks.file_modes",
    "dev.checks.file_paths",
    "dev.checks.hardcoded",
    "dev.checks.identifier_uniqueness",
    "dev.checks.kmp_target_expansion",
    "dev.checks.layout_drift",
    "dev.checks.large_files",
    "dev.checks.managed_generated_files",
    "dev.checks.migrations",
    "dev.checks.project_files",
    "dev.checks.python_bandit",
    "dev.checks.python_black",
    "dev.checks.python_coverage_report",
    "dev.checks.python_coverage_xml",
    "dev.checks.python_deptry",
    "dev.checks.python_diff_cover",
    "dev.checks.python_import_linter",
    "dev.checks.python_mypy",
    "dev.checks.python_pip_audit",
    "dev.checks.python_pyright",
    "dev.checks.python_pytest",
    "dev.checks.python_ruff",
    "dev.checks.python_semgrep",
    "dev.checks.python_unittest",
    "dev.checks.python_vulture",
    "dev.checks.repo_contributors",
    "dev.checks.repo_properties",
    "dev.checks.root_paths",
    "dev.checks.text_quality",
    "dev.checks.trufflehog",
)


class ScriptCommandContext(Protocol):
    def register(self, *, name: str, func: object) -> None: ...


class Callback:
    pass


@dataclass(frozen=True)
class TypedConfigCommandRegistration:
    command_type: type[object]
    apply: Callable[[object], None]


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

    def __enter__(self) -> "Scope":
        assert len(self.deferred) == 0
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del traceback  # Unused by this scope implementation.
        for callback in reversed(self.deferred):
            try:
                if isinstance(callback, OnExitCallback):
                    callback.value()
                elif isinstance(callback, OnFailureCallback):
                    if exc_value is not None:
                        callback.value(exc_value)
                elif isinstance(callback, OnSuccessCallback):
                    if exc_type is None:
                        callback.value()
            except Exception as e:
                error(f"Error during deferred execution: {e}")


class Module:

    def register_script_commands(self, ctx: ScriptCommandContext) -> None:
        pass

    def register_typed_config_commands(self) -> list[TypedConfigCommandRegistration]:
        return []

    @staticmethod
    def _has_required_constructor_args(module_type: type["Module"]) -> bool:
        import inspect

        try:
            signature = inspect.signature(module_type)
        except (TypeError, ValueError):
            return False

        for parameter in signature.parameters.values():
            if parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ) and parameter.default is inspect.Parameter.empty:
                return True
        return False

    @staticmethod
    def load_modules() -> dict[str, "Module"]:
        import inspect
        from importlib import import_module

        # Get the file location of base.py to discover all checks
        modules: dict[str, Module] = {}

        # Keep this explicit so frozen builds do not depend on runtime filesystem scans.
        for module_name in CHECK_MODULE_IMPORTS:
            module = import_module(module_name)
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

                    if Module._has_required_constructor_args(obj):
                        continue

                    # print(f"Loading module: {name}")
                    modules[name] = obj()  # assumes no-arg ctor

        return modules
