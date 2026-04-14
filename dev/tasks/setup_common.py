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
    project_repo_root,
)
from dev.generated_files import prepend_generated_comment
from dev.licenses import (
    canonicalize_license_key,
    cla_primary_license_reference,
    license_display_name,
    render_project_license,
)
from dev.messages import error, warning
from dev.project_layout import (
    cleanup_misplaced_legal_files,
    discover_test_license_roots,
    expected_test_license_copy_paths,
    project_preserves_root_legal_files,
    project_uses_managed_legal_files,
)
from dev.setup_plan import SetupPlan, SetupPlanCategory, SetupPlanOwnership


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

    @property
    def setup_plan(self) -> SetupPlan: ...


CANONICAL_BANNER_RELATIVE_PATH = Path(".meta") / "github-project-banner.png"
LEGACY_BANNER_RELATIVE_PATH = Path(".banner.png")


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


def write_requirements_file(
    path: Path,
    deps: list[str],
    *,
    interactive: bool,
    project_name: str,
    setup_plan: SetupPlan | None = None,
    repo_root: Path | None = None,
) -> None:
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
    cleaned_text = clean_text(requirements_text)
    if setup_plan is None or repo_root is None:
        dev.io.write_text_file(path, cleaned_text)
        return

    setup_plan.replace_text(
        repo_root=repo_root,
        path=path,
        content=cleaned_text,
        category=SetupPlanCategory.BUILD,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )


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
    if normalized == "LicenseRef-Wabbit-Public-Test-License-1.1":
        for compatibility_candidate in [
            "LicenseRef-Wabbit-Public-Test-License",
            "Wabbit-Public-Tests-License",
        ]:
            if compatibility_candidate not in candidates:
                candidates.append(compatibility_candidate)
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
    if display_name is not None and not display_name.startswith("LicenseRef-"):
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


def _legal_root(project: Project) -> Path:
    return project.path / "legal"


def _cla_path(project: Project) -> Path:
    return _legal_root(project) / "cla" / "v1.0.0" / "CLA.md"


def _cla_explanations_path(project: Project) -> Path:
    return _legal_root(project) / "cla" / "v1.0.0" / "CLA_EXPLANATIONS.md"


def _contributor_privacy_path(project: Project) -> Path:
    return _legal_root(project) / "contributor-privacy" / "v1.0.0" / "CONTRIBUTOR_PRIVACY.md"


def _code_of_conduct_path(project: Project) -> Path:
    return _legal_root(project) / "code-of-conduct" / "v1.0.0" / "CODE_OF_CONDUCT.md"


def _license_notice_path(project: Project) -> Path:
    return project.path / "NOTICE.md"


def _extra_license_dir(project: Project) -> Path:
    return project.path / "LICENSES"


def _raw_extra_license_filename(license_key: str) -> str:
    safe_name = license_key.replace("/", "-").replace("\\", "-")
    return f"{safe_name}.md"


def _extra_license_filename(license_key: str) -> str:
    normalized = canonicalize_license_key(license_key) or license_key
    return _raw_extra_license_filename(normalized)


def _extra_license_path(project: Project, license_key: str) -> Path:
    return _extra_license_dir(project) / _extra_license_filename(license_key)


def _raw_extra_license_path(project: Project, license_key: str) -> Path:
    return _extra_license_dir(project) / _raw_extra_license_filename(license_key)


def _legacy_root_legal_paths(project: Project) -> list[Path]:
    return [
        project.path / "CLA.md",
        project.path / "CLA_EXPLANATIONS.md",
        project.path / "CONTRIBUTOR_PRIVACY.md",
        project.path / "CODE_OF_CONDUCT.md",
    ]


def _planned_repo_root(project: Project) -> Path:
    return project_repo_root(project).resolve()


def _cleanup_legacy_root_legal_paths(ctx: CommonSetupContext, project: Project) -> None:
    repo_root = _planned_repo_root(project)
    for path in _legacy_root_legal_paths(project):
        ctx.setup_plan.delete_path(
            repo_root=repo_root,
            path=path,
            category=SetupPlanCategory.LEGAL,
            ownership=SetupPlanOwnership.MANAGED_FILE,
        )


def _cleanup_test_license_outputs(
    ctx: CommonSetupContext,
    project: Project,
    *,
    keep_license: str | None = None,
) -> None:
    repo_root = _planned_repo_root(project)
    keep_paths: set[Path] = set()
    if keep_license is not None:
        keep_paths.add(_extra_license_path(project, keep_license))
        keep_paths.add(_raw_extra_license_path(project, keep_license))
    for candidate in [
        "LicenseRef-Wabbit-Public-Test-License",
        "LicenseRef-Wabbit-Public-Test-License-1.1",
    ]:
        for candidate_path in {
            _extra_license_path(project, candidate),
            _raw_extra_license_path(project, candidate),
        }:
            if candidate_path in keep_paths:
                continue
            ctx.setup_plan.delete_path(
                repo_root=repo_root,
                path=candidate_path,
                category=SetupPlanCategory.LEGAL,
                ownership=SetupPlanOwnership.MANAGED_FILE,
            )
    licenses_dir = _extra_license_dir(project)
    if licenses_dir.is_dir() and not any(licenses_dir.iterdir()):
        ctx.setup_plan.delete_path(
            repo_root=repo_root,
            path=licenses_dir,
            category=SetupPlanCategory.LEGAL,
            ownership=SetupPlanOwnership.MANAGED_FILE,
        )


