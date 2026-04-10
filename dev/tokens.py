from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

GPT_5_4_MODEL = "gpt-5.4"
GPT_5_FALLBACK_MODEL = "gpt-5"
GPT_5_FALLBACK_ENCODING = "o200k_base"


@dataclass(frozen=True)
class TokenCountResult:
    requested_model: str
    resolved_model: str
    encoding_name: str
    total_tokens: int
    fallback_used: bool


class _TiktokenEncoding(Protocol):
    name: str

    def encode(self, text: str) -> list[int]: ...


class _TiktokenModule(Protocol):
    def encoding_for_model(self, model_name: str) -> _TiktokenEncoding: ...

    def get_encoding(self, encoding_name: str) -> _TiktokenEncoding: ...


def _load_tiktoken() -> _TiktokenModule:
    try:
        import tiktoken
    except ImportError as ex:
        raise RuntimeError(
            "tiktoken is required for GPT-5.4 token counting. "
            "Install the app-wabbit-dev Python dependencies and rerun the command."
        ) from ex
    return tiktoken


def count_text_tokens_for_gpt_5_4(text: str) -> TokenCountResult:
    tiktoken = _load_tiktoken()

    try:
        encoding = tiktoken.encoding_for_model(GPT_5_4_MODEL)
        resolved_model = GPT_5_4_MODEL
        fallback_used = False
    except KeyError:
        try:
            encoding = tiktoken.encoding_for_model(GPT_5_FALLBACK_MODEL)
            resolved_model = GPT_5_FALLBACK_MODEL
        except KeyError:
            encoding = tiktoken.get_encoding(GPT_5_FALLBACK_ENCODING)
            resolved_model = GPT_5_FALLBACK_ENCODING
        fallback_used = True

    return TokenCountResult(
        requested_model=GPT_5_4_MODEL,
        resolved_model=resolved_model,
        encoding_name=encoding.name,
        total_tokens=len(encoding.encode(text)),
        fallback_used=fallback_used,
    )
