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
    """Build a Jira API client.

    Two modes:

    - Cloud (default, JIRA_CLOUD=true): atlassian.net hosting. Auth is
      `username=email + password=API_token` (the API token from
      id.atlassian.com).

    - Server / Data Center (JIRA_CLOUD=false): self-hosted enterprise Jira.
      Auth is a Personal Access Token (PAT) via Bearer header. The
      JIRA_API_TOKEN env var holds the PAT; JIRA_EMAIL is unused but kept
      for diagnostic display.
    """
    if config.jira_cloud:
        return Jira(
            url=config.jira_base_url,
            username=config.jira_email,
            password=config.jira_api_token,
            cloud=True,
        )
    # Self-hosted Jira Server / Data Center — Bearer token auth
    return Jira(
        url=config.jira_base_url,
        token=config.jira_api_token,
        cloud=False,
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

    key = issue.get("key", "")
    project_key = key.split("-", 1)[0].upper() if "-" in key else key.upper()

    parent = fields.get("parent") or {}
    parent_key = parent.get("key") if parent else None

    return {
        "key": key,
        "project_key": project_key,
        "parent_key": parent_key,
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
        "url": f"{issue.get('self', '').split('/rest/')[0]}/browse/{key}"
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
        include_project_routing: bool = True,
    ) -> list[dict[str, Any]]:
        """List Jira tickets assigned to a user, across all projects.

        Args:
            assignee_email: defaults to the configured JIRA_EMAIL.
            status: Jira status filter; pass None for any status.
            limit: max tickets to return.
            include_project_routing: if True (default) and project_mapping is
                configured, each ticket's response includes routing info
                (target repo, target workspace, whether current workspace matches).

        Returns each ticket with: key, project_key, parent_key, summary,
        ticket_type, status, labels, components, assignee, url, plus when
        routing is enabled: project_routing dict with repo, workspace,
        current_workspace_match, source.
        """
        assignee = assignee_email or config.jira_email
        client = _client(config)
        jql_parts = [f'assignee = "{assignee}"']
        if status:
            jql_parts.append(f'status = "{status}"')
        jql_parts.append("ORDER BY updated DESC")
        jql = " AND ".join(jql_parts[:-1]) + " " + jql_parts[-1]
        result = client.jql(jql, limit=limit)

        tickets = [_summarize_issue(i) for i in result.get("issues", [])]

        if include_project_routing:
            # Lazy import to avoid cycle
            from .project_routing import _project_key_from_jira_key, _resolve
            from pathlib import Path

            current_ws = config.workspace_path.resolve()
            for t in tickets:
                project_key = t.get("project_key") or _project_key_from_jira_key(t["key"])
                routing = _resolve(config, project_key)
                expected_ws = Path(routing["workspace_path"]).resolve()
                t["project_routing"] = {
                    "project_key": project_key,
                    "github_owner": routing["github_owner"],
                    "github_repo": routing["github_repo"],
                    "workspace_path": str(expected_ws),
                    "current_workspace_match": expected_ws == current_ws,
                    "source": routing["source"],
                }

        return tickets

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