def _cleanup_test_license_copies(ctx: CommonSetupContext, project: Project) -> None:
    repo_root = _planned_repo_root(project)
    for path in expected_test_license_copy_paths(project):
        ctx.setup_plan.delete_path(
            repo_root=repo_root,
            path=path,
            category=SetupPlanCategory.LEGAL,
            ownership=SetupPlanOwnership.MANAGED_FILE,
        )


def _write_test_license_copies(ctx: CommonSetupContext, project: Project, rendered_test_license_text: str) -> None:
    repo_root = _planned_repo_root(project)
    for root in discover_test_license_roots(project):
        ctx.setup_plan.replace_text(
            repo_root=repo_root,
            path=root / "LICENSE.md",
            content=rendered_test_license_text,
            category=SetupPlanCategory.LEGAL,
            ownership=SetupPlanOwnership.MANAGED_FILE,
        )


def _render_license_notice_file(
    *,
    project: Project,
    primary_license_reference: str,
    test_license_reference: str,
    test_license_path: Path,
) -> str:
    test_paths = "\n".join(f"- `{path}`" for path in _test_license_paths(project))
    return clean_text(f"""# Notices

This repository contains materials under multiple licenses.

- Production source code and other non-test project materials are licensed under [{primary_license_reference}](LICENSE.md).
- Test suites, test fixtures, test data, benchmark code, and test-only helper code under the following repository path conventions are licensed under [{test_license_reference}]({test_license_path.relative_to(project.path).as_posix()}):

{test_paths}

If a file carries a different SPDX header, that file-level notice controls.

Published artifacts must not include files covered by the test license.
""")


def write_wabbit_legal_documents(ctx: CommonSetupContext, project: Project) -> None:
    legal_template_context = _wabbit_legal_template_context(ctx, project)
    if not legal_template_context:
        return
    repo_root = _planned_repo_root(project)

    ctx.setup_plan.replace_text(
        repo_root=repo_root,
        path=_cla_path(project),
        content=render_template(ctx.cla, **legal_template_context),
        category=SetupPlanCategory.LEGAL,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )
    ctx.setup_plan.replace_text(
        repo_root=repo_root,
        path=_cla_explanations_path(project),
        content=render_template(ctx.cla_explanations, **legal_template_context),
        category=SetupPlanCategory.LEGAL,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )
    ctx.setup_plan.replace_text(
        repo_root=repo_root,
        path=_contributor_privacy_path(project),
        content=render_template(ctx.contributor_privacy_policy, **legal_template_context),
        category=SetupPlanCategory.LEGAL,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )
    ctx.setup_plan.replace_text(
        repo_root=repo_root,
        path=_code_of_conduct_path(project),
        content=render_template(ctx.coc, **legal_template_context),
        category=SetupPlanCategory.LEGAL,
        ownership=SetupPlanOwnership.MANAGED_FILE,
    )
    _cleanup_legacy_root_legal_paths(ctx, project)


