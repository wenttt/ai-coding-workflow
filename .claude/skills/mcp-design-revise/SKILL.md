---
name: mcp-design-revise
description: Revise an existing design Issue based on reviewer comments. Reads the current Issue body and comments, applies targeted edits to the body, posts a summary comment. Used when reviewers leave feedback on the design Issue. 3-strike retry-aware.
---

# mcp-design-revise

You are revising a design Issue that received reviewer feedback. Your job is to read the comments, apply minimal targeted changes to the Issue body, and post a comment summarizing what changed.

This is **not** a re-write from scratch. Preserve everything reviewers didn't object to.

**You operate on the GitHub Issue, not on a branch or PR.** The Issue body is the design's source of truth during Stage 1.

## Bash-free contract

MCP tools only:
- `find_design_issue_for_jira(jira_key)` — find the design Issue
- `get_issue_state(issue_number)` — read current Issue body + state
- `list_issue_comments(issue_number)` — get reviewer feedback
- `read_operation_logs(jira_key)` — see prior attempts
- `update_design_issue(issue_number, body)` — push the new body
- `add_issue_comment(issue_number, body)` — leave a "what I changed" comment
- `get_retry_count(jira_key, "design-revision")` — check budget
- `escalate(...)` — when 3-strike kicks in
- `write_operation_log` — mandatory

You will **not** call any git/PR tool.

## Input contract

```python
{
  "jira_key": "PROJ-123",
  "stage": "design-revision",
  "skill_name": "mcp-design-revise",
  "ticket": {...},
  "mode": "brownfield" | "greenfield",
  "workspace_root": "...",
  "prior_operation_logs": [...],   # IMPORTANT: includes earlier design attempts + revisions
  "retry_count": N,                 # 1, 2, or 3
  "max_retries": 3,
}
```

## Phases

### Phase 1: Check budget

Call `get_retry_count(jira_key, "design-revision")`. If `attempts_so_far >= max_retries`, **stop**:

```python
escalate(
    jira_key=jira_key,
    stage="design-revision",
    skill_invoked="mcp-design-revise",
    agent="<agent>",
    reason="Design rejected 3 times. Cannot resolve via further automated revisions.",
    attempts_summary="<read from prior operation logs>",
    what_humans_need_to_decide=(
        "Reviewers' feedback may be conflicting, the ticket may be under-specified, "
        "or the proposed direction may be fundamentally wrong. Human design review needed."
    ),
    notify_pr_number=None,  # we'd post to the Issue instead — see below
)
# Also leave a comment on the Issue pointing to the escalation
add_issue_comment(
    issue_number=<from find_design_issue_for_jira>,
    body=(
        "WARNING This design has been revised 3 times without converging. "
        "Auto-revision stopped per pipeline policy.\n\n"
        "See escalation log: docs/operations/{jira_key}/...\n\n"
        "Reviewers please decide:\n"
        "- Resolve conflicting feedback among reviewers, OR\n"
        "- Close with `not_planned` and re-scope the Jira ticket, OR\n"
        "- A human takes over the design"
    ),
)
```

### Phase 2: Find the Issue + read prior attempts

```python
issue_info = find_design_issue_for_jira(jira_key)
if not issue_info or issue_info["state"] != "open":
    # This skill only operates on open Issues
    return error
issue_number = issue_info["number"]
```

Read all `prior_operation_logs` filtered by stage `design` and `design-revision`. Pay attention to:
- The latest design log's `engineering_decisions` — what was justified vs. guessed
- The latest design log's `what_i_could_not_do` — what was already flagged as open
- All revision logs — what was tried in earlier rounds

**DO NOT make the same change a previous revision already tried that the reviewer rejected.**

### Phase 3: Read the current Issue body + comments

- `get_issue_state(issue_number)` -> current body
- `list_issue_comments(issue_number)` -> all comments

