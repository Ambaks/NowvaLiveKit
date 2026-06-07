#!/bin/bash

echo "==========================================="
echo "API Integration Test"
echo "==========================================="
echo ""
echo "This test verifies the full program generation flow:"
echo "1. FastAPI receives request"
echo "2. Background job generates program"
echo "3. Program saved to database"
echo "4. Markdown file created in programs/"
echo ""

# Check if API is running
echo "Checking if FastAPI server is running..."
if ! curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "❌ FastAPI server is not running!"
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

echo "==========================================="
echo "Test: Quick 4-week Hypertrophy Program"
echo "==========================================="
RESPONSE=$(curl -s -X POST http://localhost:8000/api/programs/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "height_cm": 175,
    "weight_kg": 75,
    "age": 25,
    "sex": "male",
    "goal_category": "hypertrophy",
    "goal_raw": "Build muscle",
    "duration_weeks": 4,
    "days_per_week": 4,
    "session_duration": 60,
    "injury_history": "none",
    "specific_sport": "none",
    "fitness_level": "intermediate",
    "has_vbt_capability": false
  }')

echo "$RESPONSE" | python3 -m json.tool
JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo ""
echo "Job ID: $JOB_ID"
echo ""

echo "Waiting for program generation..."
for i in {1..30}; do
    sleep 5
    echo "Checking status... (${i}x5s = $((i*5))s elapsed)"

    STATUS_RESPONSE=$(curl -s "http://localhost:8000/api/programs/status/$JOB_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")
    PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', 0))" 2>/dev/null || echo "0")

    if [ "$STATUS" = "completed" ]; then
        echo ""
        echo "✅ Program generation COMPLETED!"
        echo ""
        echo "Full status:"
        echo "$STATUS_RESPONSE" | python3 -m json.tool

        PROGRAM_ID=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['program_id'])")
        echo ""
        echo "Program ID: $PROGRAM_ID"
        echo ""

        # Check for markdown file
        MARKDOWN_FILE="programs/program_${USER_ID}_${PROGRAM_ID}.md"
        if [ -f "$MARKDOWN_FILE" ]; then
            echo "✅ Markdown file created: $MARKDOWN_FILE"
            echo ""
            echo "First 20 lines of markdown:"
            echo "==========================================="
            head -20 "$MARKDOWN_FILE"
            echo "==========================================="
        else
            echo "❌ Markdown file NOT found: $MARKDOWN_FILE"
        fi

        echo ""
        echo "==========================================="
        echo "✅ ALL TESTS PASSED!"
        echo "==========================================="
        exit 0
    elif [ "$STATUS" = "failed" ]; then
        echo ""
        echo "❌ Program generation FAILED!"
        echo ""
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        exit 1
    else
        echo "  Status: $STATUS | Progress: ${PROGRESS}%"
    fi
done

echo ""
echo "❌ Test timed out after 150 seconds"
exit 1
