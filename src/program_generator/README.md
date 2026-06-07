# program_generator/

6-layer agentic workout program generator. Takes an athlete profile and produces a complete periodized training program with exercise selection, volume prescription, and week-by-week progression.

## Architecture

The pipeline runs 6 layers in sequence. Layers 1-4 and 6 are deterministic (no LLM). Layer 5 uses LLM for validation review. Total runtime: <1 second without LLM, 10-20 seconds with.

| Layer | File | Purpose | LLM? |
|-------|------|---------|------|
| 1 | `layer1_profile_builder.py` | Build athlete profile from structured or natural language input | Optional |
| 2 | `layer2_strategy_engine.py` | Select training split + periodization strategy via rules engine | Optional fallback |
| 3 | `layer3_volume_engine.py` | Calculate volume allocation per muscle group/session | No |
| 4 | `layer4_program_builder.py` | Build program via 3-phase greedy exercise selection algorithm | No |
| 5 | `layer5_validator.py` | Validate constraints + auto-fix loop, LLM full-program review | Optional |
| 6 | `layer6_serializer.py` | Serialize to output JSON format | No |

## Entry Points

- `generate_program_v5()` — async entry point, used by Celery tasks
- `generate_program_v5_sync()` — synchronous wrapper for direct use
- CLI: `PYTHONPATH=src python -m program_generator.main`

## Key Files

- `schemas.py` — all Pydantic data models (`AthleteProfile`, `ProgramStrategy`, `BuiltProgram`, `PrescribedExercise`, etc.)
- `exercise_library.py` — 144-exercise catalog with muscle targets, equipment, difficulty
- `volume_tables.py` — evidence-based volume landmarks per muscle group
- `split_templates.py` — training split templates (PPL, Upper/Lower, Full Body, etc.)
- `sport_mappings.py` — sport-specific training emphasis maps
- `vbt_profiles.py` — velocity-based training profiles per exercise
- `scoring.py` — exercise selection scoring algorithm
- `prompts.py` — LLM prompt templates for profile extraction and week review
- `mutator.py` — program mutation operators for LLM-driven modifications

## How It Works

1. **Profile** — structured user data (age, experience, goals, equipment, injuries) is normalized into an `AthleteProfile`
2. **Strategy** — rules engine picks split type, periodization model, session frequency based on the profile
3. **Volume** — calculates weekly sets per muscle group using evidence-based volume landmarks, distributed across sessions
4. **Build** — greedy algorithm fills each session: primary compounds first, then accessories, then isolation. Scores exercises by muscle coverage, equipment match, and progression fit
5. **Validate** — checks constraints (session duration, exercise variety, volume balance), auto-fixes violations, optionally sends to LLM for review
6. **Serialize** — maps internal `BuiltProgram` to the output JSON schema
