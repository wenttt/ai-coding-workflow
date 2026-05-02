---
name: mcp-design-greenfield
description: Generate a tech design + tech-stack decision for a Jira ticket where the workspace has no existing code. Stage 1 of the AI Coding Workflow pipeline (greenfield path). Picks language, framework, database, deployment, and lays out the initial project skeleton plan. Output is a GitHub Issue — branches and PRs are Stage 2.
---

# mcp-design-greenfield

Stage 1 of the pipeline for a **greenfield** project (the workspace is empty or has only scaffolding).

**Output is a GitHub Issue containing a tech-stack decision matrix and project skeleton plan**, not a branch or a file. Reviewers approve by closing the Issue.

## Bash-free contract

Use only MCP tools — no shell commands. Tools you'll need:

- `read_jira_ticket(jira_key)` — get ticket
- `analyze_repo_state()` — confirm greenfield
- `read_repo_file(path)`, `list_repo_files(...)` — see what little is there
- `find_design_issue_for_jira(jira_key)` — check for existing Issue
- `create_design_issue(jira_key, title, body, labels?, assignees?)`
- `write_operation_log(...)` — mandatory

You will **not** call `git_create_branch`, `git_commit`, `git_push`, or `create_pr`.

## Input contract

Same as `mcp-design-brownfield` but `mode == "greenfield"`.

## Phases

### Phase 1: Verify mode + check for existing Issue

`analyze_repo_state()`. If `mode != "greenfield"`, stop and tell the Agent to switch to `mcp-design-brownfield`.

`find_design_issue_for_jira(jira_key)`:
- None -> first attempt; continue
- Open Issue exists -> tell user; stop (suggest `mcp-design-revise`)
- Closed/completed -> design approved; suggest Stage 2
- Closed/not_planned -> rejected outright; ask user how to proceed

### Phase 2: Synthesize requirements

Read `ticket` carefully. For greenfield work, the ticket usually describes a system or capability rather than a single feature. Extract:

- **Functional requirements**: what the system must do
- **Non-functional requirements (NFR)**: performance, scale, latency, availability targets
- **Constraints**: company tech standards, security requirements, integrations, team size
- **Out-of-scope**: what's explicitly NOT being built

Read `linked_issues` if any exist.

If NFRs are absent from the ticket, list reasonable defaults in "Open questions" rather than inventing specifics.

### Phase 3: Pick the template

For greenfield:
- Brand-new whole project -> `templates/greenfield/new_project.md`
- New service inside a multi-service org -> `templates/greenfield/new_service.md`
- New module inside what's clearly going to be a monorepo -> `templates/greenfield/new_module.md`

Default to `new_project.md` if unsure.

### Phase 4: Tech stack decision matrix

This is the highest-stakes part of greenfield design. For EACH dimension, propose a recommendation, list alternatives, give rationale.

Dimensions to cover (at minimum):
1. Language
2. Framework
3. Database (and ORM if any)
4. Cache (or "none" — explain why)
5. API style (REST / GraphQL / gRPC / events)
6. Auth (built-in / third-party / OAuth provider)
7. Deployment (Kubernetes / Cloud Run / Lambda / VMs)
8. CI/CD
9. Testing framework
10. Logging / observability stack

For each:
- **Recommended**: ONE choice (don't hedge)
- **Alternatives considered**: 1-3, briefly
- **Rationale**: 1-2 sentences

If the ticket / linked tickets specify any of these, record them and note "constrained by ticket".

Mirror the recommended values in the frontmatter `proposed_stack` so downstream stages can read them programmatically.

### Phase 5: High-level architecture

A diagram (mermaid or ASCII) showing major modules + data flow + external dependencies. Aim for 5-10 boxes.

### Phase 6: Project skeleton

Lay out the directory structure. NOT generated yet — Stage 2 will create it. The design just states what it should look like.

### Phase 7: Phasing plan

Greenfield projects need to be sequenced. Lay out phases:

| Phase | Sub-task (suggested Jira ticket) | Deliverable |
|---|---|---|
| 1 | Skeleton + smoke test | `curl /health` returns 200 |
| 2 | DB layer + first model | One read + write works |
| ... | ... | ... |

This becomes the sub-task breakdown the Epic eventually fans out into.

### Phase 8: Add the "How to review" footer

Append to the bottom of the body (same as brownfield):

```markdown
---

## How to review

- Comment in this Issue to request changes or ask questions.
- **The tech stack matrix is the most important section** — pay attention there.
- When approved, **close this Issue with reason `completed`**. That triggers Stage 2.
- If a fundamental rethink is needed, close with reason `not planned` and discuss in Jira.

Up to 3 revision rounds are auto-handled. After that, escalates.
```

### Phase 9: Create the Issue

```python
result = create_design_issue(
    jira_key=jira_key,
    title=f"[{jira_key}] Greenfield Design: {ticket['summary']}",
    body=<the full markdown>,
    labels=[f"jira:{jira_key.lower()}", "stage:design", "greenfield"],
)
```

Add `greenfield` label so it's easy to filter — these often need different reviewer attention than brownfield designs.

### Phase 10: Write the operation log

Same shape as brownfield, but key fields differ:

- `outputs.proposed_stack` should include the tech stack decisions (so downstream Stage 2 can reference)
- `engineering_decisions` should explain WHY each major stack pick was made — this is the audit trail for "why are we using X?" questions a year from now
- `what_i_could_not_do` for greenfield often includes "validate stack against company-wide policies" if you don't know them

### Phase 11: Report

Tell user:
- The Issue with the stack decision matrix
- A bulleted summary of the recommended stack
- That this is a tech-stack-decision review — reviewers should pay attention to that section especially

## Special rule: when in doubt, ask in "Open questions"

Greenfield design has more unknowns than brownfield. It's better to leave 5-10 explicit open questions in the doc than to make up plausible-sounding decisions. The reviewer (and the eventual Stage 2 implementer) needs to know what's been decided vs. what was assumed.

## Operation log honesty

If you didn't actually compare alternatives for a stack dimension and just picked "the obvious one", say so in `engineering_decisions`:

```
- Picked PostgreSQL: did not benchmark MongoDB alternative; relying on team
  familiarity and existing infra. Open question for reviewer.
```

This is fine. Hidden hand-waving is not.
