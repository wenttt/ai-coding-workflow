---
name: mcp-doc-update
description: After deploy, update project documentation (README, ARCHITECTURE, CHANGELOG) to reflect what shipped. Stage 6 of the pipeline. Closes the loop on a Jira ticket.
---

# mcp-doc-update

Once code is shipped, project docs need to catch up. This skill keeps README / ARCHITECTURE / CHANGELOG / module READMEs in sync with the actual diff.

## Bash-free contract

MCP tools only:
- `read_repo_file`, `list_repo_files`
- `git_diff` from main back to the merge SHA — exactly what shipped
- `git_log` — recent commits for CHANGELOG context
- `find_relevant_modules` — find docs that might mention the changed area
- `write_repo_file`
- `git_add`, `git_commit`, `create_pr` (or push to main if convention allows)
- `update_jira_status` — close the ticket
- `write_operation_log`

## Input contract

```python
{
  "jira_key": "PROJ-123",
  "stage": "doc-update",
  "skill_name": "mcp-doc-update",
  "ticket": {...},
  "merge_sha": "abc123",
  "prior_operation_logs": [...],
  "deploy_status": "verified" | "in_progress" | "unknown",
}
```

## Phases

### Phase 1: Identify which docs need updating

Read these files (or whatever the project has):
- `README.md`
- `docs/ARCHITECTURE.md` (if exists)
- `CHANGELOG.md`
- `docs/api/` (if exists)
- Module-level READMEs near the changed code

For each, check: does it mention things that are now wrong because of the merge?

### Phase 2: Read the diff

`git_diff(from_ref=merge_parent_sha, to_ref=merge_sha, stat_only=True)` for an overview, then full diff for areas the docs talk about.

### Phase 3: Plan doc updates

Be conservative. Don't rewrite docs — apply targeted edits:

```
Plan:
- README.md
  - Section "Configuration": add OAUTH_PROVIDER_URL row
  - Section "Auth": mention OAuth as available alongside legacy
- docs/ARCHITECTURE.md
  - Section "Auth flow": update the diagram to include OAuth handler
- CHANGELOG.md
  - Add entry under Unreleased: "Added OAuth login support (PROJ-123)"
- src/auth/README.md (module-level)
  - Add brief description of oauth_handler.py
```

### Phase 4: Write CHANGELOG entry

If the project follows Keep a Changelog format (most do):

```markdown
## Unreleased

### Added
- OAuth login support (PROJ-123)
- New env vars: OAUTH_PROVIDER_URL, OAUTH_CLIENT_ID

### Changed
- Login flow now offers OAuth alongside legacy email/password
```

If the project uses semantic versioning, suggest a version bump in the operation log's `next_step` (don't bump version automatically; that's a release decision).

### Phase 5: Apply edits

`read_repo_file` → edit in memory → `write_repo_file`. Minimal, surgical changes.

### Phase 6: Commit + push

Two patterns common in projects:

- **Direct push to main** (small projects, doc-only changes are auto-merged): commit + push to main
- **Doc PR** (most teams): create a small PR with the doc changes; tag for quick review

Default to the doc PR pattern unless the project clearly auto-merges doc changes.

```python
git_create_branch(f"doc/{jira_key}-update", from_ref="main")
git_add([list of doc files])
git_commit(f"docs: update for {ticket.summary} ({jira_key})")
git_push(...)
create_pr(
    title=f"[{jira_key}] Docs: post-deploy updates",
    body=f"Doc updates following deploy of {jira_key}.\n\nMerge SHA: {merge_sha}",
    head_branch=branch,
    labels=[f"jira:{jira_key.lower()}", "stage:docs"],
)
```

### Phase 7: Close the Jira ticket

If `deploy_status == "verified"`:

```python
update_jira_status(jira_key, target_status="Done")  # or "Closed", per project workflow
add_jira_comment(jira_key, body=(
    f"Pipeline complete. Merged in {merge_sha}. "
    f"Doc PR: <link>. "
    f"Deploy verified."
))
```

If `deploy_status` is anything else, do NOT close. Leave a comment instead:

```python
add_jira_comment(jira_key, body=(
    f"Code merged and deployed (status: {deploy_status}). "
    f"Doc updates: <link>. "
    f"Ticket pending final deploy verification."
))
```

### Phase 8: Operation log

```python
write_operation_log(
    jira_key=jira_key,
    stage="doc-update",
    skill_invoked="mcp-doc-update",
    agent="<agent>",
    status="completed",
    what_was_done="""
- Reviewed diff against main (4 files, +187/-12)
- Updated README.md (2 sections)
- Updated docs/ARCHITECTURE.md (1 section, 1 diagram)
- Added CHANGELOG entry under Unreleased
- Updated src/auth/README.md (brief mention of new module)
- Opened doc PR #129
- Closed Jira ticket {jira_key} (set to Done)
""",
    impact="""
- 4 doc files updated
- 1 CHANGELOG entry added
- Jira ticket closed
""",
    what_i_could_not_do="""
- Did not update API reference docs at docs/api/openapi.yaml — auto-generated
  by CI, will be picked up next build
- Did not bump VERSION — left for release manager
""",
    engineering_decisions="""
- Used Keep-a-Changelog format (matches existing CHANGELOG)
- Doc PR rather than direct push (project convention)
- Closed Jira (deploy_status was 'verified')
""",
    next_step="""
Pipeline complete for {jira_key}. No further actions automated.
Optional: release manager may bump VERSION when next release is cut.
""",
    outputs={
      "doc_files_updated": [...],
      "doc_pr_number": 129,
      "jira_closed": True,
    },
)
```

### Phase 9: Report

The "we made it" report:
- Doc PR number + URL
- Jira closed (yes/no, why)
- Anything left for human follow-up
- Pipeline complete

## Honesty principle

Don't write doc updates for things you didn't actually verify. If the diff added a new endpoint, don't write "supports rate limiting" in the README unless the diff shows rate-limiting code. Operation log records what was confirmed; doc updates should only assert what's confirmed.

If you can't tell from the diff whether something is true (e.g., performance characteristics), don't put it in docs. Add it as a question in the doc PR description if curious.
