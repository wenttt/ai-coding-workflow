"""MCP prompts — slash-command entry points for the IDE Agent.

These are the "one-line UX" layer of the project. Each prompt wraps a full
stage's orchestration plan so the user doesn't have to write a multi-step
prompt every time.

In VS Code Copilot Chat (and other MCP clients), these show up in the
slash-command picker. Usage in chat:

    /ai-coding-workflow:pipeline jira_key=KAN-4
    /ai-coding-workflow:revise_design jira_key=KAN-4
    /ai-coding-workflow:investigate jira_key=KAN-4

When invoked, the prompt's text is inserted as the user's message to the
Agent, and the Agent then follows it.
"""

from __future__ import annotations

from fastmcp import FastMCP

from .config import Config


def register(mcp: FastMCP, config: Config) -> None:
    """Register all orchestration prompts."""

    @mcp.prompt(
        name="pipeline",
        description=(
            "Drive the AI Coding Workflow pipeline for a Jira ticket. "
            "Auto-detects the current stage and runs the right step."
        ),
    )
    def pipeline(jira_key: str) -> str:
        """Top-level entry. Reads workflow state and dispatches to the right stage."""
        return f"""\
You are running the AI Coding Workflow pipeline for {jira_key}. Follow this orchestration:

## Step 0: Detect current stage

1. Call `get_workflow_state(jira_key="{jira_key}")` to see what stage we're in.
2. The returned `next_action` and `current_stage` tell you which stage flow to follow below.

## If next_action is "create_design"

Stage 1 — Design (Issue-driven):
1. Call `read_jira_ticket("{jira_key}")` to get the ticket.
2. Call `analyze_repo_state()` — note the `mode` field (brownfield or greenfield).
3. Call `find_design_issue_for_jira("{jira_key}")` — should be `null` for first attempt.
4. Call `find_relevant_modules` with concrete keywords from the ticket summary/description.
5. Read the relevant skill at `.claude/skills/mcp-design-{{mode}}/SKILL.md` from the ai-coding-workflow project directory.
6. Follow the skill's phases to compose the design markdown (with YAML frontmatter).
7. Call `create_design_issue(jira_key="{jira_key}", title="[{jira_key}] Design: <summary>", body=<the markdown>, labels=["jira:{jira_key.lower()}", "stage:design"])`.
8. Call `write_operation_log` with stage="design".
9. Report the Issue URL to the user. STOP. Do NOT touch git/branches/PRs.

## If next_action is "revise_design"

Stage 1 revision:
1. Call `get_retry_count(jira_key="{jira_key}", stage="design-revision")`. If at limit, call `escalate(...)` and stop.
2. Call `find_design_issue_for_jira("{jira_key}")` to get the open Issue.
3. Call `list_issue_comments(issue_number)` for reviewer feedback.
4. Call `get_issue_state(issue_number)` for current body.
5. Call `read_operation_logs("{jira_key}")` for prior attempts.
6. Read the skill at `.claude/skills/mcp-design-revise/SKILL.md` and follow its phases.
7. Call `update_design_issue(issue_number, body=<revised body>)`.
8. Call `add_issue_comment(issue_number, body=<summary of changes>)`.
9. Call `write_operation_log` with stage="design-revision".
10. Report to user. STOP.

## If next_action is "trigger_implementation"

Stage 2 — Implementation (branch + PR):
1. Confirm design Issue is closed with `state_reason=completed` via `find_design_issue_for_jira`.
2. Read the design body from the Issue (NOT from a file — Stage 1 didn't commit any file).
3. Determine sub-mode (backend / frontend / db) from ticket labels and design's `affected_modules`.
4. Read the skill at `.claude/skills/mcp-implement-{{sub_mode}}/SKILL.md` and follow its phases.
5. The skill creates a `feat/{jira_key}-...` branch, writes code, commits, pushes.
6. Open the code PR with `Closes #<design_issue_number>` in the body.
7. Call `write_operation_log` with stage="implement".
8. Report to user. STOP — wait for the next user invocation to continue to Stage 3.

## If next_action is "self_review"

Run the `mcp-self-review` skill on the just-written code. Then stop.

## If next_action is "write_tests" or "run_tests" or "fix_failing_tests"

Run the `mcp-test-write` or `mcp-test-run` skill respectively. The latter has built-in 3-strike retry.

## If next_action is "deploy"

Run `mcp-deploy` skill. Reports what was triggered. Stops.

## If next_action is "update_docs"

Run `mcp-doc-update` skill. Closes Jira at the end.

## If next_action is "escalated"

Stop. Tell the user the pipeline has escalated and what humans need to decide. Reference the ESCALATED operation log.

## Critical rules

- After every stage, call `write_operation_log` BEFORE you stop.
- For Stage 1 (design), NEVER call git_create_branch / git_commit / git_push / create_pr. Stage 1 is Issue-only.
- For Stage 2+ (implementation onward), branches and PRs are normal.
- Skills are bash-free — call MCP tools instead of running shell commands directly.
- Always check `get_retry_count` before retrying a stage. 3 strikes -> escalate.

Begin now with Step 0.
"""

    @mcp.prompt(
        name="continue_pipeline",
        description=(
            "Continue the pipeline for a Jira ticket. Same as `pipeline` but phrased "
            "for resuming after reviewer action."
        ),
    )
    def continue_pipeline(jira_key: str) -> str:
        return pipeline(jira_key=jira_key)

    @mcp.prompt(
        name="my_tickets",
        description="List Jira tickets assigned to me across all projects, grouped by project, with current pipeline stage and workspace routing info.",
    )
    def my_tickets() -> str:
        return """\
Show me my open Jira tickets across ALL projects, grouped by project.

1. Call `list_my_tickets(include_project_routing=True)` — returns tickets across all
   projects with routing info per ticket (which repo, which workspace, whether current
   workspace matches).

2. For each ticket, call `get_workflow_state(jira_key=<key>)` to see its pipeline stage.

3. Group tickets by `project_key`. Within each group, present a table:
   Jira key | summary | ticket_type | current_stage | next_action | retry | workspace match

4. For tickets where `current_workspace_match=False`, show clear hint:
   "WARNING This ticket maps to workspace `<expected>`. To work on it, switch to that
    VS Code window first."

5. Highlight any escalated tickets prominently.

6. At the end, show a summary count by project AND a count of cross-workspace tickets.

Don't take any action — just report.
"""

    @mcp.prompt(
        name="check_routing",
        description="Check whether a Jira ticket maps to the current workspace, and report cross-project info.",
    )
    def check_routing(jira_key: str) -> str:
        return f"""\
Diagnose routing for {jira_key}:

1. Call `read_jira_ticket("{jira_key}")` to get labels + components.
2. Call `lookup_project_for_ticket("{jira_key}")` for primary project.
3. Call `affected_projects_for_ticket("{jira_key}", ticket_labels=<labels>, ticket_components=<components>)`.
4. Call `check_workspace_matches("{jira_key}")`.

Report:
- Primary project routing (repo + workspace)
- If cross-project: list ALL affected projects with their repos and workspaces
- Whether current workspace matches
- Suggested action: proceed here, or switch to which workspace, or run multi-repo plan
"""

    @mcp.prompt(
        name="design_for",
        description="Stage 1 only — produce the design Issue for a Jira ticket. Stops after the Issue is opened.",
    )
    def design_for(jira_key: str) -> str:
        return f"""\
Run ONLY Stage 1 (design) for {jira_key}. Stop when the GitHub Issue is opened.

1. `get_workflow_state("{jira_key}")` — confirm we're at design stage. If not, tell user and stop.
2. `read_jira_ticket("{jira_key}")`
3. `analyze_repo_state()` — note `mode`.
4. `find_design_issue_for_jira("{jira_key}")` — confirm no Issue exists.
5. `find_relevant_modules(...)` with keywords from the ticket.
6. Read `.claude/skills/mcp-design-{{mode}}/SKILL.md` and follow its phases.
7. Compose the design markdown.
8. `create_design_issue(...)`.
9. `write_operation_log(...)` with stage="design".
10. Report Issue URL.

Do NOT touch git, branches, or PRs. Stage 1 is Issue-only.
"""

    @mcp.prompt(
        name="implement_for",
        description=(
            "Stage 2 only — implement code for a Jira ticket whose design Issue was approved. "
            "Reads the closed design Issue, creates a branch, writes code, opens PR."
        ),
    )
    def implement_for(jira_key: str) -> str:
        return f"""\
Run Stage 2 (implementation) for {jira_key}. Pre-requisite: design Issue closed with state_reason=completed.

1. `find_design_issue_for_jira("{jira_key}")` — the Issue must exist and be closed/completed.
   - If state=open, stop — design isn't approved yet.
   - If state_reason=not_planned, stop — design was rejected; escalate.
2. `get_issue_state(issue_number)` — read the design body (this IS the design — Stage 1 didn't commit any file).
3. `read_jira_ticket("{jira_key}")` — re-fetch for current ticket state.
4. `analyze_repo_state()` — confirm brownfield or greenfield.
5. Determine sub-mode: backend / frontend / db (from ticket labels + design `affected_modules`).
6. Read the skill at `.claude/skills/mcp-implement-{{sub_mode}}/SKILL.md` and follow its phases.
7. Create branch `feat/{jira_key}-<slug>` from main.
8. Snapshot the design body to `docs/designs/{jira_key}.md` in the workspace as part of the commit.
9. Write the code per the design.
10. Push branch.
11. Open code PR with `Closes #<design_issue_number>` in the body.
12. `write_operation_log(...)` with stage="implement".
13. Report PR URL.
"""

    @mcp.prompt(
        name="investigate_for",
        description="Run mcp-investigate for a stuck/failing Jira ticket — root-cause + recovery recommendation.",
    )
    def investigate_for(jira_key: str) -> str:
        return f"""\
Run the `mcp-investigate` skill for {jira_key}.

1. `read_operation_logs("{jira_key}")` — read everything that's been tried.
2. `read_jira_ticket("{jira_key}")` — current state.
3. Read `.claude/skills/mcp-investigate/SKILL.md` and follow its 4-step method:
   Symptom -> Data -> Hypothesis -> Validate.
4. `write_operation_log` with stage="investigate", body documenting the debug report.
5. Report the recommended recovery stage (which earlier stage to re-invoke).
"""
