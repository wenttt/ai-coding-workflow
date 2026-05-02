"""GitHub MCP tools.

PR lifecycle: create, push, read state, list comments. The Agent uses these
to drive the design-review and code-review loops.

We do NOT trigger Copilot Coding Agent directly here — that's a Stage 2
concern handled in tools/git.py via creating a properly-formatted issue.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from github import Auth, Github
from github.Repository import Repository

from ..config import Config


def _gh(config: Config) -> Github:
    return Github(auth=Auth.Token(config.github_token))


def _resolve_repo(config: Config, owner: str | None, repo: str | None) -> Repository:
    o = owner or config.github_default_owner
    r = repo or config.github_default_repo
    if not o or not r:
        raise ValueError(
            "GitHub owner and repo must be specified, either explicitly or via "
            "GITHUB_DEFAULT_OWNER/GITHUB_DEFAULT_REPO env vars."
        )
    return _gh(config).get_repo(f"{o}/{r}")


def _summarize_pr(pr: Any) -> dict[str, Any]:
    return {
        "number": pr.number,
        "title": pr.title,
        "body": pr.body or "",
        "state": pr.state,  # "open" | "closed"
        "merged": pr.merged,
        "mergeable": pr.mergeable,
        "draft": pr.draft,
        "head_ref": pr.head.ref,
        "base_ref": pr.base.ref,
        "author": pr.user.login,
        "url": pr.html_url,
        "labels": [lbl.name for lbl in pr.get_labels()],
        "review_decision": _get_review_decision(pr),
    }


def _get_review_decision(pr: Any) -> str:
    """Aggregate review state into a single decision label.

    Returns one of: "approved", "changes_requested", "pending", "no_review_yet".
    Looks at the *latest* review per reviewer.
    """
    latest_per_reviewer: dict[str, str] = {}
    for review in pr.get_reviews():
        if review.user is None:
            continue
        # APPROVED / CHANGES_REQUESTED / COMMENTED / DISMISSED
        if review.state in {"APPROVED", "CHANGES_REQUESTED"}:
            latest_per_reviewer[review.user.login] = review.state

    if not latest_per_reviewer:
        return "no_review_yet"
    if "CHANGES_REQUESTED" in latest_per_reviewer.values():
        return "changes_requested"
    if all(state == "APPROVED" for state in latest_per_reviewer.values()):
        return "approved"
    return "pending"


def register(mcp: FastMCP, config: Config) -> None:
    @mcp.tool()
    def get_pr_state(
        pr_number: int,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Read the current state of a PR.

        Returns: number, title, body, state (open/closed), merged, mergeable,
        head_ref, base_ref, author, url, labels, review_decision.

        review_decision is the key field for pull-based loop logic:
        "approved" | "changes_requested" | "pending" | "no_review_yet"
        """
        gh_repo = _resolve_repo(config, owner, repo)
        pr = gh_repo.get_pull(pr_number)
        return _summarize_pr(pr)

    @mcp.tool()
    def find_pr_by_branch(
        branch: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any] | None:
        """Find a PR by its head branch name. Returns None if no open PR exists."""
        gh_repo = _resolve_repo(config, owner, repo)
        full_owner = gh_repo.owner.login
        prs = gh_repo.get_pulls(state="all", head=f"{full_owner}:{branch}")
        for pr in prs:
            return _summarize_pr(pr)
        return None

    @mcp.tool()
    def list_pr_review_comments(
        pr_number: int,
        owner: str | None = None,
        repo: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all review comments on a PR (line-level + general review bodies).

        Format suitable for skills doing revision: each entry has author, body,
        path (or null for general review comments), line, created_at, state.
        """
        gh_repo = _resolve_repo(config, owner, repo)
        pr = gh_repo.get_pull(pr_number)

        out: list[dict[str, Any]] = []
        for review in pr.get_reviews():
            if review.body and review.body.strip():
                out.append({
                    "kind": "review_summary",
                    "author": review.user.login if review.user else None,
                    "body": review.body,
                    "state": review.state,
                    "created_at": review.submitted_at.isoformat() if review.submitted_at else None,
                    "path": None,
                    "line": None,
                })
        for comment in pr.get_review_comments():
            out.append({
                "kind": "line_comment",
                "author": comment.user.login if comment.user else None,
                "body": comment.body,
                "state": None,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "path": comment.path,
                "line": comment.line,
            })
        return sorted(out, key=lambda c: c["created_at"] or "")

    @mcp.tool()
    def create_pr(
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        owner: str | None = None,
        repo: str | None = None,
        labels: list[str] | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Open a new PR. The branch must already exist on the remote."""
        gh_repo = _resolve_repo(config, owner, repo)
        pr = gh_repo.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=base_branch,
            draft=draft,
        )
        if labels:
            pr.set_labels(*labels)
        return _summarize_pr(pr)

    @mcp.tool()
    def add_pr_comment(
        pr_number: int,
        body: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Post a general (issue-style) comment on a PR."""
        gh_repo = _resolve_repo(config, owner, repo)
        pr = gh_repo.get_pull(pr_number)
        comment = pr.create_issue_comment(body)
        return {"id": comment.id, "url": comment.html_url}

    @mcp.tool()
    def create_implementation_issue(
        jira_key: str,
        design_doc_url: str,
        body: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Open an issue assigned to @copilot to trigger Copilot Coding Agent.

        Title is `[{jira_key}] Implement: ...`. Body should reference the
        design doc URL and any relevant context. The user must have Copilot
        Coding Agent enabled on the repo.
        """
        gh_repo = _resolve_repo(config, owner, repo)
        full_body = (
            f"@copilot please implement per the design at:\n\n"
            f"{design_doc_url}\n\n"
            f"---\n\n"
            f"{body}\n\n"
            f"---\nJira: {jira_key}"
        )
        issue = gh_repo.create_issue(
            title=f"[{jira_key}] Implement",
            body=full_body,
            labels=[f"jira:{jira_key.lower()}", "stage:impl"],
        )
        return {
            "number": issue.number,
            "url": issue.html_url,
        }
