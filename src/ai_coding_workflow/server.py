"""MCP server entry point.

Wires together all the tools defined in ai_coding_workflow.tools.* and exposes
them via FastMCP.

Run with:
    ai-coding-workflow

Or from Python:
    python -m ai_coding_workflow.server
"""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP

from .config import Config, load_config

log = logging.getLogger("ai_coding_workflow")


def build_server(config: Config) -> FastMCP:
    """Build and wire up the MCP server."""
    mcp = FastMCP(
        name="ai-coding-workflow",
        instructions=(
            "AI Coding Agent team workflow orchestrator. "
            "Drives a Jira ticket from design through deploy, calling project-specific "
            "skills at each stage, with operation logs and 3-strike escalation. "
            "See docs/ARCHITECTURE.md in this server's repo for the full model."
        ),
    )

    # Lazy imports — keeps startup fast and avoids import cycles
    from . import prompts
    from .tools import escalation, github, git, jira, repo, skill_router, tests, workflow_state

    jira.register(mcp, config)
    github.register(mcp, config)
    git.register(mcp, config)
    repo.register(mcp, config)
    tests.register(mcp, config)
    workflow_state.register(mcp, config)
    skill_router.register(mcp, config)
    escalation.register(mcp, config)
    prompts.register(mcp, config)

    return mcp


def main() -> int:
    """CLI entry point. Reads .env (if present), starts the server on stdio."""
    # Load .env from the working directory if available — purely a convenience for dev
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass  # dotenv is optional; in production env vars come from the IDE config

    try:
        config = load_config()
    except RuntimeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    log.info(
        "Starting ai-coding-workflow MCP server "
        "(workspace=%s, jira=%s, max_retries=%d)",
        config.workspace_path,
        config.jira_base_url,
        config.max_retries_per_stage,
    )

    server = build_server(config)
    server.run()  # blocks on stdio
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
