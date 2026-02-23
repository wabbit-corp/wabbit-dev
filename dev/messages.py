from collections.abc import Mapping
from typing import TypeVar, overload

T = TypeVar("T")

###############################################################################
# Output prefixes
###############################################################################

try:
    from termcolor import colored

    CHECKMARK = "[" + colored("✓", "green") + "]"
    CROSSMARK = "[" + colored("✗", "red") + "]"
    QUESTIONMARK = "[" + colored("?", "yellow") + "]"
    INFOMARK = "[" + colored("i", "blue") + "]"
except ImportError:
    CHECKMARK = "[✓]"
    CROSSMARK = "[✗]"
    QUESTIONMARK = "[?]"
    INFOMARK = "[i]"


def _message(prefix: str, raw_prefix: str, *args: object) -> None:
    msg = "\n".join(str(arg) for arg in args)
    first = True
    for line in msg.split("\n"):
        if first:
            print(f"{prefix} {line}")
        else:
            print(f"{' ' * len(raw_prefix)} {line}")
        first = False


# Use CROSSMARK for errors
def error(*msg: object) -> None:
    _message(CROSSMARK, "[✗]", *msg)


# Use QUESTIONMARK for warnings
def warning(*msg: object) -> None:
    _message(QUESTIONMARK, "[?]", *msg)


# Use INFOMARK for information
def info(*msg: object) -> None:
    _message(INFOMARK, "[i]", *msg)


# Use CHECKMARK for success
def success(*msg: object) -> None:
    _message(CHECKMARK, "[✓]", *msg)


YN: dict[str, bool] = {"Y": True, "N": False}


@overload
def ask(*msg: object, result_type: None = None) -> bool: ...


@overload
def ask(*msg: object, result_type: str) -> str: ...


@overload
def ask[T](*msg: object, result_type: dict[str, T]) -> T: ...


def ask(*msg: object, result_type: Mapping[str, object] | str | None = None) -> object:
    _message(QUESTIONMARK, "[?]", *msg)

    if result_type is None:
        result_type = {"y": True, "n": False}
    elif isinstance(result_type, str):
        result_type = {r: r for r in result_type}

    assert isinstance(result_type, dict), f"Invalid result type: {result_type}"
    assert all(isinstance(k, str) for k in result_type), f"Invalid result type: {result_type}"
    assert all(len(k) == 1 for k in result_type), f"Invalid result type: {result_type}"
    assert all(k.islower() for k in result_type), f"Invalid result type: {result_type}"

    options = "".join(result_type.keys())

    while True:
        response = input(f"Respond with [{options}] ").strip().lower()
        if response in result_type:
            return result_type[response]
        else:
            print(f"Invalid response. Please enter one of [{options}].")
