---
name: mcp-test-run
description: Run the test suite, parse results, fix failing tests (or fix code under test), retry up to 3 times. Stage 4 (run) of the pipeline. The retry loop is the whole point of this skill.
---

# mcp-test-run

Run the tests written in `mcp-test-write` (and any existing tests). On failure, decide whether to fix the test or fix the code, apply the fix, and retry — up to `max_retries` times.

## Bash-free contract

MCP tools only:
- `run_tests`, `discover_test_files` — execution
- `read_repo_file`, `write_repo_file` — fix code or tests
- `git_diff`, `git_changed_files`
- `git_add`, `git_commit`, `git_push`
- `read_operation_logs`, `write_operation_log`
- `get_retry_count`, `escalate` — for the 3-strike rule

## Input contract

```python
{
  "jira_key": "PROJ-123",
  "stage": "test-run",
  "skill_name": "mcp-test-run",
  "ticket": {...},
  "design_doc_path": "...",
  "prior_operation_logs": [...],   # includes test-write log + previous test-run attempts if retrying
  "retry_count": N,                # 0 on first run; 1, 2, 3 on retries
  "max_retries": 3,
}
```

## Phases

### Phase 1: Check budget

`get_retry_count(jira_key, "test-run")`. If `attempts_so_far >= max_retries`, **stop**:

```python
escalate(
    jira_key=jira_key,
    stage="test-run",
    skill_invoked="mcp-test-run",
    agent="<agent>",
    reason=f"Tests failed {max_retries} times in a row. Cannot resolve automatically.",
    attempts_summary="<read from prior operation logs>",
    what_humans_need_to_decide=(
        "1. Are the failing tests valid (catching real bugs)? "
        "2. Or are the tests wrong? "
        "3. Or is the design wrong (forces impossible tests)?"
    ),
)
```

The user takes over.

### Phase 2: Run

```python
result = run_tests(test_paths=None)  # full suite
# Or if you want to scope: run_tests(test_paths=["tests/auth/test_oauth_handler.py"])
```

`result` has: `framework`, `command`, `exit_code`, `passed`, `failed`, `errors`, `skipped`, `stdout`, `stderr`, `timed_out`.

### Phase 3: Decide outcome

**All passing**:
- Status: `completed`
- Operation log records green run
- Next stage: open code PR (the Agent does this with `create_pr` MCP tool)

**Failures**:
- Status: depends on whether you can fix in this attempt

### Phase 4: Diagnose failures (if any)

For each failure (parse from stdout):
- Read the failing test file
- Read the file under test
- Decide: is this a **test bug** or a **code bug**?

Heuristics for distinguishing:

| Sign it's a code bug | Sign it's a test bug |
|---|---|
| Failure messages say what was expected vs got, mismatch is real | Test sets up wrong fixtures / wrong mocks |
| Multiple tests in the same area fail similarly | Only one test fails, others pass |
| Stack trace points to production code, not test code | Stack trace is in test file or fixture |
| Behavior contradicts the design's AC | Test asserts something the design didn't ask for |

If unclear: **assume it's a code bug**. Tests are usually right (especially ones from `mcp-test-write` based on design ACs).

### Phase 5: Fix

Apply the minimum fix:

- **Code bug**: read the failing code, apply the fix, ensure it doesn't break other tests
- **Test bug**: read the test, fix the test (e.g., wrong assertion, missing mock setup)
- **Both**: fix both, but in separate commits if practical

Do NOT:
- Skip / disable failing tests to make the suite green
- Catch the exception that the test is asserting on
- Change the assertion to match the buggy output ("oh, the test expected 5 but got 7, let me change it to 7")

If you find yourself wanting to do any of the above, that's a sign this is escalation territory.

### Phase 6: Commit the fix

```python
git_add([list of modified files])
git_commit(f"test-run: fix {failure_summary} (retry {revision}, {jira_key})")
git_push(impl_branch)
```

### Phase 7: Re-run

Go back to Phase 2. If green, move to Phase 8. If still failing:
- If retry budget remaining: log the attempt and try again (loop to Phase 4)
- If at retry limit: escalate (Phase 1's check)

### Phase 8: Operation log

```python
write_operation_log(
    jira_key=jira_key,
    stage="test-run",
    skill_invoked="mcp-test-run",
    agent="<agent>",
    status="completed",  # or "failed" if escalating
    what_was_done="""
Run 1: 11 passed / 2 failed (test_oauth_callback, test_token_refresh)
  - Diagnosed: code bug. handler.refresh() didn't handle empty refresh_token.
  - Fix: src/auth/oauth_handler.py:91 added null check.
  - Pushed commit abc123.

Run 2: 13 passed / 0 failed.
""",
    impact="""
- 1 code fix applied: src/auth/oauth_handler.py
- Final test result: all 13 tests passing
- 1 commit added to impl branch
""",
    what_i_could_not_do="""
- Could not verify the fix doesn't break in real OAuth provider scenarios
  (no test credentials)
""",
    engineering_decisions="""
- Diagnosed run 1 failures as code bugs (not test bugs) because:
  - Test assertions matched the design AC literally
  - Failure was a NoneType crash in production code path
- Did not change tests; only changed src/auth/oauth_handler.py
""",
    next_step="""
All tests passing. Open code PR for human review:
- Branch: impl/PROJ-123-...
- Title: [PROJ-123] Implement: <ticket summary>
- Body should reference design PR + test results
""",
    retry_context={
        "previous_attempts": [
            "v1: 11 passed / 2 failed — null deref bug in refresh()",
        ],
        "failure_signal": None,
    },
    outputs={
      "final_test_count": {"passed": 13, "failed": 0, "skipped": 0},
      "retries_used": 1,
      "fixes_applied": ["src/auth/oauth_handler.py"],
    },
)
```

### Phase 9: Report

Tell user:
- Test outcome (final)
- How many retries used
- What fixes were applied
- Suggest opening the code PR (or, if escalated, suggest human inspection)

## Escalation example

If after 3 retries tests still fail, the escalation log should be specific:

```
Escalation reason:
"The test test_token_refresh fails because the OAuth provider's refresh token
TTL behavior is non-deterministic in our test environment. Three attempts to
fix:
- v1: tightened mock — still flaky
- v2: increased test timeout — still flaky
- v3: stubbed provider entirely — broke other tests

This is an environment / strategy decision. Options:
- Mark the test as integration-only, run in a different harness
- Get a sandbox OAuth provider for testing
- Re-design the refresh flow to be more deterministic
"
```

## Honesty principle

Don't quietly skip a test to ship green. The test is there for a reason. If it's actually wrong, fix it explicitly. If you're unsure whether it's wrong, escalate. The pipeline is designed to make you stop rather than fudge.
