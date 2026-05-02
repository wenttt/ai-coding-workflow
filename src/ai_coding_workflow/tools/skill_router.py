"""Skill routing + input packaging.

Loads `skill_mapping.yaml` and answers two questions:
  1. Given (stage, sub_mode), which skill should I invoke?
  2. What inputs does that skill need (assembled from Jira + repo + logs)?
"""

from __future__ import annotations

from typing import Any

import yaml
from fastmcp import FastMCP

from ..config import Config
from ..state import operation_log


def _load_mapping(config: Config) -> dict[str, Any]:
    path = config.effective_skill_mapping_path
    if not path.exists():
        raise RuntimeError(
            f"Skill mapping not found at {path}. "
            f"Default ships with the package; override with SKILL_MAPPING_PATH."
        )
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _evaluate_condition(
    condition: str,
    *,
    ticket: dict[str, Any],
    workspace_state: dict[str, Any],
    extras: dict[str, Any] | None = None,
) -> bool:
    """Evaluate a simple condition expression. Deliberately limited grammar."""
    extras = extras or {}
    if not condition or condition.strip().lower() == "always":
        return True

    # Available bindings for conditions:
    labels = set(ticket.get("labels", []))
    components = set(ticket.get("components", []))
    mode = workspace_state.get("mode", "brownfield")

    # Predicate helpers
    def has_label(name: str) -> bool:
        return name in labels

    def has_component(name: str) -> bool:
        return name in components

    safe_globals = {
        "__builtins__": {},
        "has_label": has_label,
        "has_component": has_component,
        "mode": mode,
        "ticket": ticket,
        "labels": labels,
        "components": components,
        **extras,
    }

    try:
        return bool(eval(condition, safe_globals, {}))  # noqa: S307 - intentional limited eval
    except Exception:
        # If a condition fails to evaluate, treat as False (skill won't be added)
        return False


def register(mcp: FastMCP, config: Config) -> None:
    @mcp.tool()
    def get_skill_chain_for_stage(
        stage: str,
        sub_mode: str | None = None,
        ticket: dict[str, Any] | None = None,
        workspace_state: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve which skill(s) to invoke for the given stage.

        Args:
            stage: top-level stage key (e.g., "design", "implement", "self_review").
            sub_mode: sub-key within the stage (e.g., "brownfield" / "greenfield"
                for design, "backend" / "frontend" / "db" for implement).
            ticket: Jira ticket dict (for condition evaluation).
            workspace_state: from analyze_repo_state (for mode-based conditions).

        Returns:
            Ordered list of {"skill": "...", "role": "primary"|"supplementary"}.
        """
        mapping = _load_mapping(config)
        stage_block = mapping.get(stage)
        if stage_block is None:
            raise ValueError(
                f"Stage {stage!r} is not in skill_mapping. "
                f"Available stages: {sorted(mapping.keys())}"
            )

        if sub_mode is not None and sub_mode in stage_block:
            sub_block = stage_block[sub_mode]
        elif "primary" in stage_block:
            sub_block = stage_block
        else:
            raise ValueError(
                f"Stage {stage!r} requires a sub_mode (one of "
                f"{sorted(k for k in stage_block if k != 'primary')})."
            )

        out: list[dict[str, Any]] = []
        primary = sub_block.get("primary")
        if primary:
            out.append({"skill": primary, "role": "primary"})

        supplementary = sub_block.get("supplementary", []) or []
        ticket = ticket or {}
        workspace_state = workspace_state or {}
        for entry in supplementary:
            cond = entry.get("condition", "always")
            if _evaluate_condition(cond, ticket=ticket, workspace_state=workspace_state):
                out.append({"skill": entry["skill"], "role": "supplementary"})

        return out

    @mcp.tool()
    def prepare_skill_input(
        jira_key: str,
        stage: str,
        skill_name: str,
        ticket: dict[str, Any],
        workspace_state: dict[str, Any] | None = None,
        review_comments: list[dict[str, Any]] | None = None,
        extra_context_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Assemble the input package for a skill.

        Returns a dict with the cross-stage common fields plus any
        stage-specific fields. The skill's SKILL.md describes which fields
        it expects.
        """
        operation_log_root = config.operation_log_root
        prior_logs = operation_log.read_logs_for_ticket(operation_log_root, jira_key)
        prior_log_summaries = [
            {
                "path": str(log.path.relative_to(config.workspace_path)),
                "stage": log.stage,
                "revision": log.revision,
                "status": log.status,
                "skill": log.skill_invoked,
                "timestamp": log.frontmatter.get("timestamp"),
            }
            for log in prior_logs
        ]

        retry_count_for_stage = sum(
            1 for log in prior_logs
            if log.stage == stage and not log.is_escalated
        )

        return {
            "jira_key": jira_key,
            "stage": stage,
            "skill_name": skill_name,
            "ticket": ticket,
            "mode": (workspace_state or {}).get("mode", "brownfield"),
            "workspace_root": str(config.workspace_path),
            "design_doc_dir": config.design_doc_dir,
            "operation_log_dir": config.operation_log_dir,
            "prior_operation_logs": prior_log_summaries,
            "retry_count": retry_count_for_stage,
            "max_retries": config.max_retries_per_stage,
            "review_comments": review_comments or [],
            "extra_context_files": extra_context_files or [],
            "design_doc_path": f"{config.design_doc_dir}/{jira_key}.md",
        }
