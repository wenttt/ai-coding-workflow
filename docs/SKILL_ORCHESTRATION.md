# Skill Orchestration

How the Agent decides what to do next, and how skills are picked.

## The decision loop

When the user invokes the Agent ("look at JIRA-123" or "continue JIRA-123"):

```
1. Agent calls: get_workflow_state(jira_key="JIRA-123")
   Returns: {
     "current_stage": "design",
     "stage_status": "rejected",
     "retry_count": 1,
     "next_action": "revise_design",
     "skill_to_invoke": "mcp-design-revise",
     "blockers": []
   }

2. Agent calls: prepare_skill_input(jira_key, stage, skill_name)
   Returns: {
     "ticket": {...},
     "mode": "brownfield" | "greenfield",
     "template_path": "...",
     "prior_logs": [...],
     "review_comments": [...],
     "context_files": [...]
   }

3. Agent invokes the skill (using IDE's Skill tool, or manually following SKILL.md)

4. Skill writes its output (design doc, code changes, etc.) to the workspace

5. Agent calls: write_operation_log(jira_key, stage, ...)

6. Agent reports to user: "Done. Next: open the PR and request review."
```

Each invocation = one trip through this loop.

## Stage detection

`get_workflow_state` infers the current stage from the source-of-truth signals.

Stage 1 (design) is **Issue-driven**. Stage 2+ is **PR-driven**.

| Signal | Implies |
|---|---|
| No design Issue exists | Stage 1 (design) — `pending` |
| Design Issue is `open` | Stage 1 — `awaiting review` |
| Design Issue has comments newer than last revision log | Stage 1 — `changes requested` (next: revise) |
| Design Issue closed with `state_reason=completed` | Stage 1 approved -> Stage 2 (implement) `pending` |
| Design Issue closed with `state_reason=not_planned` | Design rejected -> escalate |
| Impl issue exists (assigned to @copilot), no code changes | Stage 2 — `in progress` |
| Code changes exist, no PR | Stage 3 (self-review) — `pending` |
| Code PR exists, status open | Stage 3 — `awaiting review` |
| Code PR has CHANGES_REQUESTED | Stage 3 — `rejected` |
| Tests not yet run | Stage 4 — `pending` |
| Tests failing | Stage 4 — `rejected` (next action: fix code or fix tests) |
| All checks pass, code PR not merged | `awaiting human merge` |
| Code PR merged, no deploy record | Stage 5 — `pending` |
| Deployed, Jira not closed | Stage 6 — `pending` |

Retry counts come from filesystem: `ls docs/operations/{KEY}/{NN}-{stage}-v*.md | wc -l`.

## Skill mapping

`src/ai_coding_workflow/resources/skill_mapping.yaml` is the routing table. Format:

```yaml
{stage_name}:
  {sub_mode}:                    # optional sub-key (e.g., backend / frontend / db)
    primary: {skill-name}
    supplementary:
      - skill: {skill-name}
        condition: "{condition expression}"
```

Conditions are simple expressions evaluated against the ticket + workspace state:
- `"ticket.has_label('database')"`
- `"design.affected_modules has 'src/db/'"`
- `"diff.lines_changed > 500"`
- `"mode == 'frontend'"`
- `"always"`

`get_skill_chain_for_stage` evaluates the conditions and returns the ordered list of skills to invoke for the current stage.

## Default skill mapping (Day-1)

```yaml
design:
  brownfield:
    primary: mcp-design-brownfield
  greenfield:
    primary: mcp-design-greenfield
  revision:                       # invoked when design PR is rejected
    primary: mcp-design-revise

implement:
  backend:
    primary: mcp-implement-backend
  frontend:
    primary: mcp-implement-frontend
  db:
    primary: mcp-implement-db

self_review:
  primary: mcp-self-review

test:
  write:
    primary: mcp-test-write
  run:
    primary: mcp-test-run

deploy:
  primary: mcp-deploy

post_deploy:
  primary: mcp-doc-update

bug_recovery:
  primary: mcp-investigate
```

`api-migrate` is intentionally NOT in the default mapping. It's for a specific migration scenario. Teams that need it can add it to their fork.

## Sub-mode selection (implement stage)

For Stage 2, the Agent picks `backend` / `frontend` / `db` based on:

1. Jira ticket labels (most reliable): `backend`, `frontend`, `database`
2. Design doc frontmatter `affected_modules`: paths matching backend/frontend/db conventions
3. Diff scope (if some implementation has started): which paths are touched

If multiple match, the Agent invokes them as a chain (e.g., backend + db for a feature that adds an API + a schema migration).

## Forking the mapping

A team that wants different routing copies `skill_mapping.yaml` to its repo, edits, and points the MCP server at its copy via `SKILL_MAPPING_PATH` env var.

This lets, e.g.:
- A team using a different test framework swap `mcp-test-run` for their own
- A team with no design review skip Stage 1
- A team adding `api-migrate` for a specific migration project

## Skill input contract

Every MCP-aware skill's SKILL.md begins with the input contract it expects from `prepare_skill_input`. The contract describes the JSON shape. Skills can rely on every field being present (or explicitly null).

Common fields across all skills:
- `jira_key`: e.g., "PROJ-123"
- `ticket`: full Jira ticket object
- `mode`: "brownfield" | "greenfield"
- `prior_operation_logs`: list of {stage, revision, content_path}
- `workspace_root`: absolute path
- `retry_count`: integer

Stage-specific fields are documented in each skill's `SKILL.md`.

## Skill output contract

Every skill writes one operation log file at `docs/operations/{JIRA_KEY}/{NN}-{stage}-v{N}.md` before exiting. See `OPERATION_LOG_SCHEMA.md` for the schema.

After writing, the skill returns to the Agent, which reports to the user.
