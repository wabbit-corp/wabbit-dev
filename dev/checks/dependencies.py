"""
* [ ] Keep Dependencies Up-to-Date: Regularly update dependencies to incorporate security patches and improvements.
* [ ] Pin and Lock Dependencies: Use explicit version pinning and lock files for all dependencies to ensure reproducible builds.
* [ ] Remove Unused Dependencies: Periodically audit each repository for dependencies that are not actually
      used in the code. This can be automated with tools (like depcheck for Node or pip-autoremove for Python)
      that detect imports vs. declared dependencies.
* [ ] License Compliance for Dependencies: All dependencies should have licenses compatible with your project’s
      license (especially important for open source releases).
"""

from __future__ import annotations

from packaging.requirements import Requirement
from packaging.version import InvalidVersion
from packaging.version import Version as PythonVersion

from dev.checks.base import FileCheck, FileContext, IssueType

E_UNPINNED_DEPENDENCY = IssueType(
    "E_UNPINNED_DEPENDENCY",
    "Dependency '{dep}' is not version pinned.",
)


class PythonRequirementsPinnedCheck(FileCheck):
    """Ensure entries in ``requirements.txt`` are version pinned."""

    def _is_exact_pin(self, req: Requirement) -> bool:
        return len(req.specifier) == 1 and all(spec.operator in {"==", "==="} for spec in req.specifier)

    def _is_major_pin(self, req: Requirement) -> bool:
        if len(req.specifier) != 2:
            return False

        lower: str | None = None
        upper: str | None = None
        for spec in req.specifier:
            if spec.operator == ">=" and lower is None:
                lower = spec.version
                continue
            if spec.operator == "<" and upper is None:
                upper = spec.version
                continue
            return False

        if lower is None or upper is None:
            return False

        try:
            lower_version = PythonVersion(lower)
            upper_version = PythonVersion(upper)
        except InvalidVersion:
            return False

        if upper_version <= lower_version:
            return False
        if upper_version.minor != 0 or upper_version.micro != 0:
            return False
        if upper_version.major != lower_version.major + 1:
            return False
        if upper_version.pre is not None or upper_version.post is not None or upper_version.dev is not None:
            return False

        return True

    def check(self, ctx: FileContext) -> None:
        if not ctx.path.is_file():
            return
        if ctx.path.name != "requirements.txt":
            return

        text = ctx.read_text(E_UNPINNED_DEPENDENCY)
        for ln, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                req = Requirement(line)
            except Exception:
                continue

            if not req.specifier:
                ctx.add_issue(E_UNPINNED_DEPENDENCY, line=ln, dep=line)
                continue

            if self._is_exact_pin(req) or self._is_major_pin(req):
                continue

            ctx.add_issue(E_UNPINNED_DEPENDENCY, line=ln, dep=line)


__all__ = [
    "E_UNPINNED_DEPENDENCY",
    "PythonRequirementsPinnedCheck",
]
