# V3 Program Generation Fixes - Verification Report

## Issues Fixed

### 1. ✅ SetCalculator Missing Required Parameter
**Location**: `src/api/services/incremental_batch_generator.py:98`

**Problem**:
```python
self.set_calculator = SetCalculator()  # ❌ Missing required 'exercises' parameter
```

**Fix**:
```python
self.set_calculator = SetCalculator(exercises)  # ✅ Correct
```

**Verification**: All SetCalculator instantiations checked:
- ✅ `batch_generator.py:39` - Correct
- ✅ `incremental_batch_generator.py:98` - Fixed
- ✅ `set_calculator.py:374` - Correct (convenience function)

---

### 2. ✅ PhaseMapper Method Error
**Location**: `src/api/services/incremental_batch_generator.py:255`

**Problem**:
```python
phase_name=phase_mapper.get_phase_name(week_num)  # ❌ Method doesn't exist
```

**Fix**:
```python
phase = phase_mapper.get_phase_for_week(week_num)
phase_name=phase.phase_name if phase else "Training"  # ✅ Correct
```

**Verification**: All PhaseMapper method calls checked:
- ✅ All uses call `get_phase_for_week()` or access `phase_schedule` directly
- ✅ No remaining calls to non-existent `get_phase_name()` method

---

### 3. ✅ SetCalculator Method Signature Mismatch
**Location**: `src/api/services/incremental_batch_generator.py:467-472`

**Problem**:
```python
exercise.sets = self.set_calculator.calculate_sets(
    exercise=exercise,
    profile=profile,
    phase_data=phase_data,  # ❌ Wrong parameter name
    exercise_def=self.exercises.get(exercise.exercise_id)  # ❌ Wrong parameter
)
```

**Fix**:
```python
phase_spec = phase_mapper.get_phase_for_week(week_num)
exercise.sets = self.set_calculator.calculate_sets(
    exercise=exercise,
    phase_spec=phase_spec,  # ✅ Correct parameter
    profile=profile,
    strategy=strategy,  # ✅ Added required parameter
    week_number=week_num  # ✅ Correct parameter name
)
```

**Method Signature**:
```python
def calculate_sets(
    self,
    exercise: GeneratedExercise,
    phase_spec: MappedPhase,
    profile: NormalizedUserProfile,
    strategy: StrategyPlan,
    week_number: int
) -> List[GeneratedSet]
```

---

### 4. ✅ Missing Parameters in _validate_and_lock_exercise
**Location**: `src/api/services/incremental_batch_generator.py:430-437`

**Problem**:
Method didn't receive necessary parameters to call `calculate_sets`.

**Fix**:
Added required parameters to method signature:
```python
def _validate_and_lock_exercise(
    self,
    exercise: GeneratedExercise,
    profile: NormalizedUserProfile,
    previous_exercises: List[LockedExercise],
    week_num: int,          # ✅ Added
    strategy: StrategyPlan,  # ✅ Added
    phase_mapper: PhaseMapper  # ✅ Added
) -> Optional[LockedExercise]:
```

Updated call site at line 352-359 to pass new parameters.

---

### 5. ✅ Tool Definition Missing Strict Mode
**Location**: `src/api/services/diff_based_repair_engine.py:521-548`

**Problem**:
```python
{
    "type": "function",
    "function": {
        "name": "check_volume_status",
        "description": "...",
        # ❌ Missing "strict": True
        "parameters": {
            "type": "object",
            "properties": {
                "weeks_generated": {
                    "type": "array",
                    "items": {"type": "object"}  # ❌ Invalid for strict mode
                }
            },
            "required": ["weeks_generated"]
            # ❌ Missing "additionalProperties": False
        }
    }
}
```

**Fix**:
```python
{
    "type": "function",
    "function": {
        "name": "check_volume_status",
        "description": "...",
        "strict": True,  # ✅ Added
        "parameters": {
            "type": "object",
            "properties": {
                "weeks_generated": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True  # ✅ Proper strict schema
                    }
                }
            },
            "required": ["weeks_generated"],
            "additionalProperties": False  # ✅ Required for strict mode
        }
    }
}
```

**Verification**: All tool definitions in `batch_generator.py` already have `strict: True`.

---

## Comprehensive Verification

### All Validator Instantiations ✅
All validators consistently require `exercises` parameter and are correctly instantiated:

- ✅ ExerciseValidator
- ✅ WorkoutValidator
- ✅ WeekValidator
- ✅ BlockValidator
- ✅ VolumeValidator
- ✅ TimeValidator
- ✅ BalanceValidator
- ✅ InjuryValidator
- ✅ RecoveryValidator
- ✅ GoalValidator
- ✅ ProgramValidator

### All SetCalculator Calls ✅
All `calculate_sets()` calls use correct parameters:

1. **batch_generator.py:524** ✅
   ```python
   exercise.sets = self.set_calculator.calculate_sets(
       exercise, phase_spec, profile, strategy, week.week_number
   )
   ```

2. **incremental_batch_generator.py:477** ✅ (Fixed)
   ```python
   exercise.sets = self.set_calculator.calculate_sets(
       exercise=exercise,
       phase_spec=phase_spec,
       profile=profile,
       strategy=strategy,
       week_number=week_num
   )
   ```

3. **set_calculator.py:375** ✅
   ```python
   return calculator.calculate_sets(
       exercise, phase_spec, profile, strategy, week_number
   )
   ```

### All PhaseMapper Method Calls ✅
No incorrect method calls found. All use:
- `get_phase_for_week(week_num)` → Returns `MappedPhase` or `None`
- `phase_schedule` → Direct list access
- `get_phases_for_batch(start, end)` → Returns list of phases
- `get_phase_progression_summary()` → Returns string
- `get_deload_schedule_summary()` → Returns string
- `get_phase_count()` → Returns int

---

## Testing Recommendations

1. **Run full program generation test**:
   ```bash
   curl -X POST http://localhost:8000/api/programs/generate_v3 \
     -H "Content-Type: application/json" \
     -d @test_request.json
   ```

2. **Monitor for these specific errors**:
   - ❌ `SetCalculator.__init__() missing 1 required positional argument: 'exercises'`
   - ❌ `'PhaseMapper' object has no attribute 'get_phase_name'`
   - ❌ `check_volume_status is not strict`
   - ❌ `calculate_sets() got an unexpected keyword argument`

3. **Check celery logs** for successful generation:
   ```bash
   tail -f celery_worker.log | grep -E "(✅|❌|Generation)"
   ```

---

## Summary

All identified issues have been fixed:
- ✅ SetCalculator instantiation
- ✅ PhaseMapper method calls
- ✅ SetCalculator.calculate_sets() parameters
- ✅ Tool schema strict mode
- ✅ Method signature consistency

**Status**: Ready for testing
**Date**: 2026-02-09
