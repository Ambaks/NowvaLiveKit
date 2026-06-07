# Pre-Workout Assessment & Coaching Agent — Context Document

## User's Original Request

> no. We should only use the coaching agent when we want to. In the main pipeline that is: right before calibration (we do this to see if the user has bad form that needs to be fixed before we calibrate). Once the user passes (no immediate fixes to be given) we move onto calibration.
>
> I want to be able to test this by running main.py and doing a set of squats for the first time. It should flag that i have never done squats (no calibration data for squats like dorsiflexion etc..) and then it should ask me to do two reps at bodyweight. This is where we loop until the issues are fixed. after that, we calibrate (5 reps), get the data and save it (so next time we dont go through this and everything is already saved. The peak dorsi and all that info should be saved. We should have a reference squat for a user after running through the coaching agent that we can always access fast for comparisons.)

---

## What Needs to Be Built

A **pre-workout form assessment** phase that runs before calibration for first-time users. The coaching agent (diagnosis engine) runs on 2 bodyweight reps, identifies immediate form issues (e.g., knee valgus, excessive forward lean), and loops the user through corrective feedback until no immediate causes are detected. Only then does calibration proceed. The result is a persisted **reference squat profile** for the user.

### Flow for a First-Time User

```
User says "let's squat"
  → check_calibration(user_id, "Barbell Back Squat") → None (no data)
  → Voice agent: "I don't have your movement data yet. Do 2 bodyweight squats."
  → Pipeline starts in ASSESSMENT mode (2 reps, diagnosis engine runs)
  → Diagnosis engine produces DiagnosisResult
  → IF immediate_causes exist:
      → Voice agent speaks the top issue + adjustment
      → "Try again — 2 more reps"
      → Loop
  → IF no immediate_causes (user passes):
      → Move to CALIBRATION mode (5 reps, standard CalibrationTracker)
      → Save peaks, thresholds, athlete_params, baseline to DB
      → This becomes the user's reference squat
  → Proceed to workout
```

### Flow for a Returning User

```
User says "let's squat"
  → check_calibration(user_id, "Barbell Back Squat") → {thresholds dict}
  → Load calibration profile (already have reference squat)
  → Skip assessment, skip calibration
  → Proceed directly to workout
```

---

## Current System State

### How Calibration Works Today

1. **Detection**: `main_menu_agent.py:84-93` and `main_menu_agent.py:186-197` call `check_calibration()` when starting a workout or quick exercise. If no calibration exists in DB, it sets `calibration.active = True` in state.

2. **Pipeline launch**: `main.py:521-537` reads `calibration.active` from state and passes `calibration_mode=True` to the pipeline subprocess.

3. **Pipeline calibration phase**: `pose_estimation_process.py:190-341` runs a `CalibrationTracker` for 5 reps:
   - Records peak angles per frame (trunk flexion, hip adduction, asymmetry, dorsiflexion drop, knee flexion)
   - On completion: builds calibration profile, applies to rule engine, sends `calibration_complete` IPC message
   - Extracts `athlete_params` (shoulder_width, femur, torso, hip_width, tibia, foot lengths) from bone constraints
   - Extracts `baseline` (peakDorsi, peakKneeFlex) from peaks
   - Calls `session_tracker.set_athlete_params(athlete_params, baseline)`

4. **Voice agent side**: `coaching_service.py:283-381` handles `calibration_complete` — saves peaks + thresholds to `UserCalibration` table via `save_user_calibration()`, stores profile in state, announces completion.

5. **WorkoutAgent greeting**: `workout_agent.py:48-68` checks `calibration.active` and speaks a greeting telling the user to do 5 bodyweight squats.

### What Gets Saved to DB

**Table**: `user_calibrations` (`src/db/models.py`)
- `user_id` (UUID FK → users)
- `movement_pattern` (e.g., "squat")
- `peaks` (JSONB): `{trunk_flexion, hip_adduction, hip_adduction_per_rep, asymmetry, dorsiflexion_drop, avg_depth, depth_per_rep}`
- `thresholds` (JSONB): `{knee_valgus: {mild, moderate, severe}, forward_lean: {...}, bilateral_asymmetry: {...}, heel_rise: {threshold_degrees}, depth: {parallel_threshold, half_threshold, quarter_threshold}}`
- `calibration_reps` (int)

**What's NOT saved today**: `athlete_params` (bone lengths) and `baseline` (peakDorsi, peakKneeFlex) — these are only set on `SessionTracker` in-memory. They're lost after the session ends.

### The Diagnosis Engine

**Files**: `src/biomechanics/diagnosis/`

The engine takes a `SetFeatures` (per-rep kinematics + anthropometry + ROM) and produces:

