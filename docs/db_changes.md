# DB Changes: User Anthropometry & ROM Accessors

## New Table: `user_anthropometry`

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | UUID (PK, FK → users) | One row per user |
| `femur_length_avg` | DECIMAL(5,2) | Average femur length (metres) |
| `tibia_length_avg` | DECIMAL(5,2) | Average tibia length (metres) |
| `torso_length` | DECIMAL(5,2) | Shoulder-to-hip length (metres) |
| `hip_width` | DECIMAL(5,2) | Inter-hip distance (metres) |
| `shoulder_width` | DECIMAL(5,2) | Inter-shoulder distance (metres) |
| `femur_tibia_ratio` | DECIMAL(5,3) | femur / tibia |
| `femur_torso_ratio` | DECIMAL(5,3) | femur / torso |
| `calibration_quality_score` | DECIMAL(5,3) | 0–1 (bone pair coverage) |
| `last_updated` | TIMESTAMP | Auto-set on insert/update |

**Model**: `src/db/models.py:UserAnthropometry`  
**Migration**: `src/db/migrations/add_user_anthropometry.py`

## Persistence Hook

**Location**: `scripts/visualize_video_squats.py` (after `compute_athlete_params`)  
**Mechanism**: Calls `save_anthropometry_to_file(bone_constraints)` which writes
`data/anthropometry.json`. Only overwrites if new `calibration_quality_score` is
higher than existing.

The main pipeline hook (in `src/biomechanics/pipeline.py`) is deferred — the
infrastructure is in place but not wired until user_id plumbing is added to the
pose subprocess.

## Calibration Schema Documentation

**Path**: `docs/calibration_schema.md`  
Documents every key in `UserCalibration.peaks` JSONB, types, units, and how
they feed into fault thresholds.

## Accessor Module

**Path**: `src/db/anthropometry_utils.py`

Functions:
- `get_anthropometry()` → loads from `data/anthropometry.json`
- `get_user_rom(joint_name)` → single ROM value from latest calibration profile
- `get_user_rom_full()` → all ROM values as dict
- `save_anthropometry_to_file(bone_constraints)` → persist after calibration

ROM canonical names: `trunk_flexion`, `hip_adduction`, `asymmetry`,
`dorsiflexion_drop`, `avg_depth`
