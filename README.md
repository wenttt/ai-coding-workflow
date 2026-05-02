# AI Coding Workflow MCP Server

A Model Context Protocol (MCP) server that turns GitHub Copilot / Claude Code / Cursor / any MCP client into a structured AI coding agent for full-pipeline team collaboration.

**This server provides the data plumbing and orchestration. The IDE Copilot does the LLM work. Skills do the procedural work. You and your team do the judgment.**

## What it does

Given a Jira ticket, the orchestrating Agent (your IDE Copilot) walks the full development pipeline, calling project-specific skills at each step:

```
Jira ticket
    ↓
[Stage 1: Design]            mcp-design-brownfield / mcp-design-greenfield
    ↓ (publishes a GitHub Issue with the design markdown)
[Human review on GitHub Issue]
    ↓ Issue closed `completed` (or comments → mcp-design-revise → loop, max 3)
[Stage 2: Implementation]    mcp-implement-{backend,frontend,db}
    ↓ (creates feat/{KEY}-* branch with code)
[Stage 3: Self review]       mcp-self-review
    ↓
[Stage 4: Test]              mcp-test-write → mcp-test-run (max 3 retries)
    ↓
[Code PR opened]             (PR body has `Closes #<design-issue>`)
    ↓ human review (or rejected → loop, max 3)
[Stage 5: Deploy]            mcp-deploy
    ↓
[Stage 6: Doc update]        mcp-doc-update
    ↓
[Jira closed]
```

**The split is deliberate**: design discussion lives in **Issues** (lightweight, no branches), code lives in **PRs** (with branch isolation for parallel team development).

Every step writes a structured operation log to `docs/operations/{JIRA-KEY}/`. After 3 failed retries on any stage, the pipeline escalates to a human.

## Design principles (non-negotiable)

1. **Pull-based, not webhook-driven.** Agent reads GitHub state when invoked, not the other way around.
2. **One step per invocation.** Human stays in the loop. No long-running daemons.
3. **Operation logs are first-class.** Every step writes `docs/operations/{KEY}/{NN}-{stage}-v{N}.md` with: did / impact / could-not / engineering-decisions / next.
4. **Rejection loops are main flow, not error handling.**
5. **3-strike escalation.** Auto-retry 3 times, then escalate to human.
6. **Skills are bash-free.** All shell operations go through MCP tools (which run in this server's process).
7. **Brownfield + Greenfield are first-class branches.** Stage 1 detects mode and dispatches.
8. **Skill mapping is configurable.** Each team can fork `resources/skill_mapping.yaml`.

## Quick start

See `docs/INSTALL.md` for IDE-specific setup (VS Code Copilot, Claude Code, Cursor).

```bash
# 1. Install
pip install -e .

# 2. Set credentials in .env
cp .env.example .env
# edit .env

# 3. Configure your IDE to use this MCP server
# (see docs/INSTALL.md)

# 4. In your IDE Agent, say:
# "Start working on JIRA-123"
```

## Project structure

```
ai-coding-workflow/
├── src/ai_coding_workflow/
│   ├── server.py          # MCP server entry point
│   ├── config.py          # Environment + paths
│   ├── state/             # Operation logs, retry tracking, frontmatter
│   ├── tools/             # MCP tools (Jira, GitHub, repo, git, tests, etc.)
│   └── resources/
│       ├── skill_mapping.yaml      # stage → skill routing (forkable)
│       └── templates/              # Design doc templates (brownfield + greenfield)
├── .claude/skills/        # MCP-aware custom skills (bash-free)
├── docs/                  # Architecture + protocol docs
├── examples/              # Full pipeline walkthroughs
└── tests/
```

## Documents to read in order

1. `docs/ARCHITECTURE.md` — Why pull-based, why skill-orchestrated, how it all fits
2. `docs/SKILL_ORCHESTRATION.md` — How `skill_mapping.yaml` routes stages to skills
3. `docs/OPERATION_LOG_SCHEMA.md` — The single most important contract in this project
4. `docs/INSTALL.md` — IDE-specific setup
5. `docs/ROADMAP.md` — What's done in Day-1 vs later
6. `docs/origin-design.md` — How this project was conceived (office-hours session, 2026-05-02). Historical record; superseded by ARCHITECTURE.md where they disagree.

## Status

**Day-1 scope** — see `docs/ROADMAP.md`:
- Stage 1, 3, 6 fully wired with custom skills
- Stage 2, 4, 5 have skills + tools, real-world coverage hardens with usage
- All cross-cutting tools (operation logs, retry, escalation) production-ready

This is intentionally not a "platform" yet. It is the smallest thing that proves the pipeline works on real Jira tickets.
