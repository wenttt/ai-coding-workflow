---
name: mcp-implement-backend
description: Implement backend code for a Jira ticket whose design has been approved. Reads the approved design doc + relevant existing code, writes new/modified files matching the project's conventions, and produces a structured operation log. Stage 2 (backend) of the pipeline.
---

# mcp-implement-backend

You are implementing the backend portion of a feature whose design was approved in Stage 1. The design doc is the spec; deviations require justification in the operation log.

## Bash-free contract

MCP tools only:
- `read_repo_file`, `list_repo_files`, `find_relevant_modules`
- `write_repo_file`
- `read_operation_logs(jira_key)` — read prior stages' decisions
- `git_create_branch`, `git_add`, `git_commit`, `git_push`
- `git_diff` — for self-checking
- `write_operation_log` — mandatory

## Input contract

```python
{
  "jira_key": "PROJ-123",
  "stage": "implement",
  "skill_name": "mcp-implement-backend",
  "ticket": {...},
  "mode": "brownfield" | "greenfield",
  "design_doc_path": "docs/designs/PROJ-123.md",
  "prior_operation_logs": [...],   # design + design-revision logs
  "retry_count": 0,
  "max_retries": 3,
}
```

## Phases

### Phase 1: Read the design

`read_repo_file(design_doc_path)`. Parse:
- Frontmatter `affected_modules` — files you should touch
- Frontmatter `ac` — acceptance criteria your code must satisfy
- Body section "Implementation outline" — the planned approach
- Body section "Engineering decisions" / "Risks" — constraints to respect

Read the latest design log (from `prior_operation_logs`) to see decisions made after the doc was written (if any revisions happened).

### Phase 2: Survey existing code (brownfield)

For each path in `affected_modules`, read it. Note:
- File header conventions (license, imports, docstrings)
- Function/class naming style
- Error handling patterns (exceptions, error codes, Result types)
- Logging style
- Testing patterns

You're matching style to the surrounding code. New code that looks alien gets pushback in self-review.

For greenfield, skip this — you're establishing conventions, not matching them. Reference the project skeleton from the design doc.

### Phase 3: Plan the change

Write down (mentally or in a scratch file) the diff plan:

```
Plan:
- New file: src/auth/oauth_handler.py
  - OAuthHandler class with methods: start_flow, handle_callback, refresh
- Modified: src/api/login.py
  - Add /oauth/callback endpoint
  - Inject OAuthHandler dependency
- Modified: .env.example
  - Add OAUTH_PROVIDER_URL, OAUTH_CLIENT_ID
- Untouched: src/auth/legacy/ — design says preserve backward compat
```

### Phase 4: Branch

`git_create_branch(name=f"impl/{jira_key}-{slug}", from_ref="main")`.

### Phase 5: Write the code

For each file in your plan:
- `read_repo_file` (if existing) to know the current state
- Compose the new content
- `write_repo_file(path, content)`

Order matters. Write data layer first, then domain, then API. This makes self-review easier — reviewers can read top-down.

**Anti-patterns to avoid (these get caught in self-review):**
- Adding an import for a library not already in the project's deps
- Introducing a new abstraction the design didn't ask for
- Silent feature flags or env-gated branches that the design didn't request
- "Quick fix" comments or `# TODO` markers without a Jira link

### Phase 6: Self-check the diff

`git_diff` to see what you've changed. Sanity check:
- Are all `affected_modules` from the design touched (or explicitly excluded)?
- Are any files outside `affected_modules` modified? If yes, can you justify?
- Is the line count reasonable for the scope?

If you went WAY over scope (e.g., refactored an unrelated module), revert that part. Implementation is not refactoring.

### Phase 7: Commit + push

```python
git_add([list of files])
git_commit(f"impl: {ticket.summary} ({jira_key})")
git_push(impl_branch)
```

Do NOT open the code PR yet. The pipeline opens the code PR after Stage 4 (test) passes. Stage 3 (self-review) and Stage 4 (test) happen on this branch first.

### Phase 8: Operation log (MANDATORY)

```python
write_operation_log(
    jira_key=jira_key,
    stage="implement",
    skill_invoked="mcp-implement-backend",
    agent="<agent>",
    status="completed",
    what_was_done="""
- Read design at docs/designs/{key}.md
- Surveyed existing code in [list]
- New file(s): [...]
- Modified file(s): [...]
- Did NOT modify: [list of nearby modules left alone, with reasons]
""",
    impact="""
- N files changed (X new, Y modified)
- +A / -B lines per git_diff stat
- 0 schema changes / N schema changes
- New env var(s): [...]
- New deps: [...] / NO new deps
- Breaking changes: [explicit list, or "none"]
""",
    what_i_could_not_do="""
- Design referenced internal SDK X for audit logging — token not configured;
  left a TODO at src/.../foo.py:78 with Jira reference
- Three error-case branches design didn't fully specify; used senior-engineer
  defaults — flagged in self-review for confirmation
""",
    engineering_decisions="""
- Followed existing errno format (AUTH-OAUTH-{4xx})
- Reused src/common/retry.py decorator (no new lib)
- All new code is async/await per project convention
- Deviated from design's class structure: [details + why]
""",
    next_step="""
Invoke Stage 3: mcp-self-review against this branch.
""",
    inputs={"design_doc_path": "...", "affected_modules_planned": [...]},
    outputs={
      "files_created": [...],
      "files_modified": [...],
      "diff_stat": {"additions": A, "deletions": B, "files": F},
      "branch": "impl/...",
    },
)
```

### Phase 9: Report to user

Tell them:
- Branch name + diff stat
- Major design deviations (if any)
- Anything in "What I could not do"
- Suggest invoking `mcp-self-review` next

## Failure modes

- **Design has internal contradictions** → Stop. Status `failed`, document the contradiction, suggest user re-open Stage 1 (revise design).
- **Required deps missing from project** → Stop. Don't add them silently. Status `failed`, list the deps in operation log.
- **Some `affected_modules` paths don't exist** → Continue best-effort, but flag prominently in `what_i_could_not_do`. Don't create unrelated files to "fill the gap."

## Honesty principle

If you implemented something the design DIDN'T specify (you noticed an obvious bug nearby and "while I'm here..."), STOP. Document it in `what_i_could_not_do` as "did not fix [thing] because it's out of scope; suggest separate Jira ticket". Drift is the #1 killer of code reviewability.
