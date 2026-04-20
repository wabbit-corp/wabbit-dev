from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dev.config import Config

type AiProvider = Literal["gpt", "claude", "gemini", "brave"]

KEYS_ENV_FILENAME = "keys.env"


@dataclass(frozen=True)
class ResolvedCredential:
    key: str
    source: str


def _strip_credential(value: str | None) -> str | None:
    match value:
        case None:
            return None
        case str(text):
            stripped = text.strip()
            return stripped if stripped else None


def _unquote_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _parse_keys_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    entries: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, separator, raw_value = line.partition("=")
        if separator != "=":
            continue
        key = name.strip()
        if not key:
            continue
        entries[key] = _unquote_value(raw_value)
    return entries


def _provider_config_key(config: Config, provider: AiProvider) -> str | None:
    match provider:
        case "gpt":
            return _strip_credential(config.openai_key)
        case "claude":
            return _strip_credential(config.anthropic_key)
        case "gemini":
            return _strip_credential(config.gemini_key)
        case "brave":
            return _strip_credential(config.brave_key)


def _provider_env_names(provider: AiProvider) -> tuple[str, ...]:
    match provider:
        case "gpt":
            return ("OPENAI_API_KEY", "OPENAI_KEY")
        case "claude":
            return ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "CLAUDE_API_KEY", "CLAUDE_KEY")
        case "gemini":
            return ("GEMINI_API_KEY", "GEMINI_KEY", "GOOGLE_API_KEY")
        case "brave":
            return ("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY", "BRAVE_KEY")


def provider_key_config_hint(provider: AiProvider) -> str:
    match provider:
        case "gpt":
            return '(openai-key "...")'
        case "claude":
            return '(claude-key "...") or (anthropic-key "...")'
        case "gemini":
            return '(gemini-key "...")'
        case "brave":
            return '(brave-key "...")'


def resolve_provider_key(config: Config, provider: AiProvider) -> ResolvedCredential | None:
    configured = _provider_config_key(config, provider)
    if configured is not None:
        return ResolvedCredential(key=configured, source="root.private.clj")

    for env_name in _provider_env_names(provider):
        env_value = _strip_credential(os.environ.get(env_name))
        if env_value is not None:
            return ResolvedCredential(key=env_value, source=f"env:{env_name}")

    workspace_root = config.workspace_root
    match workspace_root:
        case Path() as root:
            keys_env_entries = _parse_keys_env(root / KEYS_ENV_FILENAME)
        case _:
            keys_env_entries = {}

    for env_name in _provider_env_names(provider):
        env_value = _strip_credential(keys_env_entries.get(env_name))
        if env_value is not None:
            return ResolvedCredential(key=env_value, source=f"keys.env:{env_name}")

    return None


__all__ = [
    "AiProvider",
    "KEYS_ENV_FILENAME",
    "ResolvedCredential",
    "provider_key_config_hint",
    "resolve_provider_key",
]
