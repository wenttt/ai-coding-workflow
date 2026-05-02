# Operation Log Schema

This is the single most important contract in the project.

Every skill, every retry, every stage transition writes one log file. These logs are:
- **The audit trail** — what did the Agent do, when, why
- **The retry input** — next attempt reads previous attempts to learn what failed
- **The escalation evidence** — when 3-strike kicks in, the logs are what humans review
- **The handoff record** — when humans take over, the logs explain how the Agent got here

## File path

```
{workspace_root}/{OPERATION_LOG_DIR}/{JIRA_KEY}/{NN}-{stage}-v{N}.md
```

Where:
- `OPERATION_LOG_DIR` is `docs/operations` by default
- `NN` is a 2-digit zero-padded sequence number per ticket (`01`, `02`, ...)
- `stage` is the canonical stage name: `design`, `design-revision`, `implement`, `self-review`, `test-write`, `test-run`, `pr-review-fix`, `deploy`, `doc-update`, `investigate`
- `N` is the retry number for this stage, starting at 1

Examples:
- `docs/operations/JIRA-123/01-design-v1.md` — first design attempt
- `docs/operations/JIRA-123/02-design-revision-v1.md` — first revision after rejection
- `docs/operations/JIRA-123/02-design-revision-v2.md` — second revision (still rejected, retry)
- `docs/operations/JIRA-123/03-implement-v1.md` — implementation
- `docs/operations/JIRA-123/04-self-review-v1.md` — self-review
- `docs/operations/JIRA-123/05-test-run-v1.md` — first test run (failed)
- `docs/operations/JIRA-123/05-test-run-v2.md` — retry
- `docs/operations/JIRA-123/05-test-run-ESCALATED.md` — 3-strike escalation

## File format

YAML frontmatter + Markdown body. The frontmatter is machine-readable; the body is human-readable but structured.

```markdown
---
jira_key: JIRA-123
stage: implement
revision: 1
status: completed | failed | escalated
skill_invoked: mcp-implement-backend
agent: claude-code | copilot | cursor | other
timestamp: 2026-05-02T15:30:00Z
duration_seconds: 240
inputs:
  - design_doc: docs/designs/JIRA-123.md
  - context_files:
      - src/auth/
      - src/api/login.py
  - prior_logs:
      - docs/operations/JIRA-123/01-design-v1.md
outputs:
  files_created:
    - src/auth/oauth_handler.py
  files_modified:
    - src/api/login.py
    - .env.example
  files_deleted: []
  diff_summary:
    additions: 187
    deletions: 12
    files: 4
retry_context:
  previous_attempts: []        # for retry rounds, summarize earlier failures
  failure_signal: null         # what triggered the retry, if any
escalation_reason: null        # populated only when status: escalated
---

## What was done

Concrete, action-by-action description. Use bullets. Reference files by path.

- Read `design.md` frontmatter, extracted `affected_modules: [src/auth/, src/api/]`
- Read `src/auth/__init__.py` and `src/api/login.py` to understand current patterns
- Created `src/auth/oauth_handler.py` implementing the OAuth flow per design section 3.2
- Modified `src/api/login.py` to delegate to new handler (lines 24-47)
- Added `OAUTH_PROVIDER_URL` to `.env.example`
- Did NOT touch `src/auth/legacy/` (per design's "preserve backward compatibility")

## Impact

What changes for the system, the team, the next stage.

- 4 files changed (3 modified, 1 new), +187 / -12 lines
- No DB schema changes
- New required env var `OAUTH_PROVIDER_URL` — must be set before next deploy
- Public API surface: 1 new endpoint, 0 breaking changes

## What I could not do

Be specific. This is what tells the next stage (or the human) what's still open.

- Audit logging integration (per design section 4.1) — required internal SDK token I don't have, left a TODO at `src/auth/oauth_handler.py:78`
- Three error case classifications (token-expired-mid-request, refresh-loop-detected, provider-unreachable) — design didn't specify, used `senior-engineer`-style defaults
- Dependency upgrade `httpx>=0.28` — pyproject.toml constraint blocked, kept current version

## Engineering decisions

Decisions made under the design's silence, or where existing repo conventions had to be picked between alternatives. Future maintainers (or Stage 3 self-review) need to see these.

- All OAuth errors use error codes `AUTH-OAUTH-{4xx}` per existing `errno` table convention
- Reused `src/common/retry.py` decorator (already present), did not introduce a new retry library
- All new code follows project's async/await convention (no callbacks)

## Next step

What the Agent recommends as the next invocation.

- Invoke Stage 3: `mcp-self-review` against the new diff
- Then Stage 4 test: `mcp-test-write` followed by `mcp-test-run`
```

## Conventions

### When to write a new log

- Every successful skill invocation: one log
- Every failed retry: one log (incrementing `revision`)
- Every escalation: one log with `status: escalated`
- Every Agent decision that changes user-visible state (creating PR, pushing commit, etc.): one log

### When NOT to write a log

- Pure read operations (the Agent reading a file to understand context)
- The Agent's internal "thinking" steps that produce no artifact

### Log honesty

The "What I could not do" section is the most important. Skills MUST NOT silently skip parts of the task. If the design says do X and X cannot be done, the log explicitly says so.

This is a non-negotiable principle. Hidden gaps are worse than visible gaps.

### Retry context inheritance

When `revision > 1`, the new log's `retry_context.previous_attempts` summarizes (1-2 lines per attempt) what each prior attempt did and why it was rejected. This gives Stage-3 reviewers and human escalators a quick view of the trajectory without reading every prior log.

## Reading from logs (programmatic)

The `read_operation_logs(jira_key)` MCP tool returns a parsed list:

```python
[
    {
        "path": "...",
        "frontmatter": {...},  # parsed YAML
        "sections": {
            "what_was_done": "...",
            "impact": "...",
            "could_not_do": "...",
            "engineering_decisions": "...",
            "next_step": "..."
        }
    },
    ...
]
```

Skills doing retries call this to understand "what did the previous attempt try, and why did it fail?"
