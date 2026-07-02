#!/usr/bin/env bash
# Quick-start script for local development
set -e

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Copy .env if it doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it to configure the remote API key and Discord bot."
fi

# Run
echo ""
echo "Starting server on http://localhost:${PORT:-5000}"
echo "Press Ctrl+C to stop."
echo ""
python main.py
