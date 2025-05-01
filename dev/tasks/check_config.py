from dev.config import load_config
from dev.messages import error, success

def check_config() -> None:
    config = load_config()
    success("Config is valid")
    return