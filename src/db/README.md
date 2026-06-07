# db/

SQLAlchemy database layer for Nowva. PostgreSQL in production, SQLite for local development.

## Key Files

- `models.py` — SQLAlchemy ORM models: `User`, `Program`, `Workout`, `Schedule`, `CalibrationProfile`, `ProgramGenerationJob`
- `database.py` — engine and session factory (`get_db()`, `init_db()`)
- `setup_db.py` — database initialization and table creation

## Utility Modules

| Module | Purpose |
|--------|---------|
| `calibration_utils.py` | Save/load user biomechanical calibration profiles |
| `program_utils.py` | Program CRUD operations |
| `progress_utils.py` | Workout progress tracking and VBT metrics |
| `schedule_utils.py` | Training schedule management |
| `schedule_history.py` | Schedule modification history |
| `recovery_analysis.py` | Recovery and readiness scoring |
| `training_load.py` | Training load calculations (tonnage, intensity) |

## Migrations

Manual migration scripts in `migrations/`. Each adds columns or tables to the schema. Run them directly:

```bash
PYTHONPATH=src python -m db.migrations.add_athlete_params_to_calibrations
```

## Configuration

Set `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgresql://user:pass@localhost:5432/nowva
```

Falls back to SQLite (`nowva.db`) if not set.
