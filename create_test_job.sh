#!/bin/bash
# Script to create a test program generation job

echo "Creating test program generation job..."
echo "=========================================="

# Make sure server is running
if ! curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "❌ Error: Server is not running at http://localhost:8000"
    echo "Please start the server first with: ./start_fastapi.sh"
    exit 1
fi

# Create the job
response=$(curl -s -X POST http://localhost:8000/api/programs/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "702a82ef-5915-4433-9f01-9a473e39aaf4",
    "height_cm": 180,
    "weight_kg": 80,
    "goal_category": "strength",
    "goal_raw": "Get stronger with barbell training",
    "duration_weeks": 4,
    "days_per_week": 3,
    "fitness_level": "intermediate",
    "age": 30,
    "sex": "M",
    "session_duration": 60,
    "injury_history": "none",
    "specific_sport": "none",
    "has_vbt_capability": false,
    "user_notes": "This is a test program"
  }')

# Extract job_id from response
job_id=$(echo $response | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', 'ERROR'))" 2>/dev/null)

if [ "$job_id" == "ERROR" ] || [ -z "$job_id" ]; then
    echo "❌ Failed to create job"
    echo "Response: $response"
    exit 1
fi

echo "✅ Job created successfully!"
echo "Job ID: $job_id"
echo ""
echo "=========================================="
echo "Monitor job status with:"
echo "  curl http://localhost:8000/api/programs/status/$job_id"
echo ""
echo "Or watch it continuously:"
echo "  watch -n 2 \"curl -s http://localhost:8000/api/programs/status/$job_id | python3 -m json.tool\""
echo ""
echo "Check server logs for detailed progress:"
echo "  tail -f fastapi.log | grep -E 'JOB|PROMPT|OpenAI'"
