#!/bin/bash
# Revert program_creation_prompt.py to original version
# Run this if the optimized prompt doesn't work

echo "Reverting program_creation_prompt.py to original version..."

if [ -f "src/agents/prompts/program_creation_prompt.py.backup" ]; then
    cp src/agents/prompts/program_creation_prompt.py.backup src/agents/prompts/program_creation_prompt.py
    echo "✅ Successfully reverted to backup"
    echo "Original prompt restored"
else
    echo "❌ Backup file not found!"
    echo "Cannot revert - backup missing"
    exit 1
fi
