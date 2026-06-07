# src/

Main source code for Nowva. All Python imports assume `src/` is on `sys.path` (set via `PYTHONPATH=src` or `sys.path.insert` in entry points).

## Entry Point

`main.py` — orchestrates the full console application: starts FastAPI, voice agent, and biomechanics pipeline as subprocesses, connected via UNIX socket IPC.

## Directory Map

| Directory | Purpose |
|-----------|---------|
| `agent/` | Voice agent stack — conversational AI, session management, coaching services |
| `biomechanics/` | Core IP — real-time squat diagnosis engine (pose → IK → faults → coaching) |
| `program_generator/` | 6-layer agentic workout program generator |
| `api/` | FastAPI REST backend (auth, programs, workouts, LiveKit tokens) |
| `db/` | SQLAlchemy models, migrations, and database utilities |
| `auth/` | User authentication and account management |
| `assets/` | Pre-cached audio cue WAV files |
| `templates/` | HTML/CSS templates for program PDF generation |
| `utils/` | Shared utilities (date parsing, username generation) |

## Import Conventions

- `import numpy as np` — always aliased
- `from agent.core.X import Y` — voice agent infrastructure
- `from biomechanics.X import Y` — diagnosis engine
- `from program_generator import generate_program_v5` — program generation
- `from api.main import app` — FastAPI app
