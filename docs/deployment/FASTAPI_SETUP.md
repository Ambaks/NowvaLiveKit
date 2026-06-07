# FastAPI Backend Setup Guide

The Nowva system now uses a FastAPI backend to handle long-running program generation tasks. This solves timeout issues with the OpenAI Realtime API.

## Architecture

```
┌─────────────────┐         ┌──────────────────────┐
│  Voice Agent    │  HTTP   │   FastAPI Backend    │
│  (LiveKit)      │────────▶│   (Port 8000)        │
│                 │         │                      │
│  - User speech  │         │  - Job Management    │
│  - Function     │         │  - GPT-5 Generation  │
│    calling      │         │  - Status Tracking   │
└─────────────────┘         └──────────────────────┘
         │                            │
         └──────────┬─────────────────┘
                    ▼
          ┌──────────────────────┐
          │   PostgreSQL DB      │
          │                      │
          │  - Users             │
          │  - Programs          │
          │  - Generation Jobs   │
          └──────────────────────┘
```

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `httpx` - Async HTTP client for voice agent

### 2. Run Database Migration

Create the `program_generation_jobs` table:

```bash
python src/db/migrations/add_program_generation_jobs.py
```

## Running the System

You need to run **two processes** in separate terminals:

### Terminal 1: FastAPI Backend

```bash
cd src
uvicorn api.main:app --reload --port 8000
```

You should see:
```
🚀 Nowva FastAPI Backend Starting...
📚 API Docs: http://localhost:8000/docs
🔍 ReDoc: http://localhost:8000/redoc
💚 Health Check: http://localhost:8000/api/health
```

### Terminal 2: Voice Agent

```bash
python src/main.py
```

The voice agent will automatically connect to the FastAPI backend at `http://localhost:8000`.

## How It Works

### 1. User Provides Program Parameters

Voice agent collects:
- Height & weight
- Goal (power/strength/hypertrophy)
- Duration (weeks)
- Training frequency (days/week)
- Fitness level (beginner/intermediate/advanced)

### 2. Start Generation (Returns Immediately)

```python
# Voice agent calls:
generate_workout_program()
  ↓
# FastAPI endpoint:
POST /api/programs/generate
  ↓
# Returns immediately with job_id
{
  "job_id": "a1b2c3d4-...",
  "status": "pending",
  "message": "Program generation started"
}
```

### 3. Poll for Status

```python
# Voice agent waits 45 seconds, then calls:
check_program_status()
  ↓
# FastAPI endpoint:
GET /api/programs/status/{job_id}
  ↓
# Returns status
{
  "job_id": "a1b2c3d4-...",
  "status": "in_progress",  # or "completed" or "failed"
  "progress": 65,            # 0-100
  "program_id": null         # populated when complete
}
```

### 4. Retrieve Program (When Complete)

When status is "completed":

```python
{
  "status": "completed",
  "progress": 100,
  "program_id": "xyz789..."
}
```

Voice agent saves the `program_id` and moves to `finish_program_creation()`.

## API Endpoints

### Health Check
```
GET /api/health
```

Returns API status.

### Start Program Generation
```
POST /api/programs/generate

Body:
{
  "user_id": "uuid",
  "height_cm": 190.5,
  "weight_kg": 87.5,
  "goal_category": "hypertrophy",
  "goal_raw": "muscle gain",
  "duration_weeks": 12,
  "days_per_week": 4,
  "fitness_level": "intermediate"
}

Response (202 Accepted):
{
  "job_id": "uuid",
  "status": "pending",
  "message": "Program generation started"
}
```

### Check Generation Status
```
GET /api/programs/status/{job_id}

Response:
{
  "job_id": "uuid",
  "status": "in_progress",
  "progress": 65,
  "created_at": "2025-10-20T22:00:00Z",
  "started_at": "2025-10-20T22:00:05Z",
  "completed_at": null,
  "program_id": null,
  "error_message": null
}
```

### Get Program
```
GET /api/programs/{program_id}

Response:
{
  "id": "uuid",
  "name": "12-Week Hypertrophy Program",
  "description": "...",
  "duration_weeks": 12,
  "created_at": "2025-10-20T22:02:00Z"
}
```

## Interactive API Documentation

FastAPI provides automatic interactive docs:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

You can test all endpoints directly from your browser!

## Troubleshooting

### FastAPI won't start
```bash
# Make sure you're in the src/ directory
cd src

# Check if port 8000 is already in use
lsof -ti:8000

# Kill the process if needed
kill -9 $(lsof -ti:8000)
```

### Voice agent can't connect to FastAPI
```bash
# Check if FastAPI is running
curl http://localhost:8000/api/health

# Should return:
# {"status":"healthy","service":"Nowva Program Generator API","version":"1.0.0"}
```

### Generation fails
Check the FastAPI terminal for error logs. Common issues:
- Missing `OPENAI_API_KEY` in `.env`
- Database connection issues
- GPT-5 API timeout (should auto-retry)

## Environment Variables

Add to your `.env` file:

```bash
# OpenAI
OPENAI_API_KEY=your_key_here
PROGRAM_CREATION_MODEL=gpt-5-mini  # or gpt-4o

# FastAPI (optional - defaults shown)
FASTAPI_URL=http://localhost:8000
```

## Benefits

✅ **No timeouts** - Voice agent doesn't wait for long GPT-5 calls
✅ **Progress updates** - Can tell user "65% complete..."
✅ **Better UX** - User knows generation is happening
✅ **Scalable** - Can handle multiple users simultaneously
✅ **Easier debugging** - Separate logs for voice agent and backend
✅ **Production-ready** - Can deploy to cloud with Docker

## Next Steps

For production deployment:
1. Use environment-based `FASTAPI_URL`
2. Add authentication (API keys)
3. Deploy FastAPI to cloud (AWS/GCP/Azure)
4. Use managed task queue (Celery + Redis)
5. Add monitoring (Sentry, Datadog)
