#!/bin/bash

echo "==========================================="
echo "Test 2: Advanced Power/Basketball (VBT ON)"
echo "==========================================="
echo ""

# Check if API is running
echo "Checking if FastAPI server is running..."
if ! curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "❌ FastAPI server is NOT running!"
    echo ""
    echo "Please start it in another terminal:"
    echo "  cd /Users/naiahoard/NowvaLiveKit"
    echo "  source venv/bin/activate"
    echo "  uvicorn src.api.main:app --reload --port 8000"
    echo ""
    exit 1
fi

echo "✅ FastAPI server is running"
echo ""

USER_ID="ee611076-e172-45c9-8562-c30aeebd037f"

echo "Submitting program generation request..."
echo ""

RESPONSE=$(curl -s -X POST http://localhost:8000/api/programs/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "height_cm": 185,
    "weight_kg": 86,
    "age": 24,
    "sex": "male",
    "goal_category": "power",
    "goal_raw": "Improve vertical jump for basketball",
    "duration_weeks": 6,
    "days_per_week": 4,
    "session_duration": 60,
    "injury_history": "none",
    "specific_sport": "basketball",
    "user_notes": "Training for college season",
    "fitness_level": "advanced",
    "has_vbt_capability": true
  }')

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool
echo ""

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
    echo "❌ Failed to get job ID"
    exit 1
fi

echo "✅ Job started: $JOB_ID"
echo ""
echo "Monitoring progress (will check every 10 seconds)..."
echo ""

# Monitor for up to 10 minutes (60 checks x 10 seconds)
for i in {1..60}; do
    sleep 10

    STATUS_RESPONSE=$(curl -s "http://localhost:8000/api/programs/status/$JOB_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")
    PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', 0))" 2>/dev/null || echo "0")

    echo "[$(date '+%H:%M:%S')] Check $i/60: Status=$STATUS, Progress=${PROGRESS}%"

    if [ "$STATUS" = "completed" ]; then
        echo ""
        echo "==========================================="
        echo "✅ PROGRAM GENERATION COMPLETE!"
        echo "==========================================="
        echo ""

        PROGRAM_ID=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['program_id'])")

        echo "Job ID: $JOB_ID"
        echo "Program ID: $PROGRAM_ID"
        echo ""

        # Find the markdown file
        MARKDOWN_FILE="programs/program_${USER_ID}_${PROGRAM_ID}.md"

        if [ -f "$MARKDOWN_FILE" ]; then
            echo "✅ Markdown file created: $MARKDOWN_FILE"
            echo ""
            echo "First 50 lines:"
            echo "==========================================="
            head -50 "$MARKDOWN_FILE"
            echo "==========================================="
            echo ""
            TOTAL_LINES=$(wc -l < "$MARKDOWN_FILE")
            echo "Total lines: $TOTAL_LINES"
        else
            echo "⚠️  Markdown file not found at: $MARKDOWN_FILE"
            echo ""
            echo "Checking programs directory:"
            ls -lh programs/*.md 2>/dev/null || echo "No markdown files found"
        fi

        echo ""
        echo "==========================================="
        echo "✅ TEST COMPLETE!"
        echo "==========================================="
        exit 0
    elif [ "$STATUS" = "failed" ]; then
        echo ""
        echo "❌ PROGRAM GENERATION FAILED!"
        echo ""
        ERROR=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error_message', 'Unknown error'))")
        echo "Error: $ERROR"
        echo ""
        echo "Full response:"
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        exit 1
    fi
done

echo ""
echo "❌ Timeout after 10 minutes"
echo "Last status: $STATUS ($PROGRESS%)"
exit 1
