# Roadmap

What's done in Day-1, what's deliberately deferred, what's the order of attack later.

## Day-1 (this scaffold)

### ✅ Fully implemented

- **Project skeleton** — pyproject, README, env, gitignore, package layout
- **Architecture docs** — ARCHITECTURE / SKILL_ORCHESTRATION / OPERATION_LOG_SCHEMA / INSTALL / this file
- **State management** — operation_log read/write, retry counter, frontmatter parser
- **Core data tools** — Jira client, GitHub client, workspace repo reader, git wrapper
- **Skill router** — `get_skill_chain_for_stage`, `prepare_skill_input`
- **Operation logging** — schema fully defined, MCP tool to write/read
- **Retry / escalation** — 3-strike rule, escalation log writer
- **Skill mapping config** — `resources/skill_mapping.yaml` (forkable per team)
- **Design templates** — brownfield (user_story / task / sub_task / epic), greenfield (new_project / new_module / new_service)
- **Custom MCP-aware skills (12)** — design-{brownfield, greenfield, revise}, implement-{backend, frontend, db}, self-review, test-{write, run}, deploy, investigate, doc-update
- **PR conventions check** — GitHub Action enforcing JIRA-key in title, required body fields
- **Example walkthrough** — `examples/full-pipeline-walkthrough.md`

### 🟡 Implemented with caveats

- **Skills' depth varies** — design / self-review / investigate are most thorough (highest value, most-invoked). Implement / test / deploy lay out structure but expect refinement based on real usage.
- **Greenfield bootstrap** — `bootstrap_project` MCP tool generates directory tree + dependency manifest, but does not run package installs. Day-2 gap.
- **PR alignment check** — design-vs-impl alignment uses heuristics on `affected_modules` from frontmatter. A real semantic check is Day-2.
- **Test framework detection** — recognizes pytest, jest, junit conventions. Other frameworks need explicit config.

### ❌ Deliberately not in Day-1

- **Webhook-driven mode** — pull-based by design (see ARCHITECTURE.md)
- **Slack / email notifications** — MCP doesn't notify. The IDE Agent reports to its user.
- **Dashboard / web UI** — not needed; logs are markdown in the repo
- **Multi-LLM provider abstraction** — IDE's Copilot does the LLM work
- **api-migrate skill** — not generic. Forkable add-on.
- **Long-running daemon mode** — Agent invocations are one-shot

## Day-2 priorities (rank-ordered)

These pick up after Day-1 hits real Jira tickets and we see what hurts:

1. **Sharper test framework integration** — once a real first team picks pytest/jest/etc., harden the discovery + result-parsing for that one
2. **Real semantic alignment check** — code PR diff vs design's `affected_modules` and AC. Currently heuristic.
3. **Greenfield bootstrap with package installs** — `bootstrap_project` actually runs `npm install`, `pip install`, `cargo build`, etc.
4. **Skill input cache** — skills re-read context on every invocation. For long pipelines, cache.
5. **Cross-ticket dependencies** — what if JIRA-124 blocks on JIRA-123? Currently each ticket is independent.

## Day-N (someday)

- **Failure pattern learning** — read past escalation logs, propose preventive checks for next ticket
- **Per-team skill mapping diff tool** — show one team's skill_mapping vs the default
- **Time / token usage telemetry** — anonymized, opt-in, useful for tuning

## What we will NOT build

- A "platform" — this is a tool, not a product
- An LLM router — your IDE handles that
- A second project management system — Jira + GitHub + filesystem are enough
- A Slack bot wrapper — too easy to want, too easy to maintain badly

## Decision: when does a stage's skill graduate from "thin" to "production-hard"?

Heuristic: when 3 different real tickets have walked through that stage and at least 1 retry was needed at that stage. Then we have:
- Evidence the stage is exercised
- A real failure case to harden against
- Enough variety to avoid overfitting

Until then, the skill stays simple and we keep our hands off.
