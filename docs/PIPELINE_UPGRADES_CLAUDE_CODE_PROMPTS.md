# NowvaLiveKit — Claude Code Prompts for Pipeline Upgrades

**Usage:** Feed each prompt to Claude Code in sequence. Each prompt assumes the previous one was completed. Before starting, make sure Claude Code has access to the `docs/PIPELINE_UPGRADES_IMPLEMENTATION.md` spec file in the repo.

---

## Prompt 0: Context Loading

```
Read the file docs/PIPELINE_UPGRADES_IMPLEMENTATION.md thoroughly. This is the implementation specification for 5 new features being added to the biomechanics pipeline. All subsequent tasks reference this document.

Also read and understand these existing files to establish context:
- src/biomechanics/pipeline.py (the main pipeline we're modifying)
- src/biomechanics/utils/types.py (Skeleton3D, JointAngles, Point3D, CocoKeypoints)
- src/biomechanics/utils/geometry.py (existing geometry helpers)
- src/biomechanics/utils/filters.py (existing One Euro Filter and JointAngleFilter)
- src/biomechanics/utils/derivatives.py (existing DerivativeTracker and AngleDerivatives)
- src/biomechanics/faults/rule_engine.py (existing fault detection)
- src/biomechanics/faults/rep_counter.py (existing rep counter with phase detection)
- src/biomechanics/config.py (existing config system — Pydantic models + YAML loading)
- config/biomechanics.yaml (existing config file)

Do not make any changes yet. Just confirm you've loaded everything and understand the current architecture.
```

---

## Prompt 1: Config Models

```
Following the spec in docs/PIPELINE_UPGRADES_IMPLEMENTATION.md, Section 8 (Config Changes):

1. Add these 4 new Pydantic config models to src/biomechanics/config.py:
   - VelocityClampConfig (max_velocity_m_per_s: float = 2.5)
   - BoneConstraintsConfig (calibration_frames: int = 30, tolerance: float = 0.15)
   - ConfidenceBlendConfig (min_confidence: float = 0.1, max_confidence: float = 0.9)
   - PredictiveStateConfig (horizon_seconds: float = 0.2, max_extrapolation_deg: float = 15.0)

2. Add all 4 as fields on BiomechanicsConfig with default_factory.

3. Update the YAML loading in load_pipeline_config() so these new sections are parsed if present in the YAML file.

4. Add the corresponding sections to config/biomechanics.yaml with the default values.

Keep all existing config models and fields unchanged. Only add — do not modify or remove anything existing.
```

---

## Prompt 2: Confidence-Weighted Blending

```
Following the spec in docs/PIPELINE_UPGRADES_IMPLEMENTATION.md, Section 4 (Confidence-Weighted Blending):

Create the new file src/biomechanics/utils/confidence_blend.py with the ConfidenceBlender class.

Requirements:
- Takes min_confidence and max_confidence constructor params
- blend() method takes a Skeleton3D, returns a new Skeleton3D
- First frame: stores positions, returns unchanged
- Subsequent frames: for each keypoint, computes a blend weight by mapping its confidence from [min_confidence, max_confidence] to [0, 1], then blends: weight * detected + (1-weight) * previous
- Preserves original confidence values, timestamp, frame_index on the returned Skeleton3D
- Has a reset() method that clears _prev_positions
- Uses numpy vectorized operations, not per-keypoint Python loops

Write a unit test file tests/test_biomechanics/test_confidence_blend.py with these test cases:
1. test_first_frame_passthrough — first call returns skeleton unchanged
2. test_high_confidence_passthrough — all confidences 0.95, output matches input within 1e-6
3. test_low_confidence_uses_previous — all confidences 0.05, output matches previous frame within 1e-6
4. test_mid_confidence_interpolation — confidence 0.5 (which maps to 0.5 blend weight given default params), output is midpoint of current and previous
5. test_reset_clears_state — after reset, next call acts as first frame

Use Skeleton3D.from_numpy() to create test skeletons. Use numpy for assertions (np.allclose).
```

---

