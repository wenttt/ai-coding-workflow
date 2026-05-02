---
name: mcp-investigate
description: Systematic root-cause investigation when a stage fails repeatedly or something structurally goes wrong. Reads everything that's been tried, forms a hypothesis, validates it, writes a debug report. Cross-stage skill triggered by escalation or by the Agent's own judgment.
---

# mcp-investigate

When a stage has hit retry limits, or when something is structurally broken (not just a one-off failure), this skill takes over. It produces a debug report and recommends a recovery path — usually back to a specific earlier stage.

This skill subsumes both `investigate` (root-cause analysis) and `debug-method` (4-step methodology). Bash-free, MCP-only.

## Bash-free contract

MCP tools only:
- `read_operation_logs(jira_key)` — read EVERYTHING that's happened on this ticket
- `read_repo_file`, `list_repo_files`, `find_relevant_modules`
- `git_log`, `git_diff` — recent changes context
- `list_pr_review_comments` — what humans said about this work
- `discover_test_files`, `run_tests` — to verify hypotheses
- `write_operation_log`

## Input contract

```python
{
  "jira_key": "PROJ-123",
  "stage": "investigate",
  "skill_name": "mcp-investigate",
  "ticket": {...},
  "trigger_reason": "<why investigation was triggered>",
  "failed_stage": "test-run",     # which stage repeatedly failed
  "prior_operation_logs": [...],  # ALL of them
}
```

## Phases — 4-step method

### Phase 1: Symptom (what is true?)

Read everything. Synthesize "what's actually happening" in 1-2 paragraphs. Be precise.

Examples of bad symptom statements:
- "Tests are flaky" (vague)
- "Something's wrong with auth" (vague)

Examples of good symptom statements:
- "test_token_refresh fails 100% of the time on retry attempts (3 of 3 runs). The test asserts that after a refresh, `session.access_token != original_token`. The actual behavior is that `session.access_token` is unchanged after refresh()."
- "The design PR was rejected 3 times. v1 by @boss for tech stack. v2 by @sec for missing audit log. v3 by @boss again, this time citing operational complexity. Each rejection cited different blocking concerns."

### Phase 2: Data (what evidence do I have?)

Collect, don't speculate yet. Read:
- All operation logs in chronological order — what was tried at each step?
- Test output (most recent run) — what's the actual failure mode?
- Code at the failure point — what's the surrounding logic?
- Git log — recent changes near the failure point
- PR review comments — what reasons were given for rejections?
- Linked Jira tickets — is there context elsewhere?

Don't form theories yet. Just gather.

### Phase 3: Hypothesis (what's the simplest explanation?)

State 1-3 hypotheses ordered by likelihood. For each:
- What it predicts you'd see
- What evidence already supports it
- What evidence would falsify it

Example:
```
Hypothesis A (most likely):
  refresh() returns the same access_token because the OAuth provider mock isn't
  rotating tokens between calls.
  Predicted: stub.access_token in mock returns a constant
  Existing evidence: mock fixture returns access_token="test-token-1" hardcoded
  Falsifier: mock fixture has dynamic token generation

Hypothesis B:
  refresh() short-circuits when expires_at hasn't passed, returning cached token
  Predicted: there's a cache-check in refresh() before the network call
  Existing evidence: src/auth/oauth_handler.py:88 has a `if not expired: return self.access_token`
  Falsifier: that line doesn't exist or has different logic
```

### Phase 4: Validate

Read or run something that disambiguates the hypotheses.

- For code-related: read the file, validate against the hypothesis prediction
- For test-related: `run_tests(test_paths=[specific test])` to confirm reproduction
- For design-rejection-related: read the PR comments and trace each rejection to the design body

State which hypothesis is confirmed. Or, if none, go back to Phase 3 with new theories.

### Phase 5: Recommendation

The investigation's output is a recommendation, not a fix. The fix happens at the right stage:

- **If the issue is a code bug at the implementation level** → recommend re-running `mcp-implement-{backend|frontend|db}` with the diagnosis as input
- **If the issue is a test that's wrong** → recommend re-running `mcp-test-write` for the specific test
- **If the issue is a design flaw** → recommend re-opening Stage 1 with `mcp-design-revise` (or a new design entirely)
- **If the issue is environmental / infra / out of scope** → recommend human takeover with a specific runbook

### Phase 6: Operation log = debug report

```python
write_operation_log(
    jira_key=jira_key,
    stage="investigate",
    skill_invoked="mcp-investigate",
    agent="<agent>",
    status="completed",
    what_was_done="""
## Symptom

test_token_refresh fails 100% of runs (3 of 3 retries). Assertion error:
`assert old_token != new_token`. Actual: tokens are identical.

## Data gathered

- Operation logs: implement-v1, test-write-v1, test-run-v1/v2/v3 (all failed same way)
- src/auth/oauth_handler.py: refresh() at line 88-105
- tests/auth/test_oauth_handler.py: test_token_refresh at line 47

## Hypothesis (confirmed)

H1: refresh() short-circuits when token isn't yet expired, returning the
cached `self.access_token` unchanged. The test mock sets expires_at to far
in the future, so the short-circuit always triggers.

Confirmation: src/auth/oauth_handler.py:91 has `if datetime.utcnow() < self.expires_at: return self.access_token` — exactly the predicted behavior.

## Root cause

The test as written exercises a path that refresh() considers a no-op. The
test is incorrect, OR the design's AC #2 ("user can refresh access_token") is
itself ambiguous — does "refresh" mean "force new token" or "ensure unexpired
token"?

## Recommended fix path

Option 1 (preferred): Update the test to set expires_at in the past, forcing a
real refresh. Re-invoke mcp-test-write to update tests/auth/test_oauth_handler.py:47.

Option 2: Update the design AC to specify "force-refresh" semantics, then the
implementation needs an explicit force-refresh code path. This requires Stage 1
revision.

Choose Option 1 unless the design ambiguity matters to the product.
""",
    impact="""
- No code changes (investigation only)
- Diagnosis written; fix path identified
""",
    what_i_could_not_do="""
- Cannot decide between Option 1 and Option 2 without product input
- Cannot verify the OAuth provider's actual refresh semantics in production
""",
    engineering_decisions="""
- Concluded the test is wrong, not the code
- Recommended the test-write path (lower risk than design revision)
""",
    next_step="""
User to choose: Option 1 (re-test-write) or Option 2 (re-design).
Most likely: invoke mcp-test-write with this report as context.
""",
    outputs={
      "root_cause": "test mock sets expires_at too far in future",
      "recommended_recovery_stage": "test-write",
    },
)
```

### Phase 7: Report

Crisp summary of:
- Root cause in 1-2 sentences
- Recommended next action (which stage to re-invoke, with what context)
- The debug report path (operation log)

## Honesty principle

If you can't form a confident root cause, say so. Don't fabricate one to feel productive. "I couldn't isolate the cause; the most likely explanations are A and B; here's the data needed to disambiguate" is a valid investigation outcome — and gets the human the right next step.

The 3-strike rule already kicked in to summon you. Don't repeat the same mistake by rushing to a wrong conclusion.
