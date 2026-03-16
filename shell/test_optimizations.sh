#!/bin/bash

echo "==========================================="
echo "Program Generation Optimization Test"
echo "==========================================="
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please create it first:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Running optimization tests..."
echo ""
echo "This will generate 3 programs:"
echo "  1. 2-week program (SHORT CAG)"
echo "  2. 5-week program (MEDIUM CAG, VBT enabled)"
echo "  3. 12-week program (FULL CAG)"
echo ""
echo "Programs will be saved to the programs/ folder."
echo "==========================================="
echo ""

python3 test_program_optimizations.py

echo ""
echo "==========================================="
echo "Test complete!"
echo "==========================================="
