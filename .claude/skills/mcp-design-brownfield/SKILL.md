---
name: mcp-design-brownfield
description: Generate a tech design document for a Jira ticket against an existing codebase. Reads the Jira ticket, finds relevant code modules, picks the right template, then publishes the design as a GitHub Issue (Stage 1 of the AI Coding Workflow pipeline). The Issue is the design discussion artifact — branches and PRs come later in Stage 2.
---

# mcp-design-brownfield

You are operating Stage 1 of the AI Coding Workflow pipeline for a **brownfield** project (the workspace has substantive code).

**The output of this stage is a GitHub Issue**, NOT a branch or a file in the repo. The Issue body contains the full design markdown (with YAML frontmatter at top). Reviewers comment on the Issue. Closing the Issue with `state_reason: completed` means approved -> triggers Stage 2.

This shape mirrors how mature teams work: discussion lives in Issues, code lives in PRs.

## Bash-free contract

Use only MCP tools — no shell commands. Tools you'll need:

- `read_jira_ticket(jira_key)` — get ticket details
- `analyze_repo_state()` — confirm brownfield mode
- `find_relevant_modules(keywords)` — discover files related to the ticket
- `read_repo_file(path)` — read individual files for context
- `find_design_issue_for_jira(jira_key)` — check whether a design Issue already exists
- `create_design_issue(jira_key, title, body, labels?, assignees?)` — publish the design
- `write_operation_log(...)` — record what you did (mandatory before you finish)

You will **not** call `git_create_branch`, `git_commit`, `git_push`, or `create_pr`. Those are for Stage 2 (implementation).

## Input contract

The `prepare_skill_input` tool gives you a dict with:

```python
{
  "jira_key": "PROJ-123",
  "stage": "design",
  "skill_name": "mcp-design-brownfield",
  "ticket": {...},                    # from read_jira_ticket
  "mode": "brownfield",
  "workspace_root": "/abs/path",
  "operation_log_dir": "docs/operations",
  "prior_operation_logs": [],         # empty for first attempt
  "retry_count": 0,
  "max_retries": 3,
}
```

## Phases

### Phase 1: Verify mode and check for existing Issue

1. Call `analyze_repo_state()`. If `mode != "brownfield"`, stop and tell the user this skill is for brownfield. The Agent should switch to `mcp-design-greenfield`.

2. Call `find_design_issue_for_jira(jira_key)` to detect whether a design Issue already exists for this Jira ticket.
   - If returns `None` -> normal Stage 1 first attempt; continue to Phase 2.
   - If returns an Issue with `state="open"` -> tell the user it already exists (link to it); stop. They probably want `mcp-design-revise` instead.
   - If returns an Issue with `state="closed", state_reason="completed"` -> design was already approved; tell user Stage 2 is the next step; stop.
   - If returns an Issue with `state="closed", state_reason="not_planned"` -> the design was rejected outright; ask user whether to start fresh or escalate.

### Phase 2: Read the ticket

The `ticket` field already has the parsed Jira data. Note especially:
- `summary`, `description`, `ticket_type`, `labels`, `components`, `linked_issues`

### Phase 3: Find relevant modules

Pick 3-7 keywords from `summary` + `description` (concrete nouns, technical terms, component names — NOT generic words). Call `find_relevant_modules(keywords)`.

Read the top 3-5 returned files via `read_repo_file` to understand:
- Existing patterns in the affected area
- Naming conventions
- Error-handling style
- Dependencies already in use

If you find no relevant modules, say so explicitly in the operation log's "What I could not do" — do not make up modules.

### Phase 4: Pick the template

Based on `ticket.ticket_type`:
- `user_story` -> `src/ai_coding_workflow/resources/templates/brownfield/user_story.md`
- `task` -> `templates/brownfield/task.md`
- `sub_task` -> `templates/brownfield/sub_task.md`
- `epic` -> `templates/brownfield/epic.md`

Read the template via `read_repo_file` from the ai-coding-workflow package install path, OR construct from the schema if it's not accessible from the workspace.

### Phase 5: Compose the design markdown

