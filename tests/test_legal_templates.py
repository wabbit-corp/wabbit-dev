from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import jinja2

import dev.io
from dev.config import OwnershipType
from dev.licenses import load_license_texts
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
    config: object
    licenses: dict[str, str]
    coc: jinja2.Template
    cla: jinja2.Template
    cla_explanations: jinja2.Template
    contributor_privacy_policy: jinja2.Template
    repo_template: Path


def _workspace_template_root() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root.parent / "data-repo-template"


def test_workspace_legal_templates_do_not_contain_manual_placeholders() -> None:
    template_root = _workspace_template_root() / "legal"
    disallowed_fragments = (
        "{{COMPANY_EMAIL}}",
        "[insert link]",
        "[Project Lead",
        "preferred contact method",
    )

    template_files = sorted(template_root.rglob("*.md"))
    assert template_files

    for path in template_files:
        text = path.read_text(encoding="utf-8")
        for fragment in disallowed_fragments:
            assert fragment not in text, f"{path} still contains {fragment!r}"


def test_workspace_legal_templates_render_without_unresolved_placeholders(tmp_path: Path) -> None:
    template_root = _workspace_template_root()
    legal_root = template_root / "legal"
    project = _FakeProject(
        path=tmp_path,
        ownership=OwnershipType.WABBIT,
        license="MIT",
        name="demo-proj",
        description="Example project",
        authors=["Alice Example <alice@example.com>"],
    )
    context = _FakeContext(
        config=SimpleNamespace(
            default_company_email="legal@example.com",
            default_company_legal_name="Example Legal Co",
            default_company_short_name="Example Co",
        ),
        licenses=load_license_texts(legal_root / "licenses"),
        coc=dev.io.read_template(legal_root / "code-of-conduct" / "v1.0.0" / "CODE_OF_CONDUCT.md", strict=True),
        cla=dev.io.read_template(legal_root / "cla" / "v1.0.0" / "CLA.md", strict=True),
        cla_explanations=dev.io.read_template(
            legal_root / "cla" / "v1.0.0" / "CLA_EXPLANATIONS.md",
            strict=True,
        ),
        contributor_privacy_policy=dev.io.read_template(
            legal_root / "contributor-privacy" / "v1.0.0" / "CONTRIBUTOR_PRIVACY.md",
            strict=True,
        ),
        repo_template=template_root,
    )

    write_wabbit_legal_files(context, project)

    generated_paths = [
        tmp_path / "LICENSE.md",
        tmp_path / "CLA.md",
        tmp_path / "CLA_EXPLANATIONS.md",
        tmp_path / "CONTRIBUTOR_PRIVACY.md",
        tmp_path / "CODE_OF_CONDUCT.md",
    ]
    disallowed_fragments = (
        "{{",
        "}}",
        "{{COMPANY_EMAIL}}",
        "[insert link]",
        "[Project Lead",
        "preferred contact method",
    )

    for path in generated_paths:
        text = path.read_text(encoding="utf-8")
        for fragment in disallowed_fragments:
            assert fragment not in text, f"{path} still contains {fragment!r}"

    assert "MIT License (MIT)" in (tmp_path / "CLA.md").read_text(encoding="utf-8")
    assert "Example Legal Co" in (tmp_path / "CLA.md").read_text(encoding="utf-8")
    assert "Example Co" in (tmp_path / "CLA.md").read_text(encoding="utf-8")
    assert "Example Legal Co" in (tmp_path / "CONTRIBUTOR_PRIVACY.md").read_text(encoding="utf-8")
    assert "Example Co" in (tmp_path / "CONTRIBUTOR_PRIVACY.md").read_text(encoding="utf-8")
    assert "legal@example.com" in (tmp_path / "CLA.md").read_text(encoding="utf-8")
    assert "legal@example.com" in (tmp_path / "CONTRIBUTOR_PRIVACY.md").read_text(encoding="utf-8")
    assert "legal@example.com" in (tmp_path / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
