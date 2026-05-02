"""Test discovery + execution.

Skills can't run pytest/jest/etc. directly because they may not have terminal
access. These tools run tests via subprocess in the workspace and parse the
results into a structured form skills can consume.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from ..config import Config


def _detect_test_framework(workspace: Path) -> str:
    """Sniff which test framework the workspace uses."""
    if (workspace / "pyproject.toml").exists() or any(workspace.glob("pytest.ini")):
        if any(workspace.rglob("test_*.py")) or any(workspace.rglob("*_test.py")):
            return "pytest"
    if (workspace / "package.json").exists():
        try:
            import json
            pkg = json.loads((workspace / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                if "jest" in str(scripts.get("test", "")):
                    return "jest"
                if "vitest" in str(scripts.get("test", "")):
                    return "vitest"
                return "npm-test"
        except Exception:
            pass
    if (workspace / "go.mod").exists():
        return "go-test"
    if (workspace / "Cargo.toml").exists():
        return "cargo-test"
    if (workspace / "pom.xml").exists() or (workspace / "build.gradle").exists():
        return "maven-or-gradle"
    return "unknown"


def _command_for(framework: str, test_paths: list[str]) -> list[str]:
    """Build the test invocation command."""
    if framework == "pytest":
        return ["pytest", "-x", "--tb=short"] + test_paths
    if framework == "jest":
        return ["npx", "jest"] + test_paths
    if framework == "vitest":
        return ["npx", "vitest", "run"] + test_paths
    if framework == "npm-test":
        return ["npm", "test"]
    if framework == "go-test":
        if test_paths:
            return ["go", "test"] + test_paths
        return ["go", "test", "./..."]
    if framework == "cargo-test":
        return ["cargo", "test"]
    raise RuntimeError(
        f"Don't know how to run tests for framework {framework!r}. "
        f"See docs/INSTALL.md to add explicit config."
    )


# Regexes to extract pass/fail counts from common test framework output
_PYTEST_RESULT_RE = re.compile(
    r"(\d+) passed|(\d+) failed|(\d+) error|(\d+) skipped"
)
_JEST_RESULT_RE = re.compile(
    r"Tests:\s+(?:(\d+) failed,\s+)?(?:(\d+) passed,?\s+)?(\d+) total"
)


def _parse_results(framework: str, stdout: str, stderr: str) -> dict[str, Any]:
    combined = (stdout or "") + "\n" + (stderr or "")
    passed = 0
    failed = 0
    skipped = 0
    errors = 0

    if framework == "pytest":
        for m in _PYTEST_RESULT_RE.finditer(combined):
            if m.group(1):
                passed += int(m.group(1))
            if m.group(2):
                failed += int(m.group(2))
            if m.group(3):
                errors += int(m.group(3))
            if m.group(4):
                skipped += int(m.group(4))
    elif framework in {"jest", "vitest"}:
        m = _JEST_RESULT_RE.search(combined)
        if m:
            failed = int(m.group(1) or 0)
            passed = int(m.group(2) or 0)
    # Other frameworks: caller can inspect raw stdout

    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "total": passed + failed + skipped + errors,
    }


def register(mcp: FastMCP, config: Config) -> None:
    workspace = config.workspace_path

    @mcp.tool()
    def discover_test_framework() -> dict[str, Any]:
        """Detect the test framework used in this workspace."""
        framework = _detect_test_framework(workspace)
        return {
            "framework": framework,
            "supported": framework not in {"unknown", "maven-or-gradle"},
        }

    @mcp.tool()
    def discover_test_files(
        path_filter: str | None = None,
        max_files: int = 200,
    ) -> list[str]:
        """List test files in the workspace.

        Args:
            path_filter: optional substring filter on the file path.
            max_files: max results.
        """
        framework = _detect_test_framework(workspace)
        patterns: list[str]
        if framework == "pytest":
            patterns = ["test_*.py", "*_test.py", "tests/**/*.py"]
        elif framework in {"jest", "vitest", "npm-test"}:
            patterns = ["**/*.test.ts", "**/*.test.tsx", "**/*.test.js",
                        "**/*.spec.ts", "**/*.spec.js"]
        elif framework == "go-test":
            patterns = ["**/*_test.go"]
        elif framework == "cargo-test":
            patterns = ["tests/**/*.rs", "src/**/*.rs"]  # Rust tests are inline; rough
        else:
            patterns = ["**/*test*", "**/*spec*"]

        seen: set[str] = set()
        out: list[str] = []
        for pattern in patterns:
            for p in workspace.glob(pattern):
                if not p.is_file():
                    continue
                rel = str(p.relative_to(workspace))
                if rel in seen:
                    continue
                if path_filter and path_filter not in rel:
                    continue
                seen.add(rel)
                out.append(rel)
                if len(out) >= max_files:
                    return out
        return out

    @mcp.tool()
    def run_tests(
        test_paths: list[str] | None = None,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        """Run tests in the workspace.

        Args:
            test_paths: specific test files/paths to run; empty for all.
            timeout_seconds: hard timeout for the test run.

        Returns:
            framework, command, exit_code, passed, failed, skipped, errors,
            stdout (truncated to 50KB), stderr (truncated to 20KB), timed_out.
        """
        framework = _detect_test_framework(workspace)
        cmd = _command_for(framework, test_paths or [])
        timed_out = False
        try:
            result = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            exit_code = -1
            timed_out = True

        parsed = _parse_results(framework, stdout, stderr)
        return {
            "framework": framework,
            "command": " ".join(cmd),
            "exit_code": exit_code,
            "timed_out": timed_out,
            **parsed,
            "stdout": stdout[-50_000:],
            "stderr": stderr[-20_000:],
        }
