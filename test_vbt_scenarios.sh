#!/bin/bash

USER_ID="ee611076-e172-45c9-8562-c30aeebd037f"

echo "========================================="
echo "Test 1: Beginner Hypertrophy (VBT OFF)"
echo "========================================="
TEST1=$(curl -s -X POST http://localhost:8000/api/programs/generate \
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
echo "$TEST1" | python3 -m json.tool
JOB1=$(echo "$TEST1" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID: $JOB1"
echo ""

echo "========================================="
echo "Test 2: Advanced Power + Basketball (VBT ON)"
echo "========================================="
TEST2=$(curl -s -X POST http://localhost:8000/api/programs/generate \
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
echo "$TEST2" | python3 -m json.tool
JOB2=$(echo "$TEST2" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID: $JOB2"
echo ""

echo "========================================="
echo "Test 3: Intermediate Strength (VBT OFF)"
echo "========================================="
TEST3=$(curl -s -X POST http://localhost:8000/api/programs/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "height_cm": 180,
    "weight_kg": 90,
    "age": 28,
    "sex": "male",
    "goal_category": "strength",
    "goal_raw": "Get stronger on the big three",
    "duration_weeks": 10,
    "days_per_week": 4,
    "session_duration": 75,
    "injury_history": "none",
    "specific_sport": "none",
    "fitness_level": "intermediate",
    "has_vbt_capability": false
  }')
echo "$TEST3" | python3 -m json.tool
JOB3=$(echo "$TEST3" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID: $JOB3"
echo ""

echo "========================================="
echo "Test 4: Advanced Powerlifting (VBT ON)"
echo "========================================="
TEST4=$(curl -s -X POST http://localhost:8000/api/programs/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "height_cm": 178,
    "weight_kg": 95,
    "age": 32,
    "sex": "male",
    "goal_category": "strength",
    "goal_raw": "Training for powerlifting competition",
    "duration_weeks": 8,
    "days_per_week": 5,
    "session_duration": 90,
    "injury_history": "previous lower back strain, fully recovered",
    "specific_sport": "powerlifting",
    "user_notes": "Competition in 8 weeks",
    "fitness_level": "advanced",
    "has_vbt_capability": true
  }')
echo "$TEST4" | python3 -m json.tool
JOB4=$(echo "$TEST4" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID: $JOB4"
echo ""

echo "========================================="
echo "Waiting 90 seconds for generation..."
echo "========================================="
sleep 90

echo ""
echo "Checking statuses..."
echo "========================================="

echo "Test 1 Status (Beginner Hypertrophy - VBT OFF):"
curl -s "http://localhost:8000/api/programs/status/$JOB1" | python3 -m json.tool
echo ""

echo "Test 2 Status (Advanced Power/Basketball - VBT ON):"
curl -s "http://localhost:8000/api/programs/status/$JOB2" | python3 -m json.tool
echo ""

echo "Test 3 Status (Intermediate Strength - VBT OFF):"
curl -s "http://localhost:8000/api/programs/status/$JOB3" | python3 -m json.tool
echo ""

echo "Test 4 Status (Advanced Powerlifting - VBT ON):"
curl -s "http://localhost:8000/api/programs/status/$JOB4" | python3 -m json.tool
echo ""

echo "========================================="
echo "All tests completed!"
echo "========================================="
echo "User ID: $USER_ID"
echo "Test 1 (Beginner Hypertrophy - VBT OFF): $JOB1"
echo "Test 2 (Advanced Power/Basketball - VBT ON): $JOB2"
echo "Test 3 (Intermediate Strength - VBT OFF): $JOB3"
echo "Test 4 (Advanced Powerlifting - VBT ON): $JOB4"
