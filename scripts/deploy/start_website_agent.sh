#!/bin/bash

# Start Website Voice Agent for LiveKit

echo "=========================================="
echo "Starting Nowva Website Voice Agent"
echo "=========================================="
echo ""

# Set library path for WeasyPrint on macOS
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"

# Run the website voice agent in dev mode (auto-reloads on code changes)
PYTHONPATH='src' python3 src/agent/agents/website_voice_agent.py dev
