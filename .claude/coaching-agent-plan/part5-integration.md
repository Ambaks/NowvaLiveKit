# Part 5: Integration & End-to-End Wiring

## Goal
Connect the athlete params pipeline (calibration → SessionTracker), verify the full loop works end-to-end, and handle edge cases.

## Files to modify

### `src/pose/pose_estimation_process.py`

**Wire athlete params after calibration:**
- After calibration completes (the pipeline already detects this), extract anthropometric measurements and ROM baseline
- Call `session_tracker.set_athlete_params(athlete_params, baseline)`
- Source: the pipeline's calibration step already computes segment lengths from the standing pose. Map these to the dict format `bridge.build_anthro_dict()` expects: `shoulder_width_m`, `femur_avg_m`, `torso_avg_m`, `hip_width_m`, `tibia_avg_m`, `foot_avg_m`
- ROM baseline: `peakDorsi` and `peakKneeFlex` from calibration peaks (already computed and sent via `calibration_complete` IPC message)

**Verify message ordering:**
- `set_complete` and `diagnosis_complete` are both sent from `SessionTracker._end_current_set()`
- They go through the same IPC socket sequentially, so ordering is guaranteed
- Voice agent receives `set_complete` first (existing behavior), then `diagnosis_complete`

### `src/biomechanics/coaching/session_tracker.py`

**Handle edge case: set ends before calibration**
- If `_athlete_params` is None, `_end_current_set()` skips diagnosis entirely
- `set_complete` still fires (existing behavior preserved)
- No error, no warning — just no diagnosis data

**Handle edge case: reps with missing bottom frame data**
- If `bottom_kpts` or `bottom_angles` is None for a rep, skip `RepKinematicSummary` for that rep
- Diagnosis still runs on whatever reps had complete data
- If zero reps had complete data, skip diagnosis

### `src/services/coaching_service.py`

**Handle edge case: `diagnosis_complete` arrives with no active orchestrator**
- Log and drop (same pattern as other message types)

**Handle edge case: `diagnosis_complete` arrives after set recap already spoke**
- The orchestrator stores it — it'll be available for the exercise recap at minimum
- In practice this shouldn't happen (same IPC socket, sequential sends)

## End-to-end verification

### Happy path
1. Run pipeline + voice agent
2. Complete calibration (triggers `set_athlete_params`)
3. Do a set of 5 squats with intentional knee valgus
4. Set ends → verify in logs:
   - `rep_complete` × 5 (existing)
   - `set_complete` × 1 (existing)
   - `diagnosis_complete` × 1 (new — should show knee_valgus as detected symptom)
5. Voice agent speaks set recap → verify it references the diagnosis ("your knees were caving in, try widening your stance")
6. Complete all sets → exercise recap includes cross-set trends

### Pre-calibration
1. Start pipeline, do reps before calibration
2. `set_complete` fires, `diagnosis_complete` does NOT fire
3. Set recap uses existing basic stats only — no regression

### Early termination
1. Start a set, do 2 reps, say "stop" (triggers `rest_start` or `workout_complete`)
2. `_end_current_set()` fires with 2 reps
3. Diagnosis runs on 2 reps (engine handles small rep counts)
4. Results sent to voice agent

### Missing data
1. Simulate reps where bottom frame capture fails (bottom_kpts is None)
2. Those reps are excluded from kinematic buffer
3. Diagnosis runs on remaining reps, or is skipped if all are missing

## What's NOT in scope
- Per-rep LLM coaching cues (diagnosis is set-level, not per-rep)
- New agent types or agent handoffs
- Coaching mode toggle on orchestrator (not needed — existing flow is enriched, not replaced)
- Sending keypoints to the voice agent
