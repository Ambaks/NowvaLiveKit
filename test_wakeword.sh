#!/usr/bin/env bash
# Test the ONNX wake word system end-to-end.
#
# What it does:
#   1. Patches the agent state file to "workout" mode so the agent
#      boots straight into WorkoutAgent (which starts the wake word system).
#   2. Launches the voice agent in console mode (local mic/speaker — no room
#      client needed) with WAKE_WORD_LOCAL_MIC=1 so detection taps the mic
#      directly instead of a LiveKit room track.
#   3. Restores the original state file on exit.
#
# Usage:
#   ./test_wakeword.sh              # ONNX engine, default threshold (0.7)
#   ./test_wakeword.sh 0.6          # looser threshold (if real "Hey Nova"s get missed)
#
# Porcupine engine (needs PORCUPINE_ACCESS_KEY in .env or shell):
#   WAKE_WORD_ENGINE=porcupine ./test_wakeword.sh
#   Custom "Hey Nova": set PORCUPINE_KEYWORD_PATH=models/hey_nova.ppn
#   Before the .ppn is trained, test with a built-in keyword:
#   WAKE_WORD_ENGINE=porcupine PORCUPINE_KEYWORD=porcupine ./test_wakeword.sh
#
# What to test:
#   - Say "Hey Nova" → agent should respond with a short acknowledgment
#   - Stay silent ~2 seconds after the exchange → agent reverts to dormant mode
#   - Say random words / make noise → should NOT trigger
#   - Check logs for "[WAKE WORD] ★ DETECTED" lines

set -uo pipefail
cd "$(dirname "$0")"

THRESHOLD="${1:-0.7}"
STATE_FILE=$(ls .agent_state_*.json 2>/dev/null | head -1)

if [ -z "$STATE_FILE" ]; then
    echo "ERROR: No .agent_state_*.json found. Run the agent normally first to create one."
    exit 1
fi

# Back up original state
cp "$STATE_FILE" "${STATE_FILE}.bak"

restore_state() {
    if [ -f "${STATE_FILE}.bak" ]; then
        cp "${STATE_FILE}.bak" "$STATE_FILE"
        rm "${STATE_FILE}.bak"
        echo ""
        echo "[test_wakeword] State file restored."
    fi
}
trap restore_state EXIT

# Patch mode to "workout" so the agent boots into WorkoutAgent
python3 -c "
import json, sys
with open('$STATE_FILE') as f:
    state = json.load(f)
state['mode'] = 'workout'
state['workout']['active'] = True
state['workout']['greeting_done'] = True
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
print('[test_wakeword] State patched to workout mode')
"

echo "[test_wakeword] Engine: ${WAKE_WORD_ENGINE:-onnx}"
echo "[test_wakeword] Wake word threshold: $THRESHOLD"
echo "[test_wakeword] Model: models/hey_nova.onnx"
echo "[test_wakeword] Say 'Hey Nova' to test detection."
echo "[test_wakeword] Press Ctrl+C to stop."
echo ""

PYTHONPATH="src:${PYTHONPATH:-}" \
WAKE_WORD_THRESHOLD="$THRESHOLD" \
WAKE_WORD_MODEL_PATH="models/hey_nova.onnx" \
WAKE_WORD_LOCAL_MIC=1 \
    ./venv/bin/python -m agent.agents.voice_agent console 2>&1
