# Install + IDE Setup

## Prerequisites

- Python 3.11+
- Access to a Jira instance (Cloud or Self-hosted) with API token
- Access to a GitHub organization with a personal access token (or installation token)
- A local clone of the repo this server will operate on

## Install the server

```bash
# Clone this project
git clone <this-repo-url> ai-coding-workflow
cd ai-coding-workflow

# Install (use uv, pip, or your preferred tool)
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your Jira / GitHub credentials and workspace path
```

Verify:

```bash
ai-coding-workflow --help
```

## Configure your IDE

This server speaks MCP (Model Context Protocol). Any MCP-compatible client can use it.

### VS Code Copilot

#### Step 1: Drop the auto-instructions into your sandbox/team repo

Copy `templates/.github/copilot-instructions.md` from this project to **your team repo's** `.github/copilot-instructions.md`:

```bash
# Replace <your-target-repo> with your team's repo path
cp /path/to/ai-coding-workflow/templates/.github/copilot-instructions.md /path/to/<your-target-repo>/.github/copilot-instructions.md
```

This file teaches Copilot the pipeline workflow. After this, **the user can just say "start working on KAN-4"** and Copilot follows the orchestration without needing a multi-step prompt.

(You can commit this file to your team repo — it has no secrets, just instructions.)

#### Step 2: Configure the MCP server

1. Open VS Code settings (JSON).
2. Add MCP server config:

```json
{
  "github.copilot.advanced.mcp.servers": {
    "ai-coding-workflow": {
      "command": "ai-coding-workflow",
      "args": [],
      "env": {
        "JIRA_BASE_URL": "${env:JIRA_BASE_URL}",
        "JIRA_EMAIL": "${env:JIRA_EMAIL}",
        "JIRA_API_TOKEN": "${env:JIRA_API_TOKEN}",
        "GITHUB_TOKEN": "${env:GITHUB_TOKEN}",
        "WORKSPACE_PATH": "${workspaceFolder}"
      }
    }
  }
}
```

3. Reload VS Code.
4. Open Copilot Chat in **Agent mode** (top selector). Three ways to start the pipeline:

**Way A — natural language (recommended once Step 1 is done):**
```
Start working on JIRA-123
```
Copilot reads `.github/copilot-instructions.md`, recognizes the Jira key, and follows the pipeline orchestration automatically.

**Way B — slash command:**
```
/ai-coding-workflow:pipeline jira_key=JIRA-123
```
Auto-detects current stage and runs the right step.

**Way C — explicit stage:**
```
/ai-coding-workflow:design_for jira_key=JIRA-123
/ai-coding-workflow:implement_for jira_key=JIRA-123
/ai-coding-workflow:my_tickets
```

All three converge on the same orchestration. Way A is the most natural; Way B/C are useful for explicit control.

### Claude Code

Add to `~/.claude/claude_desktop_config.json` (or your Claude Code MCP config):

```json
{
  "mcpServers": {
    "ai-coding-workflow": {
      "command": "ai-coding-workflow",
      "env": {
        "JIRA_BASE_URL": "...",
        "JIRA_EMAIL": "...",
        "JIRA_API_TOKEN": "...",
        "GITHUB_TOKEN": "...",
        "WORKSPACE_PATH": "/absolute/path/to/your/repo"
      }
    }
  }
}
```

Restart Claude Code. The skills in this project's `.claude/skills/` directory are discovered automatically when you open a workspace under that directory, OR copy them to `~/.claude/skills/` for global availability.

### Cursor

Cursor supports MCP servers via `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ai-coding-workflow": {
      "command": "ai-coding-workflow",
      "env": { ... }
    }
  }
}
```

## Required scopes / permissions

### Jira API token
- Read tickets (always)
- Update ticket status (for Stage 6 close-out — optional, can be done manually)
- Add comments (for escalation notifications — optional)

### GitHub token
- `repo` (read + write code, PRs, comments)
- `workflow` (if you want to trigger CI workflows from `mcp-deploy`)
- `read:org` (to resolve assignees)

If using a GitHub App, the equivalent installation permissions.

## Troubleshooting

### "Tool 'X' not found"
Check `ai-coding-workflow --version` matches what you expect. Restart your IDE — MCP discovery happens at IDE start.

### "Cannot connect to Jira"
- Verify `JIRA_BASE_URL` (no trailing slash)
- Verify your email matches the API token's owner
- Try `curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN" $JIRA_BASE_URL/rest/api/3/myself` — should return your profile

### "Cannot find skills"
Skills are in `.claude/skills/` of this project. They are discovered when:
- Claude Code: workspace is opened under or above this directory
- Copilot: skill discovery follows the same pattern (workspace-rooted), or copy `.claude/skills/mcp-*` to your repo's `.claude/skills/`

### "Bash error in skill"
This means a skill tried to run a shell command. Skills in this project are bash-free by design. If you see this:
- Check you're using the project's `.claude/skills/mcp-*`, not a globally-installed skill of similar name
- File a bug — it's a regression in the skill design

### "Pipeline picked the wrong stage"
The Agent's stage inference uses Jira status + GitHub PR state + operation log presence. If it's wrong, check:
- Is your Jira ticket in an expected state?
- Are there orphan PRs (open PRs that should have been closed)?
- Are operation logs out of sequence?

You can override with: `Continue JIRA-123 from stage <stage_name>`.

## Updating

```bash
cd ai-coding-workflow
git pull
pip install -e . --upgrade
# Restart your IDE to pick up new tools
```
