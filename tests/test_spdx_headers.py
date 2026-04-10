from __future__ import annotations

from pathlib import Path

import pytest

from dev.checks.base import FileContext
from dev.checks.file_headers import SpdxHeaderCheck, expected_spdx_identifier, render_spdx_fixed_text
from dev.config import OwnershipType, PythonProject


def _project(tmp_path: Path) -> PythonProject:
    return PythonProject(
        path=tmp_path,
        name="demo",
        version=None,
        description=None,
        authors=[],
        license="AGPL",
        github_repo=None,
        requires_python=None,
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        application=None,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=False,
        test_license="LicenseRef-Wabbit-Public-Test-License",
        ownership=OwnershipType.WABBIT,
    )


def test_expected_spdx_identifier_uses_main_and_test_licenses(tmp_path: Path) -> None:
    project = _project(tmp_path)
    main_file = tmp_path / "src" / "commonMain" / "kotlin" / "demo" / "Main.kt"
    test_file = tmp_path / "src" / "commonTest" / "kotlin" / "demo" / "MainSpec.kt"
    main_file.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    main_file.write_text("package demo\n", encoding="utf-8")
    test_file.write_text("package demo\n", encoding="utf-8")

    assert expected_spdx_identifier(FileContext(check_name="x", path=main_file, project=project)) == "AGPL-3.0-or-later"
    assert (
        expected_spdx_identifier(FileContext(check_name="x", path=test_file, project=project))
        == "LicenseRef-Wabbit-Public-Test-License-1.1"
    )


def test_render_spdx_fixed_text_adds_header_for_kotlin_file() -> None:
    text = "package demo\n\nclass Main\n"
    fixed = render_spdx_fixed_text(Path("Main.kt"), text, "AGPL-3.0-or-later")
    assert fixed == "// SPDX-License-Identifier: AGPL-3.0-or-later\n\npackage demo\n\nclass Main\n"


def test_render_spdx_fixed_text_replaces_incorrect_existing_header() -> None:
    text = "// SPDX-License-Identifier: MIT\n\npackage demo\n"
    fixed = render_spdx_fixed_text(Path("Main.kt"), text, "AGPL-3.0-or-later")
    assert fixed == "// SPDX-License-Identifier: AGPL-3.0-or-later\n\npackage demo\n"


def test_render_spdx_fixed_text_replaces_existing_header_after_long_preamble() -> None:
    text = (
        "// Copyright 2026 Example\n"
        "// Generated from upstream metadata\n"
        "// Additional context line 1\n"
        "// Additional context line 2\n"
        "// Additional context line 3\n"
        "// Additional context line 4\n"
        "// SPDX-License-Identifier: MIT\n"
        "\n"
        "package demo\n"
    )
    fixed = render_spdx_fixed_text(Path("Main.kt"), text, "AGPL-3.0-or-later")
    assert fixed.count("SPDX-License-Identifier:") == 1
    assert "// SPDX-License-Identifier: AGPL-3.0-or-later\n" in fixed
    assert "// SPDX-License-Identifier: MIT\n" not in fixed


def test_spdx_header_check_reports_fix_for_missing_header(tmp_path: Path) -> None:
    project = _project(tmp_path)
    file_path = tmp_path / "src" / "commonMain" / "kotlin" / "demo" / "Main.kt"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("package demo\n", encoding="utf-8")

    ctx = FileContext(check_name="SpdxHeaderCheck", path=file_path, project=project)
    check = SpdxHeaderCheck()
    check.check(ctx)

    assert len(ctx.issues.issues) == 1
    issue = ctx.issues.issues[0]
    assert issue.fix is not None
    issue.fix()
    assert file_path.read_text(encoding="utf-8").startswith("// SPDX-License-Identifier: AGPL-3.0-or-later\n")


def test_spdx_headers_task_delegates_to_spdx_check(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev.tasks import spdx_headers as task_module

    captured: list[tuple[str, list[str], bool]] = []

    def fake_check_main(project_or_dir_or_file: str, checks: list[str], fix: bool) -> int:
        captured.append((project_or_dir_or_file, checks, fix))
        return 0

    monkeypatch.setattr(task_module, "check_main", fake_check_main)

    assert task_module.spdx_headers(":kotlin-base58", fix=True) == 0
    assert captured == [(":kotlin-base58", ["SpdxHeaderCheck"], True)]
