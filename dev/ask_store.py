from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Literal

from dev.caching import DEFAULT_CACHE_DB_PATH
from dev.json_types import JSONArray, JSONObject, JSONValue

type ConversationRole = Literal["user", "assistant"]

CREATE_ASK_CONVERSATIONS_SQL = """
CREATE TABLE IF NOT EXISTS ask_conversations (
    conversation_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    workspace_root TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    history_json TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    filename: str
    media_type: str
    data_base64: str


type ConversationPart = TextPart | ImagePart


@dataclass(frozen=True)
class ConversationMessage:
    role: ConversationRole
    parts: tuple[ConversationPart, ...]


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    provider: str
    model: str
    workspace_root: Path | None
    created_at: datetime
    updated_at: datetime
    history: tuple[ConversationMessage, ...]


def default_ask_store_path() -> Path:
    return Path(DEFAULT_CACHE_DB_PATH).expanduser().resolve().with_name("ask-cache.db")


def _connect(store_path: Path) -> sqlite3.Connection:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(store_path, timeout=60)
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    with connection:
        connection.execute(CREATE_ASK_CONVERSATIONS_SQL)
    return connection


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _part_to_payload(part: ConversationPart) -> JSONObject:
    match part:
        case TextPart(text=text):
            return {
                "kind": "text",
                "text": text,
            }
        case ImagePart(filename=filename, media_type=media_type, data_base64=data_base64):
            return {
                "kind": "image",
                "filename": filename,
                "mediaType": media_type,
                "dataBase64": data_base64,
            }


def _message_to_payload(message: ConversationMessage) -> JSONObject:
    return {
        "role": message.role,
        "parts": [_part_to_payload(part) for part in message.parts],
    }


def _part_from_payload(payload: JSONValue) -> ConversationPart | None:
    match payload:
        case {"kind": "text", "text": str(text)}:
            return TextPart(text=text)
        case {
            "kind": "image",
            "filename": str(filename),
            "mediaType": str(media_type),
            "dataBase64": str(data_base64),
        }:
            return ImagePart(filename=filename, media_type=media_type, data_base64=data_base64)
        case _:
            return None


def _message_from_payload(payload: JSONValue) -> ConversationMessage | None:
    match payload:
        case {"role": str(role), "parts": [*parts_payload]}:
            if role not in {"user", "assistant"}:
                return None
            parts: list[ConversationPart] = []
            for part_payload in parts_payload:
                part = _part_from_payload(part_payload)
                if part is None:
                    return None
                parts.append(part)
            return ConversationMessage(role=role, parts=tuple(parts))
        case _:
            return None


def _history_to_json(history: tuple[ConversationMessage, ...]) -> str:
    payload: JSONArray = [_message_to_payload(message) for message in history]
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _history_from_json(text: str) -> tuple[ConversationMessage, ...] | None:
    try:
        payload: JSONValue = json.loads(text)
    except json.JSONDecodeError:
        return None

    match payload:
        case [*messages_payload]:
            history: list[ConversationMessage] = []
            for message_payload in messages_payload:
                message = _message_from_payload(message_payload)
                if message is None:
                    return None
                history.append(message)
            return tuple(history)
        case _:
            return None


def load_conversation(conversation_id: str, *, store_path: Path | None = None) -> ConversationRecord | None:
    active_store_path = default_ask_store_path() if store_path is None else store_path
    if not active_store_path.is_file():
        return None

    connection = _connect(active_store_path)
    try:
        row = connection.execute(
            """
            SELECT conversation_id, provider, model, workspace_root, created_at, updated_at, history_json
            FROM ask_conversations
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
    finally:
        connection.close()

    match row:
        case (
            str(saved_conversation_id),
            str(provider),
            str(model),
            workspace_root_raw,
            str(created_at_text),
            str(updated_at_text),
            str(history_json),
        ):
            match workspace_root_raw:
                case None:
                    workspace_root = None
                case str(workspace_root_text):
                    workspace_root = Path(workspace_root_text)
                case _:
                    return None

            history = _history_from_json(history_json)
            if history is None:
                return None

            return ConversationRecord(
                conversation_id=saved_conversation_id,
                provider=provider,
                model=model,
                workspace_root=workspace_root,
                created_at=_parse_datetime(created_at_text),
                updated_at=_parse_datetime(updated_at_text),
                history=history,
            )
        case _:
            return None


def save_conversation(conversation: ConversationRecord, *, store_path: Path | None = None) -> None:
    active_store_path = default_ask_store_path() if store_path is None else store_path
    connection = _connect(active_store_path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO ask_conversations (
                    conversation_id,
                    provider,
                    model,
                    workspace_root,
                    created_at,
                    updated_at,
                    history_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    provider = excluded.provider,
                    model = excluded.model,
                    workspace_root = excluded.workspace_root,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    history_json = excluded.history_json
                """,
                (
                    conversation.conversation_id,
                    conversation.provider,
                    conversation.model,
                    str(conversation.workspace_root) if conversation.workspace_root is not None else None,
                    conversation.created_at.astimezone(UTC).isoformat(),
                    conversation.updated_at.astimezone(UTC).isoformat(),
                    _history_to_json(conversation.history),
                ),
            )
    finally:
        connection.close()


__all__ = [
    "ConversationMessage",
    "ConversationPart",
    "ConversationRecord",
    "ConversationRole",
    "ImagePart",
    "TextPart",
    "default_ask_store_path",
    "load_conversation",
    "save_conversation",
]
