"""Workspace repo file operations + project mode detection.

These are mostly thin wrappers, but they enforce the workspace boundary —
nothing can read/write outside config.workspace_path.

Greenfield bootstrap is here too, since it operates on the workspace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from ..config import Config


# A workspace is "greenfield" if it has fewer than this many code files
# (not counting README, .gitignore, LICENSE, etc.).
_GREENFIELD_FILE_THRESHOLD = 5

# Files we consider "scaffolding" rather than substantive code
_SCAFFOLDING_NAMES = {
    "README.md", "README", "README.rst",
    "LICENSE", "LICENSE.md", "LICENSE.txt",
    ".gitignore", ".gitattributes",
    "CHANGELOG.md", "CHANGELOG",
    "CONTRIBUTING.md", "AUTHORS", "MAINTAINERS",
    "pyproject.toml", "setup.py", "setup.cfg",  # project skeleton
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock",
    "go.mod", "go.sum",
    ".env.example", ".env.template",
}

# Extensions we count as substantive code
_CODE_EXTENSIONS = {
    ".py", ".pyi",
    ".ts", ".tsx", ".js", ".jsx", ".mjs",
    ".go", ".rs", ".java", ".kt",
    ".rb", ".php",
    ".c", ".cpp", ".cc", ".h", ".hpp",
    ".cs",
    ".swift", ".m",
}


def _is_inside_workspace(workspace: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _enforce_workspace(workspace: Path, relative_path: str) -> Path:
    target = (workspace / relative_path).resolve()
    if not _is_inside_workspace(workspace, target):
        raise ValueError(
            f"Path {relative_path!r} resolves outside the workspace; refused."
        )
    return target


def register(mcp: FastMCP, config: Config) -> None:
    workspace = config.workspace_path

    @mcp.tool()
    def read_repo_file(path: str, max_bytes: int = 200_000) -> str:
        """Read a file relative to the workspace root.

        Args:
            path: relative path under workspace (e.g., "src/auth/login.py")
            max_bytes: refuse files larger than this (returns a notice).
        """
        target = _enforce_workspace(workspace, path)
        if not target.exists():
            raise FileNotFoundError(f"File not found in workspace: {path}")
        if not target.is_file():
            raise IsADirectoryError(f"Not a file: {path}")
        size = target.stat().st_size
        if size > max_bytes:
            return f"<file too large: {size} bytes; use list_repo_files or chunked reads>"
        return target.read_text(encoding="utf-8", errors="replace")

    @mcp.tool()
    def list_repo_files(
        directory: str = "",
        glob: str = "**/*",
        include_hidden: bool = False,
        limit: int = 500,
    ) -> list[str]:
        """List files under a workspace directory matching a glob pattern.

        Returns paths relative to workspace root.
        """
        root = _enforce_workspace(workspace, directory) if directory else workspace
        if not root.exists() or not root.is_dir():
            return []
        out: list[str] = []
        for path in root.glob(glob):
            if not path.is_file():
                continue
            rel = path.relative_to(workspace)
            if not include_hidden and any(part.startswith(".") for part in rel.parts):
                continue
            out.append(str(rel))
            if len(out) >= limit:
                break
        return out

    @mcp.tool()
    def write_repo_file(path: str, content: str, create_parents: bool = True) -> dict[str, Any]:
        """Write a file (overwriting if exists). Restricted to the workspace."""
        target = _enforce_workspace(workspace, path)
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "path": path,
            "size_bytes": target.stat().st_size,
        }

    @mcp.tool()
    def analyze_repo_state() -> dict[str, Any]:
        """Detect whether the workspace is brownfield or greenfield.

        Counts substantive code files (by extension) excluding scaffolding.
        Returns: mode, code_file_count, languages, has_tests, has_ci.
        """
        code_count = 0
        languages: dict[str, int] = {}
        has_tests = False
        has_ci = False

        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(workspace)
            # Skip hidden dirs (.git, .idea, etc.) — but check .github separately
            parts = rel.parts
            if any(p.startswith(".") and p != ".github" for p in parts):
                continue
            if "node_modules" in parts or "__pycache__" in parts or "venv" in parts:
                continue

            name = path.name
            ext = path.suffix.lower()

            if name in _SCAFFOLDING_NAMES:
                continue
            if ext in _CODE_EXTENSIONS:
                code_count += 1
                languages[ext] = languages.get(ext, 0) + 1

            if "test" in name.lower() or "spec" in name.lower():
                has_tests = True

            if ".github" in parts and "workflows" in parts:
                has_ci = True

        mode = "greenfield" if code_count < _GREENFIELD_FILE_THRESHOLD else "brownfield"
        return {
            "mode": mode,
            "code_file_count": code_count,
            "languages": languages,
            "has_tests": has_tests,
            "has_ci": has_ci,
            "workspace_path": str(workspace),
        }

    @mcp.tool()
    def find_relevant_modules(
        keywords: list[str],
        max_files: int = 20,
    ) -> list[dict[str, Any]]:
        """Find files in the workspace matching any of the given keywords.

        Returns matches with: path, match_count, first_matching_line.
        Used by Stage 1 design to discover code modules relevant to a Jira ticket.
        """
        results: list[dict[str, Any]] = []
        keywords_lower = [k.lower() for k in keywords if k.strip()]
        if not keywords_lower:
            return []

        for path in workspace.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _CODE_EXTENSIONS:
                continue
            rel = path.relative_to(workspace)
            if any(p.startswith(".") for p in rel.parts):
                continue
            if "node_modules" in rel.parts or "__pycache__" in rel.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            text_lower = text.lower()
            match_count = sum(text_lower.count(k) for k in keywords_lower)
            if match_count == 0:
                continue

            first_line = ""
            for line in text.splitlines():
                if any(k in line.lower() for k in keywords_lower):
                    first_line = line.strip()[:200]
                    break

            results.append({
                "path": str(rel),
                "match_count": match_count,
                "first_matching_line": first_line,
            })

        results.sort(key=lambda r: r["match_count"], reverse=True)
        return results[:max_files]
