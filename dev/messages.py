from typing import TypeVar, Dict, overload, Any

###############################################################################
# Output prefixes
###############################################################################

try:
    from termcolor import colored
    CHECKMARK    = '[' + colored("✓", "green") + ']'
    CROSSMARK    = '[' + colored("✗", "red") + ']'
    QUESTIONMARK = '[' + colored("?", "yellow") + ']'
    INFOMARK     = '[' + colored("i", "blue") + ']'
except ImportError:
    CHECKMARK    = "[✓]"
    CROSSMARK    = "[✗]"
    QUESTIONMARK = "[?]"
    INFOMARK     = "[i]"

def _message(prefix: str, raw_prefix: str, *args):
    msg = '\n'.join(str(arg) for arg in args)
    first = True
    for line in msg.split('\n'):
        if first: print(f"{prefix} {line}")
        else:     print(f"{' ' * len(raw_prefix)} {line}")
        first = False

# Use CROSSMARK for errors
def error(*msg): _message(CROSSMARK, '[✗]', *msg)

# Use QUESTIONMARK for warnings
def warning(*msg): _message(QUESTIONMARK, '[?]', *msg)

# Use INFOMARK for information
def info(*msg): _message(INFOMARK, '[i]', *msg)

# Use CHECKMARK for success
def success(*msg): _message(CHECKMARK, '[✓]', *msg)


YN: Dict[str, bool] = { "Y": True, "N": False }

@overload
def ask(*msg, result_type: None = None) -> bool: ...

@overload
def ask(*msg, result_type: str) -> str: ...

@overload
def ask[T](*msg, result_type: Dict[str, T]) -> T: ...

def ask(*msg, result_type: Dict[str, Any] | str | None = None) -> Any:
    _message(QUESTIONMARK, '[?]', *msg)

    if result_type is None:
        result_type = {"y": True, "n": False}
    elif isinstance(result_type, str):
        result_type = {r : r for r in result_type}
    
    assert isinstance(result_type, dict), f"Invalid result type: {result_type}"
    assert all(isinstance(k, str) for k in result_type), f"Invalid result type: {result_type}"
    assert all(len(k) == 1 for k in result_type), f"Invalid result type: {result_type}"
    assert all(k.islower() for k in result_type), f"Invalid result type: {result_type}"

    options = ''.join(result_type.keys())

    while True:
        response = input(f"Respond with [{options}] ").strip().lower()
        if response in result_type:
            return result_type[response]
        else:
            print(f"Invalid response. Please enter one of [{options}].")