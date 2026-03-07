#!/usr/bin/env bash
set -e

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
fi

mkdir -p data
echo "Starting tracker on http://localhost:5000"
python3 utopia.py
