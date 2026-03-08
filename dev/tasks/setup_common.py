from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Protocol

import jinja2

import dev.io
from dev.banner import create_banner
from dev.config import OwnershipType, Project
from dev.licenses import canonicalize_license_key, render_project_license
from dev.messages import error, warning


class RepoSetupMode(Enum):
    PROD = "prod"
    DEV = "dev"
    LOCAL = "local"


class CommonSetupContext(Protocol):
    @property
    def licenses(self) -> dict[str, str]: ...

    @property
    def coc(self) -> str: ...

    @property
    def cla(self) -> jinja2.Template: ...

    @property
    def cla_explanations(self) -> jinja2.Template: ...

    @property
    def contributor_privacy_policy(self) -> jinja2.Template: ...

    @property
    def repo_template(self) -> Path: ...


def render_template(template: jinja2.Template, **kwargs: object) -> str:
    rendered = template.render(**kwargs)
    return rendered.rstrip() + "\n"


def clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = text.replace("\t", "    ")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    if not text.endswith("\n"):
        text = text + "\n"
    return text


def write_requirements_file(path: Path, deps: list[str], *, interactive: bool, project_name: str) -> None:
    del interactive
    if not deps:
        if path.exists():
            warning(f"No dependencies configured for {project_name}; leaving {path} untouched")
        return

    dev.io.write_text_file(path, clean_text("\n".join(deps) + "\n"))


def write_wabbit_legal_files(ctx: CommonSetupContext, project: Project) -> None:
    if project.ownership != OwnershipType.WABBIT:
        return

    project_license = canonicalize_license_key(project.license)
    if project_license is not None:
        license_text = ctx.licenses.get(project_license)
        if license_text is None:
            supported = ", ".join(sorted(ctx.licenses))
            error(f"Unknown license key: {project_license}. Supported keys: {supported}")
        else:
            rendered_license_text = render_project_license(license_text, project)
            dev.io.write_text_file(project.path / "LICENSE.md", rendered_license_text)

    dev.io.write_text_file(project.path / "CLA.md", render_template(ctx.cla))
    dev.io.write_text_file(project.path / "CLA_EXPLANATIONS.md", render_template(ctx.cla_explanations))
    dev.io.write_text_file(
        project.path / "CONTRIBUTOR_PRIVACY.md",
        render_template(ctx.contributor_privacy_policy),
    )
    dev.io.write_text_file(project.path / "CODE_OF_CONDUCT.md", ctx.coc)


def write_banner(ctx: CommonSetupContext, project: Project) -> None:
    create_banner(
        image_path=ctx.repo_template / "banner4c.png",
        font_path=str(ctx.repo_template / "CooperHewitt-Light.otf"),
        main_text=project.name,
        subtitle_text=None,
        background_color=(0, 0, 0, 0),
        output_path=str(project.path / ".banner.png"),
        font_size=60,
        subtitle_font_size=None,
        padding=40,
    )


__all__ = [
    "clean_text",
    "RepoSetupMode",
    "render_template",
    "write_banner",
    "write_requirements_file",
    "write_wabbit_legal_files",
]
