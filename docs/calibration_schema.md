# UserCalibration.peaks JSONB Schema

The `peaks` column in `user_calibrations` stores per-user kinematic peak values
measured during calibration reps (typically 5 bodyweight squats). These values
are produced by `CalibrationTracker.get_peaks()` in
`src/biomechanics/calibration.py`.

## Keys

| Key | Type | Unit | Description | Example |
|-----|------|------|-------------|---------|
| `trunk_flexion` | float | degrees | Peak trunk flexion (180-convention: lower = more forward lean). Minimum value of trunk angle observed across all calibration frames. | `142.3` |
| `hip_adduction` | float | degrees | Average of per-rep peak absolute hip adduction. Reflects typical knee-valgus tendency during descent. | `8.7` |
| `hip_adduction_per_rep` | list[float] | degrees | Per-rep peak absolute hip adduction values. Length = calibration_reps. | `[7.2, 9.1, 8.5, 9.3, 9.4]` |
| `asymmetry` | float | degrees | Peak bilateral asymmetry observed (max of knee and hip asymmetry across all frames). | `4.2` |
| `dorsiflexion_drop` | float | degrees | Peak dorsiflexion drop from standing baseline. Measures how much ankle mobility decreases at depth. | `12.5` |
| `avg_depth` | float | degrees | Average peak knee flexion across all calibration reps. Represents typical squat depth. | `118.4` |
| `depth_per_rep` | list[float] | degrees | Per-rep peak knee flexion values. Length = calibration_reps. | `[115.2, 119.8, 117.3, 120.1, 119.6]` |

## How peaks are used

`build_calibration_profile(peaks)` converts these raw measurements into
personalized fault-detection thresholds:

- **knee_valgus** thresholds: `hip_adduction + [5, 10, 15]°`
- **forward_lean** thresholds: `trunk_flexion - [10, 15, 20]°`
- **bilateral_asymmetry** thresholds: `asymmetry + [5, 10, 15]°`
- **heel_rise** threshold: `dorsiflexion_drop + 20°`
- **depth** thresholds: `avg_depth - [10, 25, 55]°` (parallel, half, quarter)

## Source

Written by: `src/services/coaching_service.py:_on_calibration_complete()`  
Produced by: `src/biomechanics/calibration.py:CalibrationTracker.get_peaks()`  
Read by: `src/db/calibration_utils.py:get_user_calibration_full()`
