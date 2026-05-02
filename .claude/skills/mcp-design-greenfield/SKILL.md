---
name: mcp-design-greenfield
description: Generate a tech design + tech-stack decision for a Jira ticket where the workspace has no existing code. Stage 1 of the AI Coding Workflow pipeline (greenfield path). Picks language, framework, database, deployment, and lays out the initial project skeleton plan.
---

# mcp-design-greenfield

You are operating Stage 1 of the AI Coding Workflow pipeline for a **greenfield** project (the workspace is empty or has only scaffolding). Your output is a design doc that includes a **tech stack decision matrix** and a **project skeleton plan**, written to `docs/designs/{JIRA_KEY}.md` and pushed as a design PR.

## Bash-free contract

Use only MCP tools — no shell commands. Tools you'll need:

- `read_jira_ticket(jira_key)` — get ticket
- `analyze_repo_state()` — confirm greenfield
- `read_repo_file(path)`, `list_repo_files(...)` — see what little is there
- `git_create_branch`, `write_repo_file`, `git_add`, `git_commit`, `git_push`
- `create_pr(...)`
- `write_operation_log(...)` — mandatory

## Input contract

Same as `mcp-design-brownfield` but `mode == "greenfield"` and there are no relevant modules to find (workspace is empty).

## Phases

### Phase 1: Verify mode

`analyze_repo_state()`. If `mode != "greenfield"`, stop and tell the Agent to switch to `mcp-design-brownfield`.

### Phase 2: Synthesize requirements

Read `ticket` carefully. For greenfield work, the ticket usually describes a system or capability rather than a single feature. Extract:

- **Functional requirements**: what the system must do
- **Non-functional requirements (NFR)**: performance, scale, latency, availability targets
- **Constraints**: company tech standards, security requirements, integrations, team size
- **Out-of-scope**: what's explicitly NOT being built

Read `linked_issues` if any exist — they often have additional context.

If NFRs are absent from the ticket, list reasonable defaults in "Open questions" rather than inventing specifics. Do not assume "must scale to 10M QPS" if the ticket doesn't say so.

### Phase 3: Pick the template

For greenfield:
- Brand-new whole project → `templates/greenfield/new_project.md`
- New service inside a multi-service org → `templates/greenfield/new_service.md`
- New module inside what's clearly going to be a monorepo → `templates/greenfield/new_module.md`

Default to `new_project.md` if unsure.

### Phase 4: Tech stack decision matrix

This is the highest-stakes part of greenfield design. For EACH dimension, propose
a recommendation, list alternatives, give rationale.

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
- **Recommended**: ONE choice (don't hedge in the recommendation column)
- **Alternatives considered**: 1-3, briefly
- **Rationale**: 1-2 sentences. Reference team familiarity, requirements, ecosystem maturity.

If the ticket / linked tickets specify any of these (e.g., "must use the company Java stack"), record them and note "constrained by ticket".

Mirror the recommended values in the frontmatter `proposed_stack` so downstream stages can read them programmatically.

### Phase 5: High-level architecture

A diagram (mermaid or ASCII) showing major modules + data flow + external dependencies. Aim for 5-10 boxes — too many is over-engineering at design time.

### Phase 6: Project skeleton

Lay out the directory structure. NOT generated yet — Stage 2 (`mcp-implement-*`) or `bootstrap_project` MCP tool will create it. The design just states what it should look like.

```
{{ project-name }}/
├── pyproject.toml
├── ...
```

Match the recommended language/framework conventions.

### Phase 7: Phasing plan

Greenfield projects almost always need to be sequenced. Lay out phases:

| Phase | Sub-task (suggested Jira ticket) | Deliverable |
|---|---|---|
| 1 | Skeleton + smoke test | `curl /health` returns 200 |
| 2 | DB layer + first model | One read + write works |
| 3 | First feature endpoint | One real user-facing endpoint |
| ... | ... | ... |

This becomes the sub-task breakdown the Epic eventually fans out into.

### Phase 8: Write + branch + push + PR

Same shape as brownfield Phase 6-7. Branch name: `design/{JIRA_KEY}-greenfield-{slug}`.

PR body should make explicit that this is a **tech stack decision request**, not just a design — the human reviewer is approving choices that will shape the project for years.

### Phase 9: Write the operation log (MANDATORY)

Same shape as brownfield, but key fields differ:

- `outputs.proposed_stack` should include the tech stack decisions (so downstream
  Stage 2 skills can reference)
- `engineering_decisions` should explain WHY each major stack pick was made — this
  is the audit trail for "why are we using X?" questions a year from now
- `what_i_could_not_do` for greenfield often includes "validate stack against
  company-wide policies" if you don't know them

### Phase 10: Report

Tell user:
- The design PR with the stack decision matrix
- A bulleted summary of the recommended stack
- That this is a tech-stack-decision review — not just routine design — so
  reviewers should pay attention to that section

## Special rule: when in doubt, ask in "Open questions"

Greenfield design has more unknowns than brownfield. It's better to leave 5-10
explicit open questions in the doc than to make up plausible-sounding decisions.
The reviewer (and the eventual Stage 2 implementer) needs to know what's been
decided vs. what was assumed.

## Operation log honesty

If you didn't actually compare alternatives for a stack dimension and just picked
"the obvious one", say so in `engineering_decisions`:

```
- Picked PostgreSQL: did not benchmark MongoDB alternative; relying on team
  familiarity and existing infra. Open question for reviewer.
```

This is fine. Hidden hand-waving is not.
