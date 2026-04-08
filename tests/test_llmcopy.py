from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dev.tasks import llmcopy as llmcopy_task
from dev.tokens import TokenCountResult, count_text_tokens_for_gpt_5_4


def test_count_text_tokens_for_gpt_5_4_falls_back_to_gpt_5(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEncoding:
        name = "o200k_base"

        def encode(self, text: str) -> list[int]:
            assert text == "hello"
            return [1, 2, 3]

    def fake_encoding_for_model(model: str) -> FakeEncoding:
        if model == "gpt-5.4":
            raise KeyError("missing")
        if model == "gpt-5":
            return FakeEncoding()
        raise AssertionError(f"Unexpected model {model}")

    monkeypatch.setattr(
        "dev.tokens._load_tiktoken",
        lambda: SimpleNamespace(encoding_for_model=fake_encoding_for_model),
    )

    result = count_text_tokens_for_gpt_5_4("hello")

    assert result == TokenCountResult(
        requested_model="gpt-5.4",
        resolved_model="gpt-5",
        encoding_name="o200k_base",
        total_tokens=3,
        fallback_used=True,
    )


def test_count_text_tokens_for_gpt_5_4_falls_back_to_o200k_base(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEncoding:
        name = "o200k_base"

        def encode(self, text: str) -> list[int]:
            assert text == "hello"
            return [1, 2, 3, 4]

    def fake_encoding_for_model(model: str) -> FakeEncoding:
        raise KeyError(f"missing {model}")

    monkeypatch.setattr(
        "dev.tokens._load_tiktoken",
        lambda: SimpleNamespace(
            encoding_for_model=fake_encoding_for_model,
            get_encoding=lambda name: FakeEncoding(),
        ),
    )

    result = count_text_tokens_for_gpt_5_4("hello")

    assert result == TokenCountResult(
        requested_model="gpt-5.4",
        resolved_model="o200k_base",
        encoding_name="o200k_base",
        total_tokens=4,
        fallback_used=True,
    )


def test_llmcopy_reports_total_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, str] = {}
    source = tmp_path / "demo.txt"
    source.write_text("hello world\n", encoding="utf-8")

    monkeypatch.setattr(llmcopy_task.pyperclip, "copy", lambda value: captured.setdefault("value", value))
    monkeypatch.setattr(
        llmcopy_task,
        "count_text_tokens_for_gpt_5_4",
        lambda text: TokenCountResult(
            requested_model="gpt-5.4",
            resolved_model="gpt-5.4",
            encoding_name="o200k_base",
            total_tokens=123,
            fallback_used=False,
        ),
    )

    llmcopy_task.llmcopy([str(source)])

    assert '<contents path="' in captured["value"]
    assert "hello world" in captured["value"]

    output = capsys.readouterr().out
    assert "Copied to clipboard" in output
    assert "1 file" in output
    assert "123 GPT-5.4 tokens" in output
