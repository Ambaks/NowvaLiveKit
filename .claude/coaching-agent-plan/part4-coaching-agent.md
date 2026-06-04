# Part 4: CoachingAgent

## Goal
Create the CoachingAgent — a BaseNovaAgent that runs an iterative coaching loop: receive rep data → diagnose → score → coach via LLM → repeat until acceptable or max iterations.

## New files

### `src/agents/coaching_agent.py`

**Constructor params:**
- `state`, `userdata` — standard
- `exercise: str` — exercise being coached
- `max_iterations: int` — configurable per invocation
- `acceptable_score: float = 0.75` — composite score threshold
- `run_calibration_after: bool = False` — trigger 5-rep calibration on exit
- `context: dict | None` — prior coaching history from caller

**Key methods:**
- `on_enter()` — load athlete params, create HypothesisEngine, register callback on CoachingService, enable coaching mode on orchestrator, deliver opening speech
- `_on_rep_data(message)` — the per-rep loop: build RepKinematicSummary via bridge, run diagnosis, score rep, decide (acceptable / max reached / iterate), generate LLM coaching cue
- `_finish()` — set-level summary, store results in state, unregister callback, disable coaching mode, optionally trigger calibration, hand off to WorkoutAgent
- `move_on()` function tool — user exits early

**Per-rep LLM prompt should include:**
- Current rep score (composite + sub-scores)
- Top tier-1 cause with explanation and specific numbers
- Past iteration results for coherent progression
- Instruction to give ONE specific cue, acknowledge improvement

**On finish:**
- Run `score_set()` on all accumulated reps
- Run set-level `engine.diagnose()`
- Store in state as `coaching.last_results` for downstream use
- If `run_calibration_after`: set `calibration.active = True`, announce calibration

**Handoff:** Always creates WorkoutAgent on exit (same pattern as TeachingAgent → WorkoutAgent)

### `src/agents/prompts/coaching_prompt.py`
System prompt for the CoachingAgent persona.

## Key dependencies
- `biomechanics.diagnosis.engine.HypothesisEngine`
- `biomechanics.diagnosis.bridge.build_frame_from_ipc`, `build_rep_kinematic_summary`, `build_anthro_dict`, `build_rom_dict`
- `biomechanics.diagnosis.rep_scoring.score_rep`, `score_set`
- `biomechanics.diagnosis.types.SetFeatures`, `RepKinematicSummary`
- Parts 1-3 must be done first for full functionality, but agent can be built with graceful degradation (fall back to basic coaching from `is_clean`/`faults_in_rep` if enriched data not present)

## Verification
- Mock IPC messages with bottom_kpts/bottom_angles, verify diagnosis runs and LLM prompt is constructed correctly
- Test early exit via move_on tool
- Test max iterations reached behavior
- Test acceptable score reached on first rep (should finish immediately)
