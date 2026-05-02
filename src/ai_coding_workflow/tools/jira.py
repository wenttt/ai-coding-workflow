"""Jira MCP tools.

Read tickets, list tickets, update status, add comments. The Agent uses these
to (a) understand what a ticket is asking for and (b) update the ticket as
the pipeline progresses.

We use atlassian-python-api which works against both Jira Cloud and Self-Hosted.
"""

from __future__ import annotations

from typing import Any

from atlassian import Jira
from fastmcp import FastMCP

from ..config import Config


def _client(config: Config) -> Jira:
    return Jira(
        url=config.jira_base_url,
        username=config.jira_email,
        password=config.jira_api_token,
        cloud=True,  # most common; atlassian-python-api auto-detects in practice
    )


def _summarize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """Reduce a Jira issue payload to what the Agent actually needs."""
    fields = issue.get("fields", {})
    issuetype = (fields.get("issuetype") or {}).get("name", "").lower()
    # Map Jira issuetype names to our canonical ticket_type names
    type_map = {
        "story": "user_story",
        "user story": "user_story",
        "task": "task",
        "sub-task": "sub_task",
        "subtask": "sub_task",
        "epic": "epic",
        "bug": "task",  # treat bugs as tasks for template purposes
    }
    canonical_type = type_map.get(issuetype, "task")

    return {
        "key": issue.get("key"),
        "summary": fields.get("summary", ""),
        "description": fields.get("description") or "",
        "status": (fields.get("status") or {}).get("name", ""),
        "ticket_type": canonical_type,
        "raw_issuetype": issuetype,
        "labels": fields.get("labels") or [],
        "assignee": ((fields.get("assignee") or {}).get("emailAddress")
                     or (fields.get("assignee") or {}).get("displayName")),
        "reporter": ((fields.get("reporter") or {}).get("emailAddress")
                     or (fields.get("reporter") or {}).get("displayName")),
        "priority": (fields.get("priority") or {}).get("name"),
        "components": [c.get("name") for c in (fields.get("components") or [])],
        "linked_issues": [
            link.get("outwardIssue", link.get("inwardIssue", {})).get("key")
            for link in (fields.get("issuelinks") or [])
        ],
        "url": f"{issue.get('self', '').split('/rest/')[0]}/browse/{issue.get('key')}"
        if issue.get("self") else None,
    }


def register(mcp: FastMCP, config: Config) -> None:
    @mcp.tool()
    def read_jira_ticket(jira_key: str) -> dict[str, Any]:
        """Read a Jira ticket and return its essential fields.

        Args:
            jira_key: e.g., "PROJ-123"

        Returns:
            A dict with: key, summary, description, status, ticket_type,
            labels, assignee, reporter, priority, components, linked_issues, url.
        """
        client = _client(config)
        issue = client.issue(jira_key)
        return _summarize_issue(issue)

    @mcp.tool()
    def list_my_tickets(
        assignee_email: str | None = None,
        status: str | None = "In Progress",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List Jira tickets assigned to a user.

        Args:
            assignee_email: defaults to the configured JIRA_EMAIL.
            status: Jira status filter; pass None for any status.
            limit: max tickets to return.
        """
        assignee = assignee_email or config.jira_email
        client = _client(config)
        jql_parts = [f'assignee = "{assignee}"']
        if status:
            jql_parts.append(f'status = "{status}"')
        jql_parts.append("ORDER BY updated DESC")
        jql = " AND ".join(jql_parts[:-1]) + " " + jql_parts[-1]
        result = client.jql(jql, limit=limit)
        return [_summarize_issue(i) for i in result.get("issues", [])]

    @mcp.tool()
    def update_jira_status(jira_key: str, target_status: str) -> dict[str, Any]:
        """Transition a Jira ticket to a new status.

        Args:
            jira_key: e.g., "PROJ-123"
            target_status: target status name (must match a transition available
                from the current state, e.g., "In Review", "Done").

        Returns:
            {"key", "previous_status", "new_status"}.
        """
        client = _client(config)
        issue = client.issue(jira_key)
        previous = (issue.get("fields", {}).get("status") or {}).get("name", "")
        client.set_issue_status(jira_key, target_status)
        # Re-read to confirm
        new_issue = client.issue(jira_key)
        new_status = (new_issue.get("fields", {}).get("status") or {}).get("name", "")
        return {
            "key": jira_key,
            "previous_status": previous,
            "new_status": new_status,
        }

    @mcp.tool()
    def add_jira_comment(jira_key: str, body: str) -> dict[str, Any]:
        """Add a comment to a Jira ticket. Used for escalation notifications,
        cross-references to design PRs, etc.
        """
        client = _client(config)
        result = client.issue_add_comment(jira_key, body)
        return {"key": jira_key, "comment_id": result.get("id")}
