---
name: mcp-self-review
description: Self-review the diff produced by Stage 2 (implementation) before opening a code PR for human review. Combines code-review's defect catching with senior-engineer's architectural judgment. Stage 3 of the pipeline.
---

# mcp-self-review

You are reviewing your own code from Stage 2 before any human sees it. The goal is to catch the issues that would otherwise burn a human reviewer's first round of comments.

## Bash-free contract

MCP tools only:
- `git_diff`, `git_changed_files` — see what was changed
- `read_repo_file` — read changed files + their neighbors for context
- `read_repo_file(design_doc_path)` — re-read design to check alignment
- `find_relevant_modules` — find similar patterns elsewhere in the repo
- `read_operation_logs` — see what the implementer flagged in `what_i_could_not_do`
- `write_operation_log` — mandatory

Optionally, on retry:
- `read_operation_log` of the prior self-review to know what was already fixed

## Input contract

```python
{
  "jira_key": "PROJ-123",
  "stage": "self-review",
  "skill_name": "mcp-self-review",
  "ticket": {...},
  "design_doc_path": "...",
  "prior_operation_logs": [...],   # design + implement logs
  "retry_count": 0,
  "max_retries": 3,
  "impl_branch": "impl/PROJ-123-...",
}
```

## Phases

### Phase 1: Read everything

- Design doc (frontmatter + body)
- Implement operation log: especially `what_i_could_not_do` and `engineering_decisions`
- `git_diff(from_ref="main", to_ref="HEAD", stat_only=True)` — overview
- `git_changed_files(from_ref="main", to_ref="HEAD")` — list

### Phase 2: Read each changed file in context

For each changed file:
- `read_repo_file(path)` — full content
- Read 1-2 nearby files in the same module — what do they look like? (Style consistency)

### Phase 3: 6-pass review

Run six focused passes. Don't try to do them all at once — one pass per concern, write findings.

#### Pass 1: Design alignment
- Are all `affected_modules` from the design's frontmatter actually touched?
- Are there modifications outside `affected_modules` without justification in the implement log?
- Does each AC in the frontmatter have a clear "this code does that" mapping?
- Are explicit non-goals respected?

#### Pass 2: Defects (severity-tiered)
**Severity 1 (must fix before PR):**
- Bug that will fail tests or break existing functionality
- Security: SQL injection, XSS, hardcoded secrets, unvalidated input from a trust boundary
- Resource leak: file handle / connection / goroutine not released
- Race condition / deadlock potential
- Wrong import (would fail at runtime)

**Severity 2 (should fix before PR):**
- Performance regression in a hot path (N+1 query, redundant work in loop)
- Error handling: catch-and-swallow, generic exception when a specific one is meaningful
- Missing nullability check / boundary check that the design implies
- Public API breaking change not flagged in operation log

**Severity 3 (nice to fix; OK to flag in PR):**
- Style drift from project conventions
- Naming inconsistencies
- Missing comments on non-obvious logic
- Test gaps for edge cases

#### Pass 3: Engineering judgment (senior-engineer-flavored)
- Data flow: trace one critical path end-to-end. Does it make sense?
- Blast radius: what breaks if this change is wrong?
- Reusability: was an existing utility duplicated instead of imported?
- Error handling consistency: does new code use the project's errno/exception style?
- Resource management: connections / files / locks all paired with release?

#### Pass 4: What the implementer flagged
For every item in the implement log's `what_i_could_not_do`:
- Is the flag accurate (it really wasn't done)?
- Was the right TODO marker / comment left in code?
- Should it block the PR or just be noted?

#### Pass 5: Honesty pass
Quick scan for anti-patterns:
- `# TODO` without a Jira link
- `# FIXME` left intentionally? Why?
- Commented-out code blocks (delete or document why)
- Print statements / debug logs that should be removed or set to debug level
- Test files with skipped tests (`@pytest.mark.skip`, `it.skip`) — why?

#### Pass 6: Operability
- Are config changes (`.env.example`) documented?
- Are new dependencies in lockfiles?
- Are new env vars referenced consistently?
- Logging: are key events logged at appropriate levels?

### Phase 4: Decide outcome

Based on findings, the review status is:

- **`completed`** with `body_sections.what_was_done` listing zero or only Severity-3 findings — green light to next stage
- **`completed`** with Severity-1 or Severity-2 findings — code requires fix before PR; the Agent should NOT proceed to test stage. Status is `completed` (review itself was thorough), but the operation log's `next_step` says "fix Sev-1/2 then re-run mcp-self-review or proceed manually"
- **`failed`** — only if the review itself couldn't be done (e.g., couldn't read the diff). NOT for "found problems."

### Phase 5: Operation log

Use a slightly extended schema for self-review — list findings explicitly:

```python
write_operation_log(
    jira_key=jira_key,
    stage="self-review",
    skill_invoked="mcp-self-review",
    agent="<agent>",
    status="completed",
    what_was_done="""
6-pass review of {N} changed files (+{additions}/-{deletions} lines).

## Severity 1 findings (must fix)
- [src/auth/oauth_handler.py:47] Missing null check on `tokens.refresh_token` — will NPE when provider doesn't issue refresh token
- ...

## Severity 2 findings (should fix)
- [src/api/login.py:23] N+1 query in get_user_sessions — add prefetch
- ...

## Severity 3 findings (advisory)
- [src/auth/oauth_handler.py] Naming: project convention is `_validate_X` not `validateX`
- ...

## Design alignment
- ✅ All affected_modules touched
- ⚠️ src/api/middleware.py modified, not in design — implementer flagged this in
  their log. OK rationale.
- ✅ All ACs have code mapping

## Implementer's flags reviewed
- [audit logging TODO at src/auth/oauth_handler.py:78] — accurate, OK to ship
  with this gap noted in PR
""",
    impact="""
Review found N Sev-1, M Sev-2, K Sev-3 findings.
Recommendation: {green light / fix Sev-1 then proceed / etc.}
""",
    what_i_could_not_do="""
- Could not verify performance claim about new endpoint without benchmarks
- Could not check downstream consumer compatibility (separate repo)
""",
    engineering_decisions="""
- Decided Sev-2 N+1 is acceptable in this PR because the path is admin-only
  (low traffic), but flagged for follow-up
- Did not run the linter (no shell access); style findings come from manual
  inspection only
""",
    next_step="""
{If clean}: Invoke Stage 4 — mcp-test-write
{If Sev-1/2 found}: Fix the listed findings, then re-run mcp-self-review
{If borderline}: Open code PR; let human reviewers weigh in on the borderline calls
""",
    inputs={...},
    outputs={
      "files_reviewed": [...],
      "findings_count": {"sev1": N, "sev2": M, "sev3": K},
    },
)
```

### Phase 6: Report

Summarize for the user:
- Total findings count by severity
- The 1-2 most important ones
- Recommended next action

## Honesty principle

Self-review is the easiest stage to half-ass — it's tempting to declare "looks good" without actually reading the code. Don't. The whole pipeline's quality depends on this stage being thorough.

If you're tired of reviewing or the diff is huge (>500 lines), say so explicitly in the operation log: "Diff is large; my review focused on the {auth, api} subsets and was lighter on {migration, tests}." That's better than pretending you read it all.
