"""Git MCP tools.

Wraps git CLI via subprocess. The MCP server has shell access (it's a separate
Python process); skills do not. So skills call these tools instead of running
git directly.

All operations work in the configured WORKSPACE_PATH.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from ..config import Config


class GitError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise GitError(
            f"git command failed: {' '.join(shlex.quote(c) for c in cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


def register(mcp: FastMCP, config: Config) -> None:
    workspace = config.workspace_path

    @mcp.tool()
    def git_current_branch() -> str:
        """Return the current branch name in the workspace."""
        result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], workspace)
        return result.stdout.strip()

    @mcp.tool()
    def git_status(short: bool = True) -> str:
        """git status in the workspace.

        Args:
            short: if True, use --short format.
        """
        cmd = ["git", "status"]
        if short:
            cmd.append("--short")
        return _run(cmd, workspace).stdout

    @mcp.tool()
    def git_diff(
        from_ref: str = "HEAD",
        to_ref: str | None = None,
        path: str | None = None,
        stat_only: bool = False,
    ) -> str:
        """Return a diff in the workspace.

        Args:
            from_ref: base ref (default HEAD)
            to_ref: target ref (default working tree)
            path: optional path filter relative to workspace root
            stat_only: if True, return --stat output instead of full diff
        """
        cmd = ["git", "diff"]
        if stat_only:
            cmd.append("--stat")
        if to_ref:
            cmd.append(f"{from_ref}..{to_ref}")
        else:
            cmd.append(from_ref)
        if path:
            cmd.extend(["--", path])
        return _run(cmd, workspace).stdout

    @mcp.tool()
    def git_log(max_count: int = 20, path: str | None = None) -> str:
        """Recent commit log."""
        cmd = ["git", "log", f"-{max_count}", "--oneline", "--decorate"]
        if path:
            cmd.extend(["--", path])
        return _run(cmd, workspace).stdout

    @mcp.tool()
    def git_changed_files(from_ref: str = "HEAD", to_ref: str | None = None) -> list[str]:
        """List file paths changed between two refs (or vs working tree)."""
        cmd = ["git", "diff", "--name-only"]
        if to_ref:
            cmd.append(f"{from_ref}..{to_ref}")
        else:
            cmd.append(from_ref)
        result = _run(cmd, workspace)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    @mcp.tool()
    def git_create_branch(name: str, from_ref: str = "main") -> dict[str, Any]:
        """Create and checkout a new branch from from_ref."""
        _run(["git", "checkout", "-b", name, from_ref], workspace)
        return {"branch": name, "from": from_ref}

    @mcp.tool()
    def git_checkout(ref: str) -> dict[str, Any]:
        """Checkout an existing branch or commit."""
        _run(["git", "checkout", ref], workspace)
        return {"checked_out": ref}

    @mcp.tool()
    def git_add(paths: list[str]) -> dict[str, Any]:
        """Stage files."""
        cmd = ["git", "add", "--"] + paths
        _run(cmd, workspace)
        return {"staged": paths}

    @mcp.tool()
    def git_commit(message: str, allow_empty: bool = False) -> dict[str, Any]:
        """Create a commit with the given message. Stages must already be set."""
        cmd = ["git", "commit", "-m", message]
        if allow_empty:
            cmd.append("--allow-empty")
        _run(cmd, workspace)
        # Get the new SHA
        sha = _run(["git", "rev-parse", "HEAD"], workspace).stdout.strip()
        return {"sha": sha, "message": message}

    @mcp.tool()
    def git_push(branch: str | None = None, set_upstream: bool = True) -> dict[str, Any]:
        """Push the current (or named) branch to origin."""
        cmd = ["git", "push"]
        if set_upstream:
            cmd.append("-u")
        cmd.append("origin")
        if branch:
            cmd.append(branch)
        else:
            current = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], workspace).stdout.strip()
            cmd.append(current)
        result = _run(cmd, workspace)
        return {"stdout": result.stdout, "stderr": result.stderr}
