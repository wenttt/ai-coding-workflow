"""Tests for state management — operation logs, retry tracking, frontmatter.

These are the riskiest pieces of the codebase: filename parsing, retry
counting, and YAML round-tripping. Bugs here would silently corrupt the
audit trail or miscount retries (causing premature escalation or
escalation that should have happened but didn't).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_coding_workflow.state import frontmatter as fm
from ai_coding_workflow.state import operation_log, retry_tracker


# --- frontmatter ---------------------------------------------------------

def test_frontmatter_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "design.md"
    metadata = {
        "jira_key": "PROJ-1",
        "mode": "brownfield",
        "ticket_type": "user_story",
        "ac": ["First AC", "Second AC"],
    }
    body = "# Design\n\nBody content."
    fm.write(path, metadata, body)

    parsed_meta, parsed_body = fm.read(path)
    assert parsed_meta == metadata
    assert "Body content." in parsed_body


def test_design_frontmatter_validates_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "design.md"
    fm.write(path, {"jira_key": "PROJ-1"}, "body")
    with pytest.raises(fm.FrontmatterError):
        fm.read_design_frontmatter(path)


def test_design_frontmatter_validates_mode(tmp_path: Path) -> None:
    path = tmp_path / "design.md"
    fm.write(path, {
        "jira_key": "PROJ-1",
        "mode": "invalid_mode",
        "ticket_type": "task",
    }, "body")
    with pytest.raises(fm.FrontmatterError, match="mode"):
        fm.read_design_frontmatter(path)


# --- operation log filenames --------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("01-design-v1.md", (1, "design", 1, False)),
    ("02-design-revision-v3.md", (2, "design-revision", 3, False)),
    ("06-test-run-ESCALATED.md", (6, "test-run", 0, True)),
    ("99-doc-update-v10.md", (99, "doc-update", 10, False)),
])
def test_parse_log_filename(name: str, expected: tuple[int, str, int, bool]) -> None:
    assert operation_log.parse_log_filename(name) == expected


@pytest.mark.parametrize("bad", [
    "design-v1.md",          # missing seq
    "1-design-v1.md",         # seq not 2-digit
    "01-design.md",           # missing version suffix
    "01-design-v1.txt",       # wrong extension
    "01-Design-v1.md",        # uppercase stage
    "01-design-version1.md",  # wrong version format
])
def test_parse_log_filename_rejects_invalid(bad: str) -> None:
    assert operation_log.parse_log_filename(bad) is None


# --- operation log writing + reading ------------------------------------

def test_write_log_creates_canonical_filename(tmp_path: Path) -> None:
    path = operation_log.write_log(
        tmp_path,
        jira_key="PROJ-1",
        stage="design",
        skill_invoked="mcp-design-brownfield",
        agent="claude-code",
        status="completed",
        body_sections={
            "what_was_done": "Wrote design",
            "impact": "Added 1 file",
            "what_i_could_not_do": "_(none)_",
            "engineering_decisions": "Picked user_story template",
            "next_step": "Wait for review",
        },
    )
    assert path.name == "01-design-v1.md"
    assert path.parent.name == "PROJ-1"
    assert path.exists()

    # Round-trip
    log = operation_log.read_log(path)
    assert log.frontmatter["jira_key"] == "PROJ-1"
    assert log.frontmatter["status"] == "completed"
    assert "Wrote design" in log.sections["what_was_done"]


def test_subsequent_revisions_increment(tmp_path: Path) -> None:
    common: dict = dict(
        jira_key="PROJ-1",
        stage="design",
        skill_invoked="mcp-design-brownfield",
        agent="claude-code",
        status="completed",
        body_sections={
            "what_was_done": "x",
            "impact": "x",
            "what_i_could_not_do": "x",
            "engineering_decisions": "x",
            "next_step": "x",
        },
    )
    p1 = operation_log.write_log(tmp_path, **common)
    p2 = operation_log.write_log(tmp_path, **common)
    p3 = operation_log.write_log(tmp_path, **common)
    assert p1.name == "01-design-v1.md"
    assert p2.name == "01-design-v2.md"
    assert p3.name == "01-design-v3.md"


def test_new_stage_increments_sequence(tmp_path: Path) -> None:
    common: dict = dict(
        jira_key="PROJ-1",
        skill_invoked="x",
        agent="claude-code",
        status="completed",
        body_sections={
            "what_was_done": "x", "impact": "x",
            "what_i_could_not_do": "x", "engineering_decisions": "x",
            "next_step": "x",
        },
    )
    p1 = operation_log.write_log(tmp_path, stage="design", **common)
    p2 = operation_log.write_log(tmp_path, stage="implement", **common)
    p3 = operation_log.write_log(tmp_path, stage="implement", **common)
    p4 = operation_log.write_log(tmp_path, stage="self-review", **common)
    assert p1.name == "01-design-v1.md"
    assert p2.name == "02-implement-v1.md"
    assert p3.name == "02-implement-v2.md"
    assert p4.name == "03-self-review-v1.md"


def test_escalated_log_uses_escalated_suffix(tmp_path: Path) -> None:
    path = operation_log.write_log(
        tmp_path,
        jira_key="PROJ-1",
        stage="test-run",
        skill_invoked="mcp-test-run",
        agent="claude-code",
        status="escalated",
        escalation_reason="3 attempts failed",
        body_sections={
            "what_was_done": "x", "impact": "x",
            "what_i_could_not_do": "x", "engineering_decisions": "x",
            "next_step": "x",
        },
    )
    assert path.name.endswith("-ESCALATED.md")


def test_unknown_stage_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown stage"):
        operation_log.write_log(
            tmp_path,
            jira_key="PROJ-1",
            stage="bogus-stage",
            skill_invoked="x",
            agent="x",
            status="completed",
            body_sections={
                "what_was_done": "x", "impact": "x",
                "what_i_could_not_do": "x", "engineering_decisions": "x",
                "next_step": "x",
            },
        )


# --- retry tracker ------------------------------------------------------

def _write_log(tmp_path: Path, stage: str, status: str = "completed") -> None:
    operation_log.write_log(
        tmp_path,
        jira_key="PROJ-1",
        stage=stage,
        skill_invoked="x",
        agent="claude-code",
        status=status,
        body_sections={
            "what_was_done": "x", "impact": "x",
            "what_i_could_not_do": "x", "engineering_decisions": "x",
            "next_step": "x",
        },
    )


def test_retry_status_no_logs(tmp_path: Path) -> None:
    status = retry_tracker.compute_retry_status(tmp_path, "PROJ-1", "design", max_retries=3)
    assert status.attempts_so_far == 0
    assert status.is_escalated is False
    assert status.can_retry is True
    assert status.next_revision_if_retried == 1


def test_retry_status_after_one_attempt(tmp_path: Path) -> None:
    _write_log(tmp_path, "design")
    status = retry_tracker.compute_retry_status(tmp_path, "PROJ-1", "design", max_retries=3)
    assert status.attempts_so_far == 1
    assert status.can_retry is True
    assert status.next_revision_if_retried == 2


def test_retry_status_at_limit(tmp_path: Path) -> None:
    _write_log(tmp_path, "design")
    _write_log(tmp_path, "design")
    _write_log(tmp_path, "design")
    status = retry_tracker.compute_retry_status(tmp_path, "PROJ-1", "design", max_retries=3)
    assert status.attempts_so_far == 3
    assert status.can_retry is False  # 3 attempts already; next would be #4
    assert retry_tracker.should_escalate(status, max_retries=3) is True


def test_retry_status_escalated_blocks_retries(tmp_path: Path) -> None:
    _write_log(tmp_path, "design")
    _write_log(tmp_path, "design", status="escalated")
    status = retry_tracker.compute_retry_status(tmp_path, "PROJ-1", "design", max_retries=3)
    assert status.is_escalated is True
    assert status.can_retry is False
