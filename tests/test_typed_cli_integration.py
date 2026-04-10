from __future__ import annotations

import argparse

import pytest


@pytest.mark.asyncio
async def test_docs_commands_bypass_argparse_with_typed_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev import cli
    from dev.tasks import docs_check as docs_check_task

    called: list[tuple[list[str], bool, bool]] = []

    def fake_parse_args(
        self: cli.SuggestingArgumentParser,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        del args, namespace
        raise AssertionError("argparse should not handle docs typed-cli commands")

    def fake_docs_check(
        targets: list[str] | None = None,
        *,
        semantic: bool = False,
        json_output: bool = False,
    ) -> int:
        called.append((targets or [], semantic, json_output))
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", fake_parse_args)
    monkeypatch.setattr(docs_check_task, "docs_check", fake_docs_check)
    monkeypatch.setattr("sys.argv", ["dev.py", "docs", "check", "--semantic", "--json", "app-wabbit-dev"])

    result = await cli.async_main()

    assert result == 0
    assert called == [(["app-wabbit-dev"], True, True)]


@pytest.mark.asyncio
async def test_release_parent_help_bypasses_argparse_with_typed_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    def fake_parse_args(
        self: cli.SuggestingArgumentParser,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        del args, namespace
        raise AssertionError("argparse should not handle release typed-cli commands")

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", fake_parse_args)
    monkeypatch.setattr("sys.argv", ["dev.py", "release"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "Verify release readiness for publishable projects." in output
    assert "verify" in output
