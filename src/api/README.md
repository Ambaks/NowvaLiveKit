# api/

FastAPI REST backend for Nowva. Handles program generation and workout tracking.

## How to Run

```bash
PYTHONPATH=src uvicorn api.main:app --port 8000
```

Or via the deploy script: `scripts/deploy/start_fastapi.sh`

## Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `health.py` | `/health` | Health check endpoint |
| `auth.py` | `/auth` | User registration and login |
| `programs.py` | `/programs` | Program generation (async via Celery), retrieval, PDF download |
| `workouts.py` | `/workouts` | Workout session tracking and progress |

## Services

- `job_manager.py` — manages async Celery job lifecycle for program generation
- `program_saver_v5.py` — persists generated programs to database
- `program_updater.py` — LLM-powered program modification (swap exercises, adjust volume)
- `pdf_generator.py`, `html_generator.py`, `markdown_generator.py` — program export formats
- `exercise_library_service.py` — exercise search and metadata
- `v5_adapter.py` — adapts V5 program generator output for the API response schema

## Background Tasks

`celery_tasks.py` defines Celery tasks for async program generation. Workers connect to Valkey (Redis-compatible) and are started via `scripts/deploy/start_celery_workers.sh`.
