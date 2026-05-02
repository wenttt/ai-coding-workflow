---
name: mcp-test-write
description: Generate test code from the design doc's acceptance criteria. Reads the design's `ac` frontmatter, the implementation diff, and existing test patterns, then writes new test files. Stage 4 (write) of the pipeline.
---

# mcp-test-write

Write tests for the implementation done in Stage 2, using the design's acceptance criteria as the spec.

## Bash-free contract

MCP tools only:
- `read_repo_file`, `list_repo_files`, `find_relevant_modules`
- `discover_test_framework`, `discover_test_files`
- `git_diff`, `git_changed_files`
- `write_repo_file`
- `git_add`, `git_commit`, `git_push`
- `read_operation_logs`, `write_operation_log`

## Input contract

```python
{
  "jira_key": "PROJ-123",
  "stage": "test-write",
  "skill_name": "mcp-test-write",
  "ticket": {...},
  "design_doc_path": "docs/designs/PROJ-123.md",
  "prior_operation_logs": [...],
}
```

## Phases

### Phase 1: Read the inputs

- Design's frontmatter `ac` — these are the test cases (one test per AC, at minimum)
- Implement log's `outputs.files_created` and `files_modified` — knows what to test
- `discover_test_framework()` — pytest / jest / vitest / go-test / ...
- `discover_test_files(path_filter=<relevant subdir>)` — find existing tests for patterns

### Phase 2: Find a reference test file

`find_relevant_modules` with keywords from the changed code. Look at the closest existing test file to model on. Note:
- File naming convention (`test_X.py` vs `X.test.ts`)
- Import patterns
- Setup / teardown style (fixtures, hooks)
- Mock / stub patterns
- Assertion style

### Phase 3: Plan tests

For each AC in the design's frontmatter:

```
AC #1: "User can log in with email + password"
  → test_login_success
  → test_login_with_wrong_password
  → test_login_with_unknown_email
  → test_login_account_locked

AC #2: "User sees error on wrong password"
  → covered by test_login_with_wrong_password
```

Plus structural tests for new code:
- Constructor / factory edge cases
- Error path: every `raise` in the new code should have a test
- Boundary conditions: empty input, null input, max-size input

### Phase 4: Decide test type

- **Unit tests** — for pure logic (most new business code)
- **Integration tests** — for code paths that span modules (DB + service, API + service)
- **E2E tests** — only if the design explicitly calls for them, OR if the project has clear E2E conventions

Default to unit tests unless the AC requires integration. Don't over-build.

### Phase 5: Write the test file(s)

Match the reference file's structure exactly.

For each test:
- Clear test name describing what it tests
- Arrange / act / assert structure
- One logical assertion concept per test (multi-assert is OK if all cover one concept)
- Mocks only where needed — prefer real integration where cheap

### Phase 6: Verify the tests are findable

`discover_test_files()` after writing — your new files should appear. If not, you used the wrong naming convention.

### Phase 7: Commit + push (do not run tests yet)

```python
git_add([list of new test files])
git_commit(f"test: add tests for {ticket.summary} ({jira_key})")
git_push(impl_branch)
```

The next skill (`mcp-test-run`) actually runs them.

### Phase 8: Operation log

```python
write_operation_log(
    jira_key=jira_key,
    stage="test-write",
    skill_invoked="mcp-test-write",
    agent="<agent>",
    status="completed",
    what_was_done="""
- Read 4 ACs from design frontmatter
- Reference test file: tests/auth/test_legacy_login.py (matched its style)
- Test framework: pytest (detected)
- New test files:
  - tests/auth/test_oauth_handler.py — 8 tests covering AC #1, AC #2, plus 4 unit edges
  - tests/api/test_oauth_endpoint.py — 3 integration tests covering AC #3
- Total tests: 11
""",
    impact="""
- 2 new test files
- +N lines test code
- Coverage of: 4/4 ACs explicitly mapped to tests
""",
    what_i_could_not_do="""
- AC #4 mentions 'audit log' which isn't yet wired up (implementer flagged) — wrote
  a test that asserts the audit hook is called, but skipped for now
- E2E test from a real OAuth provider — would need test credentials; assumed
  out of scope
""",
    engineering_decisions="""
- Mocked the OAuth provider HTTP client (followed pattern in test_legacy_login.py)
- Did not add new test dependencies — used existing pytest + responses mock library
""",
    next_step="""
Invoke Stage 4 (run): mcp-test-run
""",
    outputs={
      "test_files_added": [...],
      "test_count": 11,
      "ac_coverage": {"covered": 4, "skipped": 0, "deferred": 0},
    },
)
```

### Phase 9: Report

Summarize:
- Test framework, count, files
- AC coverage map
- Any AC not covered (and why)
- Suggest invoking `mcp-test-run` next

## Honesty principle

If the design's ACs are vague (e.g., "should be fast"), don't write fake tests like `assert response_time < 999`. Either:
- Skip the test and flag in `what_i_could_not_do`
- Translate the AC to something concrete IF you have evidence (e.g., "design says 'fast'; project has a 1s SLO doc → wrote `assert response_time < 1000ms`")
- Open question in operation log: "what's 'fast' here?"

Don't pad the test count.
