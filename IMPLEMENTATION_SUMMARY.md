# FastAPI Backend Implementation Summary

## What Was Built

A complete FastAPI backend system to handle long-running workout program generation, solving the OpenAI Realtime API timeout issues.

## Files Created

### Backend Structure
```
src/api/
├── __init__.py
├── main.py                              # FastAPI app entry point
├── models/
│   ├── __init__.py
│   ├── requests.py                      # Pydantic request models
│   └── responses.py                     # Pydantic response models
├── routers/
│   ├── __init__.py
│   ├── health.py                        # Health check endpoint
│   └── programs.py                      # Program generation endpoints
└── services/
    ├── __init__.py
    ├── job_manager.py                   # Job status tracking
    └── program_generator.py             # Background GPT-5 generation
```

### Database
- `src/db/migrations/add_program_generation_jobs.py` - Migration script
- `src/db/models.py` - Added `ProgramGenerationJob` model

### Voice Agent
- `src/agents/voice_agent.py` - Refactored to use FastAPI:
  - `generate_workout_program()` - Calls FastAPI to start generation
  - `check_program_status()` - Polls for completion
  - Old GPT-5 code moved to `_generate_workout_program_old()` (deprecated)

### Documentation & Scripts
- `FASTAPI_SETUP.md` - Complete setup and usage guide
- `start_fastapi.sh` - Quick start script for FastAPI server
- `requirements.txt` - Updated with FastAPI dependencies

## How It Works

### Flow Diagram

```
1. User speaks → "I want to build muscle for 12 weeks"
                    ↓
2. Voice agent collects all parameters
                    ↓
3. generate_workout_program() called
                    ↓
4. POST /api/programs/generate (returns immediately with job_id)
                    ↓
5. Background worker starts GPT-5 generation
                    ↓
6. Voice agent waits 45 seconds
                    ↓
7. check_program_status() polls every 15 seconds
                    ↓
8. When complete → finish_program_creation()
                    ↓
9. Return to main menu
```

### Key Improvements

| Before (Direct GPT-5) | After (FastAPI) |
|----------------------|-----------------|
| 60-300 second blocking call | Returns in < 1 second |
| Voice agent freezes | Voice agent responsive |
| No progress updates | Can show 25%, 50%, 75% progress |
| Timeout errors | No timeouts |
| Single user at a time | Multiple concurrent users |
| Hard to debug | Separate logs for each component |

## Database Schema

### program_generation_jobs Table

```sql
CREATE TABLE program_generation_jobs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    status VARCHAR(50),           -- pending, in_progress, completed, failed
    progress INTEGER,              -- 0-100

    -- Input parameters
    height_cm DECIMAL(5,2),
    weight_kg DECIMAL(5,2),
    goal_category VARCHAR(50),
    goal_raw VARCHAR(500),
    duration_weeks INTEGER,
    days_per_week INTEGER,
    fitness_level VARCHAR(50),

    -- Output
    program_id UUID REFERENCES user_generated_programs(id),
    error_message VARCHAR(1000),

    -- Timestamps
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

## API Endpoints

### POST /api/programs/generate
Start a new program generation job.

**Request:**
```json
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
```

**Response (202 Accepted):**
```json
{
  "job_id": "uuid",
  "status": "pending",
  "message": "Program generation started"
}
```

### GET /api/programs/status/{job_id}
Check generation progress.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "in_progress",
  "progress": 65,
  "created_at": "2025-10-20T22:00:00Z",
  "started_at": "2025-10-20T22:00:05Z",
  "completed_at": null,
  "program_id": null
}
```

### GET /api/programs/{program_id}
Retrieve generated program.

**Response:**
```json
{
  "id": "uuid",
  "name": "12-Week Hypertrophy Program",
  "description": "...",
  "duration_weeks": 12,
  "created_at": "2025-10-20T22:02:00Z"
}
```

## Running the System

### Terminal 1: FastAPI Backend
```bash
./start_fastapi.sh
# or
cd src && uvicorn api.main:app --reload --port 8000
```

