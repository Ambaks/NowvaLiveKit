#!/bin/bash
# Test script for the new V2 program generator with structured outputs

echo "=================================="
echo "Testing Program Generation V2"
echo "=================================="
echo ""

# Check if FastAPI is running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "❌ Error: FastAPI server is not running on port 8000"
    echo "Start it with: uvicorn src.api.main:app --reload"
    exit 1
fi

echo "✅ FastAPI server is running"
echo ""

# Get user ID - check if provided as argument, otherwise prompt
if [ -n "$1" ]; then
    USER_ID="$1"
    echo "Using provided User ID: $USER_ID"
else
    echo "No user ID provided. Please provide a user ID from your database."
    echo ""
    echo "Usage: $0 <user-id>"
    echo ""
    echo "To find a user ID, run one of these:"
    echo "  1. Check your database users table"
    echo "  2. Create a test user via your API"
    echo "  3. Run: psql \$DATABASE_URL -c 'SELECT id, name, email FROM users LIMIT 5;'"
    echo ""

    # Try to get user from API health endpoint or similar
    echo "Attempting to fetch any existing user..."

    # For now, exit with instructions
    echo ""
    echo "❌ Please provide a valid user ID and try again"
    echo ""
    exit 1
fi

echo "Configuration: 2 weeks, 3 days/week (small test)"
echo ""

# Start program generation
RESPONSE=$(curl -s -X POST "http://localhost:8000/api/programs/generate" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"height_cm\": 180,
    \"weight_kg\": 80,
    \"goal_category\": \"strength\",
    \"goal_raw\": \"Build foundational strength\",
    \"fitness_level\": \"intermediate\",
    \"duration_weeks\": 2,
    \"days_per_week\": 3
  }")

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""

# Extract job_id
JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
    echo "❌ Failed to start job"
    exit 1
fi

echo "✅ Job started: $JOB_ID"
echo ""
echo "Monitoring progress..."
echo ""

# Poll for completion (up to 5 minutes)
for i in {1..150}; do
    STATUS_RESPONSE=$(curl -s "http://localhost:8000/api/programs/status/$JOB_ID")

    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
    PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', 0))" 2>/dev/null)

    echo -ne "\r[$i/60] Status: $STATUS | Progress: $PROGRESS%     "

    if [ "$STATUS" = "completed" ]; then
        echo ""
        echo ""
        echo "🎉 Program generation completed!"
        echo ""
        echo "Full response:"
        echo "$STATUS_RESPONSE" | python3 -m json.tool

        PROGRAM_ID=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('program_id', ''))" 2>/dev/null)

        if [ -n "$PROGRAM_ID" ]; then
            echo ""
            echo "Program ID: $PROGRAM_ID"
            echo ""
            echo "Fetching program details..."
            curl -s "http://localhost:8000/api/programs/$PROGRAM_ID" | python3 -m json.tool
        fi

        exit 0
    fi

    if [ "$STATUS" = "failed" ]; then
        echo ""
        echo ""
        echo "❌ Program generation failed"
        echo ""
        echo "Error details:"
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        exit 1
    fi

    sleep 2
done

echo ""
echo ""
echo "⏱️  Timeout after 5 minutes"
echo "Final status:"
curl -s "http://localhost:8000/api/programs/status/$JOB_ID" | python3 -m json.tool
