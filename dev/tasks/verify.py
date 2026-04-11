from __future__ import annotations

import json
from dataclasses import dataclass

from dev.messages import accent, heading


@dataclass(frozen=True)
class VerifyWorkflow:
    id: str
    summary: str


_VERIFY_WORKFLOWS = (
    VerifyWorkflow("docs", "Run documentation verification workflows."),
    VerifyWorkflow("release", "Verify release readiness for publishable projects."),
    VerifyWorkflow("security", "Run opt-in external security tooling."),
)


def verify_workflow_ids() -> tuple[str, ...]:
    return tuple(workflow.id for workflow in _VERIFY_WORKFLOWS)


def list_verify_workflows(*, json_output: bool = False) -> int:
    if json_output:
        print(
            json.dumps(
                {
                    "workflows": [
                        {
                            "id": workflow.id,
                            "summary": workflow.summary,
                        }
                        for workflow in _VERIFY_WORKFLOWS
                    ]
                },
                indent=2,
            )
        )
        return 0

    print(heading("Available verification workflows:"))
    for workflow in _VERIFY_WORKFLOWS:
        print(f"  {accent(workflow.id)}  {workflow.summary}")
    return 0


__all__ = ["list_verify_workflows", "verify_workflow_ids"]
