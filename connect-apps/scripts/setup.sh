#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MCP_CONFIG="${PLUGIN_DIR}/.mcp.json"

echo "=== Composio Connect-Apps Setup ==="
echo ""

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed. Please install Node.js v18+ first."
    echo "  https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node --version | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "Error: Node.js v18+ is required. Current version: $(node --version)"
    exit 1
fi

echo "Node.js $(node --version) detected."

# Check for API key
if [ -z "${COMPOSIO_API_KEY:-}" ]; then
    if [ -n "${1:-}" ]; then
        COMPOSIO_API_KEY="$1"
    else
        echo ""
        echo "No COMPOSIO_API_KEY found."
        echo "Get your free API key at: https://platform.composio.dev"
        echo ""
        read -rp "Enter your Composio API key: " COMPOSIO_API_KEY
    fi
fi

if [ -z "$COMPOSIO_API_KEY" ]; then
    echo "Error: API key is required."
    exit 1
fi

# Install Composio MCP package
echo ""
echo "Installing @composio/mcp..."
npm install -g @composio/mcp@latest 2>/dev/null || {
    echo "Global install failed, will use npx instead."
}

# Write MCP config
cat > "$MCP_CONFIG" <<EOF
{
  "mcpServers": {
    "composio": {
      "command": "npx",
      "args": ["-y", "@composio/mcp@latest", "serve"],
      "env": {
        "COMPOSIO_API_KEY": "${COMPOSIO_API_KEY}"
      }
    }
  }
}
EOF

echo ""
echo "MCP configuration written to: $MCP_CONFIG"
echo ""
echo "Setup complete! Restart Claude Code to activate the Composio integration."
echo "Then ask Claude to connect to any app (Gmail, Slack, GitHub, etc.)"