For each comment, classify:
- **Concrete change request** — "change X to Y" -> must be addressed
- **Question** — "why did you pick X?" -> answer in a reply comment + clarify in body
- **Suggestion** — "consider Z" -> judgment call; if you don't take it, justify why
- **Approval** — "looks good" -> ignore for revision purposes

### Phase 4: Plan the changes

Make a list of specific edits:

```
Edits to Issue body:
1. Section "Tech stack decision" -> change PostgreSQL row to Cassandra (per @boss comment #5)
2. Section "Phasing" -> add Phase 0 for security review (per @sec comment #3)
3. Frontmatter `risk_level` -> change "medium" to "high" (per @boss reasoning)
4. Section "Open questions" -> resolve question #2 (the answer is now in scope)

Comments to leave on Issue:
- Reply summarizing all changes
- For @sec #3: "addressed in revision"
- For @engr #1: "clarified inline; this was an assumption"
```

### Phase 5: Apply changes to the body

The current body is in `issue_info["body"]`. Edit it in memory (preserving structure), then:

```python
update_design_issue(issue_number=issue_number, body=<new body>)
```

If reviewers' requests conflict with each other, surface explicitly in your summary comment (Phase 6) and pick a path with reasoning.

### Phase 6: Post a summary comment

```python
summary = f"""
**Revision {revision}/{max_retries}** — body updated.

## Addressed
- @reviewer1's comment about X -> changed to Y in section Z
- @reviewer2's comment about A -> ...

## Did NOT take
- @reviewer3's suggestion about M, because N (with reasoning)

## Open conflict (please resolve)
- @reviewer1 wants X, @reviewer2 wants Y. Picked X. Reasons: ...

---
If the design now looks good, close this Issue with reason `completed` to trigger Stage 2.
If more changes needed, comment and the next revision will pick them up.
"""

add_issue_comment(issue_number=issue_number, body=summary)
```

### Phase 7: 3-strike awareness in the comment

If this revision is `revision == max_retries` (i.e. last allowed auto-revision), prepend a warning:

```
WARNING **This is revision N/N — the last automated revision allowed.**
If reviewers reject again, the pipeline escalates and a human must take over.
```

Don't wait for auto-escalation to happen silently — make the budget visible.

### Phase 8: Operation log

```python
write_operation_log(
    jira_key=jira_key,
    stage="design-revision",
    skill_invoked="mcp-design-revise",
    agent="<agent>",
    status="completed",
    what_was_done="<list of specific edits applied to Issue body, comments addressed>",
    impact="<which sections of the design changed>",
    what_i_could_not_do="<comments not addressed and why>",
    engineering_decisions="<choices made, especially for conflicts>",
    next_step=f"Wait for re-review on Issue #{issue_number}. If still rejected, retry_count will be {revision+1}/{max_retries}.",
    retry_context={
        "previous_attempts": [
            "v1: initial design — rejected by @boss (tech stack)",
            "v2: revised stack to Cassandra — rejected by @sec (no audit log)",
        ],
        "failure_signal": "<this revision's trigger>",
    },
    outputs={"design_issue_number": issue_number},
)
```

### Phase 9: Report to user

Crisp summary:
- Issue number + URL
- Number of comments addressed
- Any unresolved conflicts
- Whether this was the last auto-revision

## Failure modes

- **Conflicting reviewer comments with no clear winner** -> Escalate. `escalate(...)` MCP tool. Status: `escalated`. Add Issue comment.
- **Same comment as last revision, you can't change it without breaking something** -> Escalate.
- **Out-of-budget** (would be revision 4+) -> handled in Phase 1.
- **Issue is closed (not open)** -> wrong skill; tell user; if `state_reason==completed` they're past Stage 1.

## Honesty principle

If a reviewer's comment requires information you don't have (e.g., "what does the legal team think?"), don't fabricate. Add it to "Open questions" in the body, leave an Issue comment explicitly @-tagging the right person, and note in the operation log that you couldn't resolve it.
