# Templates

Workspace-level instruction files for different IDE Agents. Each file teaches the Agent how to follow the AI Coding Workflow pipeline.

**You don't put these in this repo — you put them in your sandbox / team repo (the one the pipeline operates on).**

Pick the one matching your IDE:

| IDE Agent | File to copy | Destination in your team repo |
|---|---|---|
| GitHub Copilot Chat (VS Code) | `.github/copilot-instructions.md` | `.github/copilot-instructions.md` |
| Roo Code (VS Code extension) | `roo/.roorules` | `.roorules` (workspace root) |
| Cline | `roo/.roorules` | `.clinerules` (same content, different filename) |
| Claude Code | (uses MCP server instructions directly — no file needed) | n/a |

For Cursor, see `roo/.roorules` — Cursor reads workspace-level rules from `.cursorrules` (same content, copy + rename).

## Generic version (AGENTS.md cross-tool standard)

If your team uses multiple AI agents and wants one shared instruction file, the emerging `AGENTS.md` convention is supported by Roo Code, Cursor, and increasingly by other tools. You can copy `roo/.roorules` to `AGENTS.md` at your workspace root.
