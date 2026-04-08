from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, IssueType, ProjectCheck, Severity
from dev.config import GradleProject, Project, load_config
from dev.kmp_target_suggestions import find_kmp_target_expansion_suggestions

E_KMP_POSSIBLE_MISSING_TARGET = IssueType(
    "E_KMP_POSSIBLE_MISSING_TARGET",
    "Project may be able to add KMP target {platform}: {supporting_dependencies} already support it, "
    "newly activated source sets have no Kotlin sources ({source_sets}).",
    severity=Severity.WARNING,
)


class KmpTargetExpansionCheck(ProjectCheck):
    """Suggests missing KMP targets that look likely to work from current dependency and source-set shape."""

    order = 220

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if not isinstance(project, GradleProject) or not project.is_kmp:
            return []

        config = load_config()
        issues: list[Issue] = []
        for suggestion in find_kmp_target_expansion_suggestions(project, config):
            issues.append(
                E_KMP_POSSIBLE_MISSING_TARGET.make(
                    platform=suggestion.platform,
                    supporting_dependencies=", ".join(suggestion.supporting_dependencies),
                    source_sets=", ".join(suggestion.newly_activated_source_sets),
                ).at(path)
            )
        return issues


__all__ = [
    "E_KMP_POSSIBLE_MISSING_TARGET",
    "KmpTargetExpansionCheck",
]
