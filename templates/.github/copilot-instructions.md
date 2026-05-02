# Copilot Instructions: AI Coding Workflow

> Copy this file to **your sandbox / target repo's** `.github/copilot-instructions.md`. VS Code Copilot reads it automatically when you open the workspace, and uses it to drive its behavior.
>
> Do not commit it to the `ai-coding-workflow` server repo (that repo isn't the workspace where Copilot drives the pipeline — your team repo is).

---

You have access to the `ai-coding-workflow` MCP server. It exposes tools and prompts for driving software development from a Jira ticket through deploy.

## When the user mentions a Jira ticket key (e.g., "KAN-4", "start working on PROJ-123", "continue KAN-4")

**Always start by detecting state, never guess what stage we're in:**

1. Call `get_workflow_state(jira_key="<KEY>")` — returns the current pipeline stage and what to do next.
2. Match the returned `next_action` against the flows below and follow.
3. After completing the stage, call `write_operation_log` and stop. Do not advance to the next stage automatically — wait for the user to invoke you again.

## Flows by `next_action`

### `create_design` → Stage 1 (Issue-driven)

1. `read_jira_ticket(jira_key)`
2. `analyze_repo_state()` — note `mode` (brownfield or greenfield)
3. `find_design_issue_for_jira(jira_key)` — should be null
4. `find_relevant_modules(keywords)` with concrete keywords from the ticket
5. Read the skill at `.claude/skills/mcp-design-{mode}/SKILL.md` from the ai-coding-workflow project, follow its phases
6. Compose the design markdown (with YAML frontmatter at top)
7. `create_design_issue(jira_key, title, body, labels)`
8. `write_operation_log(stage="design", ...)`
9. Report the Issue URL. STOP.

**Stage 1 is Issue-only. Do NOT call `git_create_branch`, `git_commit`, `git_push`, or `create_pr`.**

### `revise_design` → Stage 1 revision

1. `get_retry_count(jira_key, "design-revision")` — if at limit, call `escalate(...)` and stop
2. `find_design_issue_for_jira(jira_key)`
3. `list_issue_comments(issue_number)`
4. `get_issue_state(issue_number)` — current body
5. `read_operation_logs(jira_key)` — see prior attempts; do NOT redo what was already tried
6. Read `.claude/skills/mcp-design-revise/SKILL.md` and follow phases
7. `update_design_issue(issue_number, body=<revised>)`
8. `add_issue_comment(issue_number, body=<summary of edits>)`
9. `write_operation_log(stage="design-revision", ...)`
10. Report. STOP.

### `trigger_implementation` → Stage 2 (branch + PR)

The design Issue should be closed with `state_reason=completed`.

1. `find_design_issue_for_jira(jira_key)` — confirm closed/completed
2. `get_issue_state(issue_number)` — read design body (the design lives in the Issue, not a file)
3. `read_jira_ticket(jira_key)`
4. `analyze_repo_state()`
5. Determine sub-mode: backend / frontend / db (from ticket labels + design's `affected_modules`)
6. Read `.claude/skills/mcp-implement-{sub_mode}/SKILL.md` and follow phases
7. `git_create_branch(name="feat/{KEY}-{slug}", from_ref="main")`
8. `write_repo_file("docs/designs/{KEY}.md", <body from Issue>)` — snapshot the design as part of the commit
9. Write code per the design (use Read/Edit/Write)
10. `git_add(...)`, `git_commit(...)`, `git_push(...)`
11. `create_pr(title, body=<includes "Closes #<design_issue_number>">, head_branch, base_branch="main", labels=["jira:<key>", "stage:impl"])`
12. `write_operation_log(stage="implement", ...)`
13. Report. STOP.

### `self_review` → Stage 3

1. `git_diff(from_ref="main")` — see what was changed
2. Read `.claude/skills/mcp-self-review/SKILL.md` and follow its 6-pass review
3. `write_operation_log(stage="self-review", ...)`
4. Report findings (Sev-1/2/3 counts). STOP.

### `write_tests` → Stage 4 (write)

1. Read design from operation logs or the Issue body
2. Read `.claude/skills/mcp-test-write/SKILL.md` and follow phases
3. `discover_test_framework()`, `discover_test_files()`
4. Write test files via `write_repo_file`
5. `write_operation_log(stage="test-write", ...)`
6. STOP.

### `run_tests` or `fix_failing_tests` → Stage 4 (run)

1. `get_retry_count(jira_key, "test-run")` — if at limit, escalate
2. `run_tests()`
3. If failing, read failure output, read `.claude/skills/mcp-test-run/SKILL.md`, fix, `git_add` + `git_commit` + `git_push`, retry
4. `write_operation_log(stage="test-run", ...)`
5. Report. STOP.

### `deploy` → Stage 5

Read `.claude/skills/mcp-deploy/SKILL.md` and follow.

### `update_docs` → Stage 6

Read `.claude/skills/mcp-doc-update/SKILL.md` and follow. Closes Jira at the end.

### `escalated` → STOP

Tell the user the pipeline has escalated. Reference the ESCALATED operation log. Do not retry.

## Useful slash commands (provided by the MCP server)

The MCP server registers these prompts; they show up in the Copilot Chat slash-command picker:

- `/ai-coding-workflow:pipeline jira_key=<KEY>` — auto-detect stage and run it
- `/ai-coding-workflow:design_for jira_key=<KEY>` — Stage 1 only
- `/ai-coding-workflow:implement_for jira_key=<KEY>` — Stage 2 only
- `/ai-coding-workflow:my_tickets` — list tickets assigned to me with their current stage
- `/ai-coding-workflow:investigate_for jira_key=<KEY>` — root-cause for stuck tickets
- `/ai-coding-workflow:revise_design jira_key=<KEY>` — Stage 1 revision

## Critical rules (apply to every stage)

1. **State is real** — don't assume. Always call `get_workflow_state` first.
2. **One stage per invocation** — finish a stage, log it, stop. The user calls again to continue.
3. **Operation logs are mandatory** — every successful tool sequence ends with `write_operation_log`.
4. **3-strike retries** — within a single invocation, if a stage's `get_retry_count >= max_retries`, call `escalate(...)` instead of retrying.
5. **Stage 1 is Issue-only** — never use git tools in design stage.
6. **Skills are the source of truth** — when a flow has a corresponding `.claude/skills/mcp-*/SKILL.md`, read it and follow its phases. Don't improvise.
