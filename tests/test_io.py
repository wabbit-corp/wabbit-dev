from __future__ import annotations

from pathlib import Path

import pytest

from dev.generated_files import prepend_generated_comment
from dev.io import write_text_file


def test_write_text_file_reports_generated_pyproject_guidance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dev.io as dev_io

    messages: list[str] = []
    monkeypatch.setattr(dev_io, "info", lambda message: messages.append(message))

    path = tmp_path / "pyproject.toml"
    write_text_file(
        path,
        prepend_generated_comment(
            '[tool.poetry]\nname = "demo"\n',
            comment_prefix="#",
            body_lines=["This file is generated from workspace configuration in root.clj."],
        ),
    )
    write_text_file(
        path,
        prepend_generated_comment(
            '[tool.poetry]\nname = "demo-renamed"\n',
            comment_prefix="#",
            body_lines=["This file is generated from workspace configuration in root.clj."],
        ),
    )

    assert any("Generated managed file:" in message for message in messages)
    assert any("pyproject.extra.toml" in message for message in messages)


def test_write_text_file_reports_generated_gradle_build_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dev.io as dev_io

    messages: list[str] = []
    monkeypatch.setattr(dev_io, "info", lambda message: messages.append(message))

    path = tmp_path / "build.gradle.kts"
    write_text_file(
        path,
        prepend_generated_comment(
            "plugins {}\n",
            comment_prefix="//",
            body_lines=["This file is generated from workspace configuration in root.clj."],
        ),
    )
    write_text_file(
        path,
        prepend_generated_comment(
            'plugins { id("java") }\n',
            comment_prefix="//",
            body_lines=["This file is generated from workspace configuration in root.clj."],
        ),
    )

    assert any("Generated managed file:" in message for message in messages)
    assert any("build.extra.gradle.kts" in message for message in messages)
