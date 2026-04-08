import os
import sys
from collections.abc import Mapping
from typing import IO, TypeVar, overload

T = TypeVar("T")

###############################################################################
# Output prefixes
###############################################################################

CHECKMARK = "[✓]"
CROSSMARK = "[✗]"
QUESTIONMARK = "[?]"
INFOMARK = "[i]"

_TEXT_COLORS: dict[str, int] = {
    "grey": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
}
_BACKGROUND_COLORS: dict[str, int] = {
    "on_grey": 40,
    "on_red": 41,
    "on_green": 42,
    "on_yellow": 43,
    "on_blue": 44,
    "on_magenta": 45,
    "on_cyan": 46,
    "on_white": 47,
}
_ATTR_CODES: dict[str, int] = {
    "bold": 1,
    "dark": 2,
    "underline": 4,
    "blink": 5,
    "reverse": 7,
    "concealed": 8,
}


def _env_truthy(name: str) -> bool:
    value = os.environ.get(name)
    return value not in (None, "", "0")


def supports_color(stream: IO[str] | None = None) -> bool:
    if _env_truthy("FORCE_COLOR") or _env_truthy("CLICOLOR_FORCE"):
        return True
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CLICOLOR") == "0":
        return False

    active_stream = sys.stdout if stream is None else stream
    isatty = getattr(active_stream, "isatty", None)
    if not callable(isatty) or not isatty():
        return False

    return os.environ.get("TERM", "").lower() != "dumb"


def style(
    text: object,
    color: str | None = None,
    *,
    attrs: tuple[str, ...] = (),
    on_color: str | None = None,
    stream: IO[str] | None = None,
) -> str:
    rendered = str(text)
    if not supports_color(stream):
        return rendered

    codes: list[int] = []
    if color is not None:
        color_code = _TEXT_COLORS.get(color)
        if color_code is not None:
            codes.append(color_code)
    if on_color is not None:
        background_code = _BACKGROUND_COLORS.get(on_color)
        if background_code is not None:
            codes.append(background_code)
    for attr in attrs:
        attr_code = _ATTR_CODES.get(attr)
        if attr_code is not None:
            codes.append(attr_code)
    if not codes:
        return rendered
    joined = ";".join(str(code) for code in codes)
    return f"\033[{joined}m{rendered}\033[0m"


def heading(text: object, *, stream: IO[str] | None = None) -> str:
    return style(text, "cyan", attrs=("bold",), stream=stream)


def accent(text: object, color: str = "cyan", *, stream: IO[str] | None = None) -> str:
    return style(text, color, attrs=("bold",), stream=stream)


def muted(text: object, *, stream: IO[str] | None = None) -> str:
    return style(text, attrs=("dark",), stream=stream)


def command_text(text: object, *, stream: IO[str] | None = None) -> str:
    return style(text, "green", stream=stream)


def _prefix(symbol: str, color: str) -> str:
    return f"[{style(symbol, color, attrs=('bold',))}]"


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
    _message(_prefix("✗", "red"), CROSSMARK, *msg)


# Use QUESTIONMARK for warnings
def warning(*msg: object) -> None:
    _message(_prefix("?", "yellow"), QUESTIONMARK, *msg)


# Use INFOMARK for information
def info(*msg: object) -> None:
    _message(_prefix("i", "blue"), INFOMARK, *msg)


# Use CHECKMARK for success
def success(*msg: object) -> None:
    _message(_prefix("✓", "green"), CHECKMARK, *msg)


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
