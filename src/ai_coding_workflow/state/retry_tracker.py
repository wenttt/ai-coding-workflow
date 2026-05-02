"""Retry counting + 3-strike escalation logic.

Retry count for a (ticket, stage) is the number of operation log files for
that stage at the latest sequence. Escalation triggers when a new attempt
would exceed `max_retries_per_stage`.

Escalation = the Agent stops auto-retrying and writes an `-ESCALATED.md`
log. A human needs to step in.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .operation_log import (
    list_logs_for_ticket,
    parse_log_filename,
)


@dataclass
class RetryStatus:
    jira_key: str
    stage: str
    attempts_so_far: int
    is_escalated: bool
    can_retry: bool
    next_revision_if_retried: int


def compute_retry_status(
    operation_log_root: Path,
    jira_key: str,
    stage: str,
    max_retries: int,
) -> RetryStatus:
    """Inspect operation logs and compute retry status for the given stage."""
    paths = list_logs_for_ticket(operation_log_root, jira_key)

    revisions_for_stage: list[int] = []
    is_escalated = False

    for path in paths:
        parsed = parse_log_filename(path.name)
        if parsed is None:
            continue
        _, log_stage, revision, escalated = parsed
        if log_stage != stage:
            continue
        if escalated:
            is_escalated = True
        else:
            revisions_for_stage.append(revision)

    attempts = max(revisions_for_stage) if revisions_for_stage else 0
    can_retry = (not is_escalated) and (attempts < max_retries)

    return RetryStatus(
        jira_key=jira_key,
        stage=stage,
        attempts_so_far=attempts,
        is_escalated=is_escalated,
        can_retry=can_retry,
        next_revision_if_retried=attempts + 1,
    )


def should_escalate(retry_status: RetryStatus, max_retries: int) -> bool:
    """Return True if the next attempt would be the (max_retries + 1)-th."""
    return retry_status.attempts_so_far >= max_retries
