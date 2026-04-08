from __future__ import annotations

from dev.checks.base import FileCheck, FileContext, IssueType
from dev.generated_files import managed_file_repair_guidance, verify_managed_text_integrity

E_MANAGED_GENERATED_FILE_EDITED = IssueType(
    "E_MANAGED_GENERATED_FILE_EDITED",
    "Managed generated file was edited after setup ({reason}). {guidance}",
)


class ManagedGeneratedFileIntegrityCheck(FileCheck):
    """Verifies embedded integrity stamps on setup-managed generated files."""

    order = 60

    def check(self, ctx: FileContext) -> None:
        if not ctx.is_file or not ctx.expected_properties.is_text:
            return

        text = ctx.read_text()
        verification = verify_managed_text_integrity(text)
        if not verification.is_managed or not verification.has_integrity:
            return
        if verification.is_valid:
            return

        ctx.add_issue(
            E_MANAGED_GENERATED_FILE_EDITED,
            reason=verification.reason or "integrity stamp mismatch",
            guidance=managed_file_repair_guidance(ctx.path),
        )