### Terminal 2: Voice Agent
```bash
python src/main.py
```

## Testing

### 1. Run Migration
```bash
python src/db/migrations/add_program_generation_jobs.py
```

### 2. Install Dependencies
```bash
pip install fastapi uvicorn httpx
```

### 3. Test FastAPI
```bash
# Start FastAPI
./start_fastapi.sh

# In another terminal, test health check
curl http://localhost:8000/api/health
```

### 4. Test End-to-End
1. Start FastAPI backend
2. Start voice agent
3. Create account (if needed)
4. Say "create a program"
5. Provide parameters
6. Watch the logs for:
   - `[PROGRAM] 🌐 Calling FastAPI to start generation...`
   - `[PROGRAM] ✅ Started generation job: xxx`
   - `[PROGRAM] Generation in progress: 40%`
   - `[PROGRAM] ✅ Program generation complete!`

## Code Changes Summary

### voice_agent.py
- ✅ Replaced direct GPT-5 call with FastAPI HTTP request
- ✅ Added `check_program_status()` for polling
- ✅ Removed `save_generated_program()` and `generate_program_markdown()` (FastAPI handles this)
- ✅ Kept old code as `_generate_workout_program_old()` for reference

### New FastAPI Backend
- ✅ Implements async job pattern
- ✅ Background task queue (using FastAPI BackgroundTasks)
- ✅ Progress tracking (0-100%)
- ✅ Error handling and logging
- ✅ Automatic API documentation (/docs)

### Database
- ✅ New `program_generation_jobs` table
- ✅ Migration script with rollback support
- ✅ Indexes on `user_id` and `status`

## Benefits

1. **Solves Timeout Issues** - Voice agent doesn't wait for long GPT-5 calls
2. **Better UX** - User gets progress updates
3. **Scalable** - Can handle multiple users
4. **Production-Ready** - Easy to deploy to cloud
5. **Easier Debugging** - Separate logs for backend and voice agent
6. **API Documentation** - Auto-generated Swagger UI at /docs

## Next Steps for Production

1. **Authentication** - Add API key authentication
2. **Rate Limiting** - Prevent abuse
3. **Caching** - Cache common program types
4. **Monitoring** - Add Sentry/Datadog
5. **Task Queue** - Migrate to Celery + Redis for robustness
6. **Deployment** - Deploy to AWS/GCP with Docker
7. **Webhooks** - Notify voice agent when generation completes (instead of polling)

## Environment Variables

Add to `.env`:
```bash
# Required
OPENAI_API_KEY=your_key_here

# Optional (defaults shown)
PROGRAM_CREATION_MODEL=gpt-5-mini
FASTAPI_URL=http://localhost:8000
```

## Troubleshooting

### FastAPI won't start
- Check if port 8000 is in use: `lsof -ti:8000`
- Make sure you're in `src/` directory

### Voice agent can't connect
- Verify FastAPI is running: `curl http://localhost:8000/api/health`
- Check `FASTAPI_URL` in `.env`

### Generation fails
- Check FastAPI terminal for GPT-5 API errors
- Verify `OPENAI_API_KEY` is set
- Check database connection

## Success Criteria

✅ FastAPI starts without errors
✅ Health check endpoint responds
✅ Database migration runs successfully
✅ Voice agent can start generation
✅ Status polling works
✅ Program saves to database
✅ No timeout errors
✅ Can handle user saying "OK" without triggering duplicate calls

## Files Modified

- `src/agents/voice_agent.py` - Refactored for FastAPI
- `src/db/models.py` - Added ProgramGenerationJob
- `requirements.txt` - Added FastAPI dependencies

## Files Added

- `src/api/` - Entire FastAPI backend (9 files)
- `src/db/migrations/add_program_generation_jobs.py`
- `FASTAPI_SETUP.md`
- `IMPLEMENTATION_SUMMARY.md` (this file)
- `start_fastapi.sh`
