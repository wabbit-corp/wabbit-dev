from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jinja2

from dev.config import OwnershipType
from dev.tasks.setup_common import write_wabbit_legal_files


@dataclass
class _FakeProject:
    path: Path
    ownership: OwnershipType
    license: str | None
    name: str
    description: str | None
    authors: list[str]
    copyright_holder: str | None = None
    copyright_year_start: int | None = None


@dataclass
class _FakeContext:
    licenses: dict[str, str]
    coc: str
    cla: jinja2.Template
    cla_explanations: jinja2.Template
    contributor_privacy_policy: jinja2.Template
    repo_template: Path


def test_write_wabbit_legal_files_renders_license_template_variables(tmp_path: Path) -> None:
    project = _FakeProject(
        path=tmp_path,
        ownership=OwnershipType.WABBIT,
        license="MIT",
        name="demo-proj",
        description="Example project",
        authors=["Alice Example <alice@example.com>"],
    )
    context = _FakeContext(
        licenses={
            "MIT": (
                "Copyright (c) {{ copyright_year }} {{ copyright_holder }}\n"
                "{{ project_name }}\n"
                "{{ project_header_line }}\n"
            )
        },
        coc="CODE OF CONDUCT\n",
        cla=jinja2.Template("CLA {{ project_primary_license_reference }}\n"),
        cla_explanations=jinja2.Template("CLA EXPLAIN {{ project_primary_license_reference }}\n"),
        contributor_privacy_policy=jinja2.Template("PRIVACY\n"),
        repo_template=tmp_path,
    )

    write_wabbit_legal_files(context, project)

    license_text = (tmp_path / "LICENSE.md").read_text(encoding="utf-8")
    assert "Alice Example" in license_text
    assert "demo-proj" in license_text
    assert "demo-proj: Example project" in license_text

    assert (tmp_path / "CLA.md").read_text(encoding="utf-8") == "CLA MIT License (MIT)\n"
    assert (tmp_path / "CLA_EXPLANATIONS.md").read_text(encoding="utf-8") == "CLA EXPLAIN MIT License (MIT)\n"
    assert (tmp_path / "CONTRIBUTOR_PRIVACY.md").read_text(encoding="utf-8") == "PRIVACY\n"
    assert (tmp_path / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8") == "CODE OF CONDUCT\n"
