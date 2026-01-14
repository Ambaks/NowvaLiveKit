#!/bin/bash

# Start FastAPI Backend for Nowva

#

echo "=========================================="
echo "Starting Nowva FastAPI Backend"
echo "=========================================="
echo ""

# Set library path for WeasyPrint on macOS (required for PDF generation)
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"

PYTHONPATH='src' uvicorn api.main:app --reload --port 8000