Fill in the template with:
- All `{{ }}` placeholders replaced with concrete content
- The YAML frontmatter populated:
  - `jira_key`: from input
  - `mode`: `brownfield`
  - `ticket_type`: from ticket
  - `ac`: list of acceptance criteria as plain strings (Stage 4 reads this)
  - `affected_modules`: paths under workspace root that this design touches
  - `risk_level`: your judgment — `low` / `medium` / `high`

Add a clear header at the top of the body (above the frontmatter? GitHub renders frontmatter as a code block, that's fine; you can add a one-line "Jira: <url>" line below the frontmatter for quick navigation).

**Key rule for the body**: Every section the template has, you must fill in. If something genuinely doesn't apply, write `_(N/A — see Open Questions)_` rather than deleting the section. The template is the contract for downstream stages.

### Phase 6: Add a "How to review this Issue" footer

Append this to the bottom of the body so reviewers know what to do:

```markdown
---

## How to review

- Comment in this Issue to request changes or ask questions.
- Mention specific reviewers with `@username`.
- When the design looks good, **close this Issue with reason `completed`**. That triggers Stage 2 (implementation).
- If the design is fundamentally wrong, close with reason `not planned` and discuss in Jira.

Up to 3 revision rounds are auto-handled. After that, the pipeline escalates to a human.
```

### Phase 7: Create the Issue

```python
result = create_design_issue(
    jira_key=jira_key,
    title=f"[{jira_key}] Design: {ticket['summary']}",
    body=<the full markdown>,
    labels=[f"jira:{jira_key.lower()}", "stage:design"],
    assignees=[<reviewer logins, optional>]
)
issue_number = result["number"]
issue_url = result["url"]
```

### Phase 8: Write the operation log (MANDATORY)

```python
write_operation_log(
    jira_key=jira_key,
    stage="design",
    skill_invoked="mcp-design-brownfield",
    agent="<agent-name>",
    status="completed",
    what_was_done="""
- Confirmed brownfield mode (X code files, languages: ...)
- Confirmed no prior design Issue exists (find_design_issue_for_jira returned None)
- Read Jira ticket: <one-sentence summary>
- Searched repo with keywords: [...] — found N relevant modules
- Read top files: <list>
- Used template: brownfield/{ticket_type}.md
- Created GitHub Issue #{issue_number}
""",
    impact="""
- 1 GitHub Issue opened (no repo file changes, no branch, no commit)
- Issue body declares affected_modules: [...]
- Awaiting review
""",
    what_i_could_not_do="<be specific; or '_(none)_' if everything was clean>",
    engineering_decisions="""
- Picked template X because ...
- Risk level: X because ...
- AC phrasing follows GIVEN/WHEN/THEN per project convention
""",
    next_step=f"""
Wait for reviewer feedback on Issue #{issue_number} ({issue_url}).
- If reviewers close with `completed` -> invoke Stage 2 via mcp-implement-{{backend|frontend|db}}
- If reviewers comment requesting changes -> invoke mcp-design-revise with the issue_number
- If reviewers close with `not_planned` -> escalate to user
""",
    inputs={...},
    outputs={
      "design_issue_number": issue_number,
      "design_issue_url": issue_url,
      "labels": result["labels"],
    },
)
```

### Phase 9: Report to user

Tell the user:
- The Issue number + URL
- A 2-3 sentence summary of the design
- "Reviewers can comment on the Issue. Close it with `completed` reason when approved. Call me again with `Continue {jira_key}` after they respond."

Then stop.

## Failure modes

If you can't complete (Jira down, can't find any relevant code, template parsing fails):
- Set `status="failed"` in the operation log
- Be honest in "What I could not do"
- Suggest specific recovery in "Next step"
- The Agent will see status:failed and present options to the user

## Honesty principle

If acceptance criteria are vague in the Jira ticket, write a draft AC list and put the ambiguities in "Open questions" of the design — DO NOT make up specific behavior the ticket didn't ask for.

If you guess at affected modules without code evidence, mark them with `?` in the body and explain in the operation log's "Engineering decisions". Stage 2 will read these guesses.
