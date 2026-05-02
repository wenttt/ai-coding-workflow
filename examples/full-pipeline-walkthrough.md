# Full Pipeline Walkthrough

A realistic trace of one Jira ticket going from "open" to "closed" through the AI Coding Workflow pipeline. Read this end-to-end to understand how the pieces fit.

**Setting**: An existing brownfield project. Jira ticket `PROJ-123: Add OAuth login`.

---

## Invocation 1 — User starts the pipeline

```
User → IDE Copilot:
"Start working on PROJ-123."
```

**Agent's actions:**

1. `read_jira_ticket("PROJ-123")` →
   ```
   {
     "key": "PROJ-123",
     "summary": "Add OAuth login",
     "ticket_type": "user_story",
     "labels": ["backend", "auth"],
     ...
   }
   ```

2. `analyze_repo_state()` →
   ```
   {"mode": "brownfield", "code_file_count": 247, "languages": {".py": 180, ".ts": 67}, ...}
   ```

3. `get_workflow_state("PROJ-123")` →
   ```
   {"current_stage": "design", "next_action": "create_design", "retry_count": 0, ...}
   ```

4. `get_skill_chain_for_stage(stage="design", sub_mode="brownfield", ticket=..., workspace_state=...)` →
   ```
   [{"skill": "mcp-design-brownfield", "role": "primary"}]
   ```

5. `prepare_skill_input("PROJ-123", "design", "mcp-design-brownfield", ...)` →
   ```
   { jira_key, ticket, mode, design_doc_path, prior_operation_logs (empty), ... }
   ```

6. **Invoke skill `mcp-design-brownfield`** → reads ticket + finds modules + writes design doc + opens PR #45

7. `write_operation_log(...)` → `docs/operations/PROJ-123/01-design-v1.md`

**Agent reports to user:**

> Design PR #45 opened: https://github.com/.../pull/45
>
> Summary:
> - Touches src/auth/, src/api/login.py
> - Risk: medium
> - 5 acceptance criteria mapped
>
> Reviewers please leave comments on the markdown file. Call me again with `Continue PROJ-123` after review.

---

## Invocation 2 — User checks state after review

Reviewer @boss left CHANGES_REQUESTED on PR #45 with two comments.

```
User: "Continue PROJ-123"
```

**Agent's actions:**

1. `get_workflow_state("PROJ-123")` →
   ```
   {"current_stage": "design", "stage_status": "rejected", "retry_count": 0, "next_action": "revise_design", ...}
   ```

2. `find_pr_by_branch("design/PROJ-123-...")` → PR #45 with `review_decision: "changes_requested"`

3. `list_pr_review_comments(45)` → review comments

4. `get_skill_chain_for_stage(stage="design", sub_mode="revision", ...)` → `[{"skill": "mcp-design-revise", "role": "primary"}]`

5. **Invoke `mcp-design-revise`** → reads comments, applies edits, pushes new commit, replies on PR

6. `write_operation_log(...)` → `docs/operations/PROJ-123/02-design-revision-v1.md`

**Agent reports:**

> Revision 1/3 pushed to PR #45.
>
> Addressed:
> - @boss's tech-stack concern → switched to existing OAuth lib
> - @boss's risk concern → added rollback plan section
>
> Wait for re-review.

---

## Invocation 3 — Approved!

```
User: "Continue PROJ-123"
```

**Agent's actions:**

1. `get_workflow_state(...)` shows last stage `design-revision` completed, but PR is now **approved**.

2. The Agent's logic: "design approved means design phase is done; move to implement". Proceed.

