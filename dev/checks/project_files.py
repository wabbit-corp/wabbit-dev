"""
* [ ] Ensure there’s a README, LICENSE, and possibly a CONTRIBUTING guide or code of conduct (depending on the project).
* [ ] Security Policy: If applicable, include a SECURITY.md file that details how to report vulnerabilities in the project.
* [ ] Changelog or Release Notes: For projects that are released or versioned, maintain a CHANGELOG.md or release notes
      documenting notable changes in each version.
* [ ] Check Version Number Consistency: Compare version numbers mentioned in key files
      (e.g., README.md, CHANGELOG.md, setup/package files like package.json, setup.py, pom.xml)
      against the latest Git tag to ensure they are aligned, especially after a release.
* [ ] Check that a dependency files (e.g., requirements.txt, package.json, etc.) are present and up-to-date.
* [ ] Check for a .gitignore file to ensure that sensitive files (e.g., .env, credentials) are not committed.
* [ ] If the project seems to use Docker, check for a .dockerignore file to ensure that sensitive files
      (e.g., .env, credentials) are not included in Docker images.
* [ ] Check for a .gitattributes file to ensure that line endings are consistent across platforms.
* [ ] Check that the year in the LICENSE (if applicable) is current, and that badges in README
      (for CI, coverage, etc.) are functional (they often embed build status – ensure they point
      to the correct project).
* [ ] Check CHANGELOG Format and Recency: Verify that a CHANGELOG file (if used) follows a consistent
      format (like Keep a Changelog) and has entries corresponding to recent version tags, ensuring
      release notes are kept up-to-date.
* [ ] Check Project Name/Description Consistency: Compare the project's name and description across
      various metadata files (README.md, package.json, setup.py, pom.xml, etc.) to ensure they are consistent.
* [ ] Check License Consistency: Verify that the license specified in package manager files (e.g., license
      field in package.json, license classifier in setup.py) matches the license declared in the main LICENSE
      file in the repository root.
"""

import re
import os
import platform
import unicodedata
from pathlib import Path
from typing import List, Set, Optional, Dict, Pattern, Any, Tuple, Union

# Import necessary components from your base framework
# (Adjust the import path if necessary)
from dev.checks.base import (
    ProjectCheck,
    Issue,
    IssueType,
    Severity,
    FileLocation,
    IntRangeSet,
    FileContext,
    IssueList,
)

E_MISSING_README = IssueType(
    "d0b2162a-119d-4a0b-a4e4-ca8d1d6a40a8", "Missing README file"
)
E_README_NO_BANNER = IssueType(
    "9a39b395-43d1-4c6f-b9ba-8d21496fac4e",
    "README file does not contain a project banner",
)
E_README_NO_BADGES = IssueType(
    "1631689a-8d5d-400e-a604-a1853f65c049", "README file does not contain badges"
)
E_README_NO_INSTALL = IssueType(
    "c4f3b5a0-8d1e-4a2b-9c6d-7f3e1f2b5a8d",
    "README file does not contain installation instructions",
)
E_README_NO_USAGE = IssueType(
    "798866e6-feb5-4634-8954-188245c02a29",
    "README file does not contain usage instructions",
)
E_README_NO_LICENSE = IssueType(
    "4bd8af48-b638-4bf9-b0e1-4ca4b1932ac0",
    "README file does not contain license information",
)
E_README_NO_CONTRIBUTING = IssueType(
    "358e5d64-54a1-4fe5-9343-cad86552d4f2",
    "README file does not contain contributing instructions",
)

E_MISSING_LICENSE = IssueType(
    "c92b8c51-b0bb-464d-98fd-03b9d74d37be", "Missing LICENSE file"
)
E_MISSING_CLA = IssueType("9438a917-3202-42ad-ba34-7723dc477a45", "Missing CLA file")
E_MISSING_CLA_SIMPLE = IssueType(
    "e9908e2a-16df-4149-96c4-f48603978f5e", "Missing CLA explanations file"
)
E_MISSING_GITIGNORE = IssueType(
    "9156d9e0-a4fc-40eb-82e0-26fc22391e8f", "Missing .gitignore file"
)


class GenericProjectStructureCheck(ProjectCheck):
    """
    A check for project files, ensuring they are in the correct format and location.
    """

    def check(self, path: Path, project: Any) -> List[Issue]:
        issues = []

        readme_path = path / "README.md"

        if not readme_path.exists():
            issues.append(E_MISSING_README.at(path))
        else:
            with open(readme_path, "r") as f:
                readme_content = f.read()

                if '<img src=".banner.png"/>' not in readme_content:
                    issues.append(E_README_NO_BANNER.at(readme_path))
                if '<img src="https://img.shields.io' not in readme_content:
                    issues.append(E_README_NO_BADGES.at(readme_path))
                if "## 🚀 Installation" not in readme_content:
                    issues.append(E_README_NO_INSTALL.at(readme_path))
                if "## 🚀 Usage" not in readme_content:
                    issues.append(E_README_NO_USAGE.at(readme_path))
                if "## Licensing" not in readme_content:
                    issues.append(E_README_NO_LICENSE.at(readme_path))
                if "## Contributing" not in readme_content:
                    issues.append(E_README_NO_CONTRIBUTING.at(readme_path))

        if not (path / "LICENSE").exists() and not (path / "LICENSE.md").exists():
            issues.append(E_MISSING_LICENSE.at(path))
        if not (path / "CLA.md").exists():
            issues.append(E_MISSING_CLA.at(path))
        if not (path / "CLA_EXPLANATIONS.md").exists():
            issues.append(E_MISSING_CLA_SIMPLE.at(path))
        if not (path / ".gitignore").exists():
            issues.append(E_MISSING_GITIGNORE.at(path))

        return issues
