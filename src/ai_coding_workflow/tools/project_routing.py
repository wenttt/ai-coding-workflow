"""Project routing — map Jira project keys to GitHub repos and workspace paths.

For team-scale work where a developer's Jira tickets span multiple projects,
each backed by a different GitHub repo. The mapping lives in
`project_mapping.yaml` (path set via PROJECT_MAPPING_PATH env var, optional).

If no mapping is configured, all routing falls back to the configured
GITHUB_DEFAULT_OWNER / GITHUB_DEFAULT_REPO / WORKSPACE_PATH.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastmcp import FastMCP

from ..config import Config


@lru_cache(maxsize=1)
def _load_mapping_cached(path_str: str) -> dict[str, Any]:
    """Load and cache the project mapping YAML. Cache key is the path string."""
    with Path(path_str).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_mapping(config: Config) -> dict[str, Any] | None:
    """Load project mapping if configured. Returns None if not."""
    if not config.has_project_mapping:
        return None
    return _load_mapping_cached(str(config.project_mapping_path))


def _project_key_from_jira_key(jira_key: str) -> str:
    """Extract the project key from a Jira ticket key. PROJ-123 -> PROJ."""
    if "-" not in jira_key:
        return jira_key.upper()
    return jira_key.split("-", 1)[0].upper()


def _resolve(
    config: Config,
    project_key: str,
) -> dict[str, Any]:
    """Resolve project_key to routing info. Always returns a dict.

    Order of precedence:
    1. project_mapping.yaml `projects.<KEY>` block
    2. project_mapping.yaml `default` block
    3. Config defaults (env vars)
    """
    fallback = {
        "project_key": project_key,
        "github_owner": config.github_default_owner,
        "github_repo": config.github_default_repo,
        "workspace_path": str(config.workspace_path),
        "description": None,
        "default_base_branch": "main",
        "default_reviewers": [],
        "source": "env_defaults",
    }

    mapping = _load_mapping(config)
    if mapping is None:
        return fallback

    projects = mapping.get("projects") or {}
    if project_key in projects:
        entry = projects[project_key]
        return {
            "project_key": project_key,
            "github_owner": entry.get("github_owner") or fallback["github_owner"],
            "github_repo": entry.get("github_repo") or fallback["github_repo"],
            "workspace_path": entry.get("workspace_path") or fallback["workspace_path"],
            "description": entry.get("description"),
            "default_base_branch": entry.get("default_base_branch", "main"),
            "default_reviewers": entry.get("default_reviewers") or [],
            "source": "project_mapping",
        }

    default_block = mapping.get("default")
    if default_block:
        return {
            "project_key": project_key,
            "github_owner": default_block.get("github_owner") or fallback["github_owner"],
            "github_repo": default_block.get("github_repo") or fallback["github_repo"],
            "workspace_path": default_block.get("workspace_path") or fallback["workspace_path"],
            "description": default_block.get("description"),
            "default_base_branch": default_block.get("default_base_branch", "main"),
            "default_reviewers": default_block.get("default_reviewers") or [],
            "source": "project_mapping_default",
        }

    return fallback


def register(mcp: FastMCP, config: Config) -> None:
    @mcp.tool()
    def lookup_project_for_ticket(jira_key: str) -> dict[str, Any]:
        """Map a Jira ticket key to its GitHub repo + local workspace.

        Args:
            jira_key: e.g., "PROJ-123"

        Returns:
            project_key, github_owner, github_repo, workspace_path,
            description, default_base_branch, default_reviewers, source.

        `source` indicates where the routing came from:
        - "project_mapping": matched a specific project entry
        - "project_mapping_default": fell through to the default block
        - "env_defaults": no mapping configured at all (or no match + no default)

        Use this at the top of any pipeline invocation to know:
        1. Which GitHub repo should receive the design Issue / impl PR
        2. Which local workspace path the file ops should target
        3. Whether the current workspace matches (compare with current cwd /
           the WORKSPACE_PATH env)
        """
        project_key = _project_key_from_jira_key(jira_key)
        return _resolve(config, project_key)

    @mcp.tool()
    def list_projects() -> dict[str, Any]:
        """List all configured projects + the default fallback.

        Returns: { configured_projects: [...], default: {...}, has_mapping: bool }
        """
        if not config.has_project_mapping:
            return {
                "configured_projects": [],
                "default": {
                    "github_owner": config.github_default_owner,
                    "github_repo": config.github_default_repo,
                    "workspace_path": str(config.workspace_path),
                },
                "has_mapping": False,
                "note": (
                    "No project_mapping.yaml configured. All operations route to "
                    "the env-default repo and workspace."
                ),
            }

        mapping = _load_mapping(config)
        projects: list[dict[str, Any]] = []
        for key, entry in (mapping.get("projects") or {}).items():
            projects.append({
                "project_key": key,
                "github_owner": entry.get("github_owner"),
                "github_repo": entry.get("github_repo"),
                "workspace_path": entry.get("workspace_path"),
                "description": entry.get("description"),
            })

        default_block = mapping.get("default")
        return {
            "configured_projects": projects,
            "default": default_block,
            "has_mapping": True,
        }

    @mcp.tool()
    def affected_projects_for_ticket(
        jira_key: str,
        ticket_labels: list[str] | None = None,
        ticket_components: list[str] | None = None,
    ) -> dict[str, Any]:
        """Resolve all projects affected by a ticket — handles cross-project work.

        Single-project case (most common): returns just the primary.
        Cross-project case: ticket has `repo:foo` labels OR multiple components
        mapping to different projects. Returns primary + additional list.

        Args:
            jira_key: e.g., "PROJ-100"
            ticket_labels: from read_jira_ticket; checked for `repo:<name>` patterns
            ticket_components: from read_jira_ticket; checked against project keys

        Returns:
            primary_project: {...}                # always present
            additional_projects: [{...}, ...]     # empty list if not cross-project
            is_cross_project: bool
            all_workspaces: [paths]               # convenience for the agent
        """
        primary_key = _project_key_from_jira_key(jira_key)
        primary = _resolve(config, primary_key)

        additional_keys: set[str] = set()

        # Detect cross-project signals in labels (e.g., "repo:proj-frontend")
        for label in (ticket_labels or []):
            if not label.startswith("repo:"):
                continue
            repo_hint = label[len("repo:"):].strip().lower()
            # Match against configured projects
            mapping = _load_mapping(config) or {}
            for proj_key, entry in (mapping.get("projects") or {}).items():
                if (entry.get("github_repo", "") or "").lower() == repo_hint:
                    if proj_key.upper() != primary_key:
                        additional_keys.add(proj_key.upper())

        # Detect cross-project signals in components (component name == project key)
        mapping = _load_mapping(config) or {}
        configured_keys = {k.upper() for k in (mapping.get("projects") or {}).keys()}
        for component in (ticket_components or []):
            comp_upper = component.upper()
            if comp_upper in configured_keys and comp_upper != primary_key:
                additional_keys.add(comp_upper)

        additional = [_resolve(config, k) for k in sorted(additional_keys)]

        all_workspaces = [primary["workspace_path"]] + [
            p["workspace_path"] for p in additional
        ]

        return {
            "primary_project": primary,
            "additional_projects": additional,
            "is_cross_project": len(additional) > 0,
            "all_workspaces": all_workspaces,
        }

    @mcp.tool()
    def check_workspace_matches(jira_key: str) -> dict[str, Any]:
        """Check whether the current MCP-server workspace matches the ticket's project.

        Used by the pipeline prompt to decide whether to proceed or to ask
        the user to switch VS Code window.

        Returns:
            jira_key, project_key, expected_workspace_path, current_workspace_path,
            matches (bool), expected_repo, current_repo, suggestion.
        """
        project_key = _project_key_from_jira_key(jira_key)
        routing = _resolve(config, project_key)

        expected_workspace = Path(routing["workspace_path"]).resolve()
        current_workspace = config.workspace_path.resolve()

        matches = expected_workspace == current_workspace

        expected_repo = f"{routing['github_owner']}/{routing['github_repo']}"
        current_repo = f"{config.github_default_owner}/{config.github_default_repo}"

        if matches:
            suggestion = "OK to proceed in this workspace."
        else:
            suggestion = (
                f"This ticket belongs to project {project_key}, which maps to "
                f"workspace {expected_workspace}. "
                f"You're currently in {current_workspace}. "
                f"Open a VS Code window on the correct workspace and re-invoke."
            )

        return {
            "jira_key": jira_key,
            "project_key": project_key,
            "expected_workspace_path": str(expected_workspace),
            "current_workspace_path": str(current_workspace),
            "matches": matches,
            "expected_repo": expected_repo,
            "current_repo": current_repo,
            "suggestion": suggestion,
        }
