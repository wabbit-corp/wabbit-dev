from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Protocol

import jinja2

import dev.io
from dev.banner import create_banner
from dev.config import (
    Config,
    DataProject,
    GradleProject,
    OwnershipType,
    PremakeProject,
    Project,
    PurescriptProject,
    PythonProject,
)
from dev.generated_files import prepend_generated_comment
from dev.licenses import (
    canonicalize_license_key,
    cla_primary_license_reference,
    license_display_name,
    render_project_license,
)
from dev.messages import error, warning


class RepoSetupMode(Enum):
    PROD = "prod"
    DEV = "dev"
    LOCAL = "local"


class CommonSetupContext(Protocol):
    @property
    def config(self) -> Config: ...

    @property
    def licenses(self) -> dict[str, str]: ...

    @property
    def coc(self) -> jinja2.Template: ...

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

    requirements_text = prepend_generated_comment(
        "\n".join(deps) + "\n",
        comment_prefix="#",
        body_lines=[
            "This file is generated from workspace configuration in root.clj.",
            "To change it, update root.clj and regenerate with the dev command, for example:",
            "  dev setup <project-or-repo>",
            "Direct edits to this file will be overwritten the next time setup runs.",
        ],
    )
    dev.io.write_text_file(path, clean_text(requirements_text))


def _legal_contact_email(ctx: CommonSetupContext) -> str:
    contact_email = ctx.config.default_company_email
    if contact_email is None or not contact_email.strip():
        raise ValueError("default-company-email is required to render Wabbit legal templates")
    return contact_email.strip()


def _company_legal_name(ctx: CommonSetupContext) -> str:
    company_name = ctx.config.default_company_legal_name
    if company_name is None or not company_name.strip():
        raise ValueError("default-company-legal-name is required to render Wabbit legal templates")
    return company_name.strip()


def _company_short_name(ctx: CommonSetupContext) -> str:
    company_name = ctx.config.default_company_short_name
    if company_name is None or not company_name.strip():
        raise ValueError("default-company-short-name is required to render Wabbit legal templates")
    return company_name.strip()


def _wabbit_legal_template_context(ctx: CommonSetupContext, project: Project) -> dict[str, str]:
    if project.ownership != OwnershipType.WABBIT:
        return {}

    project_license = canonicalize_license_key(project.license)
    return {
        "company_legal_name": _company_legal_name(ctx),
        "company_short_name": _company_short_name(ctx),
        "project_primary_license_reference": cla_primary_license_reference(project_license),
        "legal_contact_email": _legal_contact_email(ctx),
    }


def _license_lookup_candidates(license_key: str | None) -> list[str]:
    if license_key is None:
        return []

    raw = license_key.strip()
    if not raw:
        return []

    normalized = canonicalize_license_key(raw)
    candidates: list[str] = []
    for candidate in [normalized, raw]:
        if candidate is not None and candidate not in candidates:
            candidates.append(candidate)
            if candidate.startswith("LicenseRef-"):
                stripped = candidate.removeprefix("LicenseRef-")
                if stripped not in candidates:
                    candidates.append(stripped)
    return candidates


def _resolve_license_text(licenses: dict[str, str], license_key: str | None) -> str | None:
    for candidate in _license_lookup_candidates(license_key):
        template_text = licenses.get(candidate)
        if template_text is not None:
            return template_text
    return None


def _license_heading_from_text(template_text: str) -> str | None:
    for line in template_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _license_reference_label(licenses: dict[str, str], license_key: str | None) -> str:
    display_name = license_display_name(license_key)
    if display_name is not None:
        return display_name
    template_text = _resolve_license_text(licenses, license_key)
    heading = _license_heading_from_text(template_text) if template_text is not None else None
    if heading is not None:
        return heading
    return license_key or "the configured license"


def _test_license_paths(project: Project) -> list[str]:
    if isinstance(project, GradleProject):
        return [
            "src/*Test/**",
            "src/test/**",
            "test/**",
            "tests/**",
        ]
    if isinstance(project, PythonProject):
        return ["tests/**", "test/**"]
    if isinstance(project, PurescriptProject):
        return ["test/**", "tests/**"]
    if isinstance(project, PremakeProject):
        return ["test/**", "tests/**"]
    if isinstance(project, DataProject):
        return ["test/**", "tests/**"]
    return ["test/**", "tests/**"]


def _render_mixed_license_file(
    *,
    project: Project,
    primary_license_reference: str,
    primary_license_text: str,
    test_license_reference: str,
    test_license_text: str,
) -> str:
    test_paths = "\n".join(f"- `{path}`" for path in _test_license_paths(project))
    return clean_text(
        f"""# Licensing

This repository contains materials under multiple licenses.

## Primary License

Unless otherwise noted, the production source code and other non-test project materials are licensed under {primary_license_reference}.

## Test License

Test suites, test fixtures, test data, benchmark code, and test-only helper code under the following repository path conventions are licensed under {test_license_reference}:

{test_paths}

If a file carries a different SPDX header, that file-level notice controls.

Published artifacts must not include files covered by the test license.

---

## Primary License Text

{primary_license_text.rstrip()}

---

## Test License Text

{test_license_text.rstrip()}
"""
    )


def write_wabbit_legal_documents(ctx: CommonSetupContext, project: Project) -> None:
    legal_template_context = _wabbit_legal_template_context(ctx, project)
    if not legal_template_context:
        return

    dev.io.write_text_file(
        project.path / "CLA.md",
        render_template(ctx.cla, **legal_template_context),
    )
    dev.io.write_text_file(
        project.path / "CLA_EXPLANATIONS.md",
        render_template(ctx.cla_explanations, **legal_template_context),
    )
    dev.io.write_text_file(
        project.path / "CONTRIBUTOR_PRIVACY.md",
        render_template(ctx.contributor_privacy_policy, **legal_template_context),
    )
    dev.io.write_text_file(project.path / "CODE_OF_CONDUCT.md", render_template(ctx.coc, **legal_template_context))


def write_wabbit_legal_files(ctx: CommonSetupContext, project: Project) -> None:
    if project.ownership != OwnershipType.WABBIT:
        return

    project_license = canonicalize_license_key(project.license)
    test_license = canonicalize_license_key(project.test_license)
    if project_license is not None:
        license_text = _resolve_license_text(ctx.licenses, project_license)
        if license_text is None:
            supported = ", ".join(sorted(ctx.licenses))
            error(f"Unknown license key: {project_license}. Supported keys: {supported}")
            write_wabbit_legal_documents(ctx, project)
            return

        rendered_license_text = render_project_license(license_text, project)
        if test_license is not None:
            test_license_text = _resolve_license_text(ctx.licenses, test_license)
            if test_license_text is None:
                supported = ", ".join(sorted(ctx.licenses))
                error(f"Unknown test license key: {test_license}. Supported keys: {supported}")
                write_wabbit_legal_documents(ctx, project)
                return
            rendered_test_license_text = render_project_license(test_license_text, project)
            dev.io.write_text_file(
                project.path / "LICENSE.md",
                _render_mixed_license_file(
                    project=project,
                    primary_license_reference=cla_primary_license_reference(project_license),
                    primary_license_text=rendered_license_text,
                    test_license_reference=_license_reference_label(ctx.licenses, test_license),
                    test_license_text=rendered_test_license_text,
                ),
            )
        else:
            dev.io.write_text_file(project.path / "LICENSE.md", rendered_license_text)

    write_wabbit_legal_documents(ctx, project)


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
    "write_wabbit_legal_documents",
    "write_requirements_file",
    "write_wabbit_legal_files",
]