3. (User merges the design PR. Or, the Agent's design-PR-merged step does it.)

4. `read_jira_ticket(...)` re-fetches; ticket labels include `backend` (and not `frontend`).

5. `get_skill_chain_for_stage(stage="implement", sub_mode="backend", ticket=...)` →
   ```
   [
     {"skill": "mcp-implement-backend", "role": "primary"}
     # (mcp-implement-db NOT included — no 'database' label)
   ]
   ```

6. **Invoke `mcp-implement-backend`** → reads design + existing code + writes new code + commits to `impl/PROJ-123-...`.

7. Operation log #03.

**Agent reports:**

> Implementation done on branch impl/PROJ-123-add-oauth-login.
> +187 / -12 lines, 4 files.
>
> Notable:
> - Audit logging hook left as TODO (SDK not configured)
>
> Suggest: invoke self-review next.

---

## Invocation 4 — Self review

```
User: "Continue PROJ-123"
```

**Agent's actions:**

1. `get_workflow_state(...)` — implement completed, next is self-review.

2. **Invoke `mcp-self-review`** → 6-pass review of the diff. Finds:
   - 1 Sev-1: missing null check on refresh_token
   - 2 Sev-3: minor style

3. Operation log #04 with all findings.

**Agent reports:**

> Self-review complete. Found:
> - 1 Severity-1 finding (must fix before PR)
> - 2 Severity-3 (advisory)
>
> Recommendation: fix the null check, then run tests.

---

## Invocation 5 — User fixes + asks Agent to continue

User reads the operation log, fixes the null check manually (or: invokes the Agent again with "fix the Sev-1 from self-review and continue"). Either way, the Agent then proceeds.

```
User: "Continue PROJ-123"
```

**Agent's actions:**

1. `get_workflow_state(...)` — self-review completed.

2. `get_skill_chain_for_stage(stage="test", sub_mode="write")` → `mcp-test-write`.

3. **Invoke `mcp-test-write`** → reads design ACs + reference test patterns + writes 11 tests.

4. Operation log #05.

5. Same invocation, the Agent continues to test-run (or you can split):

6. **Invoke `mcp-test-run`** → run #1: 9 passed / 2 failed. Diagnose: code bug in oauth_handler.py:91. Fix. Run #2: all 11 pass.

7. Operation log #06.

**Agent reports:**

> Tests: 11/11 passing on retry 1.
> 1 fix applied during retry.
>
> Ready to open code PR for human review.

---

## Invocation 6 — Open the code PR

```
User: "Open the PR for PROJ-123"
```

**Agent's actions:**

1. `create_pr(title="[PROJ-123] Implement: Add OAuth login", body="...", head_branch="impl/...", labels=[...])`

Body links to:
- Design PR #45
- Operation logs index in `docs/operations/PROJ-123/`
- Test results from latest test-run log

**Agent reports:**

> Code PR #67 opened: https://github.com/.../pull/67

---

## Invocation 7 — Code PR review (rejected)

@reviewer asks for a refactor in the comments. CHANGES_REQUESTED.

```
User: "Continue PROJ-123"
```

**Agent's actions:**

1. `get_workflow_state(...)` — code PR rejected, sub-stage is `pr-review-fix`.

2. `list_pr_review_comments(67)` → comments.

3. (No dedicated `mcp-pr-review-fix` skill in Day-1 — Agent uses `mcp-implement-backend` again with comments as input, OR invokes `mcp-investigate` if comments are unclear.)

4. Apply fixes, push, log.

5. Wait for re-review.

(This loop has the same 3-strike rule. After 3 cycles, escalate.)

---

## Invocation 8 — Approved + merged

User merges the code PR.

```
User: "Continue PROJ-123"
```

**Agent's actions:**

1. **Invoke `mcp-deploy`** → identifies deploy mechanism, triggers (or reports trigger), notes new env vars.

2. Operation log #08.

**Agent reports:**

> Deploy triggered. Watch dashboard at <url>.
> ⚠️ New env vars to set: OAUTH_PROVIDER_URL, OAUTH_CLIENT_ID
> Re-invoke me with "verify deploy for PROJ-123" once complete.

---

## Invocation 9 — Verify + close

After deploy completes successfully:

```
User: "Verify deploy for PROJ-123"
```

**Agent's actions:**

1. (User confirms verification — or Agent can read CI status if a tool is wired up.)

2. **Invoke `mcp-doc-update`** → updates README, ARCHITECTURE, CHANGELOG. Opens doc PR #128.

3. `update_jira_status("PROJ-123", "Done")`

4. Operation log #09.

**Agent reports:**

> Pipeline complete for PROJ-123.
>
> - Design PR #45 (merged)
> - Code PR #67 (merged)
> - Doc PR #128 (open)
> - Jira: closed
> - Operation logs: docs/operations/PROJ-123/01-09

---

## What the operation logs look like end-to-end

```
docs/operations/PROJ-123/
├── 01-design-v1.md
├── 02-design-revision-v1.md
├── 03-implement-v1.md
├── 04-self-review-v1.md
├── 05-test-write-v1.md
├── 06-test-run-v1.md
├── 06-test-run-v2.md       ← retry that fixed the bug
├── 07-pr-review-fix-v1.md  ← (if PR was rejected once)
├── 08-deploy-v1.md
└── 09-doc-update-v1.md
```

Anyone reading this directory in a year understands exactly what happened, what was tried, and why each decision was made.

---

## What an escalation looks like

If at any point a stage fails 3 times, you'd see:

```
docs/operations/PROJ-123/
├── 06-test-run-v1.md    ← failed
├── 06-test-run-v2.md    ← failed
├── 06-test-run-v3.md    ← failed
└── 06-test-run-ESCALATED.md
```

The ESCALATED file says what was tried, why nothing worked, and what humans need to decide. The Agent stops auto-retrying that stage. Human picks up.

After human resolves, the Agent can be re-invoked and the pipeline continues.
