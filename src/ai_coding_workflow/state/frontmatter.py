"""Read and write YAML frontmatter on Markdown files.

Used for two distinct artifact types in this project:

1. Design docs — `docs/designs/{KEY}.md` — the frontmatter is the contract
   between Stage 1 and downstream stages (`affected_modules`, `ac`, etc.).

2. Operation logs — `docs/operations/{KEY}/{NN}-{stage}-v{N}.md` — the
   frontmatter records what the Agent did, when, with what inputs.

Backed by the python-frontmatter library to keep the format compatible
with anything else that handles Jekyll-style YAML frontmatter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter


class FrontmatterError(ValueError):
    """Raised when a file's frontmatter is malformed or missing required fields."""


def read(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a file. Returns (frontmatter_dict, body)."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        post = frontmatter.load(f)
    return dict(post.metadata), post.content


def write(path: Path, metadata: dict[str, Any], body: str) -> None:
    """Write a file with frontmatter + body. Overwrites if exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body, **metadata)
    with path.open("w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
        f.write("\n")


def read_design_frontmatter(path: Path) -> dict[str, Any]:
    """Read just the frontmatter from a design doc, validating required fields.

    Required fields per OPERATION_LOG_SCHEMA conventions:
    - jira_key
    - mode (brownfield | greenfield)
    - ticket_type
    """
    metadata, _ = read(path)
    required = {"jira_key", "mode", "ticket_type"}
    missing = required - metadata.keys()
    if missing:
        raise FrontmatterError(
            f"Design doc {path} missing required frontmatter fields: {sorted(missing)}"
        )
    if metadata["mode"] not in {"brownfield", "greenfield"}:
        raise FrontmatterError(
            f"Design doc {path}: mode must be 'brownfield' or 'greenfield', "
            f"got {metadata['mode']!r}"
        )
    return metadata


def read_operation_log_frontmatter(path: Path) -> dict[str, Any]:
    """Read frontmatter from an operation log, validating required fields."""
    metadata, _ = read(path)
    required = {"jira_key", "stage", "revision", "status", "skill_invoked", "timestamp"}
    missing = required - metadata.keys()
    if missing:
        raise FrontmatterError(
            f"Operation log {path} missing required frontmatter fields: {sorted(missing)}"
        )
    return metadata
