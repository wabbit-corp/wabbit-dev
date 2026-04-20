from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import uuid4

import requests

from dev.ai_credentials import AiProvider, provider_key_config_hint, resolve_provider_key
from dev.ask_store import (
    ConversationMessage,
    ConversationRecord,
    ImagePart,
    TextPart,
    load_conversation,
    save_conversation,
)
from dev.config import load_config
from dev.file_properties import get_expected_file_properties, infer_candidate_mime_types
from dev.json_types import JSONObject, JSONValue
from dev.messages import accent, error, heading, info, muted

type AskProvider = Literal["gpt", "claude", "gemini"]

DEFAULT_MODELS: dict[AskProvider, str] = {
    "gpt": "gpt-5.4",
    "claude": "claude-sonnet-4-6",
    "gemini": "gemini-3.1-pro-preview",
}

PROVIDER_LABELS: dict[AskProvider, str] = {
    "gpt": "GPT",
    "claude": "Claude",
    "gemini": "Gemini",
}

SUPPORTED_IMAGE_MIME_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}


@dataclass(frozen=True)
class AskTurnResult:
    conversation_id: str
    provider: AskProvider
    model: str
    response_text: str
    created_conversation: bool


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _default_model(provider: AskProvider) -> str:
    return DEFAULT_MODELS[provider]


def _provider_label(provider: AskProvider) -> str:
    return PROVIDER_LABELS[provider]


def _conversation_or_new(conversation_id: str | None, provider: AskProvider) -> tuple[str, bool]:
    match conversation_id:
        case str(text) if text.strip():
            return text.strip(), False
        case _:
            return f"{provider}-{uuid4().hex[:12]}", True


def _clip_text(value: str, *, limit: int = 600) -> str:
    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 3] + "..."


def _unsupported_attachment_message(path: Path) -> str:
    return (
        f"Unsupported attachment type for {path}. "
        "Only UTF-8 text files and raster images (PNG/JPEG/GIF/WEBP) are supported."
    )


def _text_attachment_part(path: Path) -> TextPart:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as ex:
        raise ValueError(_unsupported_attachment_message(path)) from ex
    return TextPart(text=f"Attached file: {path.name}\n\n{text}")


def _image_attachment_part(path: Path, media_type: str) -> ImagePart:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return ImagePart(filename=path.name, media_type=media_type, data_base64=encoded)


def _load_attachment_part(path_text: str) -> TextPart | ImagePart:
    path = Path(path_text).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Attachment does not exist: {path}")

    props = get_expected_file_properties(path)
    candidate_mimes = infer_candidate_mime_types(path)

    if props is not None and props.is_text:
        return _text_attachment_part(path)

    for candidate_mime in sorted(candidate_mimes):
        if candidate_mime in SUPPORTED_IMAGE_MIME_TYPES:
            return _image_attachment_part(path, candidate_mime)

    raise ValueError(_unsupported_attachment_message(path))


def _build_user_message(prompt: str, file_paths: list[str]) -> ConversationMessage:
    parts: list[TextPart | ImagePart] = []
    prompt_text = prompt.strip()
    if prompt_text:
        parts.append(TextPart(text=prompt_text))

    for file_path in file_paths:
        parts.append(_load_attachment_part(file_path))

    if not parts:
        raise ValueError("Ask requires either prompt text or at least one --file attachment.")

    return ConversationMessage(role="user", parts=tuple(parts))


def _assistant_message(text: str) -> ConversationMessage:
    return ConversationMessage(role="assistant", parts=(TextPart(text=text),))


def _openai_message_content(message: ConversationMessage) -> str | list[JSONObject]:
    items: list[JSONObject] = []
    for part in message.parts:
        match part:
            case TextPart(text=text):
                items.append({"type": "text", "text": text})
            case ImagePart(media_type=media_type, data_base64=data_base64):
                items.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{data_base64}"},
                    }
                )
    if message.role == "assistant":
        texts: list[str] = []
        for part in message.parts:
            match part:
                case TextPart(text=text):
                    texts.append(text)
                case _:
                    continue
        return "\n\n".join(texts)
    return items


