---
name: setup
description: Set up the Composio connect-apps plugin to connect Claude to 500+ external services (Gmail, Slack, GitHub, Notion, etc.)
---

# Connect Apps Setup

You are helping the user set up the Composio connect-apps plugin so Claude can interact with external services.

## Steps

1. **Check prerequisites**: Verify that Node.js (v18+) is installed by running `node --version`. If not installed, inform the user they need to install Node.js first.

2. **Check for existing API key**: Look for the `COMPOSIO_API_KEY` environment variable. If it exists, skip the API key step.

3. **Prompt for API key** (if not set): Ask the user to:
   - Go to https://platform.composio.dev and create a free account
   - Copy their API key from the dashboard
   - Provide it so you can configure the environment

4. **Install the Composio MCP package**: Run:
   ```bash
   npm install -g @composio/mcp@latest
   ```

5. **Configure the MCP server**: Run the setup script located at `${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh` with the user's API key to write the `.mcp.json` configuration.

6. **Verify the setup**: Confirm the `.mcp.json` file was created correctly in the plugin directory and contains the Composio server configuration.

7. **Test connectivity**: Ask the user which app they'd like to connect first (e.g., Gmail, Slack, GitHub, Notion) and guide them through the OAuth authorization flow.

## After Setup

Once configured, Claude can:
- **Gmail**: Send emails, read inbox, search messages
- **Slack**: Post messages, read channels, manage threads
- **GitHub**: Create issues, open PRs, manage repos
- **Notion**: Create pages, update databases, search content
- **Linear**: Create issues, update status, manage projects
- **Google Calendar**: Create events, check availability
- **And 500+ more services** via the Composio platform

To connect a new app at any time, just ask Claude: "Connect me to [app name]"

## Troubleshooting

- If the MCP server fails to start, ensure Node.js v18+ is installed
- If OAuth flows fail, check that your Composio API key is valid at https://platform.composio.dev
- Run `claude --debug` to see MCP server initialization logs