- **`DiagnosisResult`** (`types.py:67-76`):
  - `detected_symptoms`: list of `DetectedSymptom(symptom_id, severity, contributing_reps)`
  - `immediate_causes`: list of `HypothesizedCause` — **tier 1**, actionable right now (e.g., "narrow stance causing knee valgus", with `parameter_delta: {stance_width: +15%}`)
  - `session_causes`: tier 2, session-level patterns
  - `longterm_causes`: tier 3
  - `contextual_notes`: tier 4
  - `combined_perturbation`: dict of all parameter adjustments
  - `confidence`: 0.0-1.0

- **`SetScoreSummary`** (`types.py:59-64`):
  - `mean_score`: 0.0-1.0 composite
  - `per_rep_scores`: list of `RepScore` (depth, trunk_control, knee_tracking, symmetry, ankle_utilization, composite)
  - `best_rep_number`, `worst_rep_number`, `trend_slope`

**To run the engine on live data you need**:
1. `bottom_kpts` (19×3 keypoints at max knee flexion) + `bottom_angles` (JointAngles.as_dict()) per rep
2. `athlete_params` dict: `{shoulder_width_m, femur_avg_m, torso_avg_m, hip_width_m, tibia_avg_m, foot_avg_m}`
3. `baseline` dict: `{peakDorsi, peakKneeFlex}`

**The bridge** (`diagnosis/bridge.py`) converts live pipeline data → engine input:
- `build_frame_from_live_pipeline(bottom_kpts, bottom_angles)` → frame dict
- `build_rep_kinematic_summary(frame, athlete_params, rep_number)` → `RepKinematicSummary`
- `build_anthro_dict(athlete_params)` → anthropometry dict for engine
- `build_rom_dict(athlete_params, baseline)` → ROM dict for engine

**Problem for assessment**: The engine needs `athlete_params` from bone constraints, which are only available after the pipeline has seen enough standing frames to calibrate bone lengths. The readiness gate must pass first. But we do NOT need calibration peaks (those come from the 5-rep calibration phase).

### IPC Message Flow

Pipeline → main.py IPC server → forwarded to coaching IPC → CoachingService → CoachingOrchestrator

**Currently forwarded** (`main.py:487`): `cache_cues, fault, rep_complete, rest_complete, frame_data, calibration_rep, calibration_complete`

**NOT forwarded**: `diagnosis_complete`, `set_complete`, `pipeline_status`, `rep_count`

This is a bug — `diagnosis_complete` should be in the forward list for the current set recap feature to work.

### How the Coaching Agent Currently Fires

The set recap (LLM call with diagnosis data) **only fires when target reps are hit** (`coaching_orchestrator.py:342-346`). It does NOT fire for:
- Timeout-based set ends
- User verbally stopping a set
- Open-ended sets (no target reps)

The user wants the coaching agent to fire **on demand** — specifically during the pre-workout assessment loop, not automatically at set end.

---

## Key Files Reference

| Component | Path | What it does |
|---|---|---|
| Main orchestrator | `src/main.py` | Launches pipeline subprocess, forwards IPC messages |
| Pipeline entry | `src/pose/pose_estimation_process.py` | Calibration phase + main loop, sends IPC |
| Calibration logic | `src/biomechanics/calibration.py` | `CalibrationTracker`, `build_calibration_profile()`, `apply_calibration_to_rule_engine()` |
| Calibration DB | `src/db/calibration_utils.py` | `save_user_calibration()`, `get_user_calibration()`, `get_user_calibration_full()` |
| UserCalibration model | `src/db/models.py` | SQLAlchemy model with peaks, thresholds, calibration_reps |
| Agent helpers | `src/agents/shared/helpers.py` | `check_calibration()`, `start_calibration_mode()` |
| Main menu agent | `src/agents/main_menu_agent.py` | Checks calibration, triggers calibration mode |
| Workout agent | `src/agents/workout_agent.py` | Greeting, wake word, coaching service lifecycle |
| Coaching service | `src/services/coaching_service.py` | IPC listener, handles all message types, saves calibration to DB |
| Coaching orchestrator | `src/services/coaching_orchestrator.py` | Priority queue dispatch, LLM set/exercise recaps, `set_diagnosis_data()`, `_build_diagnosis_context()` |
| IPC bridge | `src/biomechanics/coaching/ipc_bridge.py` | Translates pipeline events → IPC messages, `send_diagnosis_complete()` |
| Session tracker | `src/biomechanics/coaching/session_tracker.py` | Set boundary detection, buffers `RepKinematicSummary`, runs diagnosis at set end |
| Diagnosis engine | `src/biomechanics/diagnosis/engine.py` | `HypothesisEngine.diagnose(set_features)` → `DiagnosisResult` |
| Diagnosis bridge | `src/biomechanics/diagnosis/bridge.py` | `build_frame_from_live_pipeline()`, `build_rep_kinematic_summary()`, `build_anthro_dict()`, `build_rom_dict()` |
| Diagnosis types | `src/biomechanics/diagnosis/types.py` | `RepKinematicSummary`, `SetFeatures`, `DiagnosisResult`, `SetScoreSummary`, `RepScore` |
| Rep scoring | `src/biomechanics/diagnosis/rep_scoring.py` | `score_set()` → `SetScoreSummary` |
| Pipeline core | `src/biomechanics/pipeline.py` | `BiomechanicsPipeline`, `consume_bottom_frame()`, bone constraints, readiness gate |