def _conversation_to_openai_messages(history: tuple[ConversationMessage, ...]) -> list[JSONObject]:
    messages: list[JSONObject] = []
    for message in history:
        messages.append({"role": message.role, "content": _openai_message_content(message)})
    return messages


def _conversation_to_anthropic_messages(history: tuple[ConversationMessage, ...]) -> list[JSONObject]:
    messages: list[JSONObject] = []
    for message in history:
        parts: list[JSONObject] = []
        for part in message.parts:
            match part:
                case TextPart(text=text):
                    parts.append({"type": "text", "text": text})
                case ImagePart(media_type=media_type, data_base64=data_base64):
                    parts.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": data_base64,
                            },
                        }
                    )
        messages.append({"role": message.role, "content": parts})
    return messages


def _conversation_to_gemini_contents(history: tuple[ConversationMessage, ...]) -> list[JSONObject]:
    contents: list[JSONObject] = []
    for message in history:
        parts: list[JSONObject] = []
        for part in message.parts:
            match part:
                case TextPart(text=text):
                    parts.append({"text": text})
                case ImagePart(media_type=media_type, data_base64=data_base64):
                    parts.append({"inlineData": {"mimeType": media_type, "data": data_base64}})
        role = "user" if message.role == "user" else "model"
        contents.append({"role": role, "parts": parts})
    return contents


def _extract_openai_text(payload: JSONValue) -> str:
    match payload:
        case {"choices": [*choices]}:
            for choice in choices:
                match choice:
                    case {"message": {"content": str(text)}}:
                        stripped = text.strip()
                        if stripped:
                            return stripped
                    case {"message": {"content": [*parts]}}:
                        texts: list[str] = []
                        for part in parts:
                            match part:
                                case {"type": "text", "text": str(text)}:
                                    texts.append(text)
                                case _:
                                    continue
                        combined = "\n".join(texts).strip()
                        if combined:
                            return combined
            raise ValueError("OpenAI returned no assistant text.")
        case _:
            raise ValueError("Unexpected OpenAI response payload.")


def _extract_anthropic_text(payload: JSONValue) -> str:
    match payload:
        case {"content": [*parts]}:
            texts: list[str] = []
            for part in parts:
                match part:
                    case {"type": "text", "text": str(text)}:
                        texts.append(text)
                    case _:
                        continue
            combined = "\n".join(texts).strip()
            if combined:
                return combined
            raise ValueError("Anthropic returned no assistant text.")
        case _:
            raise ValueError("Unexpected Anthropic response payload.")


def _extract_gemini_text(payload: JSONValue) -> str:
    match payload:
        case {"candidates": [*candidates]}:
            for candidate in candidates:
                match candidate:
                    case {"content": {"parts": [*parts]}}:
                        texts: list[str] = []
                        for part in parts:
                            match part:
                                case {"text": str(text)}:
                                    texts.append(text)
                                case _:
                                    continue
                        combined = "\n".join(texts).strip()
                        if combined:
                            return combined
                    case _:
                        continue
            raise ValueError("Gemini returned no assistant text.")
        case _:
            raise ValueError("Unexpected Gemini response payload.")


def _post_json(
    url: str,
    *,
    headers: dict[str, str] | None,
    params: dict[str, str] | None,
    payload: JSONObject,
) -> JSONValue:
    response = requests.post(url, headers=headers, params=params, json=payload, timeout=120)
    if not response.ok:
        raise ValueError(f"Provider request failed: {_clip_text(response.text)}")
    return response.json()


def _ask_openai(model: str, api_key: str, history: tuple[ConversationMessage, ...]) -> str:
    payload: JSONObject = {
        "model": model,
        "messages": _conversation_to_openai_messages(history),
    }
    raw_payload = _post_json(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        params=None,
        payload=payload,
    )
    return _extract_openai_text(raw_payload)