def write_wabbit_legal_files(
    ctx: CommonSetupContext,
    project: Project,
    *,
    write_test_license_copies: bool = True,
    cleanup_layout: bool = True,
) -> None:
    if project.ownership != OwnershipType.WABBIT:
        return

    if not project_uses_managed_legal_files(project):
        if project.path == project.effective_repo_root:
            ctx.setup_plan.delete_path(
                repo_root=_planned_repo_root(project),
                path=_license_notice_path(project),
                category=SetupPlanCategory.LEGAL,
                ownership=SetupPlanOwnership.MANAGED_FILE,
            )
            _cleanup_test_license_outputs(ctx, project)
            if not project_preserves_root_legal_files(project):
                ctx.setup_plan.delete_path(
                    repo_root=_planned_repo_root(project),
                    path=project.path / "LICENSE.md",
                    category=SetupPlanCategory.LEGAL,
                    ownership=SetupPlanOwnership.MANAGED_FILE,
                )
                _cleanup_legacy_root_legal_paths(ctx, project)
                cleanup_misplaced_legal_files(project.path, [project])
        _cleanup_test_license_copies(ctx, project)
        return

    project_license = canonicalize_license_key(project.license)
    test_license = canonicalize_license_key(project.test_license)
    write_root_legal_files = project.path == project.effective_repo_root
    repo_root = _planned_repo_root(project)
    if project_license is not None and write_root_legal_files:
        license_text = _resolve_license_text(ctx.licenses, project_license)
        if license_text is None:
            supported = ", ".join(sorted(ctx.licenses))
            error(f"Unknown license key: {project_license}. Supported keys: {supported}")
            write_wabbit_legal_documents(ctx, project)
            return

        rendered_license_text = render_project_license(license_text, project)
        ctx.setup_plan.replace_text(
            repo_root=repo_root,
            path=project.path / "LICENSE.md",
            content=rendered_license_text,
            category=SetupPlanCategory.LEGAL,
            ownership=SetupPlanOwnership.MANAGED_FILE,
        )
        if test_license is not None:
            test_license_text = _resolve_license_text(ctx.licenses, test_license)
            if test_license_text is None:
                supported = ", ".join(sorted(ctx.licenses))
                error(f"Unknown test license key: {test_license}. Supported keys: {supported}")
                write_wabbit_legal_documents(ctx, project)
                return
            _cleanup_test_license_outputs(ctx, project, keep_license=test_license)
            rendered_test_license_text = render_project_license(test_license_text, project)
            test_license_path = _extra_license_path(project, test_license)
            ctx.setup_plan.replace_text(
                repo_root=repo_root,
                path=test_license_path,
                content=rendered_test_license_text,
                category=SetupPlanCategory.LEGAL,
                ownership=SetupPlanOwnership.MANAGED_FILE,
            )
            ctx.setup_plan.replace_text(
                repo_root=repo_root,
                path=_license_notice_path(project),
                content=_render_license_notice_file(
                    project=project,
                    primary_license_reference=cla_primary_license_reference(project_license),
                    test_license_reference=_license_reference_label(ctx.licenses, test_license),
                    test_license_path=test_license_path,
                ),
                category=SetupPlanCategory.LEGAL,
                ownership=SetupPlanOwnership.MANAGED_FILE,
            )
        else:
            ctx.setup_plan.delete_path(
                repo_root=repo_root,
                path=_license_notice_path(project),
                category=SetupPlanCategory.LEGAL,
                ownership=SetupPlanOwnership.MANAGED_FILE,
            )
            _cleanup_test_license_outputs(ctx, project)
    elif write_root_legal_files:
        ctx.setup_plan.delete_path(
            repo_root=repo_root,
            path=project.path / "LICENSE.md",
            category=SetupPlanCategory.LEGAL,
            ownership=SetupPlanOwnership.MANAGED_FILE,
        )
        ctx.setup_plan.delete_path(
            repo_root=repo_root,
            path=_license_notice_path(project),
            category=SetupPlanCategory.LEGAL,
            ownership=SetupPlanOwnership.MANAGED_FILE,
        )
        _cleanup_test_license_outputs(ctx, project)

    if test_license is not None and write_test_license_copies:
        test_license_text = _resolve_license_text(ctx.licenses, test_license)
        if test_license_text is None:
            supported = ", ".join(sorted(ctx.licenses))
            error(f"Unknown test license key: {test_license}. Supported keys: {supported}")
            return
        _write_test_license_copies(ctx, project, render_project_license(test_license_text, project))
    elif write_test_license_copies:
        _cleanup_test_license_copies(ctx, project)

    if write_root_legal_files:
        write_wabbit_legal_documents(ctx, project)
        if cleanup_layout:
            cleanup_misplaced_legal_files(project.path, [project])


def write_banner(ctx: CommonSetupContext, project: Project) -> None:
    canonical_output_path = project.path / CANONICAL_BANNER_RELATIVE_PATH
    repo_root = _planned_repo_root(project)
    ctx.setup_plan.replace_file(
        repo_root=repo_root,
        path=canonical_output_path,
        category=SetupPlanCategory.ASSET,
        ownership=SetupPlanOwnership.GENERATED_ASSET,
        apply=lambda: create_banner(
            image_path=ctx.repo_template / "banner4c.png",
            font_path=str(ctx.repo_template / "CooperHewitt-Light.otf"),
            main_text=project.name,
            subtitle_text=None,
            background_color=(0, 0, 0, 0),
            output_path=str(canonical_output_path),
            font_size=60,
            subtitle_font_size=None,
            padding=40,
        ),
    )
    ctx.setup_plan.copy_file(
        repo_root=repo_root,
        source_path=canonical_output_path,
        destination_path=project.path / LEGACY_BANNER_RELATIVE_PATH,
        category=SetupPlanCategory.ASSET,
        ownership=SetupPlanOwnership.GENERATED_ASSET,
    )


__all__ = [
    "CANONICAL_BANNER_RELATIVE_PATH",
    "LEGACY_BANNER_RELATIVE_PATH",
    "clean_text",
    "RepoSetupMode",
    "render_template",
    "write_banner",
    "write_wabbit_legal_documents",
    "write_requirements_file",
    "write_wabbit_legal_files",
]
