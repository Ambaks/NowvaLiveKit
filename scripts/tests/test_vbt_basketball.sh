#!/bin/bash

# Test VBT Basketball Power Program Generation
# 6-week power block for basketball player with VBT capability

echo "🏀 Testing VBT Basketball Power Program Generation"
echo "=================================================="

# Use the existing test user ID
USER_ID="702a82ef-5915-4433-9f01-9a473e39aaf4"

echo "User ID: $USER_ID (Baka - Basketball VBT Test)"
echo ""

# Create the program generation request
echo "📤 Sending program generation request..."

RESPONSE=$(curl -s -X POST http://localhost:8000/api/programs/generate \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"name\": \"VBT Basketball Test\",
    \"height_cm\": 193,
    \"weight_kg\": 95,
    \"goal_category\": \"power\",
    \"goal_raw\": \"Increase vertical jump and explosive power for basketball\",
    \"duration_weeks\": 6,
    \"days_per_week\": 3,
    \"fitness_level\": \"intermediate\",
    \"session_duration\": 75,
    \"injury_history\": \"none\",
    \"age\": 24,
    \"sex\": \"M\",
    \"specific_sport\": \"basketball\",
    \"has_vbt_capability\": true,
    \"user_notes\": \"Focus on Olympic lifts and velocity tracking. Need explosive power for vertical jump and quick first step.\"
  }")

# Extract job ID from response
JOB_ID=$(echo $RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
  echo "❌ Failed to create job"
  echo "Response: $RESPONSE"
  exit 1
fi

echo "✅ Job created: $JOB_ID"
echo ""
echo "📊 Monitoring progress..."
echo ""

# Poll for completion
MAX_WAIT=600  # 10 minutes max
ELAPSED=0
INTERVAL=3

while [ $ELAPSED -lt $MAX_WAIT ]; do
  STATUS_RESPONSE=$(curl -s http://localhost:8000/api/programs/status/$JOB_ID)

  STATUS=$(echo $STATUS_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
  PROGRESS=$(echo $STATUS_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['progress'])" 2>/dev/null)

  echo -ne "\rStatus: $STATUS | Progress: $PROGRESS%    "

  if [ "$STATUS" = "completed" ]; then
    echo ""
    echo ""
    echo "✅ Program generation completed!"

    PROGRAM_ID=$(echo $STATUS_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('program_id', 'N/A'))" 2>/dev/null)
    echo "Program ID: $PROGRAM_ID"

    # Find and display the markdown file
    echo ""
    echo "📄 Generated markdown file:"
    MARKDOWN_FILE=$(find programs -name "*_${PROGRAM_ID}.md" 2>/dev/null | head -1)

    if [ -n "$MARKDOWN_FILE" ]; then
      echo "File: $MARKDOWN_FILE"
      echo ""
      echo "Preview (first 100 lines):"
      echo "------------------------------------------------------------"
      head -100 "$MARKDOWN_FILE"
      echo "------------------------------------------------------------"
      echo ""
      echo "💾 Full file saved at: $MARKDOWN_FILE"
    else
      echo "⚠️  Markdown file not found"
    fi

    exit 0
  fi

  if [ "$STATUS" = "failed" ]; then
    echo ""
    echo ""
    echo "❌ Program generation failed!"
    ERROR_MSG=$(echo $STATUS_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('error_message', 'Unknown error'))" 2>/dev/null)
    echo "Error: $ERROR_MSG"
    exit 1
  fi

  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

echo ""
echo "⏱️  Timeout reached after ${MAX_WAIT}s"
exit 1
