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

from pathlib import Path
from typing import List

from packaging.requirements import Requirement

from dev.checks.base import FileCheck, IssueType, IssueList, FileContext

E_UNPINNED_DEPENDENCY = IssueType(
    "E_UNPINNED_DEPENDENCY",
    "Dependency '{dep}' is not version pinned.",
)


class PythonRequirementsPinnedCheck(FileCheck):
    """Ensure entries in ``requirements.txt`` are version pinned."""

    def check(self, ctx: FileContext):
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
                ctx.add_issue(E_UNPINNED_DEPENDENCY, dep=line, path=ctx.path, line_number=ln)
                continue

            #     # consider pinned only if there is exactly one == specifier
            #     if len(req.specifier) != 1:
            #         issues.append(E_UNPINNED_DEPENDENCY.make(line=line).at(path, line=ln))
            #         continue

            #     spec = next(iter(req.specifier))
            #     if spec.operator != "==" and spec.operator != "===":
            #         issues.append(E_UNPINNED_DEPENDENCY.make(line=line).at(path, line=ln))
