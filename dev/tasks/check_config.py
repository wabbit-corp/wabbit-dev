from dev.config import load_config
from dev.messages import success


def check_config() -> None:
    load_config()
    success("Config is valid")
    return
