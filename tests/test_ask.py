from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dev.json_types import JSONValue


class _DummyResponse:
    def __init__(self, payload: JSONValue, *, ok: bool = True, text: str = "") -> None:
        self._payload = payload
        self.ok = ok
        self.text = text

    def json(self) -> JSONValue:
        return self._payload


def _config(
    workspace_root: Path,
    *,
    openai_key: str | None = None,
    anthropic_key: str | None = None,
    gemini_key: str | None = None,
    brave_key: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        workspace_root=workspace_root,
        openai_key=openai_key,
        anthropic_key=anthropic_key,
        gemini_key=gemini_key,
        brave_key=brave_key,
    )


def test_run_turn_openai_uses_keys_env_and_image_attachment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev.ask_store import load_conversation
    from dev.tasks import ask as ask_task

    store_path = tmp_path / "ask-cache.db"
    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (tmp_path / "keys.env").write_text('OPENAI_KEY="openai-from-env-file"\n', encoding="utf-8")

    captured: dict[str, JSONValue] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None,
        params: dict[str, str] | None,
        json: JSONValue,
        timeout: int,
    ) -> _DummyResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["json"] = json
        captured["timeout"] = timeout
        return _DummyResponse({"choices": [{"message": {"content": "OpenAI answer"}}]})

    monkeypatch.setattr(ask_task, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(ask_task.requests, "post", fake_post)

    result = ask_task.run_turn(
        "gpt",
        prompt="Describe this image",
        conversation_id="gpt-demo",
        file_paths=[str(image_path)],
        store_path=store_path,
    )

    assert result.conversation_id == "gpt-demo"
    assert result.model == "gpt-5.4"
    assert result.response_text == "OpenAI answer"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer openai-from-env-file"}
    assert captured["params"] is None
    assert captured["timeout"] == 120
    match captured["json"]:
        case {
            "model": "gpt-5.4",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image"},
                        {"type": "image_url", "image_url": {"url": str(data_url)}},
                    ],
                }
            ],
        }:
            assert data_url.startswith("data:image/png;base64,")
        case _:
            raise AssertionError(f"Unexpected OpenAI payload: {captured['json']!r}")

    conversation = load_conversation("gpt-demo", store_path=store_path)
    assert conversation is not None
    assert conversation.provider == "gpt"
    assert conversation.model == "gpt-5.4"
    assert len(conversation.history) == 2


def test_run_turn_claude_reuses_existing_conversation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev.tasks import ask as ask_task

    store_path = tmp_path / "ask-cache.db"
    image_path = tmp_path / "photo.webp"
    image_path.write_bytes(b"RIFFfakeWEBP")

    payloads: list[JSONValue] = []

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None,
        params: dict[str, str] | None,
        json: JSONValue,
        timeout: int,
    ) -> _DummyResponse:
        payloads.append(json)
        assert url == "https://api.anthropic.com/v1/messages"
        assert headers == {
            "x-api-key": "anthropic-secret",
            "anthropic-version": "2023-06-01",
        }
        assert params is None
        assert timeout == 120
        return _DummyResponse({"content": [{"type": "text", "text": "Claude answer"}]})

    monkeypatch.setattr(ask_task, "load_config", lambda: _config(tmp_path, anthropic_key="anthropic-secret"))
    monkeypatch.setattr(ask_task.requests, "post", fake_post)

    first = ask_task.run_turn(
        "claude",
        prompt="First turn",
        conversation_id="claude-demo",
        file_paths=[],
        store_path=store_path,
    )
    second = ask_task.run_turn(
        "claude",
        prompt="Second turn",
        conversation_id="claude-demo",
        file_paths=[str(image_path)],
        model="claude-sonnet-4-6",
        store_path=store_path,
    )

    assert first.response_text == "Claude answer"
    assert second.response_text == "Claude answer"
    assert len(payloads) == 2
    match payloads[1]:
        case {
            "model": "claude-sonnet-4-6",
            "max_tokens": 4096,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "First turn"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "Claude answer"}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Second turn"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/webp",
                                "data": str(encoded),
                            },
                        },
                    ],
                },
            ],
        }:
            assert encoded
        case _:
            raise AssertionError(f"Unexpected Claude payload: {payloads[1]!r}")


def test_run_turn_gemini_uses_text_attachment_from_keys_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev.tasks import ask as ask_task

    store_path = tmp_path / "ask-cache.db"
    text_path = tmp_path / "notes.md"
    text_path.write_text("# Notes\n\nShip it.\n", encoding="utf-8")
    (tmp_path / "keys.env").write_text("GEMINI_KEY=gemini-from-env-file\n", encoding="utf-8")

    captured: dict[str, JSONValue] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None,
        params: dict[str, str] | None,
        json: JSONValue,
        timeout: int,
    ) -> _DummyResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["json"] = json
        captured["timeout"] = timeout
        return _DummyResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Gemini answer"},
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(ask_task, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(ask_task.requests, "post", fake_post)

    result = ask_task.run_turn(
        "gemini",
        prompt="Summarize the attachment",
        conversation_id=None,
        file_paths=[str(text_path)],
        store_path=store_path,
    )

    assert result.model == "gemini-3.1-pro-preview"
    assert result.response_text == "Gemini answer"
    assert isinstance(result.conversation_id, str)
    assert result.conversation_id.startswith("gemini-")
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent"
    assert captured["headers"] is None
    assert captured["params"] == {"key": "gemini-from-env-file"}
    match captured["json"]:
        case {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "Summarize the attachment"},
                        {"text": str(attached_text)},
                    ],
                }
            ]
        }:
            assert attached_text.startswith("Attached file: notes.md")
            assert "Ship it." in attached_text
        case _:
            raise AssertionError(f"Unexpected Gemini payload: {captured['json']!r}")


def test_run_turn_rejects_provider_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev.ask_store import ConversationMessage, ConversationRecord, TextPart, save_conversation
    from dev.tasks import ask as ask_task

    store_path = tmp_path / "ask-cache.db"
    now = ask_task._now_utc()
    save_conversation(
        ConversationRecord(
            conversation_id="shared-id",
            provider="gpt",
            model="gpt-5.4",
            workspace_root=tmp_path,
            created_at=now,
            updated_at=now,
            history=(ConversationMessage(role="user", parts=(TextPart(text="hi"),)),),
        ),
        store_path=store_path,
    )

    monkeypatch.setattr(ask_task, "load_config", lambda: _config(tmp_path, gemini_key="gemini-secret"))

    with pytest.raises(ValueError) as exc:
        ask_task.run_turn(
            "gemini",
            prompt="Hello",
            conversation_id="shared-id",
            file_paths=[],
            store_path=store_path,
        )

    assert "belongs to provider gpt" in str(exc.value)
