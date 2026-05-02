"""Operation log read/write.

Operation logs are the project's audit trail. See docs/OPERATION_LOG_SCHEMA.md
for the full contract.

This module provides:
- write_log(...) — write a new operation log file with the canonical schema
- read_logs_for_ticket(jira_key) — list + parse all logs for a ticket, ordered
- read_log(path) — parse a single log
- next_sequence_number(jira_key, stage) — figure out what NN-stage-vN should be
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .frontmatter import read as fm_read
from .frontmatter import read_operation_log_frontmatter, write as fm_write

# Stage canonical names (must match OPERATION_LOG_SCHEMA.md)
STAGE_NAMES = {
    "design",
    "design-revision",
    "implement",
    "self-review",
    "test-write",
    "test-run",
    "pr-review-fix",
    "deploy",
    "doc-update",
    "investigate",
}

# (NN)-(stage-name)-v(N).md  OR  (NN)-(stage-name)-ESCALATED.md
_LOG_NAME_RE = re.compile(
    r"^(?P<seq>\d{2})-(?P<stage>[a-z][a-z0-9-]*)-(?:v(?P<revision>\d+)|(?P<escalated>ESCALATED))\.md$"
)


@dataclass
class OperationLog:
    """A parsed operation log."""

    path: Path
    sequence: int
    stage: str
    revision: int  # 0 for ESCALATED files
    is_escalated: bool

    frontmatter: dict[str, Any]
    body: str
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return self.frontmatter.get("status", "unknown")

    @property
    def skill_invoked(self) -> str:
        return self.frontmatter.get("skill_invoked", "unknown")


def parse_log_filename(filename: str) -> tuple[int, str, int, bool] | None:
    """Parse a log filename. Returns (seq, stage, revision, is_escalated) or None."""
    m = _LOG_NAME_RE.match(filename)
    if not m:
        return None
    seq = int(m.group("seq"))
    stage = m.group("stage")
    if m.group("escalated"):
        return seq, stage, 0, True
    revision = int(m.group("revision"))
    return seq, stage, revision, False


def _split_body_sections(body: str) -> dict[str, str]:
    """Split a log body into named sections (## headers)."""
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    for line in body.splitlines():
        if line.startswith("## "):
            if current_name is not None:
                sections[current_name] = "\n".join(current_lines).strip()
            current_name = line[3:].strip().lower().replace(" ", "_")
            current_lines = []
        else:
            current_lines.append(line)

    if current_name is not None:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections


def read_log(path: Path) -> OperationLog:
    """Parse a single operation log file."""
    parsed = parse_log_filename(path.name)
    if parsed is None:
        raise ValueError(f"Not a valid operation log filename: {path.name}")
    seq, stage, revision, is_escalated = parsed

    metadata = read_operation_log_frontmatter(path)
    _, body = fm_read(path)
    sections = _split_body_sections(body)

    return OperationLog(
        path=path,
        sequence=seq,
        stage=stage,
        revision=revision,
        is_escalated=is_escalated,
        frontmatter=metadata,
        body=body,
        sections=sections,
    )


def list_logs_for_ticket(operation_log_root: Path, jira_key: str) -> list[Path]:
    """Return ordered (by sequence then revision) list of log file paths for a ticket."""
    ticket_dir = operation_log_root / jira_key
    if not ticket_dir.exists():
        return []

    logs: list[tuple[tuple[int, int, int], Path]] = []
    for entry in ticket_dir.iterdir():
        if not entry.is_file() or not entry.name.endswith(".md"):
            continue
        parsed = parse_log_filename(entry.name)
        if parsed is None:
            continue
        seq, _stage, revision, is_escalated = parsed
        # ESCALATED files sort after vN files at same seq (revision tiebreak via the bool)
        sort_key = (seq, revision if not is_escalated else 999, 1 if is_escalated else 0)
        logs.append((sort_key, entry))

    logs.sort(key=lambda t: t[0])
    return [p for _, p in logs]


def read_logs_for_ticket(operation_log_root: Path, jira_key: str) -> list[OperationLog]:
    """Read and parse all logs for a ticket, in order."""
    return [read_log(p) for p in list_logs_for_ticket(operation_log_root, jira_key)]


def next_sequence_number(operation_log_root: Path, jira_key: str, stage: str) -> int:
    """Next seq number for this (ticket, stage). New stage = max(seen) + 1; same stage continues."""
    paths = list_logs_for_ticket(operation_log_root, jira_key)
    seen_seq_for_stage: int | None = None
    max_seq = 0
    for path in paths:
        parsed = parse_log_filename(path.name)
        if parsed is None:
            continue
        seq, log_stage, _, _ = parsed
        max_seq = max(max_seq, seq)
        if log_stage == stage and seen_seq_for_stage is None:
            seen_seq_for_stage = seq
    if seen_seq_for_stage is not None:
        return seen_seq_for_stage
    return max_seq + 1


def next_revision_number(operation_log_root: Path, jira_key: str, stage: str) -> int:
    """Next revision number for this (ticket, stage). Starts at 1."""
    paths = list_logs_for_ticket(operation_log_root, jira_key)
    max_rev = 0
    for path in paths:
        parsed = parse_log_filename(path.name)
        if parsed is None:
            continue
        _, log_stage, revision, is_escalated = parsed
        if log_stage == stage and not is_escalated:
            max_rev = max(max_rev, revision)
    return max_rev + 1


def build_log_path(
    operation_log_root: Path,
    jira_key: str,
    sequence: int,
    stage: str,
    revision: int | None,
    is_escalated: bool = False,
) -> Path:
    """Build the canonical path for an operation log."""
    if stage not in STAGE_NAMES:
        raise ValueError(f"Unknown stage {stage!r}, must be one of {sorted(STAGE_NAMES)}")
    seq_str = f"{sequence:02d}"
    if is_escalated:
        suffix = "ESCALATED"
    else:
        if revision is None or revision < 1:
            raise ValueError(f"Non-escalated log requires revision >= 1, got {revision}")
        suffix = f"v{revision}"
    return operation_log_root / jira_key / f"{seq_str}-{stage}-{suffix}.md"


def write_log(
    operation_log_root: Path,
    *,
    jira_key: str,
    stage: str,
    skill_invoked: str,
    agent: str,
    status: str,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    retry_context: dict[str, Any] | None = None,
    escalation_reason: str | None = None,
    duration_seconds: float | None = None,
    body_sections: dict[str, str] | None = None,
) -> Path:
    """Write a new operation log. Returns the path written.

    body_sections keys (ordered as in the schema):
      - what_was_done
      - impact
      - what_i_could_not_do
      - engineering_decisions
      - next_step

    If status is 'escalated', the file is named with -ESCALATED suffix and
    revision is omitted. Otherwise it gets the next revision number for
    (jira_key, stage).
    """
    is_escalated = status == "escalated"

    seq = next_sequence_number(operation_log_root, jira_key, stage)
    revision = None if is_escalated else next_revision_number(operation_log_root, jira_key, stage)

    metadata: dict[str, Any] = {
        "jira_key": jira_key,
        "stage": stage,
        "revision": revision if revision is not None else 0,
        "status": status,
        "skill_invoked": skill_invoked,
        "agent": agent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if duration_seconds is not None:
        metadata["duration_seconds"] = duration_seconds
    if inputs is not None:
        metadata["inputs"] = inputs
    if outputs is not None:
        metadata["outputs"] = outputs
    if retry_context is not None:
        metadata["retry_context"] = retry_context
    if escalation_reason is not None:
        metadata["escalation_reason"] = escalation_reason

    body_sections = body_sections or {}
    body = _format_body(body_sections)

    path = build_log_path(
        operation_log_root,
        jira_key,
        seq,
        stage,
        revision,
        is_escalated=is_escalated,
    )
    fm_write(path, metadata, body)
    return path


_SECTION_TITLES = [
    ("what_was_done", "What was done"),
    ("impact", "Impact"),
    ("what_i_could_not_do", "What I could not do"),
    ("engineering_decisions", "Engineering decisions"),
    ("next_step", "Next step"),
]


def _format_body(sections: dict[str, str]) -> str:
    parts: list[str] = []
    for key, title in _SECTION_TITLES:
        content = sections.get(key, "_(none)_")
        parts.append(f"## {title}\n\n{content.strip()}\n")
    return "\n".join(parts)
