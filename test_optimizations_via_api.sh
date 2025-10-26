#!/bin/bash

echo "==========================================="
echo "Program Generation Optimization Test (via API)"
echo "==========================================="
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

USER_ID="702a82ef-5915-4433-9f01-9a473e39aaf4"

echo "This will generate 3 programs via API:"
echo "  1. 2-week program (SHORT CAG)"
echo "  2. 5-week program (MEDIUM CAG, VBT enabled)"
echo "  3. 12-week program (FULL CAG)"
echo ""
echo "You will see these in your backend server console!"
echo "==========================================="
echo ""

# Test 1: 2-week program
echo "================================================================================  "
echo "TEST 1/3: 2-Week Short Program"
echo "================================================================================"
echo ""

RESPONSE1=$(curl -s -X POST "http://localhost:8000/api/programs/generate" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"duration_weeks\": 2,
    \"height_cm\": 180,
    \"weight_kg\": 80,
    \"age\": 30,
    \"sex\": \"M\",
    \"goal_category\": \"strength\",
    \"goal_raw\": \"Build foundational strength\",
    \"fitness_level\": \"beginner\",
    \"days_per_week\": 3,
    \"session_duration\": 60,
    \"injury_history\": \"none\",
    \"specific_sport\": \"none\",
    \"has_vbt_capability\": false,
    \"user_notes\": \"Keep it simple and focused\"
  }")

JOB_ID1=$(echo $RESPONSE1 | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "✅ Job created: $JOB_ID1"
echo "Monitor at: http://localhost:8000/api/programs/status/$JOB_ID1"
echo ""

echo "✅ TEST 1 SUBMITTED - Running in background"
echo ""

# Test 2: 5-week program with VBT
echo "================================================================================"
echo "TEST 2/3: 5-Week Medium Program (VBT)"
echo "================================================================================"
echo ""

RESPONSE2=$(curl -s -X POST "http://localhost:8000/api/programs/generate" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"duration_weeks\": 5,
    \"height_cm\": 185,
    \"weight_kg\": 90,
    \"age\": 28,
    \"sex\": \"M\",
    \"goal_category\": \"power\",
    \"goal_raw\": \"Develop explosive power for Olympic lifts\",
    \"fitness_level\": \"intermediate\",
    \"days_per_week\": 4,
    \"session_duration\": 75,
    \"injury_history\": \"none\",
    \"specific_sport\": \"Olympic Weightlifting\",
    \"has_vbt_capability\": true,
    \"user_notes\": \"Focus on velocity-based training for Olympic lifts\"
  }")

JOB_ID2=$(echo $RESPONSE2 | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "✅ Job created: $JOB_ID2"
echo "Monitor at: http://localhost:8000/api/programs/status/$JOB_ID2"
echo ""

echo "✅ TEST 2 SUBMITTED - Running in background"
echo ""

# Test 3: 12-week program
echo "================================================================================"
echo "TEST 3/3: 12-Week Long Program"
echo "================================================================================"
echo ""

RESPONSE3=$(curl -s -X POST "http://localhost:8000/api/programs/generate" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"duration_weeks\": 12,
    \"height_cm\": 175,
    \"weight_kg\": 85,
    \"age\": 35,
    \"sex\": \"M\",
    \"goal_category\": \"hypertrophy\",
    \"goal_raw\": \"Build muscle mass and strength over 12 weeks\",
    \"fitness_level\": \"advanced\",
    \"days_per_week\": 5,
    \"session_duration\": 90,
    \"injury_history\": \"minor lower back issues\",
    \"specific_sport\": \"Bodybuilding\",
    \"has_vbt_capability\": false,
    \"user_notes\": \"Include proper deload weeks and progressive overload\"
  }")

JOB_ID3=$(echo $RESPONSE3 | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "✅ Job created: $JOB_ID3"
echo "Monitor at: http://localhost:8000/api/programs/status/$JOB_ID3"
echo ""

echo "✅ TEST 3 SUBMITTED - Running in background"

echo ""
echo "================================================================================"
echo "All 3 programs submitted! They will generate in the background."
echo "Monitor them at the URLs above or check your FastAPI server console."
echo "================================================================================"
