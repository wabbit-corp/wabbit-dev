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
* [ ] Check consistency of Github metadata with project files: Ensure that the repository name,
      description, topics/tags, and homepage URL on GitHub align with the information provided
      in the project's README and metadata files.
"""

from pathlib import Path

# Import necessary components from your base framework
# (Adjust the import path if necessary)
from dev.checks.base import (
    Issue,
    IssueType,
    ProjectCheck,
)
from dev.config import Project

E_MISSING_README = IssueType("E_MISSING_README", "Missing README file")
E_README_NO_BANNER = IssueType("E_README_NO_BANNER", "README file does not contain a project banner")
E_README_NO_BADGES = IssueType("E_README_NO_BADGES", "README file does not contain badges")
E_README_NO_INSTALL = IssueType("E_README_NO_INSTALL", "README file does not contain installation instructions")
E_README_NO_USAGE = IssueType("E_README_NO_USAGE", "README file does not contain usage instructions")
E_README_NO_LICENSE = IssueType("E_README_NO_LICENSE", "README file does not contain license information")
E_README_NO_CONTRIBUTING = IssueType(
    "E_README_NO_CONTRIBUTING", "README file does not contain contributing instructions"
)
E_MISSING_LICENSE = IssueType("E_MISSING_LICENSE", "Missing LICENSE file")
E_MISSING_CLA = IssueType("E_MISSING_CLA", "Missing CLA file")
E_MISSING_CLA_SIMPLE = IssueType("E_MISSING_CLA_SIMPLE", "Missing CLA explanations file")
E_MISSING_GITIGNORE = IssueType("E_MISSING_GITIGNORE", "Missing .gitignore file")


class GenericProjectStructureCheck(ProjectCheck):
    """
    A check for project files, ensuring they are in the correct format and location.
    """

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        issues: list[Issue] = []

        readme_path = path / "README.md"

        if not readme_path.exists():
            issues.append(E_MISSING_README.at(path))
        else:
            with open(readme_path, encoding="utf-8") as f:
                readme_content = f.read()

                if '<img src=".banner.png"/>' not in readme_content:
                    issues.append(E_README_NO_BANNER.at(readme_path))
                badges_marker = '<img src="https://img.shields.io'  # check:ignore E_HARDCODED_URL
                if badges_marker not in readme_content:
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
        if not (path / "legal" / "cla" / "v1.0.0" / "CLA.md").exists():
            issues.append(E_MISSING_CLA.at(path))
        if not (path / "legal" / "cla" / "v1.0.0" / "CLA_EXPLANATIONS.md").exists():
            issues.append(E_MISSING_CLA_SIMPLE.at(path))
        if not (path / ".gitignore").exists():
            issues.append(E_MISSING_GITIGNORE.at(path))

        return issues


__all__ = [
    "E_MISSING_README",
    "E_README_NO_BANNER",
    "E_README_NO_BADGES",
    "E_README_NO_INSTALL",
    "E_README_NO_USAGE",
    "E_README_NO_LICENSE",
    "E_README_NO_CONTRIBUTING",
    "E_MISSING_LICENSE",
    "E_MISSING_CLA",
    "E_MISSING_CLA_SIMPLE",
    "E_MISSING_GITIGNORE",
    "GenericProjectStructureCheck",
]
