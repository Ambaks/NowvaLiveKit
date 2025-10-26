#!/bin/bash

echo "==========================================="
echo "Regenerating 4 Test Programs"
echo "==========================================="
echo ""
echo "This will create:"
echo "1. Beginner Hypertrophy (VBT OFF) - 12 weeks"
echo "2. Advanced Power/Basketball (VBT ON) - 6 weeks"
echo "3. Intermediate Strength (VBT OFF) - 12 weeks"
echo "4. Advanced Powerlifting (VBT ON) - 8 weeks"
echo ""

# Check if API is running
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

USER_ID="ee611076-e172-45c9-8562-c30aeebd037f"

# Test 1: Beginner Hypertrophy - VBT OFF
echo "Starting Test 1..."
RESPONSE1=$(curl -s -X POST http://localhost:8000/api/programs/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "height_cm": 175,
    "weight_kg": 75,
    "age": 22,
    "sex": "male",
    "goal_category": "hypertrophy",
    "goal_raw": "Build muscle for summer",
    "duration_weeks": 12,
    "days_per_week": 4,
    "session_duration": 60,
    "injury_history": "none",
    "specific_sport": "none",
    "fitness_level": "beginner",
    "has_vbt_capability": false
  }')
JOB1=$(echo "$RESPONSE1" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "✅ Test 1 started: $JOB1"

# Test 2: Advanced Power/Basketball - VBT ON
echo "Starting Test 2..."
RESPONSE2=$(curl -s -X POST http://localhost:8000/api/programs/generate \
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
JOB2=$(echo "$RESPONSE2" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "✅ Test 2 started: $JOB2"

# Test 3: Intermediate Strength - VBT OFF
echo "Starting Test 3..."
RESPONSE3=$(curl -s -X POST http://localhost:8000/api/programs/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "height_cm": 180,
    "weight_kg": 82,
    "age": 28,
    "sex": "male",
    "goal_category": "strength",
    "goal_raw": "Increase my big 3 lifts",
    "duration_weeks": 12,
    "days_per_week": 4,
    "session_duration": 75,
    "injury_history": "none",
    "specific_sport": "none",
    "fitness_level": "intermediate",
    "has_vbt_capability": false
  }')
JOB3=$(echo "$RESPONSE3" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "✅ Test 3 started: $JOB3"

# Test 4: Advanced Powerlifting - VBT ON
echo "Starting Test 4..."
RESPONSE4=$(curl -s -X POST http://localhost:8000/api/programs/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "height_cm": 178,
    "weight_kg": 92,
    "age": 30,
    "sex": "male",
    "goal_category": "strength",
    "goal_raw": "Prepare for powerlifting competition",
    "duration_weeks": 8,
    "days_per_week": 5,
    "session_duration": 90,
    "injury_history": "minor knee pain",
    "specific_sport": "powerlifting",
    "user_notes": "Competition in 8 weeks",
    "fitness_level": "advanced",
    "has_vbt_capability": true
  }')
JOB4=$(echo "$RESPONSE4" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "✅ Test 4 started: $JOB4"

echo ""
echo "==========================================="
echo "All 4 programs queued!"
echo "==========================================="
echo ""
echo "Job IDs:"
echo "Test 1 (Beginner Hypertrophy - VBT OFF): $JOB1"
echo "Test 2 (Advanced Power/Basketball - VBT ON): $JOB2"
echo "Test 3 (Intermediate Strength - VBT OFF): $JOB3"
echo "Test 4 (Advanced Powerlifting - VBT ON): $JOB4"
echo ""
echo "Programs will take 3-5 minutes each to generate."
echo "They will automatically save markdown to programs/ folder when complete."
echo ""
echo "To check status:"
echo "  curl -s http://localhost:8000/api/programs/status/JOB_ID | python3 -m json.tool"
