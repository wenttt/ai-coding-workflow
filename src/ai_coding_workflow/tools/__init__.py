"""MCP tools exposed to the IDE Agent.

Each module in this package contributes a related set of tools:

- jira: read Jira tickets, update status
- github: PRs, comments, reviews
- git: diff, log, branches (subprocess wrapper)
- repo: file system operations on the workspace
- tests: discover and run tests (subprocess wrapper)
- workflow_state: which stage is a ticket in
- skill_router: which skill to invoke + input packaging
- escalation: 3-strike retry tracking + human handoff
"""
