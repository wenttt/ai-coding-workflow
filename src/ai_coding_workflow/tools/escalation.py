"""Operation log writing + escalation management.

Two responsibilities:

1. write_operation_log — the canonical way for skills to record what they did.
   Skills MUST call this once per invocation (via the Agent) before returning.

2. escalate — when the 3-strike limit is hit, write the ESCALATED log and
   optionally post a PR/Jira comment so a human gets notified.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..config import Config
from ..state import operation_log, retry_tracker


def register(mcp: FastMCP, config: Config) -> None:
    @mcp.tool()
    def write_operation_log(
        jira_key: str,
        stage: str,
        skill_invoked: str,
        agent: str,
        status: str,
        what_was_done: str,
        impact: str,
        what_i_could_not_do: str,
        engineering_decisions: str,
        next_step: str,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        retry_context: dict[str, Any] | None = None,
        duration_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Write an operation log file. Returns the relative path written.

        See docs/OPERATION_LOG_SCHEMA.md for the full schema and conventions.
        """
        if status not in {"completed", "failed", "escalated"}:
            raise ValueError(
                f"status must be 'completed' | 'failed' | 'escalated', got {status!r}"
            )

        body_sections = {
            "what_was_done": what_was_done,
            "impact": impact,
            "what_i_could_not_do": what_i_could_not_do,
            "engineering_decisions": engineering_decisions,
            "next_step": next_step,
        }

        path = operation_log.write_log(
            config.operation_log_root,
            jira_key=jira_key,
            stage=stage,
            skill_invoked=skill_invoked,
            agent=agent,
            status=status,
            inputs=inputs,
            outputs=outputs,
            retry_context=retry_context,
            duration_seconds=duration_seconds,
            body_sections=body_sections,
        )
        return {
            "path": str(path.relative_to(config.workspace_path)),
            "absolute_path": str(path),
        }

    @mcp.tool()
    def get_retry_count(jira_key: str, stage: str) -> dict[str, Any]:
        """Return current retry status for (jira_key, stage)."""
        status = retry_tracker.compute_retry_status(
            config.operation_log_root,
            jira_key,
            stage,
            config.max_retries_per_stage,
        )
        return {
            "jira_key": status.jira_key,
            "stage": status.stage,
            "attempts_so_far": status.attempts_so_far,
            "is_escalated": status.is_escalated,
            "can_retry": status.can_retry,
            "next_revision_if_retried": status.next_revision_if_retried,
            "max_retries": config.max_retries_per_stage,
        }

    @mcp.tool()
    def should_escalate(jira_key: str, stage: str) -> bool:
        """Return True if attempting another retry would exceed the limit."""
        status = retry_tracker.compute_retry_status(
            config.operation_log_root,
            jira_key,
            stage,
            config.max_retries_per_stage,
        )
        return retry_tracker.should_escalate(status, config.max_retries_per_stage)

    @mcp.tool()
    def escalate(
        jira_key: str,
        stage: str,
        skill_invoked: str,
        agent: str,
        reason: str,
        attempts_summary: str,
        what_humans_need_to_decide: str,
        notify_pr_number: int | None = None,
    ) -> dict[str, Any]:
        """Write an ESCALATED operation log + optionally notify on a PR.

        After this is written, the workflow_state inference returns is_escalated=True
        for this stage and can_retry=False. The Agent must stop auto-retrying.
        """
        # Write the escalated log
        body = (
            f"Stage `{stage}` exceeded the retry limit "
            f"({config.max_retries_per_stage}). Auto-retry is now disabled "
            f"for this stage on this ticket."
        )

        path = operation_log.write_log(
            config.operation_log_root,
            jira_key=jira_key,
            stage=stage,
            skill_invoked=skill_invoked,
            agent=agent,
            status="escalated",
            escalation_reason=reason,
            body_sections={
                "what_was_done": body,
                "impact": "Pipeline halted on this ticket.",
                "what_i_could_not_do": (
                    "Resolve the rejection / failure within retry budget. "
                    "Details:\n\n" + reason
                ),
                "engineering_decisions": "Stopped to avoid burning more attempts.",
                "next_step": (
                    "Human action required:\n\n" + what_humans_need_to_decide
                    + "\n\nHistory of attempts:\n\n" + attempts_summary
                ),
            },
        )

        # Notify on PR if requested. (Defer the actual GitHub call to avoid
        # cross-tool import cycles — the Agent can call add_pr_comment afterward.)
        notification = {
            "notified_pr": notify_pr_number,
            "suggested_pr_comment": (
                f"⚠️ AI Coding Workflow escalated **{stage}** for `{jira_key}` "
                f"after {config.max_retries_per_stage} attempts. "
                f"See operation log: `{path.relative_to(config.workspace_path)}`. "
                f"Human review required.\n\n"
                f"**Reason**: {reason}"
            ),
        }

        return {
            "log_path": str(path.relative_to(config.workspace_path)),
            "notification": notification,
        }
