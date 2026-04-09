from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

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
    test_license: str | None = None
    repo_root: Path | None = None

    @property
    def effective_repo_root(self) -> Path:
        return self.repo_root or self.path


@dataclass
class _FakeContext:
    config: object
    licenses: dict[str, str]
    coc: jinja2.Template
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
        config=SimpleNamespace(
            default_company_email="legal@example.com",
            default_company_legal_name="Example Legal Co",
            default_company_short_name="Example Co",
        ),
        licenses={
            "MIT": (
                "Copyright (c) {{ copyright_year }} {{ copyright_holder }}\n"
                "{{ project_name }}\n"
                "{{ project_header_line }}\n"
            )
        },
        coc=jinja2.Template("CODE OF CONDUCT {{ company_short_name }} {{ legal_contact_email }}\n"),
        cla=jinja2.Template(
            "CLA {{ company_legal_name }} {{ company_short_name }} {{ project_primary_license_reference }} {{ legal_contact_email }}\n"
        ),
        cla_explanations=jinja2.Template(
            "CLA EXPLAIN {{ company_short_name }} {{ project_primary_license_reference }} {{ legal_contact_email }}\n"
        ),
        contributor_privacy_policy=jinja2.Template(
            "PRIVACY {{ company_legal_name }} {{ company_short_name }} {{ legal_contact_email }}\n"
        ),
        repo_template=tmp_path,
    )

    write_wabbit_legal_files(context, project)

    license_text = (tmp_path / "LICENSE.md").read_text(encoding="utf-8")
    assert "Alice Example" in license_text
    assert "demo-proj" in license_text
    assert "demo-proj: Example project" in license_text

    assert (tmp_path / "legal" / "cla" / "v1.0.0" / "CLA.md").read_text(
        encoding="utf-8"
    ) == "CLA Example Legal Co Example Co MIT License (MIT) legal@example.com\n"
    assert (tmp_path / "legal" / "cla" / "v1.0.0" / "CLA_EXPLANATIONS.md").read_text(
        encoding="utf-8"
    ) == "CLA EXPLAIN Example Co MIT License (MIT) legal@example.com\n"
    assert (tmp_path / "legal" / "contributor-privacy" / "v1.0.0" / "CONTRIBUTOR_PRIVACY.md").read_text(
        encoding="utf-8"
    ) == "PRIVACY Example Legal Co Example Co legal@example.com\n"
    assert (tmp_path / "legal" / "code-of-conduct" / "v1.0.0" / "CODE_OF_CONDUCT.md").read_text(
        encoding="utf-8"
    ) == "CODE OF CONDUCT Example Co legal@example.com\n"


def test_write_wabbit_legal_files_renders_mixed_license_notice_when_test_license_is_set(tmp_path: Path) -> None:
    project = _FakeProject(
        path=tmp_path,
        ownership=OwnershipType.WABBIT,
        license="MIT",
        test_license="LicenseRef-Wabbit-Public-Test-License",
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
        licenses={
            "MIT": "MIT body for {{ project_name }}\n",
            "LicenseRef-Wabbit-Public-Test-License": (
                "# Wabbit Public Tests License\n"
                "Custom test license for {{ project_name }}\n"
            ),
        },
        coc=jinja2.Template("CODE OF CONDUCT {{ company_short_name }} {{ legal_contact_email }}\n"),
        cla=jinja2.Template(
            "CLA {{ company_legal_name }} {{ company_short_name }} {{ project_primary_license_reference }} {{ legal_contact_email }}\n"
        ),
        cla_explanations=jinja2.Template(
            "CLA EXPLAIN {{ company_short_name }} {{ project_primary_license_reference }} {{ legal_contact_email }}\n"
        ),
        contributor_privacy_policy=jinja2.Template(
            "PRIVACY {{ company_legal_name }} {{ company_short_name }} {{ legal_contact_email }}\n"
        ),
        repo_template=tmp_path,
    )

    write_wabbit_legal_files(context, project)

    license_text = (tmp_path / "LICENSE.md").read_text(encoding="utf-8")
    assert "MIT body for demo-proj" in license_text

    notice_text = (tmp_path / "NOTICE.md").read_text(encoding="utf-8")
    assert "# Notices" in notice_text
    assert "MIT License (MIT)" in notice_text
    assert "Wabbit Public Tests License" in notice_text
    assert "`test/**`" in notice_text
    assert "Published artifacts must not include files covered by the test license." in notice_text

    test_license_text = (
        tmp_path / "LICENSES" / "LicenseRef-Wabbit-Public-Test-License-1.1.md"
    ).read_text(encoding="utf-8")
    assert "Custom test license for demo-proj" in test_license_text


def test_write_wabbit_legal_files_copies_test_license_into_existing_test_directories(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    project = _FakeProject(
        path=tmp_path,
        ownership=OwnershipType.WABBIT,
        license="MIT",
        test_license="LicenseRef-Wabbit-Public-Test-License",
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
        licenses={
            "MIT": "MIT body for {{ project_name }}\n",
            "LicenseRef-Wabbit-Public-Test-License": (
                "# Wabbit Public Tests License\n"
                "Custom test license for {{ project_name }}\n"
            ),
        },
        coc=jinja2.Template("CODE OF CONDUCT {{ company_short_name }} {{ legal_contact_email }}\n"),
        cla=jinja2.Template(
            "CLA {{ company_legal_name }} {{ company_short_name }} {{ project_primary_license_reference }} {{ legal_contact_email }}\n"
        ),
        cla_explanations=jinja2.Template(
            "CLA EXPLAIN {{ company_short_name }} {{ project_primary_license_reference }} {{ legal_contact_email }}\n"
        ),
        contributor_privacy_policy=jinja2.Template(
            "PRIVACY {{ company_legal_name }} {{ company_short_name }} {{ legal_contact_email }}\n"
        ),
        repo_template=tmp_path,
    )

    write_wabbit_legal_files(context, project)

    assert (tmp_path / "tests" / "LICENSE.md").read_text(encoding="utf-8").startswith("# Wabbit Public Tests License")
