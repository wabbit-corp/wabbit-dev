from __future__ import annotations

from pathlib import Path

import pytest

from dev.generated_files import prepend_generated_comment
from dev.io import write_text_file


def test_write_text_file_does_not_report_guidance_for_valid_managed_regeneration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    assert not any("managed file:" in message for message in messages)


def test_write_text_file_reports_guidance_when_overwriting_manually_edited_managed_file(
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
    path.write_text(
        path.read_text(encoding="utf-8").replace("plugins {}", 'plugins { id("java") }'),
        encoding="utf-8",
    )
    write_text_file(
        path,
        prepend_generated_comment(
            "plugins {}\n",
            comment_prefix="//",
            body_lines=["This file is generated from workspace configuration in root.clj."],
        ),
    )

    assert any("Overwriting manually edited managed file:" in message for message in messages)
    assert any("build.extra.gradle.kts" in message for message in messages)


def test_write_text_file_reports_guidance_when_replacing_unmanaged_file_with_managed_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dev.io as dev_io

    messages: list[str] = []
    monkeypatch.setattr(dev_io, "info", lambda message: messages.append(message))

    path = tmp_path / "settings.gradle.kts"
    path.write_text('rootProject.name = "demo"\n', encoding="utf-8")
    write_text_file(
        path,
        prepend_generated_comment(
            'rootProject.name = "demo"\n',
            comment_prefix="//",
            body_lines=["This file is generated from workspace configuration in root.clj."],
        ),
    )

    assert any("Replacing unmanaged file with managed file:" in message for message in messages)
    assert any("settings.local.gradle.kts" in message for message in messages)
