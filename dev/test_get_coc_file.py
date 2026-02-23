import sys
from pathlib import Path

import pytest


def _setup_module():
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    import dev.tasks.setup as setup_module

    return setup_module


def test_get_coc_file_uses_timeout_and_returns_text(monkeypatch) -> None:
    setup_module = _setup_module()

    calls: list[dict[str, object]] = []

    class DummyResponse:
        text = "CODE_OF_CONDUCT\n"

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, timeout: int):
        calls.append({"url": url, "timeout": timeout})
        return DummyResponse()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    result = setup_module.get_coc_file.__wrapped__()

    assert result == "CODE_OF_CONDUCT\n"
    assert calls == [
        {
            "url": "https://raw.githubusercontent.com/wabbit-corp/code-of-excellence/refs/heads/master/CODE_OF_CONDUCT.md",
            "timeout": 10,
        }
    ]


def test_get_coc_file_wraps_request_exceptions(monkeypatch) -> None:
    setup_module = _setup_module()
    import requests

    def fake_get(url: str, timeout: int):  # noqa: ARG001
        raise requests.RequestException("network error")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="Failed to fetch CoC file"):
        setup_module.get_coc_file.__wrapped__()
