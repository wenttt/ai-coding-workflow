"""AI Coding Workflow MCP Server.

A Model Context Protocol server that orchestrates a full software development
pipeline (Jira -> design -> implement -> review -> test -> deploy) by routing
each stage to a domain-specific skill.

The server itself does no LLM work. It provides:
- Data tools (Jira, GitHub, local repo, git)
- State tools (operation logs, retry tracking, escalation)
- Orchestration tools (skill routing, input packaging)

The IDE-side Agent (Copilot / Claude Code / Cursor) drives the pipeline by
reading state, calling tools, and invoking skills per stage.
"""

__version__ = "0.1.0"
