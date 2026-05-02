---
name: mcp-design-revise
description: Revise an existing design doc based on PR review comments. Reads the current design, parses review feedback, applies targeted changes, pushes a new commit. Used when a design PR is rejected and we're inside the 3-strike retry window.
---

# mcp-design-revise

You are revising a design that was rejected on PR review. Your job is to read the review feedback, apply minimal targeted changes to the design doc, and push a new commit to the same PR.

This is **not** a re-write from scratch. Preserve everything the reviewers didn't object to.

## Bash-free contract

MCP tools only:
- `read_repo_file(design_doc_path)` — current design
- `list_pr_review_comments(pr_number)` — get all review comments
- `read_operation_logs(jira_key)` — see prior attempts
- `git_checkout(branch)` — back onto the design branch
- `write_repo_file`, `git_add`, `git_commit`, `git_push` — push the revision
- `add_pr_comment(pr_number, body)` — leave a "what I changed" comment
- `write_operation_log` — mandatory

## Input contract

```python
{
  "jira_key": "PROJ-123",
  "stage": "design-revision",
  "skill_name": "mcp-design-revise",
  "ticket": {...},
  "mode": "brownfield" | "greenfield",
  "workspace_root": "...",
  "design_doc_path": "docs/designs/PROJ-123.md",
  "review_comments": [...],          # already populated from list_pr_review_comments
  "prior_operation_logs": [...],     # IMPORTANT: includes earlier design attempts + revisions
  "retry_count": N,                   # 1, 2, or 3
  "max_retries": 3,
  "design_pr_number": ...,
  "design_branch": "design/PROJ-123-...",
}
```

## Phases

### Phase 1: Read the prior attempts

Look at `prior_operation_logs`. Read the most recent design log. Pay attention to:
- Its `engineering_decisions` — what was justified, what was guessed
- Its `what_i_could_not_do` — what was already flagged as open
- If this is revision 2 or 3: read all revision logs to see what changes were made earlier and what reviewers said about them

This is critical for retry quality. **DO NOT make the same change a previous revision already tried that the reviewer rejected.**

### Phase 2: Read the current design + review comments

- `read_repo_file(design_doc_path)` to get the current state
- The `review_comments` field already has structured comments

For each comment, classify:
- **Concrete change request** — "change X to Y" → must be addressed
- **Question** — "why did you pick X?" → answer in PR comment + clarify in design body
- **Suggestion** — "consider Z" → judgment call; if you don't take it, justify why
- **Approval** — "looks good" → ignore for revision purposes

### Phase 3: Plan the changes

Make a list of specific edits:

```
Edits to apply:
1. Section "Tech stack decision" → change PostgreSQL row to Cassandra (per @boss comment #5)
2. Section "Phasing" → add Phase 0 for security review (per @sec comment #3)
3. Frontmatter `risk_level` → change "medium" to "high" (per @boss reasoning)
4. Section "Open questions" → resolve question #2 (the answer is now in scope)

Comments to leave on PR:
- Reply to @sec #3: addressed in commit
- Reply to @engr #1: clarified inline; this was an assumption
```

### Phase 4: Apply changes

Use `read_repo_file` + edit-in-memory + `write_repo_file` for the design doc.
Make changes minimal and focused. Don't refactor sections that aren't called out.

If the reviewer's request conflicts with another reviewer's earlier comment (this happens), surface it explicitly:

- In a PR comment: tag both reviewers, summarize the conflict
- Choose one path, commit to it, explain the choice in `engineering_decisions`
- If you can't resolve, escalate (see below)

### Phase 5: Commit + push

```python
git_checkout(design_branch)
git_add([design_doc_path])
git_commit(f"design: revise per review (revision {revision} of {max_retries}) — {jira_key}")
git_push(design_branch)
```

### Phase 6: Reply on PR

`add_pr_comment(pr_number, body)` with a concise summary:

```markdown
Revision {revision}/{max_retries} pushed.

Addressed:
- @reviewer1's comment about X → changed to Y in section Z
- @reviewer2's comment about A → ...

Did NOT take:
- @reviewer3's suggestion about M, because N (with reasoning)

Open conflict (please resolve):
- @reviewer1 wants X, @reviewer2 wants Y. Picked X. Reasons: ...
```

### Phase 7: Operation log

```python
write_operation_log(
    jira_key=jira_key,
    stage="design-revision",
    skill_invoked="mcp-design-revise",
    agent="<agent>",
    status="completed",
    what_was_done="<list of specific edits>",
    impact="<which sections of the design changed>",
    what_i_could_not_do="<comments not addressed and why>",
    engineering_decisions="<choices made, especially for conflicts>",
    next_step="Wait for re-review. If still rejected, retry_count will be {revision+1}/{max_retries}.",
    retry_context={
        "previous_attempts": [
            # 1-line summary per prior log
            "v1: initial design — rejected by @boss (tech stack)",
            "v2: revised stack to Cassandra — rejected by @sec (no audit log)",
        ],
        "failure_signal": "<this revision's trigger>",
    },
)
```

### Phase 8: 3-strike awareness

After pushing this revision, if the **next** rejection would be the (max_retries+1)th, surface this prominently in the PR comment AND the operation log's "Next step":

> ⚠️ This is revision {N}/{max_retries}. If reviewers reject again, the pipeline escalates and a human must take over the design.

Don't wait for the auto-escalation to happen silently — make the budget visible.

## Failure modes

- **Conflicting review comments with no clear winner** → Escalate. Use `escalate(...)` MCP tool. Set `status="escalated"` in the operation log.
- **Same comment as last revision, you can't change it without breaking something** → Escalate.
- **Out-of-budget** (this would be revision 4+) → DO NOT proceed. Call `escalate(...)`.

## Honesty principle

If a reviewer's comment requires information you don't have (e.g., "what does the legal team think?"), don't fabricate. Add it to "Open questions" in the design, leave a PR comment explicitly asking the reviewer or @-tagging the right person, and note in the operation log that you couldn't resolve it.