## Prompt 3: Velocity Clamping

```
Following the spec in docs/PIPELINE_UPGRADES_IMPLEMENTATION.md, Section 2 (Velocity Clamping):

Create the new file src/biomechanics/utils/velocity_clamp.py with the VelocityClamp class.

Requirements:
- Constructor takes max_velocity_m_per_s (default 2.5) and target_fps (default 30)
- Computes max_displacement = max_velocity_m_per_s / target_fps in __init__
- clamp() method takes Skeleton3D, returns Skeleton3D
- First frame: stores positions, returns unchanged
- Subsequent frames: for each keypoint, if displacement from previous > max_displacement, clamp to max_displacement along the direction of movement
- Direction is preserved: clamped_pos = prev + unit_direction * max_displacement
- Keypoints within threshold are unchanged
- Preserves confidence, timestamp, frame_index
- Uses numpy vectorized operations for the distance check and clamping
- Has reset() method

Write tests/test_biomechanics/test_velocity_clamp.py with:
1. test_first_frame_passthrough
2. test_within_threshold_unchanged — move keypoints 0.01m (well within 0.083m default threshold), verify output equals input
3. test_teleport_clamped — move one keypoint 0.5m, verify output distance from previous equals max_displacement
4. test_direction_preserved — after clamping, verify direction vector from prev to clamped matches direction from prev to detected
5. test_reset_clears_state
6. test_multiple_frames_accumulate — clamp a teleporting joint over 3 frames, verify it gradually approaches the target position
```

---

## Prompt 4: Bone Length Constraints

```
Following the spec in docs/PIPELINE_UPGRADES_IMPLEMENTATION.md, Section 3 (Bone Length Constraints):

Create the new file src/biomechanics/utils/bone_constraints.py with the BoneLengthConstraints class.

Requirements:
- Uses BONE_PAIRS constant: list of (proximal_idx, distal_idx) tuples following COCO 17 ordering. Include: left/right shoulder-hip, shoulder-shoulder, hip-hip, left/right hip-knee, knee-ankle, shoulder-elbow, elbow-wrist.
- Order BONE_PAIRS proximal-to-distal so corrections cascade correctly (torso first, then legs, then arms).
- Constructor takes calibration_frames (default 30) and tolerance (default 0.15)
- enforce() method: during calibration phase (first calibration_frames frames), records bone lengths per pair. After calibration, computes median length per pair and locks it.
- After calibration: for each bone pair, if abs(current_length - calibrated_length) / calibrated_length > tolerance, project the DISTAL keypoint back to calibrated_length along the direction from proximal to distal.
- Handle degenerate case where distal == proximal (distance ~0) by pushing distal in +Y direction.
- is_calibrated property
- reset() method
- Uses CocoKeypoints constants for index references

Write tests/test_biomechanics/test_bone_constraints.py with:
1. test_calibration_completes — feed 30 consistent skeletons, verify is_calibrated becomes True
2. test_not_calibrated_returns_unchanged — during calibration, skeleton passes through unmodified
3. test_violation_corrected — after calibration with femur=0.4m, feed skeleton where femur=0.7m, verify distal keypoint is projected to 0.4m from proximal
4. test_within_tolerance_unchanged — bone at 10% deviation (within 15% tolerance) passes through
5. test_direction_preserved_after_correction — corrected distal keypoint is on the line from proximal to original distal
6. test_reset_clears_calibration
```

---

## Prompt 5: Predictive Fault Pre-Cueing

