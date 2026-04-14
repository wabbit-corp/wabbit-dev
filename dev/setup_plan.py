from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import dev.io


class SetupPlanKind(Enum):
    REPLACE_TEXT = "replace-text"
    ENSURE_TEXT_IF_MISSING = "ensure-text-if-missing"
    REPLACE_FILE = "replace-file"
    COPY_FILE = "copy-file"
    DELETE_PATH = "delete-path"
    MERGE_WORD_LIST = "merge-word-list"


class SetupPlanCategory(Enum):
    BUILD = "build"
    GUIDANCE = "guidance"
    LEGAL = "legal"
    METADATA = "metadata"
    WORKFLOW = "workflow"
    ASSET = "asset"
    DOCS = "docs"


class SetupPlanOwnership(Enum):
    MANAGED_FILE = "managed-file"
    MANAGED_BLOCK = "managed-block"
    GENERATED_ASSET = "generated-asset"
    LOCAL_ONLY = "local-only"


@dataclass(frozen=True)
class SetupPlanOperation:
    kind: SetupPlanKind
    repo_root: Path
    path: Path
    category: SetupPlanCategory
    ownership: SetupPlanOwnership
    source_path: Path | None = None

    def relative_path(self) -> str:
        return self.path.resolve().relative_to(self.repo_root.resolve()).as_posix()


@dataclass
class SetupPlan:
    operations: list[SetupPlanOperation] = field(default_factory=list)

    def record(
        self,
        *,
        kind: SetupPlanKind,
        repo_root: Path,
        path: Path,
        category: SetupPlanCategory,
        ownership: SetupPlanOwnership,
        source_path: Path | None = None,
    ) -> None:
        self.operations.append(
            SetupPlanOperation(
                kind=kind,
                repo_root=repo_root.resolve(),
                path=path.resolve(),
                category=category,
                ownership=ownership,
                source_path=None if source_path is None else source_path.resolve(),
            )
        )

    def replace_text(
        self,
        *,
        repo_root: Path,
        path: Path,
        content: str,
        category: SetupPlanCategory,
        ownership: SetupPlanOwnership,
    ) -> None:
        self.record(
            kind=SetupPlanKind.REPLACE_TEXT,
            repo_root=repo_root,
            path=path,
            category=category,
            ownership=ownership,
        )
        dev.io.write_text_file(path, content)

    def ensure_text_if_missing(
        self,
        *,
        repo_root: Path,
        path: Path,
        content: str,
        category: SetupPlanCategory,
        ownership: SetupPlanOwnership,
    ) -> bool:
        if not dev.io.write_text_file_if_missing(path, content):
            return False
        self.record(
            kind=SetupPlanKind.ENSURE_TEXT_IF_MISSING,
            repo_root=repo_root,
            path=path,
            category=category,
            ownership=ownership,
        )
        return True

    def replace_file(
        self,
        *,
        repo_root: Path,
        path: Path,
        category: SetupPlanCategory,
        ownership: SetupPlanOwnership,
        apply: Callable[[], None],
    ) -> None:
        self.record(
            kind=SetupPlanKind.REPLACE_FILE,
            repo_root=repo_root,
            path=path,
            category=category,
            ownership=ownership,
        )
        apply()

    def copy_file(
        self,
        *,
        repo_root: Path,
        source_path: Path,
        destination_path: Path,
        category: SetupPlanCategory,
        ownership: SetupPlanOwnership,
    ) -> None:
        self.record(
            kind=SetupPlanKind.COPY_FILE,
            repo_root=repo_root,
            path=destination_path,
            category=category,
            ownership=ownership,
            source_path=source_path,
        )
        dev.io.copy(source_path, destination_path)

    def delete_path(
        self,
        *,
        repo_root: Path,
        path: Path,
        category: SetupPlanCategory,
        ownership: SetupPlanOwnership,
    ) -> None:
        if not path.exists():
            return
        self.record(
            kind=SetupPlanKind.DELETE_PATH,
            repo_root=repo_root,
            path=path,
            category=category,
            ownership=ownership,
        )
        dev.io.delete_if_exists(path)

    def merge_word_list(
        self,
        *,
        repo_root: Path,
        path: Path,
        words: list[str],
        category: SetupPlanCategory,
        ownership: SetupPlanOwnership,
    ) -> bool:
        if not dev.io.merge_word_list_file(path, words):
            return False
        self.record(
            kind=SetupPlanKind.MERGE_WORD_LIST,
            repo_root=repo_root,
            path=path,
            category=category,
            ownership=ownership,
        )
        return True

    def planned_paths_for_repo(
        self,
        repo_root: Path,
        *,
        include_local_only: bool = False,
    ) -> frozenset[str]:
        resolved_repo_root = repo_root.resolve()
        planned_paths: set[str] = set()
        for operation in self.operations:
            if operation.repo_root != resolved_repo_root:
                continue
            if not include_local_only and operation.ownership == SetupPlanOwnership.LOCAL_ONLY:
                continue
            planned_paths.add(operation.relative_path())
        return frozenset(planned_paths)

    def local_only_paths_for_repo(self, repo_root: Path) -> frozenset[str]:
        resolved_repo_root = repo_root.resolve()
        return frozenset(
            operation.relative_path()
            for operation in self.operations
            if operation.repo_root == resolved_repo_root and operation.ownership == SetupPlanOwnership.LOCAL_ONLY
        )


__all__ = [
    "SetupPlan",
    "SetupPlanCategory",
    "SetupPlanKind",
    "SetupPlanOperation",
    "SetupPlanOwnership",
]
