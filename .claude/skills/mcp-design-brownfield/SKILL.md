---
name: mcp-design-brownfield
description: Generate a tech design document for a Jira ticket against an existing codebase. Reads the Jira ticket, finds relevant code modules, picks the right template, writes the design doc with frontmatter, and opens a design PR. Stage 1 of the AI Coding Workflow pipeline (brownfield path).
---

# mcp-design-brownfield

You are operating Stage 1 of the AI Coding Workflow pipeline for a **brownfield** project (the workspace already has substantive code). Your output is a design document written to `docs/designs/{JIRA_KEY}.md` and pushed as a PR.

## Bash-free contract

You **MUST NOT** run shell commands. All system access is through MCP tools provided by the `ai-coding-workflow` MCP server. Tools you'll need:

- `read_jira_ticket(jira_key)` — get ticket details
- `analyze_repo_state()` — confirm we are in brownfield mode
- `find_relevant_modules(keywords)` — discover files related to the ticket
- `read_repo_file(path)` — read individual files for context
- `git_create_branch(name, from_ref)` — branch for the design PR
- `write_repo_file(path, content)` — write the design doc
- `git_add(paths)`, `git_commit(message)`, `git_push(branch)` — commit + push
- `create_pr(...)` — open the PR
- `write_operation_log(...)` — record what you did (mandatory before you finish)

## Input contract

The `prepare_skill_input` tool gives you a dict with:

```python
{
  "jira_key": "PROJ-123",
  "stage": "design",
  "skill_name": "mcp-design-brownfield",
  "ticket": {...},                    # from read_jira_ticket
  "mode": "brownfield",               # confirmed by caller
  "workspace_root": "/abs/path",
  "design_doc_dir": "docs/designs",
  "operation_log_dir": "docs/operations",
  "prior_operation_logs": [...],      # empty for first attempt
  "retry_count": 0,
  "max_retries": 3,
  "design_doc_path": "docs/designs/PROJ-123.md"
}
```

## Phases

### Phase 1: Verify mode

Call `analyze_repo_state()`. If `mode != "brownfield"`, stop and tell the user this skill is for brownfield. The Agent should switch to `mcp-design-greenfield`.

### Phase 2: Read the ticket

The `ticket` field already has the parsed Jira data. Note especially:
- `summary`, `description`, `ticket_type`, `labels`, `components`, `linked_issues`

### Phase 3: Find relevant modules

Pick 3-7 keywords from `summary` + `description` (concrete nouns, technical terms,
component names — NOT generic words). Call `find_relevant_modules(keywords)`.

Read the top 3-5 returned files via `read_repo_file` to understand:
- Existing patterns in the affected area
- Naming conventions
- Error-handling style
- Dependencies already in use

If you find no relevant modules, say so explicitly in the operation log's "What I could not do" — do not make up modules.

### Phase 4: Pick the template

Based on `ticket.ticket_type`:
- `user_story` → `src/ai_coding_workflow/resources/templates/brownfield/user_story.md`
- `task` → `templates/brownfield/task.md`
- `sub_task` → `templates/brownfield/sub_task.md`
- `epic` → `templates/brownfield/epic.md`

Read the template file with `read_repo_file` (relative to the package install
location). The MCP server resolves the templates dir for you on request — call
the convenience tool if available, or load the markdown content directly.

### Phase 5: Write the design doc

Fill in the template with:
- All `{{ }}` placeholders replaced with concrete content
- The frontmatter populated:
  - `jira_key`: from input
  - `mode`: "brownfield"
  - `ticket_type`: from ticket
  - `ac`: list of acceptance criteria as plain strings (Stage 4 reads this)
  - `affected_modules`: paths under workspace root that this design touches
  - `risk_level`: your judgment — `low` / `medium` / `high`

**Key rule for the body**: Every section the template has, you must fill in. If
something genuinely doesn't apply, write `_(N/A — see Open Questions)_` rather
than deleting the section. The template is the contract for downstream stages.

### Phase 6: Branch + push

1. `git_create_branch(name="design/{JIRA_KEY}-{slug}", from_ref="main")`
2. `write_repo_file(design_doc_path, content)`
3. `git_add([design_doc_path])`
4. `git_commit("design: {ticket.summary} ({jira_key})")`
5. `git_push(branch=name)`

### Phase 7: Open the PR

```python
create_pr(
    title=f"[{jira_key}] Design: {ticket.summary}",
    body=f"""
Jira: {ticket.url}
Stage: design

This PR contains the design document for {jira_key}.
Path: `{design_doc_path}`

Reviewers: please leave comments on the markdown file. If approved, merge —
that triggers Stage 2 (implementation).
""",
    head_branch=name,
    base_branch="main",
    labels=[f"jira:{jira_key.lower()}", "stage:design"],
)
```

### Phase 8: Write the operation log (MANDATORY)

```python
write_operation_log(
    jira_key=jira_key,
    stage="design",
    skill_invoked="mcp-design-brownfield",
    agent="<agent-name>",  # claude-code | copilot | cursor
    status="completed",
    what_was_done="""
- Confirmed brownfield mode (X code files, languages: ...)
- Read Jira ticket: <one-sentence summary>
- Searched repo with keywords: [...] — found N relevant modules
- Read top files: <list>
- Used template: brownfield/{ticket_type}.md
- Wrote design to {design_doc_path}
- Opened PR #{pr_number}
""",
    impact="""
- 1 new file: {design_doc_path}
- No code changes
- No deps changes
- Frontmatter declares affected_modules: [...]
""",
    what_i_could_not_do="<be specific; or '_(none)_' if everything was clean>",
    engineering_decisions="""
- Picked template X because ...
- Risk level: X because ...
- AC phrasing follows GIVEN/WHEN/THEN per project convention
""",
    next_step="""
Wait for human review on PR #{pr_number}.
- If APPROVED: invoke Stage 2 via mcp-implement-{backend|frontend|db}
- If CHANGES_REQUESTED: invoke mcp-design-revise with the review comments
""",
    inputs={...},
    outputs={...},
)
```

### Phase 9: Report to user

Tell the user:
- The design PR number + URL
- A 2-3 sentence summary of the design
- "Wait for review. Call me again with `Continue {jira_key}` after review."

Then stop.

## Failure modes

If you can't complete (Jira down, can't find any relevant code, template parsing fails):
- Set `status="failed"` in the operation log
- Be honest in "What I could not do"
- Suggest specific recovery in "Next step"
- The Agent will see status:failed and present options to the user

## Honesty principle

If acceptance criteria are vague in the Jira ticket, write a draft AC list and put
the ambiguities in "Open questions" of the design doc — DO NOT make up specific
behavior the ticket didn't ask for.

If you guess at affected modules without code evidence, mark them with `?` in
the body and explain in the operation log's "Engineering decisions". Stage 2
will read these guesses.
