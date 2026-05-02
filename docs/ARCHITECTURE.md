# Architecture

## The whole thing in one diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  IDE Agent  (GitHub Copilot / Claude Code / Cursor)              │
│  ─────────────────────────────────────────────────────           │
│  Responsibilities:                                                │
│  - Read workflow state                                            │
│  - Decide which step is next                                      │
│  - Invoke the corresponding skill                                 │
│  - Write operation log                                            │
│  - Stop and report to user                                        │
│                                                                   │
│  Allowed tools: Read / Write / Edit + MCP tools                  │
│  NOT allowed: Bash / shell commands (terminal perms unreliable)  │
└──────────────────────────────────────────────────────────────────┘
            │                              │
            │ calls MCP tools              │ calls Skills
            ▼                              ▼
┌────────────────────────────┐    ┌────────────────────────────────┐
│  MCP Server (this repo)    │    │  Skills (in .claude/skills/)   │
│  ─────────────────────     │    │  ──────────────────────────    │
│  Independent Python proc   │    │  Procedural workflows          │
│                            │    │                                │
│  Tools:                    │    │  - mcp-design-brownfield       │
│  - Data: jira / github /   │    │  - mcp-design-greenfield       │
│    repo / git              │    │  - mcp-design-revise           │
│  - State: ops log /        │    │  - mcp-implement-{be,fe,db}    │
│    retry / escalate        │    │  - mcp-self-review             │
│  - Orchestration:          │    │  - mcp-test-{write,run}        │
│    skill_router            │    │  - mcp-deploy                  │
│  - Subprocess: tests /     │    │  - mcp-investigate             │
│    bootstrap               │    │  - mcp-doc-update              │
│                            │    │                                │
│  Can: subprocess, network, │    │  Bash-free. Read/Write/Edit    │
│  filesystem, anything      │    │  + MCP tools only.             │
└────────────────────────────┘    └────────────────────────────────┘
            │                              │
            ▼                              │
┌────────────────────────────┐             │
│  External / FS state       │             │
│  ─────────────────────     │             │
│  - Jira (ticket status)    │ ◄───────────┤  Reads/writes
│  - GitHub (PRs, comments)  │             │  via MCP tools
│  - Local repo              │             │  + Skills' file IO
│    - design docs           │             │
│    - operation logs        │ ◄───────────┘
│    - source code           │
└────────────────────────────┘
```

## Why this shape

### Why pull-based, not webhook-driven

The IDE Agent reads GitHub PR state on demand. No webhook server, no event queue, no missed events.

Reasons:
1. **Reentrant.** Kill the Agent mid-flow, restart it, no state lost — it re-reads.
2. **Fewer moving parts.** No webhook server to deploy, no SSL cert, no domain.
3. **Human stays in the loop.** Each user invocation = one decision. Nothing happens silently.
4. **Mirrors how skilled engineers actually work.** "What's the state? Now what should I do?"

Trade-off: nothing happens automatically. The user must invoke the Agent. This is a feature, not a bug.

### Why one step per invocation

The Agent does not run a long-lived loop trying to drive a Jira ticket from open to closed. Each user invocation:
1. Reads current state
2. Picks one next step
3. Executes it (calls tools, calls skills, writes operation log)
4. Reports to user
5. Exits

This avoids:
- Long-running Agent sessions burning tokens
- Surprises where the Agent does something the user didn't intend
- Hard-to-debug failure modes deep in a multi-hour loop

### Why skills, and why these specific skills

Each pipeline stage has a "primary skill" that codifies how to do that step. The Agent doesn't reinvent the workflow each time — it follows a battle-tested procedure.

Skills are stored in `.claude/skills/mcp-*` — versioned with the project. Different teams can fork the project and customize their skills.

Skills:
- Are bash-free (so they work in restricted IDE Agent environments)
- Take structured input (assembled by `prepare_skill_input` MCP tool)
- Produce structured output (operation log entry)
- Support retry with prior-attempt context (read previous operation logs)

### Why a separate MCP server (instead of putting everything in skills)

Two reasons:

1. **Shell access.** The IDE Agent (especially Copilot) may not have terminal permissions. The MCP server is a separate Python process that does. Anything requiring `git`, `gh`, `pytest`, `npm` lives in the server.

2. **Stateful infrastructure.** API tokens, connection pools, retry tracking, idempotency — these belong in a long-lived process, not a skill that runs once per invocation.

The MCP server is *deliberately* dumb about LLM work. It does plumbing, not thinking.

## State model

There is **no central state database**. State lives in three places, and we read from the source of truth on every invocation:

| State | Source of truth | Read via |
|---|---|---|
| Ticket status (open / in design / in dev / merged / done) | Jira | `read_jira_ticket` MCP tool |
| Design or code review state (open / changes-requested / approved / merged) | GitHub | `get_pr_state` MCP tool |
| Operation history (what's been tried, what failed) | `docs/operations/{KEY}/` in workspace | `read_operation_logs` MCP tool |
| Retry count for current stage | Count of operation log files | `get_retry_count` MCP tool |

Inferring "current stage" combines all four. See `docs/SKILL_ORCHESTRATION.md` for the decision logic.

## Brownfield vs Greenfield

Stage 1 (design) detects mode and routes to a different skill chain.

`analyze_repo_state` MCP tool returns:
- `brownfield`: the workspace has substantive code (more than README + .gitignore + a couple of scaffolding files)
- `greenfield`: workspace is effectively empty

In greenfield, the design step includes tech-stack selection, top-level architecture, and an initial scaffold plan. Brownfield design integrates with existing patterns.

## Failure handling

### Retry loop (in-stage)

A stage retries up to `MAX_RETRIES_PER_STAGE` (default 3) times. Each retry:
1. Reads previous operation log(s) for this stage
2. Reads the rejection reason (review comments, failed test output, etc.)
3. Adjusts and re-runs

After the limit, the Agent writes an `ESCALATED` log and refuses to continue without human intervention. `notify_escalation` MCP tool can post a comment to the relevant PR or Jira ticket to flag a human.

### Bug recovery (cross-stage)

When something goes structurally wrong (failing tests can't be fixed, design rejected for fundamental reasons, deploy failure), the Agent invokes `mcp-investigate`. This skill:
1. Reads everything that's been tried
2. Forms a hypothesis about root cause
3. Writes a debug report
4. Either proposes a fix at a different stage (e.g., "the design was wrong; redo Stage 1") or escalates

## What this is not

- Not a CI/CD platform. Existing GitHub Actions + Jenkins + ArgoCD do that.
- Not a project management tool. Jira does that.
- Not a code review tool. GitHub PR review does that.
- Not an LLM gateway. The IDE's Copilot is.

This is the connective tissue between Jira, GitHub, the workspace, and the IDE Agent — with enough structure to keep the Agent's work auditable and recoverable.