def _ask_claude(model: str, api_key: str, history: tuple[ConversationMessage, ...]) -> str:
    payload: JSONObject = {
        "model": model,
        "max_tokens": 4096,
        "messages": _conversation_to_anthropic_messages(history),
    }
    raw_payload = _post_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        params=None,
        payload=payload,
    )
    return _extract_anthropic_text(raw_payload)


def _ask_gemini(model: str, api_key: str, history: tuple[ConversationMessage, ...]) -> str:
    payload: JSONObject = {
        "contents": _conversation_to_gemini_contents(history),
    }
    raw_payload = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers=None,
        params={"key": api_key},
        payload=payload,
    )
    return _extract_gemini_text(raw_payload)


def _provider_response_text(provider: AskProvider, model: str, api_key: str, history: tuple[ConversationMessage, ...]) -> str:
    match provider:
        case "gpt":
            return _ask_openai(model, api_key, history)
        case "claude":
            return _ask_claude(model, api_key, history)
        case "gemini":
            return _ask_gemini(model, api_key, history)


def run_turn(
    provider: AskProvider,
    *,
    prompt: str,
    conversation_id: str | None,
    file_paths: list[str],
    model: str | None = None,
    store_path: Path | None = None,
) -> AskTurnResult:
    config = load_config()
    resolved_credential = resolve_provider_key(config, provider)
    if resolved_credential is None:
        raise ValueError(
            f"Missing {_provider_label(provider)} credential. "
            f"Add {provider_key_config_hint(provider)} to root.private.clj, "
            "export the matching environment variable, or add it to keys.env."
        )

    resolved_conversation_id, created_conversation = _conversation_or_new(conversation_id, provider)
    stored_conversation = load_conversation(resolved_conversation_id, store_path=store_path)
    if stored_conversation is not None and stored_conversation.provider != provider:
        raise ValueError(
            f"Conversation {resolved_conversation_id} belongs to provider {stored_conversation.provider}, not {provider}."
        )

    if stored_conversation is not None:
        effective_model = stored_conversation.model if model is None else model
        history_prefix = list(stored_conversation.history)
        created_at = stored_conversation.created_at
    else:
        effective_model = _default_model(provider) if model is None else model
        history_prefix = []
        created_at = _now_utc()

    user_message = _build_user_message(prompt, file_paths)
    request_history = tuple([*history_prefix, user_message])
    response_text = _provider_response_text(provider, effective_model, resolved_credential.key, request_history)
    assistant_message = _assistant_message(response_text)
    final_history = tuple([*request_history, assistant_message])
    save_conversation(
        ConversationRecord(
            conversation_id=resolved_conversation_id,
            provider=provider,
            model=effective_model,
            workspace_root=config.workspace_root.resolve() if config.workspace_root is not None else None,
            created_at=created_at,
            updated_at=_now_utc(),
            history=final_history,
        ),
        store_path=store_path,
    )
    return AskTurnResult(
        conversation_id=resolved_conversation_id,
        provider=provider,
        model=effective_model,
        response_text=response_text,
        created_conversation=stored_conversation is None or created_conversation,
    )


def ask(
    provider: AskProvider,
    *,
    prompt: str,
    conversation_id: str | None,
    file_paths: list[str],
    model: str | None = None,
    store_path: Path | None = None,
) -> int:
    try:
        result = run_turn(
            provider,
            prompt=prompt,
            conversation_id=conversation_id,
            file_paths=file_paths,
            model=model,
            store_path=store_path,
        )
    except (OSError, ValueError, requests.RequestException, sqlite3.Error) as ex:
        error(str(ex))
        return 1

    print(heading(f"{_provider_label(result.provider)} [{accent(result.model)}]"))
    print(result.response_text)
    print()
    if result.created_conversation:
        info(f"Started conversation {result.conversation_id}")
    else:
        info(f"Conversation {result.conversation_id}")
    print(muted("Conversation history is cached locally for --conversation reuse."))
    return 0


__all__ = ["AskProvider", "AskTurnResult", "ask", "run_turn"]
