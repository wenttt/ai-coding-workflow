---
name: mcp-deploy
description: Trigger deployment for a merged code PR via the project's existing CI/CD, monitor health, write operation log. Does NOT replace the project's deploy infrastructure — it triggers and verifies. Stage 5 of the pipeline.
---

# mcp-deploy

Trigger the project's existing deployment workflow and verify health.

## Bash-free contract

MCP tools only. The project's deploy is presumed to be a GitHub Actions workflow, ArgoCD app, or equivalent that's triggered by some signal (PR merge to main, manual workflow_dispatch, tag push).

You do NOT write deployment infrastructure here. You drive the existing one.

Tools you'll need:
- `read_repo_file` — read deploy config to understand the trigger mechanism
- `git_log`, `git_diff` — confirm what's being deployed
- (potentially) `create_pr` to a deploy branch, OR a custom MCP tool that's wired to the project's deploy mechanism

## Input contract

```python
{
  "jira_key": "PROJ-123",
  "stage": "deploy",
  "skill_name": "mcp-deploy",
  "ticket": {...},
  "code_pr_number": ...,           # already merged at this point
  "merge_sha": ...,
  "prior_operation_logs": [...],
  "retry_count": 0,
  "max_retries": 3,
}
```

## Phases

### Phase 1: Understand the project's deploy mechanism

Read project's deploy config to figure out the trigger:

- `.github/workflows/deploy*.yml` exists? → deploy is a GitHub Actions workflow
- `Dockerfile` + `helm/` or `k8s/` exists? → likely Kubernetes; what triggers an apply?
- `fly.toml` / `render.yaml` / `vercel.json`? → that platform's deploy
- `Procfile` + git push? → Heroku-style

If the project doesn't seem to have a deploy mechanism, **stop**. Status: `failed`. Tell the user this needs setup before the pipeline can include Stage 5.

### Phase 2: Pre-deploy checks

Before triggering, verify:
- The merge SHA is what's expected (matches the code PR's merge commit)
- No newer commits on main are about to be included that aren't relevant
- Required secrets / env vars are documented (read `.env.example` for changes)

If new env vars were added to `.env.example` since the last deploy, they MUST be added to the deploy environment too. Log this prominently in `what_i_could_not_do` if you don't have visibility into deploy env vars.

### Phase 3: Trigger

How depends on mechanism:

- **GitHub Actions deploy workflow**: an MCP tool extension can call `repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches` — propose this addition; for now, the Agent reports to the user "trigger workflow X manually" if no such tool exists
- **Auto-deploy on merge to main**: nothing to do; deploy is already running
- **ArgoCD with auto-sync**: nothing to do

When in doubt, the safest default is: tell the user what to do (specific URL / specific button to click) rather than do something destructive.

### Phase 4: Wait + verify

Without long-running daemon mode, "verify" means:
- The Agent reports the deploy was triggered
- The user invokes the Agent again later to check
- Or: the user invokes the Agent specifically to verify, and the Agent reads CI status / health endpoint via available MCP tools

### Phase 5: Operation log

```python
write_operation_log(
    jira_key=jira_key,
    stage="deploy",
    skill_invoked="mcp-deploy",
    agent="<agent>",
    status="completed",  # or "failed"
    what_was_done="""
- Identified deploy mechanism: GitHub Actions workflow `.github/workflows/deploy.yml`
- Trigger: push to main (auto)
- Confirmed merge SHA abc123 is the deploy target
- Triggered the workflow run (or noted that the auto-trigger fired)
- New env vars to set in production: OAUTH_PROVIDER_URL, OAUTH_CLIENT_ID
""",
    impact="""
- Deployment in progress (or queued)
- Production env requires OAUTH_PROVIDER_URL and OAUTH_CLIENT_ID — confirm with infra team
""",
    what_i_could_not_do="""
- Could not verify the deploy completed — needs follow-up invocation
- Could not check production env vars — no MCP tool wired up to the cloud provider
- Could not run smoke tests against production — same reason
""",
    engineering_decisions="""
- Did not trigger a manual workflow_dispatch; auto-trigger covers this case
- Did not modify any deploy YAML — out of scope for this stage
""",
    next_step="""
1. Confirm new env vars are set in production
2. Wait for deploy to complete (5-15min typical)
3. Re-invoke pipeline: 'verify deploy for PROJ-123'
4. If healthy: invoke Stage 6 (mcp-doc-update) and close the Jira ticket
""",
    outputs={
      "deploy_mechanism": "github-actions",
      "deploy_trigger": "auto-on-merge",
      "merge_sha": "abc123",
      "new_env_vars": ["OAUTH_PROVIDER_URL", "OAUTH_CLIENT_ID"],
    },
)
```

### Phase 6: Report

Tell the user:
- What was deployed (PR + SHA)
- How to verify (URL, dashboard, log query)
- Critical: any new env vars that must be set
- The next-invocation prompt to verify

## Failure modes

- **No deploy mechanism detected** → status `failed`, suggest user set one up before Stage 5 can be automated
- **Required secrets missing** → status `failed`, tell user what's missing
- **Deploy already in progress on a different commit** → status `failed`, tell user about the conflict

## Honesty principle

Deploys are the highest-stakes stage. **Be loud about uncertainties.** If you don't know whether new env vars are set, the operation log must say so prominently. Quiet shipping with hidden gaps is how outages happen.
