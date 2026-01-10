#!/bin/bash

# Start FastAPI Backend for Nowva

#

echo "=========================================="
echo "Starting Nowva FastAPI Backend"
echo "=========================================="
echo ""

PYTHONPATH='src' uvicorn api.main:app --reload --port 8000