```
Following the spec in docs/PIPELINE_UPGRADES_IMPLEMENTATION.md, Section 5 (Predictive Fault Pre-Cueing):

Create the new file src/biomechanics/utils/predictive_state.py with the PredictiveStateEstimator class.

Requirements:
- Constructor takes horizon_seconds (default 0.2) and max_extrapolation_deg (default 15.0)
- predict() method takes JointAngles and AngleDerivatives, returns a new JointAngles
- For angles that have velocity tracking (hip_flexion_l/r, knee_flexion_l/r): predicted = current + velocity * horizon_seconds, clamped to max_extrapolation_deg
- For angles without velocity tracking in DerivativeTracker (hip_adduction, hip_rotation, ankle_dorsiflexion, trunk angles, pelvis angles): copy current values unchanged
- timestamp and frame_index are copied from input angles
- The _extrapolate helper should clamp: if abs(velocity * dt) > max_extrapolation_deg, limit delta to ±max_extrapolation_deg

Write tests/test_biomechanics/test_predictive_state.py with:
1. test_zero_velocity_unchanged — zero velocities produce identical angles
2. test_positive_velocity_extrapolation — knee_velocity_l = 100 deg/s, horizon=0.2s → predicted knee_flexion_l = current + 20
3. test_negative_velocity_extrapolation — hip_velocity_r = -50 deg/s → predicted hip_flexion_r = current - 10
4. test_max_extrapolation_clamp — velocity 200 deg/s with horizon 0.2s would give 40deg delta, verify clamped to 15deg
5. test_untracked_angles_copied — ankle_dorsiflexion, trunk_flexion etc are identical in input and output
6. test_metadata_preserved — timestamp and frame_index match input
```

---

## Prompt 6: Phase-Aware Smoothing

```
Following the spec in docs/PIPELINE_UPGRADES_IMPLEMENTATION.md, Section 6 (Phase-Aware Smoothing):

Modify the existing JointAngleFilter class in src/biomechanics/utils/filters.py.

Add these class-level constants:
PHASE_PARAMS = {
    "idle": (0.3, 0.003),
    "descending": (1.0, 0.007),
    "bottom": (0.8, 0.005),
    "ascending": (1.0, 0.007),
}
DEFAULT_PARAMS = (1.0, 0.007)

Add the update_phase(self, phase: str) method that:
1. Looks up (min_cutoff, beta) from PHASE_PARAMS, falling back to DEFAULT_PARAMS
2. Only updates if values actually changed (compare against self.min_cutoff and self.beta)
3. Updates self.min_cutoff and self.beta
4. Iterates self._filters and updates each OneEuroFilter's min_cutoff and beta

Do NOT change any existing methods or class behavior. Only add the new constants and method.

Write tests in tests/test_biomechanics/test_phase_aware_smoothing.py:
1. test_idle_sets_heavy_smoothing — call update_phase("idle"), verify min_cutoff=0.3 and beta=0.003
2. test_descending_sets_standard — call update_phase("descending"), verify min_cutoff=1.0 and beta=0.007
3. test_unknown_phase_uses_default — call update_phase("unknown_phase"), verify default values
4. test_existing_filters_updated — create a JointAngleFilter, call filter_angles once to create some filters, then call update_phase("idle"), verify the underlying OneEuroFilter instances have updated min_cutoff
5. test_no_update_when_same_phase — call update_phase("idle") twice, verify no error and values are still correct
```

---

## Prompt 7: Pipeline Integration

```
Following the spec in docs/PIPELINE_UPGRADES_IMPLEMENTATION.md, Section 7 (Integration):

Modify src/biomechanics/pipeline.py to integrate all 5 new features.

Changes needed:

1. Add imports at the top:
   from biomechanics.utils.confidence_blend import ConfidenceBlender
   from biomechanics.utils.velocity_clamp import VelocityClamp
   from biomechanics.utils.bone_constraints import BoneLengthConstraints
   from biomechanics.utils.predictive_state import PredictiveStateEstimator

2. In __init__, after the existing derivative tracker initialization and before the rule engine, add:
   - self._confidence_blender = ConfidenceBlender(...)
   - self._velocity_clamp = VelocityClamp(...)
   - self._bone_constraints = BoneLengthConstraints(...)
   - self._predictive_estimator = PredictiveStateEstimator(...)
   Use config values from self.config for all parameters.

3. In process_frame(), insert the pre-IK filtering layers AFTER pose estimation and BiLSTM processing, BEFORE the IK solve section. Add a "pre_ik_filters" timing entry. The order must be:
   a. Confidence blending
   b. Velocity clamping
   c. Bone length constraints

4. After derivatives are computed, add the predictive state estimator:
   predicted_angles = self._predictive_estimator.predict(angles, derivatives)

5. Change the rule_engine.evaluate() call to use predicted_angles instead of angles.

6. Keep rep_counter.update() using the ACTUAL angles (not predicted).

7. Keep calibration (record_frame_for_calibration) using ACTUAL angles.

8. After rep_counter.update(), add:
   self._angle_filter.update_phase(self._rep_counter.phase)

Do NOT change the BiLSTM branch, the PipelineFrame construction, or the release() method.
Preserve all existing latency tracking. Add "pre_ik_filters" as a new timing key.
```