---

## Gaps to Address

### 1. No Assessment Phase Exists
There is no concept of a "form check" or "assessment" phase. The pipeline goes straight from readiness gate → calibration → workout. An assessment phase needs to be inserted between readiness gate and calibration.

### 2. Athlete Params Not Persisted
`athlete_params` (bone lengths from bone constraints) is only set in-memory on `SessionTracker` during calibration. It's never saved to the DB. For a returning user, we'd need to re-derive it from standing frames or save it with the calibration data.

**What should be saved as the "reference squat"**:
- Current `peaks` and `thresholds` (already saved)
- `athlete_params` dict: `{shoulder_width_m, femur_avg_m, torso_avg_m, hip_width_m, tibia_avg_m, foot_avg_m}`
- `baseline` dict: `{peakDorsi, peakKneeFlex}`
- Possibly the `RepKinematicSummary` from the passing assessment reps (the "reference rep")

### 3. Diagnosis Engine Needs Athlete Params for Assessment
The engine needs `athlete_params` to compute stance_width_ratio, femur/torso ratio, etc. During assessment (before calibration), bone constraints should already be calibrated from the standing phase (readiness gate). Need to verify this is the case and extract `athlete_params` at that point.

### 4. `diagnosis_complete` Not Forwarded in main.py
`main.py:487` doesn't include `diagnosis_complete` in the IPC forward list. This means the voice agent never receives diagnosis results. This is a bug even for the current set recap feature.

### 5. Assessment Loop Needs New IPC Messages
The assessment phase needs new IPC message types:
- `assessment_start`: tells voice agent assessment is beginning
- `assessment_result`: sends diagnosis results after 2 assessment reps (same structure as `diagnosis_complete` but specific to assessment)
- `assessment_pass`: user passed, moving to calibration
- Or: reuse `diagnosis_complete` with an additional `phase: "assessment"` field

### 6. Voice Agent Needs Assessment Handler
`CoachingService` needs to handle assessment results and either:
- Speak the corrective feedback and tell the user to try again
- Or announce they passed and calibration is starting

### 7. Reference Squat Storage
Need a way to store and quickly retrieve a user's reference squat profile. Options:
- Extend `UserCalibration` model with `athlete_params` and `baseline` JSON columns
- Add a separate `UserReferenceSquat` model
- Store on the `User` model itself

The simplest: add `athlete_params` (JSONB) column to `user_calibrations` table. Then `get_user_calibration_full()` returns everything needed to skip both assessment and calibration.

---

## Pipeline Modes Summary

The pipeline subprocess (`pose_estimation_process.py`) currently has two modes:
1. **Calibration mode** (`calibration_mode=True`): runs `CalibrationTracker` for N reps, then enters main loop
2. **Normal mode** (`calibration_mode=False`, optionally with `calibration_file`): loads existing profile, enters main loop directly

A third mode is needed:
3. **Assessment mode**: runs 2 reps, runs diagnosis engine, sends results to voice agent. Loops if issues found. Then transitions to calibration mode.

This could be:
- A new flag (`assessment_mode=True`) on the pipeline subprocess
- Or: the pipeline always runs assessment before calibration when `calibration_mode=True` (since calibration already implies first-time user)
- Or: assessment is handled as part of the calibration phase, with a pre-check loop before the CalibrationTracker starts

### Pipeline startup sequence for first-time user:
```
Readiness gate (standing detection, bone constraint calibration)
  → Assessment loop (2 reps → diagnosis → pass/fail → repeat if fail)
  → Calibration (5 reps → CalibrationTracker → peaks → profile)
  → Main workout loop
```

### Pipeline startup for returning user:
```
Readiness gate (standing detection, bone constraint calibration)
  → Load calibration from file → apply to rule engine
  → Set athlete_params from saved data (no need to wait for bone constraints)
  → Main workout loop
```
