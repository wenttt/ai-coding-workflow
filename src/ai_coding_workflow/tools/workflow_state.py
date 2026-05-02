"""Workflow state inference.

The single most important question this server answers:

  "Given Jira ticket X, what stage are we in and what should the Agent do next?"

This tool aggregates source-of-truth signals (Jira status, GitHub PR state,
operation log presence) to infer the answer.

See docs/SKILL_ORCHESTRATION.md for the full decision logic.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..config import Config
from ..state import operation_log, retry_tracker


def register(mcp: FastMCP, config: Config) -> None:
    @mcp.tool()
    def get_workflow_state(
        jira_key: str,
        design_pr_number: int | None = None,
        code_pr_number: int | None = None,
    ) -> dict[str, Any]:
        """Infer the current pipeline stage and next action for a Jira ticket.

        Args:
            jira_key: e.g., "PROJ-123"
            design_pr_number: optional, if you already know the design PR number
            code_pr_number: optional, if you already know the code PR number

        Returns:
            current_stage, stage_status, retry_count, can_retry,
            is_escalated, next_action, recommended_skill, blockers,
            relevant_paths.

        next_action is a free-form string the Agent uses to decide what to do.
        Common values:
          - "create_design"
          - "wait_for_review"
          - "revise_design"
          - "trigger_implementation"
          - "self_review"
          - "write_tests"
          - "run_tests"
          - "fix_failing_tests"
          - "open_code_pr"
          - "address_review"
          - "deploy"
          - "update_docs"
          - "close_ticket"
          - "escalated"

        The Agent then uses get_skill_chain_for_stage(jira_key, stage) to
        pick the actual skill to invoke.
        """
        operation_log_root = config.operation_log_root
        logs = operation_log.read_logs_for_ticket(operation_log_root, jira_key)

        # Compute retry status for each stage we've seen
        stages_seen: set[str] = {log.stage for log in logs}
        retry_status_per_stage = {
            stage: retry_tracker.compute_retry_status(
                operation_log_root, jira_key, stage, config.max_retries_per_stage
            )
            for stage in stages_seen
        }

        # Find the highest-numbered (most recent) operation log
        latest = logs[-1] if logs else None

        any_escalated = any(s.is_escalated for s in retry_status_per_stage.values())

        # Default: nothing has happened, we're at design stage
        if not logs:
            return {
                "current_stage": "design",
                "stage_status": "pending",
                "retry_count": 0,
                "can_retry": True,
                "is_escalated": False,
                "next_action": "create_design",
                "recommended_skill_key": "design.brownfield_or_greenfield_decided_at_runtime",
                "blockers": [],
                "relevant_paths": [],
                "latest_log": None,
            }

        # If anything is escalated, surface that immediately
        if any_escalated:
            escalated_stage = next(
                s.stage for s in retry_status_per_stage.values() if s.is_escalated
            )
            return {
                "current_stage": escalated_stage,
                "stage_status": "escalated",
                "retry_count": retry_status_per_stage[escalated_stage].attempts_so_far,
                "can_retry": False,
                "is_escalated": True,
                "next_action": "escalated",
                "recommended_skill_key": None,
                "blockers": [
                    f"Stage {escalated_stage} hit retry limit "
                    f"({retry_status_per_stage[escalated_stage].attempts_so_far} attempts). "
                    f"Human intervention required."
                ],
                "relevant_paths": [
                    str(log.path.relative_to(config.workspace_path))
                    for log in logs if log.stage == escalated_stage
                ],
                "latest_log": str(latest.path.relative_to(config.workspace_path))
                if latest else None,
            }

        # Normal flow: figure out what's next based on latest stage
        latest_stage = latest.stage
        latest_status = latest.status
        retry_status = retry_status_per_stage.get(latest_stage)

        next_action, next_stage, recommended_key, blockers = _infer_next(
            latest_stage, latest_status, retry_status, design_pr_number, code_pr_number
        )

        return {
            "current_stage": next_stage,
            "stage_status": latest_status,
            "retry_count": retry_status.attempts_so_far if retry_status else 0,
            "can_retry": retry_status.can_retry if retry_status else True,
            "is_escalated": False,
            "next_action": next_action,
            "recommended_skill_key": recommended_key,
            "blockers": blockers,
            "relevant_paths": [
                str(log.path.relative_to(config.workspace_path))
                for log in logs[-3:]
            ],
            "latest_log": str(latest.path.relative_to(config.workspace_path)),
        }


def _infer_next(
    latest_stage: str,
    latest_status: str,
    retry_status: Any,
    design_pr_number: int | None,
    code_pr_number: int | None,
) -> tuple[str, str, str | None, list[str]]:
    """Return (next_action, next_stage, recommended_skill_key, blockers).

    Decision rules — kept simple and readable. Refine with real usage data.
    """
    # Design stage outcomes
    if latest_stage == "design":
        if latest_status == "completed":
            # Design written; waiting for review on the PR
            return ("wait_for_review", "design", None,
                    ["Awaiting review on design PR"])
        if latest_status == "failed":
            return ("revise_design", "design-revision", "design.revision",
                    [])

    if latest_stage == "design-revision":
        if latest_status == "completed":
            return ("wait_for_review", "design-revision", None,
                    ["Awaiting review on revised design PR"])

    # If design appears done (regardless of which sub-stage), move to implement
    # In practice, the user signals approval by invoking the next stage explicitly
    # or design PR review_decision goes to "approved" — Agent reads it.

    if latest_stage == "implement":
        if latest_status == "completed":
            return ("self_review", "self-review", "self_review.primary",
                    [])
        if latest_status == "failed":
            return ("retry_implement", "implement", "implement.sub_mode_of_ticket",
                    [])

    if latest_stage == "self-review":
        if latest_status == "completed":
            return ("write_tests", "test-write", "test.write",
                    [])

    if latest_stage == "test-write":
        if latest_status == "completed":
            return ("run_tests", "test-run", "test.run",
                    [])

    if latest_stage == "test-run":
        if latest_status == "completed":
            return ("open_code_pr", "implement", None,
                    ["All tests passing; ready to open code PR for human review"])
        if latest_status == "failed":
            return ("fix_failing_tests", "test-run", "test.run",
                    [])

    if latest_stage == "pr-review-fix":
        if latest_status == "completed":
            return ("wait_for_review", "pr-review-fix", None,
                    ["Awaiting re-review after addressing comments"])

    if latest_stage == "deploy":
        if latest_status == "completed":
            return ("update_docs", "doc-update", "post_deploy.primary",
                    [])

    if latest_stage == "doc-update":
        if latest_status == "completed":
            return ("close_ticket", "doc-update", None,
                    ["Pipeline complete. Update Jira to Closed."])

    # Fallback: not enough info, ask Agent to decide
    return (
        "indeterminate",
        latest_stage,
        None,
        [f"Cannot infer next action from stage={latest_stage} status={latest_status}; "
         f"Agent should ask user."],
    )