---

## Prompt 8: Integration Tests

```
Create tests/test_biomechanics/test_pipeline_upgrades_integration.py with integration tests that verify the 5 features work together in the pipeline.

Since we can't use a real camera in tests, mock the capture and pose estimation layers.

Write these tests:

1. test_full_pipeline_no_crash_100_frames:
   Create a mock pipeline that bypasses camera capture. Generate 100 synthetic Skeleton3D frames simulating a squat (knee angle going from 170 → 70 → 170 over ~30 frames, repeated). Feed each through the pre-IK filters, IK solver, predictive state, fault detection, and rep counter. Assert no exceptions are raised.

2. test_velocity_clamp_blocks_spike:
   Feed 10 normal frames then inject one frame where the left knee teleports 0.5m. Verify the output skeleton has the knee clamped to within max_displacement of its previous position.

3. test_bone_constraints_active_after_calibration:
   Feed 35 frames (30 for calibration + 5 with a bone length violation). Verify the constraint corrects the violating keypoint in frames 31-35.

4. test_predictive_cueing_fires_earlier:
   Create a scenario where knee valgus is building (hip_adduction increasing over frames). Verify that with prediction, the threshold is crossed N frames earlier than without prediction.

5. test_phase_smoothing_transitions:
   Simulate idle → descent → bottom → ascent → idle. After each phase change from the rep counter, verify the JointAngleFilter's min_cutoff matches PHASE_PARAMS.

Use Skeleton3D.from_numpy() and JointAngles() for constructing test data. Use pytest fixtures for shared setup. Import from the actual source modules — do not mock the new filter classes themselves, only mock the camera/pose layers.
```

---

## Prompt 9: Final Verification and Cleanup

```
Run all existing tests plus the new tests to make sure nothing is broken:

cd /path/to/NowvaLiveKit
python -m pytest tests/ -v --tb=short 2>&1 | head -100

If any existing tests fail due to the changes (especially if they mock pipeline.py or test fault detection timing), fix them by updating the test expectations to account for:
- The fact that fault detection now uses predicted angles (slight angle offset)
- The JointAngleFilter now has update_phase() method
- The pipeline now has additional init attributes

Also verify:
1. All new files have proper docstrings and type hints
2. No circular imports between the new modules
3. The config YAML loads cleanly with the new sections
4. __init__.py files are updated if needed to export new classes

List any test failures and fix them. Do not skip or disable existing tests.
```

---

## Troubleshooting Notes for Claude Code

**If Claude Code asks about import paths:** The project uses relative imports within the `biomechanics` package. New files in `src/biomechanics/utils/` should import from `biomechanics.utils.types`, not relative paths.

**If tests can't find modules:** Tests add `src/` to sys.path. The pattern used in existing tests is:
```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
```

**If there are Pydantic validation errors:** The project uses Pydantic v2. Use `Field(default_factory=...)` for mutable defaults, not `= VelocityClampConfig()`.

**If BiLSTM tests fail:** The BiLSTM branch should be completely untouched. If BiLSTM tests fail, it's likely because the pre-IK filters changed the skeleton that gets passed to the BiLSTM. Check that the BiLSTM still receives the skeleton BEFORE any pre-IK filtering. In the current code, BiLSTM runs on the raw skeleton before the pre-IK filter block — make sure the new code preserves this ordering.
