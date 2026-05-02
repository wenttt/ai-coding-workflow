"""GitHub MCP tools.

Two distinct flow controls in this project:

1. **Stage 1 (design): GitHub Issues**
   - Design markdown lives in the Issue body (with YAML frontmatter at top)
   - Reviewers comment on the Issue
   - Issue closing = approved -> triggers Stage 2
   - No branch operations in this phase

2. **Stage 2+ (implementation): Branches + PRs**
   - Each developer's implementation work goes on `feat/{KEY}-...` branch
   - PR opens against main with `Closes #<design-issue-number>`
   - Code review happens on the PR

This split mirrors how mature engineering teams already work:
discussion in Issues, code in PRs.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from github import Auth, Github
from github.Repository import Repository

from ..config import Config


def _gh(config: Config) -> Github:
    # Explicit timeout so flaky network surfaces as a fast error instead of hanging.
    # GitHub API is generally fast; 15s is plenty for a single REST call.
    return Github(auth=Auth.Token(config.github_token), timeout=15, retry=2)


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
        """Find a PR by its head branch name. Returns None if no open PR exists.

        Returns None on network error rather than hanging.
        """
        import logging
        log = logging.getLogger("ai_coding_workflow.github")
        try:
            gh_repo = _resolve_repo(config, owner, repo)
            full_owner = gh_repo.owner.login
            prs = gh_repo.get_pulls(state="all", head=f"{full_owner}:{branch}")
            first_page = prs.get_page(0)
            if not first_page:
                return None
            return _summarize_pr(first_page[0])
        except Exception as exc:
            log.warning("find_pr_by_branch(%s) failed: %s. Returning None.", branch, exc)
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

    # ----- Stage 1: Issue-driven design phase -----------------------------

    @mcp.tool()
    def create_design_issue(
        jira_key: str,
        title: str,
        body: str,
        owner: str | None = None,
        repo: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Open a GitHub Issue for Stage 1 design discussion.

        The Issue body holds the full design markdown (with YAML frontmatter
        at top). Reviewers comment on the Issue. Closing the Issue means
        approved -> triggers Stage 2.

        Default labels include `jira:{key}` and `stage:design`. Caller may
        override or extend.
        """
        gh_repo = _resolve_repo(config, owner, repo)
        default_labels = [f"jira:{jira_key.lower()}", "stage:design"]
        all_labels = labels if labels is not None else default_labels
        issue = gh_repo.create_issue(
            title=title,
            body=body,
            labels=all_labels,
            assignees=assignees or [],
        )
        return {
            "number": issue.number,
            "url": issue.html_url,
            "state": issue.state,
            "labels": [lbl.name for lbl in issue.labels],
        }

    @mcp.tool()
    def update_design_issue(
        issue_number: int,
        body: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Replace the body of a design Issue. Used by `mcp-design-revise`.

        The full new design markdown should be passed; GitHub will replace
        the entire body. Comment history is preserved.
        """
        gh_repo = _resolve_repo(config, owner, repo)
        issue = gh_repo.get_issue(issue_number)
        issue.edit(body=body)
        # Re-fetch to get updated_at
        issue = gh_repo.get_issue(issue_number)
        return {
            "number": issue.number,
            "url": issue.html_url,
            "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
        }

    @mcp.tool()
    def get_issue_state(
        issue_number: int,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Read the current state of an Issue.

        Returns: number, title, body, state (open/closed), state_reason,
        labels, assignees, comments_count, url, created_at, closed_at.

        For Stage 1 status checks: `state=closed AND state_reason=completed`
        means approved (proceed to Stage 2). `state=closed AND state_reason=
        not_planned` means the design was rejected outright (escalation or
        dropped). `state=open` means still under review.
        """
        gh_repo = _resolve_repo(config, owner, repo)
        issue = gh_repo.get_issue(issue_number)
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "state": issue.state,
            "state_reason": issue.state_reason,
            "labels": [lbl.name for lbl in issue.labels],
            "assignees": [a.login for a in issue.assignees],
            "comments_count": issue.comments,
            "url": issue.html_url,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
            "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
        }

    @mcp.tool()
    def list_issue_comments(
        issue_number: int,
        owner: str | None = None,
        repo: str | None = None,
    ) -> list[dict[str, Any]]:
        """List comments on an Issue.

        Used by `mcp-design-revise` to read reviewer feedback.
        """
        gh_repo = _resolve_repo(config, owner, repo)
        issue = gh_repo.get_issue(issue_number)
        out: list[dict[str, Any]] = []
        for comment in issue.get_comments():
            out.append({
                "id": comment.id,
                "author": comment.user.login if comment.user else None,
                "body": comment.body or "",
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "url": comment.html_url,
            })
        return sorted(out, key=lambda c: c["created_at"] or "")

    @mcp.tool()
    def add_issue_comment(
        issue_number: int,
        body: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Post a comment on an Issue.

        Used by `mcp-design-revise` to summarize what was changed in a
        revision and link reviewer comments to specific edits.
        """
        gh_repo = _resolve_repo(config, owner, repo)
        issue = gh_repo.get_issue(issue_number)
        comment = issue.create_comment(body)
        return {"id": comment.id, "url": comment.html_url}

    @mcp.tool()
    def close_issue(
        issue_number: int,
        state_reason: str = "completed",
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Close an Issue.

        `state_reason` controls how GitHub categorizes the closure:
        - "completed" (default): work was done / design approved
        - "not_planned": dropping the work / design rejected outright
        """
        if state_reason not in {"completed", "not_planned"}:
            raise ValueError(
                f"state_reason must be 'completed' or 'not_planned', got {state_reason!r}"
            )
        gh_repo = _resolve_repo(config, owner, repo)
        issue = gh_repo.get_issue(issue_number)
        issue.edit(state="closed", state_reason=state_reason)
        return {
            "number": issue.number,
            "state": "closed",
            "state_reason": state_reason,
        }

    @mcp.tool()
    def find_design_issue_for_jira(
        jira_key: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any] | None:
        """Find the design Issue for a Jira ticket by label.

        Returns the matching Issue's basic info, or None if not found.
        Used at the top of every Stage 1 invocation to detect whether
        a design issue already exists (and what state it's in).

        Implementation note: uses page-bounded iteration with 15s timeout
        on the underlying client. On network error or timeout, returns
        None and logs the error rather than hanging.
        """
        import logging
        log = logging.getLogger("ai_coding_workflow.github")

        try:
            gh_repo = _resolve_repo(config, owner, repo)
            jira_label = f"jira:{jira_key.lower()}"
            # Fetch only the first page (max 30 issues) to avoid full pagination.
            # Two labels means very few results expected (0 or 1).
            paginated = gh_repo.get_issues(
                state="all",
                labels=[jira_label, "stage:design"],
            )
            first_page = paginated.get_page(0)
            if not first_page:
                return None
            issue = first_page[0]
            return {
                "number": issue.number,
                "url": issue.html_url,
                "state": issue.state,
                "state_reason": issue.state_reason,
                "title": issue.title,
            }
        except Exception as exc:
            log.warning(
                "find_design_issue_for_jira(%s) failed: %s. "
                "Returning None — caller should treat as 'no existing issue found'.",
                jira_key,
                exc,
            )
            return None

    # ----- Stage 2+: Implementation issue (Copilot Coding Agent trigger) ---

    @mcp.tool()
    def create_implementation_issue(
        jira_key: str,
        design_issue_url: str,
        body: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Open an issue assigned to @copilot to trigger Copilot Coding Agent.

        Used in Stage 2 AFTER the design Issue is closed (approved). The
        implementation issue references the (closed) design Issue.

        Title is `[{jira_key}] Implement: ...`. Body references the
        design Issue URL and any relevant context. The user must have
        Copilot Coding Agent enabled on the repo.
        """
        gh_repo = _resolve_repo(config, owner, repo)
        full_body = (
            f"@copilot please implement per the approved design:\n\n"
            f"{design_issue_url}\n\n"
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
