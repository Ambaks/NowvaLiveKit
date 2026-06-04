# Part 3: SessionTracker Diagnosis Integration

## Goal
Wire the diagnosis engine into `SessionTracker` so that per-rep kinematic summaries are built in real-time as reps complete, and at set end the engine runs on the full set and sends structured results to the voice agent via IPC.

## Data flow
```
Rep completes
  → SessionTracker already receives bottom_kpts + bottom_angles
  → build_frame_from_live_pipeline() (Part 2)
  → build_rep_kinematic_summary() → buffer RepKinematicSummary
  → (repeat for each rep in set)

Set ends (timeout / target reps / rest_start / workout_complete)
  → Build SetFeatures from buffered summaries + athlete params
  → Run HypothesisEngine.diagnose() → DiagnosisResult
  → Run score_set() → SetScoreSummary
  → Send diagnosis_complete IPC message
```

## Files to modify

### `src/biomechanics/coaching/session_tracker.py`

**New state:**
- `_rep_kinematic_buffer: list[RepKinematicSummary]` — accumulated per-rep summaries for the current set
- `_athlete_params: dict | None` — anthropometry from calibration (shoulder_width_m, femur_avg_m, etc.)
- `_baseline: dict | None` — ROM baseline (peakDorsi, peakKneeFlex)

**New method: `set_athlete_params(athlete_params, baseline)`**
- Called once when calibration completes (pipeline already runs calibration and has these measurements)
- Stored for use across all subsequent sets

**Modify `on_rep_complete()`:**
- After appending to `current_set_reps` and sending `rep_complete` via IPC (existing behavior)
- If `_athlete_params` is set: convert `bottom_kpts` + `bottom_angles` to `RepKinematicSummary` via `build_frame_from_live_pipeline()` → `build_rep_kinematic_summary()`
- Append to `_rep_kinematic_buffer`
- If athlete params are not set, skip silently (diagnosis not available pre-calibration)

**Modify `_end_current_set()`:**
- After existing set summary computation and `send_set_complete()` (unchanged)
- If `_rep_kinematic_buffer` is non-empty and `_athlete_params` is set:
  - Build `SetFeatures` from buffer + athlete params + baseline
  - Run `HypothesisEngine.diagnose(set_features)`
  - Run `score_set(buffer, anthro, rom)`
  - Call `ipc_bridge.send_diagnosis_complete(...)` with structured results
- Clear `_rep_kinematic_buffer`

**Modify `reset()`:**
- Also clear `_rep_kinematic_buffer`

### `src/biomechanics/coaching/ipc_bridge.py`

**New method: `send_diagnosis_complete(set_number, diagnosis_result, score_summary)`**

Message format:
```python
{
    "type": "diagnosis_complete",
    "set_number": set_number,
    "diagnosis": {
        "confidence": diagnosis_result.confidence,
        "detected_symptoms": [
            {"symptom_id": s.symptom_id, "severity": s.severity, "contributing_reps": s.contributing_reps}
            for s in diagnosis_result.detected_symptoms
        ],
        "immediate_causes": [
            {"cause_id": c.cause_id, "score": c.score, "explanation": c.explanation, "parameter_delta": c.parameter_delta}
            for c in diagnosis_result.immediate_causes
        ],
        "session_causes": [
            {"cause_id": c.cause_id, "score": c.score, "explanation": c.explanation}
            for c in diagnosis_result.session_causes
        ],
        "combined_perturbation": diagnosis_result.combined_perturbation,
    },
    "scoring": {
        "mean_composite": score_summary.mean_composite,
        "per_dimension": score_summary.per_dimension,  # depth, trunk, knee, symmetry, ankle
        "best_rep": score_summary.best_rep,
        "worst_rep": score_summary.worst_rep,
        "trend_slope": score_summary.trend_slope,
    },
}
```

The voice agent receives this single message at set end — no keypoints, no raw angles, just the engine's structured output.

## Where do athlete_params come from?

The pipeline already computes anthropometric measurements during calibration (standing pose → segment lengths). The `set_athlete_params()` method should be called after calibration completes in `pose_estimation_process.py`, extracting the relevant measurements from the pipeline's calibration data. Exact source TBD — check what `calibration.py` already computes and map to the dict format `bridge.build_anthro_dict()` expects.

## Verification
- Run pipeline with calibration → verify `set_athlete_params()` is called with reasonable values
- Complete a set of squats → verify `_rep_kinematic_buffer` accumulates one entry per rep
- On set end → verify `diagnosis_complete` IPC message is sent with valid engine output
- Verify existing `set_complete` IPC message still fires (backward compat — orchestrator still needs it)
- Test without calibration data → verify diagnosis is skipped gracefully, no errors
