# V5 Program Generator — Claude Code Implementation Prompts

## SETUP INSTRUCTIONS (Do This First)

### Project Directory Structure
Set up your project directory like this BEFORE running any prompts:

```
your-project/
├── program_generator_v5/
│   ├── __init__.py                            ← create empty
│   ├── exercise_library.py                    ← copy exercise_library_v5.py here, rename to exercise_library.py
│   └── (everything else gets created by Claude Code)
├── docs/
│   ├── v5-program-generator-spec-FINAL.md     ← the full spec
│   └── build_v5_library.py                    ← reference only (how the library was built)
└── (your existing codebase)
```

### Steps:
1. Create `program_generator_v5/` with an empty `__init__.py`
2. Copy `exercise_library_v5.py` into it and rename to `exercise_library.py`
3. Put the spec and build script in `docs/`
4. Feed each phase prompt below to Claude Code ONE AT A TIME
5. After each phase, copy Claude Code's summary back to me for review
6. Wait for my go-ahead before starting the next phase

### Rules:
- ONE PHASE AT A TIME. Never combine phases.
- After each phase, I review Claude Code's summary and either approve or request fixes.
- Claude Code should never modify `exercise_library.py` — it's pre-built and frozen.
- All new files go inside `program_generator_v5/`

---
---

## PHASE 1: Schemas + Data Foundations

```
TASK: Implement Phase 1 of the V5 workout program generator.

SPEC LOCATION: Read the COMPLETE spec at docs/v5-program-generator-spec-FINAL.md before writing any code. You need to understand the full architecture to get the schemas right.

EXISTING FILES:
- program_generator_v5/exercise_library.py — The complete exercise library (144 exercises). DO NOT MODIFY THIS FILE. Read its import statement at the top to see exactly which types it expects from schemas.py. Your schemas.py must export every type that exercise_library.py imports.

CREATE THESE FILES inside program_generator_v5/:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. schemas.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Define ALL enums and Pydantic models from the spec. This is the foundation — every other file imports from here.

Enums (read spec for exact values):
- EquipmentTier (int enum: 1, 2, 3)
- MuscleRole (str enum: primary, secondary, stabilizer)
- ExerciseType (str enum: heavy_compound, light_compound, isolation, power, plyometric)
- MovementPattern (str enum: horizontal_push, horizontal_pull, vertical_push, vertical_pull, hip_hinge, squat, lunge, isolation_push, isolation_pull, core, power_lower, power_upper, carry, rotation)
- MuscleGroup (str enum: all 20 muscle groups from spec including upper_chest, lower_chest)

Pydantic Models — implement EVERY field specified in the spec:
- MuscleActivation (muscle, role, volume_credit)
- Exercise (the full schema — 25+ fields including cues, rotation_group, variation_tags)
- AthleteProfile (user demographics, training context, equipment, constraints, derived fields)
- SessionTemplate (session_type, muscle_groups, required/optional movement patterns, max_exercises, max_duration_minutes)
- SplitTemplate (split_id, name, sessions_per_week, session_templates, suitable_for_goals, suitable_for_levels)
- WeekProfile (week_number, mesocycle, phase, volume_multiplier, intensity_modifier, is_deload)
- ProgramStrategy (split, periodization_model, week_profiles, mesocycle_length, num_mesocycles)
- SessionVolumeTarget (muscle_group → sets mapping per session)
- WeekVolumeAllocation (week_number, session_targets, weekly_total_per_muscle)
- VolumeAllocation (weeks: list of WeekVolumeAllocation)
- PrescribedSet (set_number, reps, rpe, rir, rest_seconds, tempo, notes)
- PrescribedExercise (exercise_id, exercise_name, sets: list[PrescribedSet], superset_group, notes, volume_contributions: dict mapping muscle to credit)
- BuiltWorkout (session_day, session_type, exercises: list[PrescribedExercise], estimated_duration_minutes, volume_delivered: dict mapping muscle to sets)
- BuiltWeek (week_number, mesocycle, phase, workouts: list[BuiltWorkout], weekly_volume_actual: dict mapping muscle to total)
- BuiltProgram (profile, strategy, volume_allocation, weeks: list[BuiltWeek], mutation_log: list)
- MutationResult (success, mutation_type, description, volume_before, volume_after, constraint_violations, rollback_applied)
- MutationRequest (mutation_type, week_number, session_day, exercise_id, new_exercise_id, etc.)
- MutationLog (mutations_attempted, mutations_applied, mutations_rejected, mutations_rolled_back)

CRITICAL: After writing schemas.py, immediately test:
  python -c "from program_generator_v5.schemas import *; print('schemas OK')"
  python -c "from program_generator_v5.exercise_library import EXERCISE_LIBRARY; print(f'Loaded {len(EXERCISE_LIBRARY)} exercises')"
Both MUST succeed. If exercise_library.py fails to import, fix schemas.py until it works. DO NOT modify exercise_library.py.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. volume_tables.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Weekly set volume targets per muscle group, per training level.

Read the spec's "Volume Targets by Muscle Group (Weekly Sets)" table for intermediate values. Then:
- Beginner = round(intermediate × 0.75) for each value
- Advanced = round(intermediate × 1.15) for each value
- Clamp so MEV >= 2 always, and MEV < MAV < MRV always

Export as:
VOLUME_TABLES: dict[str, dict[str, dict[str, int]]]
  → VOLUME_TABLES["intermediate"]["chest"] = {"mev": 8, "mav": 14, "mrv": 20}

Every MuscleGroup enum value MUST have an entry at every training level.

Include helper:
def get_volume_targets(training_level: str, muscle: str) -> dict[str, int]:
    """Returns {"mev": X, "mav": Y, "mrv": Z}"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. split_templates.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Read the spec's "Split Templates" section. Implement ALL splits:
- upper_lower_4x (Upper/Lower 4 days)
- ppl_3x (Push/Pull/Legs 3 days)
- ppl_6x (PPL 6 days)
- full_body_2x (Full Body 2 days)
- full_body_3x (Full Body 3 days)
- concurrent_4x (Concurrent/Power 4 days — for power goal)
- concurrent_5x (Concurrent/Power 5 days — for advanced power)

Each split uses the SessionTemplate and SplitTemplate models from schemas.py.

Each SessionTemplate must specify:
- session_type (e.g., "upper_a", "lower_a", "push", "pull", "legs", "full_body")
- muscle_groups: which MuscleGroups this session targets
- required_movement_patterns: patterns that MUST be filled
- optional_movement_patterns: patterns that CAN be filled if time allows
- max_exercises: cap per session (typically 6-8)
- max_duration_minutes: from the athlete's session_duration_minutes

Export: SPLIT_TEMPLATES: dict[str, SplitTemplate]

Include the split selection decision tree:
def get_split_for_config(days_per_week: int, training_level: str, goal: str) -> str:
    """Returns split_id based on the decision tree in the spec."""
    # 2 days → full_body_2x
    # 3 days → ppl_3x (hyp/str) or full_body_3x (beginner)
    # 4 days → upper_lower_4x (most common) or concurrent_4x (power)
    # 5 days → concurrent_5x (power) or ppl_3x + upper_lower combo
    # 6 days → ppl_6x

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. sport_mappings.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Read the spec's "Sport → Goal Mapping" table. Implement all sport mappings.

Each sport entry includes:
- base_goal: str (hypertrophy/strength/power)
- volume_modifier: float (0.6-1.0)
- emphasis_muscles: list[str]
- deemphasis_muscles: list[str]
- mandatory_movement_patterns: list[str]
- forbidden_exercises: list[str]
- injury_prevention_additions: list[str]

Export: SPORT_MAPPINGS: dict[str, dict]

Include helper:
def get_sport_adjustments(sport: str) -> dict | None:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION — RUN ALL OF THESE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. python -c "from program_generator_v5.schemas import *; print('✅ schemas import OK')"
2. python -c "from program_generator_v5.exercise_library import EXERCISE_LIBRARY; print(f'✅ exercise_library: {len(EXERCISE_LIBRARY)} exercises')"
3. python -c "from program_generator_v5.volume_tables import VOLUME_TABLES; print(f'✅ volume_tables: {list(VOLUME_TABLES.keys())} levels, {len(VOLUME_TABLES[\"intermediate\"])} muscles'); print(f'   intermediate chest: {VOLUME_TABLES[\"intermediate\"][\"chest\"]}')"
4. python -c "from program_generator_v5.split_templates import SPLIT_TEMPLATES, get_split_for_config; print(f'✅ split_templates: {list(SPLIT_TEMPLATES.keys())}'); print(f'   4x/wk intermediate hypertrophy → {get_split_for_config(4, \"intermediate\", \"hypertrophy\")}')"
5. python -c "from program_generator_v5.sport_mappings import SPORT_MAPPINGS, get_sport_adjustments; print(f'✅ sport_mappings: {list(SPORT_MAPPINGS.keys())}'); bball = get_sport_adjustments('basketball'); print(f'   basketball → goal={bball[\"base_goal\"]}, emphasis={bball[\"emphasis_muscles\"]}')"

ALL 5 must pass.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPLEMENTATION SUMMARY — PRINT THIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
After completing all files, print a summary in EXACTLY this format:

PHASE 1 IMPLEMENTATION SUMMARY
================================

FILES CREATED:
- schemas.py: [X] lines — [brief description of what's defined]
- volume_tables.py: [X] lines — [brief description]
- split_templates.py: [X] lines — [brief description]
- sport_mappings.py: [X] lines — [brief description]

SCHEMAS DEFINED:
- Enums: [list each enum name with value count, e.g. "MuscleGroup (20 values)"]
- Models: [list each Pydantic model name]
- Total model count: [X]

VOLUME TABLES:
- Training levels: [list]
- Muscle groups covered: [X] out of [Y] MuscleGroup enum values
- Sample values (intermediate):
  - chest: MEV=[X] MAV=[X] MRV=[X]
  - quads: MEV=[X] MAV=[X] MRV=[X]
  - side_delts: MEV=[X] MAV=[X] MRV=[X]
  - biceps: MEV=[X] MAV=[X] MRV=[X]

SPLIT TEMPLATES:
- Templates defined: [list all split_ids]
- Decision tree results:
  - 2 days/wk beginner hypertrophy → [X]
  - 3 days/wk intermediate hypertrophy → [X]
  - 4 days/wk intermediate hypertrophy → [X]
  - 4 days/wk intermediate power → [X]
  - 6 days/wk advanced hypertrophy → [X]

SPORT MAPPINGS:
- Sports covered: [list all]
- Sample: basketball → base_goal=[X], volume_modifier=[X], emphasis=[list]

VALIDATION RESULTS:
1. schemas import: [PASS/FAIL]
2. exercise_library import: [PASS/FAIL] ([X] exercises loaded)
3. volume_tables check: [PASS/FAIL]
4. split_templates check: [PASS/FAIL]
5. sport_mappings check: [PASS/FAIL]

DECISIONS MADE (where spec was ambiguous):
- [list any choices you made that weren't explicitly specified]
```

---
---

## PHASE 2: Scoring + Utilities + Prompts

```
TASK: Implement Phase 2 of the V5 workout program generator.

SPEC LOCATION: Read docs/v5-program-generator-spec-FINAL.md — pay close attention to these sections:
- "Stage A: Exercise Selection Algorithm" — the scoring function with 8 weighted factors
- The prescription tables (REP_RANGES, REST_SECONDS, TEMPOS by exercise_type × goal)
- "Time Estimation"
- All LLM prompt templates (search for "PROMPT" in the spec)

EXISTING FILES (DO NOT MODIFY):
- program_generator_v5/schemas.py
- program_generator_v5/exercise_library.py
- program_generator_v5/volume_tables.py
- program_generator_v5/split_templates.py
- program_generator_v5/sport_mappings.py

CREATE THESE FILES inside program_generator_v5/:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. scoring.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The exercise scoring function that drives exercise selection in Layer 4.

Main function:
def compute_exercise_score(
    exercise: Exercise,
    remaining_volume: dict[str, float],        # muscle → remaining sets needed
    recently_used: dict[str, list],            # exercise_id → [(week_num, was_primary)]
    mesocycle_number: int,
    week_number: int,
    session_axial_count: int,                  # axial exercises already in this session
    session_grip_count: int,                   # grip-intensive exercises already in session
    program_goal: str,                         # "hypertrophy", "strength", "power"
    user_preferences: dict = None,             # exercise_id → preference score
) -> float:

Implement ALL 8 scoring factors from the spec:
1. SFR Rating — weight by goal (hypertrophy weights SFR higher than strength)
2. Volume Fill — how many remaining muscle targets does this exercise address? More = higher score. Weight primary (1.0) and secondary (0.5) contributions.
3. Variety — penalize if used in recent weeks (stronger penalty for same week, weaker for 2-3 weeks ago). Bonus for exercises never used in this mesocycle.
4. Rotation Group Freshness — penalize if an exercise from the same rotation_group was used recently
5. Compound Consistency — within a mesocycle, bonus for keeping the same primary compound in the same session slot. Between mesocycles, bonus for switching.
6. Fatigue Management — penalty for 3rd+ axial-loading exercise in session. Penalty for 3rd+ grip-intensive exercise. Heavier penalty the more you stack.
7. User Preference — bonus if exercise_id in user preferences
8. Stretch Position — bonus for exercises with "stretch" in variation_tags when goal is hypertrophy

Each factor produces a score component. Combine them with weights that depend on the goal:
- Hypertrophy: SFR and volume_fill weighted highest
- Strength: compound_consistency and fatigue_management weighted highest
- Power: exercise_type match and fatigue_management weighted highest

Return a single float score. Higher = better candidate.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. utils.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Shared utility functions used by multiple layers.

A) PRESCRIPTION ENGINE — the most important function in this file:
def prescribe_exercise(
    exercise: Exercise,
    total_sets: int,
    week_profile: WeekProfile,
    program_goal: str,
    is_last_set_to_failure: bool = False,
) -> list[PrescribedSet]:

This must implement the full prescription logic from the spec:
- Rep range selection based on exercise_type × goal:
  * heavy_compound + hypertrophy → 6-10
  * heavy_compound + strength → 1-5
  * light_compound + hypertrophy → 8-12
  * isolation + hypertrophy → 10-15
  * power → 1-5
  * plyometric → 3-6
  (Read the complete tables from the spec)
- Rep count adjusted by week intensity_modifier (lower reps in higher-intensity weeks)
- Rest periods by exercise_type × goal (heavy compound strength = 180-300s, isolation hypertrophy = 60-90s, etc.)
- RPE/RIR: compounds more conservative (RPE 7-8.5), isolations pushed harder (RPE 8-9.5). Scaled by week intensity_modifier.
- Tempo by exercise_type × goal (hypertrophy = slower eccentrics, strength = controlled, power = explosive)
- Notes: first set of heavy compounds gets "Warm up with 2-3 progressively heavier sets before working weight"
- Last set AMRAP/failure for isolations in week 3 (overreaching) of hypertrophy mesocycles

B) TIME ESTIMATION:
def estimate_session_duration(exercises: list[PrescribedExercise]) -> int:
  - 5 min warmup + 3 min cooldown
  - Per exercise: sets × (set_execution_time + rest_time) + transition_time
  - Set execution time ≈ reps × tempo_total_seconds (or 3s/rep default)
  - Transition between exercises ≈ 60s (30s for supersetted)
  - Supersetted pairs: rest reduced by 40%
  - Return total minutes rounded up

C) SUPERSET BUILDER:
def build_supersets(exercises: list[PrescribedExercise], goal: str) -> list[PrescribedExercise]:
  - Only for hypertrophy programs
  - Pair antagonist isolations (push+pull for same joint area)
  - Never superset two heavy compounds
  - Never superset exercises targeting the same primary muscle
  - Assign superset_group labels ("A", "B", etc.) to paired exercises

D) EXERCISE SORTING:
def sort_exercises_for_session(exercises: list[PrescribedExercise], goal: str) -> list[PrescribedExercise]:
  - Power/plyometric first (always, regardless of goal)
  - Heavy compounds next
  - Light compounds next
  - Isolations last
  - Within each tier, exercises targeting larger muscles first
  - Supersetted exercises stay adjacent

E) PATTERN PRIORITY:
def get_pattern_fill_priority(goal: str) -> list[MovementPattern]:
  - Returns movement patterns in the order they should be filled
  - Hypertrophy: squat, hip_hinge, horizontal_push, horizontal_pull, vertical_pull, vertical_push, then isolations
  - Strength: squat, hip_hinge, horizontal_push, vertical_push, horizontal_pull, vertical_pull
  - Power: power_lower, power_upper, squat, hip_hinge, horizontal_push, horizontal_pull

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. prompts.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALL LLM prompts as templates with format functions.

Read EVERY prompt template from the spec (search for "PROMPT" and "prompt" across the entire spec) and define them here:

1. PROFILE_EXTRACTION_PROMPT — Layer 1 natural language → structured profile
   format_profile_extraction_prompt(raw_text: str) -> str

2. STRATEGY_RESOLUTION_PROMPT — Layer 2 conflict resolution
   format_strategy_resolution_prompt(conflict_description: str, rules_output: dict, profile: AthleteProfile) -> str

3. WEEK_REVIEW_PROMPT — Layer 4 per-week coherence check
   format_week_review_prompt(week: BuiltWeek, profile: AthleteProfile, strategy: ProgramStrategy) -> str
   This needs to serialize the week's exercises into readable text for the LLM.

4. FULL_PROGRAM_REVIEW_PROMPT — Layer 5 holistic review
   format_full_program_review_prompt(program: BuiltProgram) -> str
   This needs to serialize the entire program into readable text.

Each format function should:
- Accept the required context objects
- Serialize them into clean, readable text (the LLM reads this)
- Return the complete formatted prompt string
- Include the expected JSON response format in the prompt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION — RUN ALL OF THESE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Test 1 — Scoring function:
  from program_generator_v5.scoring import compute_exercise_score
  from program_generator_v5.exercise_library import EXERCISE_BY_ID
  # Score a barbell curl with remaining bicep volume
  score = compute_exercise_score(
      exercise=EXERCISE_BY_ID["barbell_curl"],
      remaining_volume={"biceps": 6.0, "forearms": 4.0},
      recently_used={}, mesocycle_number=1, week_number=1,
      session_axial_count=0, session_grip_count=0,
      program_goal="hypertrophy"
  )
  print(f"✅ Barbell curl score: {score:.2f}")

Test 2 — Prescription (heavy compound, hypertrophy, Week 1):
  from program_generator_v5.utils import prescribe_exercise
  from program_generator_v5.schemas import WeekProfile
  week1 = WeekProfile(week_number=1, mesocycle=1, phase="introduction", volume_multiplier=1.0, intensity_modifier=0.85, is_deload=False)
  sets = prescribe_exercise(EXERCISE_BY_ID["barbell_back_squat"], 4, week1, "hypertrophy")
  print(f"✅ BB Squat prescription: {len(sets)} sets")
  for s in sets:
      print(f"   Set {s.set_number}: {s.reps} reps @ RPE {s.rpe}, rest {s.rest_seconds}s, tempo {s.tempo}")
  # VERIFY: reps should be 6-10, rest 120-180s, RPE 6.5-8.0

Test 3 — Prescription (isolation, hypertrophy, Week 3 / overreaching):
  week3 = WeekProfile(week_number=3, mesocycle=1, phase="overreaching", volume_multiplier=1.25, intensity_modifier=1.0, is_deload=False)
  sets = prescribe_exercise(EXERCISE_BY_ID["barbell_curl"], 3, week3, "hypertrophy")
  print(f"✅ BB Curl Week 3 prescription: {len(sets)} sets")
  for s in sets:
      print(f"   Set {s.set_number}: {s.reps} reps @ RPE {s.rpe}, rest {s.rest_seconds}s | notes: {s.notes}")
  # VERIFY: reps should be 10-15, rest 60-90s, RPE higher than Week 1
  # VERIFY: last set should have failure/AMRAP note

Test 4 — Prompt formatting:
  from program_generator_v5.prompts import format_profile_extraction_prompt, format_week_review_prompt
  p = format_profile_extraction_prompt("I want to get jacked, I'm 25, been lifting 3 years, have a barbell setup at home")
  print(f"✅ Profile prompt: {len(p)} chars")
  assert "{" not in p or "json" in p.lower(), "Prompt has unformatted placeholders!"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPLEMENTATION SUMMARY — PRINT THIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 2 IMPLEMENTATION SUMMARY
================================

FILES CREATED:
- scoring.py: [X] lines — [description]
- utils.py: [X] lines — [description]
- prompts.py: [X] lines — [description]

SCORING FUNCTION:
- 8 factors implemented: [list each with its weight range]
- Goal-dependent weighting: [describe how weights change per goal]
- Test score for barbell_curl (hypertrophy, full bicep volume remaining): [X]

PRESCRIPTION ENGINE:
- Rep ranges implemented (exercise_type × goal combinations): [count]
- BB Squat test (hypertrophy Week 1, 4 sets):
  - Reps: [X] | Rest: [X]s | RPE: [X] | Tempo: [X]
- BB Curl test (hypertrophy Week 3, 3 sets):
  - Reps: [X] | Rest: [X]s | RPE: [X]
  - Last set notes: [exact text]
- Rest period ranges by type: heavy_compound=[X-X]s, isolation=[X-X]s

UTILITIES:
- estimate_session_duration: [describe calculation]
- build_supersets: [describe pairing logic]
- sort_exercises_for_session: [describe ordering]
- get_pattern_fill_priority: [list for hypertrophy]

PROMPTS:
- 4 prompts defined: [list names]
- format functions: [list all 4]
- Total prompt template characters: [X]

VALIDATION RESULTS:
1. Scoring test: [PASS/FAIL] — score=[X]
2. Prescription test (squat): [PASS/FAIL] — reps=[X], rest=[X]s, RPE=[X]
3. Prescription test (curl Week 3): [PASS/FAIL] — last set failure=[yes/no]
4. Prompt format test: [PASS/FAIL]

DECISIONS MADE:
- [list any spec ambiguities and how you resolved them]
```

---
---

## PHASE 3: Volume Engine + Program Builder (Core Pipeline)

```
TASK: Implement Phase 3 — the two most critical layers of V5. This is where V4 failed. Get this right.

SPEC LOCATION: Read docs/v5-program-generator-spec-FINAL.md — these sections are essential:
- "Layer 3: Volume Engine" (the entire section)
- "Layer 4: Program Builder — Stage A" (deterministic exercise selection)
- "Stage A: Exercise Selection Algorithm" (the 3-phase greedy algorithm)
- "Variety Management"
- "WHAT SUCCESS LOOKS LIKE" (the example program output)

Read the spec's example output for an intermediate hypertrophy 4x/week program. Your code must produce something of that quality.

EXISTING FILES (DO NOT MODIFY):
- program_generator_v5/schemas.py
- program_generator_v5/exercise_library.py
- program_generator_v5/volume_tables.py
- program_generator_v5/split_templates.py
- program_generator_v5/sport_mappings.py
- program_generator_v5/scoring.py
- program_generator_v5/utils.py
- program_generator_v5/prompts.py

CREATE THESE FILES inside program_generator_v5/:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. layer3_volume_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
100% deterministic. No LLM calls. No randomness. Pure math.

Main function:
def calculate_volume(profile: AthleteProfile, strategy: ProgramStrategy) -> VolumeAllocation:

Algorithm (from spec):
For EACH week in strategy.week_profiles:
  For EACH muscle_group in MuscleGroup enum:
    1. Look up base MEV/MAV/MRV from volume_tables for profile.training_level
    2. Calculate prescribed weekly sets based on goal:
       - Hypertrophy: scale between MEV and MRV using week.volume_multiplier
         * volume_multiplier 1.0 → MEV
         * volume_multiplier ~1.25 → MAV
         * volume_multiplier ~1.5 → MRV (cap)
         * Linear interpolation: sets = MEV + (volume_multiplier - 1.0) * 2 * (MRV - MEV)
       - Strength: base at MEV + 0.3*(MAV-MEV), then scale
       - Power: base at MEV + 0.2*(MAV-MEV), then scale
       - Deload weeks: MEV * 0.5 (rounded up, minimum 2)
    3. Apply sport volume_modifier if sport is set
    4. Apply weak_point emphasis (+20% volume for weak point muscles)
    5. Apply recovery_capacity modifier (low=0.85, normal=1.0, high=1.1)
    6. Clamp: MAX(MEV, MIN(result, MRV)) for non-deload weeks
    7. Round to integers

  Distribute weekly volume across sessions:
    - Determine which sessions target this muscle (from split_template)
    - Divide evenly across those sessions
    - Cap at 10 sets per muscle per session (diminishing returns)
    - Cap total session sets at session_duration_minutes / 3.5 (rough time budget)
    - If a muscle appears in more sessions than needed, prefer sessions where it's a primary target

  Derive movement pattern requirements per session:
    - From the split template's required_movement_patterns
    - Plus: any pattern needed to fill muscle volume that isn't covered by required patterns

  Final validation per week:
    - Every non-deload muscle >= MEV → ASSERT
    - Every muscle <= MRV → ASSERT
    - Total session sets <= session time budget → WARN if exceeded

Return VolumeAllocation with all weeks populated.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. layer4_program_builder.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Build the actual program — deterministic Stage A only. LLM review (Stage B) added in Phase 5.

Main function:
def build_program(
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    volume_allocation: VolumeAllocation,
) -> BuiltProgram:

For each week, for each session:

STEP 1 — Select exercises via 3-phase greedy algorithm:
  Phase 1: Fill required movement patterns
    - Get required patterns from split template
    - Sort by priority (from utils.get_pattern_fill_priority)
    - For each required pattern:
      * Get candidate exercises: filter by equipment_tier, pattern, not avoided, not already selected, difficulty <= cap
      * Score ALL candidates using scoring.compute_exercise_score()
      * Select the highest-scoring exercise
      * Assign sets: enough to fill a meaningful portion of the remaining muscle volume (min = exercise.min_sets_per_session, max = exercise.max_sets_per_session)
      * Update remaining_volume by subtracting this exercise's volume contributions (sets × volume_credit per muscle)
      * Track the exercise as recently_used

  Phase 2: Fill remaining volume with accessories/isolations
    - While remaining_volume has any muscle > 0 AND session has room (time + exercise count):
      * Find muscles still needing volume, sorted by most deficit first
      * For the most-deficit muscle: get candidate isolation/light compound exercises
      * Score and select the best
      * Assign sets to fill the remaining volume for that muscle (capped by max_sets_per_session)
      * Update remaining_volume
    - Stop when: all muscles within 1 set of target, OR time cap reached, OR max exercises reached

  Phase 3: Validate and patch
    - Check: any muscle still significantly below target (>2 sets short)?
    - If yes: try adding 1 set to an existing exercise that contributes to that muscle
    - Check: session estimated duration > session_duration_minutes + 5?
    - If yes: remove the lowest-priority exercise (last isolation added)

STEP 2 — Prescribe each exercise:
  Call utils.prescribe_exercise() for each selected exercise with appropriate parameters.

STEP 3 — Sort and superset:
  Call utils.sort_exercises_for_session() then utils.build_supersets() if hypertrophy.

STEP 4 — Build BuiltWorkout:
  Calculate volume_delivered per muscle (sum sets × volume_credit for each exercise).
  Calculate estimated_duration_minutes.

STEP 5 — Build BuiltWeek:
  Calculate weekly_volume_actual (sum across all sessions).

STEP 6 — Track variety across weeks:
  Update recently_used dict after each week.
  Between mesocycles: reset primary compound tracking (so new mesocycle gets fresh compounds).
  But carry forward general recently_used (so exercises don't repeat too quickly across mesocycle boundaries).

Return BuiltProgram with all weeks populated.

IMPORTANT: After building, ASSERT that weekly_volume_actual for each muscle is within ±2 sets of the Layer 3 target for every non-deload week. Print a warning if any muscle is >2 sets off.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION — THE CRITICAL TEST:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generate a test program and print it fully. This is the MOST IMPORTANT validation in the entire project.

Test case: Tier 1, intermediate, hypertrophy, 4x/week, 60-minute sessions, 4-week program.

from program_generator_v5.schemas import AthleteProfile, EquipmentTier
from program_generator_v5.layer2_strategy_engine import *  # Not built yet — mock it
from program_generator_v5.layer3_volume_engine import calculate_volume
from program_generator_v5.layer4_program_builder import build_program
from program_generator_v5.split_templates import SPLIT_TEMPLATES, get_split_for_config

# Create test profile
profile = AthleteProfile(
    user_id="test", name="Test User",
    training_goal="hypertrophy", training_level="intermediate",
    program_duration_weeks=4, training_days_per_week=4,
    session_duration_minutes=60, equipment_tier=EquipmentTier.TIER_1,
    recovery_capacity="normal",
)

# Mock strategy (Layer 2 not built yet — build it manually)
split_id = get_split_for_config(4, "intermediate", "hypertrophy")
split = SPLIT_TEMPLATES[split_id]
# Build 4 WeekProfiles for a hypertrophy mesocycle:
#   Week 1: introduction (volume_multiplier=1.0, intensity=0.85)
#   Week 2: development (volume_multiplier=1.1, intensity=0.9)
#   Week 3: overreaching (volume_multiplier=1.25, intensity=1.0)
#   Week 4: deload (volume_multiplier=0.5, intensity=0.7, is_deload=True)
# Build ProgramStrategy with these week profiles and the split

strategy = ProgramStrategy(
    split=split,
    periodization_model="volume_ramp",
    week_profiles=[...],  # Build 4 WeekProfile objects as described above
    mesocycle_length=4,
    num_mesocycles=1,
)

volume = calculate_volume(profile, strategy)
program = build_program(profile, strategy, volume)

# PRINT THE FULL PROGRAM
for week in program.weeks:
    print(f"\n{'='*60}")
    print(f"WEEK {week.week_number} ({week.phase})")
    print(f"{'='*60}")
    for workout in week.workouts:
        print(f"\n  {workout.session_type} (est. {workout.estimated_duration_minutes}min)")
        print(f"  {'-'*40}")
        for i, ex in enumerate(workout.exercises, 1):
            sets_desc = f"{len(ex.sets)}×{ex.sets[0].reps}" if ex.sets else "?"
            rpe = ex.sets[0].rpe if ex.sets else "?"
            rest = ex.sets[0].rest_seconds if ex.sets else "?"
            ss = f" [SS:{ex.superset_group}]" if ex.superset_group else ""
            print(f"    {i}. {ex.exercise_name} — {sets_desc} @ RPE {rpe}, rest {rest}s{ss}")
    
    # Print volume check
    print(f"\n  Volume delivered vs target:")
    for muscle, actual in sorted(week.weekly_volume_actual.items()):
        target_week = volume.weeks[week.week_number - 1]
        target = target_week.weekly_total_per_muscle.get(muscle, 0)
        diff = actual - target
        flag = " ⚠️" if abs(diff) > 2 else " ✅"
        print(f"    {muscle}: {actual:.1f} delivered / {target} target (diff: {diff:+.1f}){flag}")

WHAT TO CHECK IN THE OUTPUT:
- Does every session have 5-7 exercises?
- Do heavy compounds come first in every session?
- Are rep ranges correct? (compounds 6-10, isolations 10-15 for hypertrophy)
- Does volume increase from Week 1 → Week 3?
- Is Week 4 clearly a deload (fewer sets, lower RPE)?
- Are exercises appropriate for Tier 1 (no dumbbell or band exercises)?
- Is volume within ±2 sets of target for each muscle?
- Do sessions estimate to ~55-65 minutes?
- Is there exercise variety between sessions (Upper A ≠ Upper B)?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPLEMENTATION SUMMARY — PRINT THIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 3 IMPLEMENTATION SUMMARY
================================

FILES CREATED:
- layer3_volume_engine.py: [X] lines — [description]
- layer4_program_builder.py: [X] lines — [description]

VOLUME ENGINE:
- Calculation method: [describe the interpolation formula used]
- Modifiers applied: [list: sport, weak_points, recovery_capacity, etc.]
- Distribution strategy: [describe how weekly volume is split across sessions]
- Sample output (intermediate hypertrophy Week 1):
  - chest: [X] weekly sets → distributed as [X per session]
  - quads: [X] weekly sets → distributed as [X per session]
  - biceps: [X] weekly sets → distributed as [X per session]

PROGRAM BUILDER:
- Selection algorithm: [describe the 3-phase approach]
- Exercise count per session: [range observed]
- Primary compounds selected for Upper A: [list]
- Primary compounds selected for Lower A: [list]
- Variety between Upper A and Upper B: [describe differences]

TEST PROGRAM OUTPUT (Tier 1, intermediate, hypertrophy, 4x/wk, 4 weeks):
Week 1 Upper A: [list exercises with sets×reps]
Week 1 Lower A: [list exercises with sets×reps]
Week 1 Upper B: [list exercises with sets×reps]
Week 1 Lower B: [list exercises with sets×reps]

Week 3 Upper A: [list exercises — should show more sets than Week 1]
Week 4 Upper A: [list exercises — should show deload: fewer sets, lower RPE]

VOLUME ACCURACY:
- Muscles within ±1 set of target: [X] out of [Y]
- Muscles within ±2 sets: [X] out of [Y]
- Largest deviation: [muscle] at [X] sets off
- Worst offender details: target=[X], delivered=[X], exercises contributing=[list]

SESSION TIMING:
- Average estimated duration: [X] minutes
- Range: [min]-[max] minutes
- Any sessions over 65 min? [yes/no — list if yes]

DECISIONS MADE:
- [list spec ambiguities and resolutions]
- [list any exercises the algorithm consistently prefers and why]
```

---
---

## PHASE 4: Mutator + Validator (The Safety Net)

```
TASK: Implement Phase 4 — the program mutator (fix engine) and Layer 5 validator.

SPEC LOCATION: Read docs/v5-program-generator-spec-FINAL.md — these sections are essential:
- "PROGRAM MUTATOR — THE FIX ENGINE" (the entire section, including all 8 primitive mutations and 5 compound mutations)
- "Layer 5: Validator" (all 17 validation rules, auto-fix loop, LLM full-program review)
- "Concrete Auto-Fix Implementations" (maps each rule ID to specific mutator calls)

EXISTING FILES (DO NOT MODIFY):
- All files from Phases 1-3

CREATE THESE FILES inside program_generator_v5/:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. mutator.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The Program Mutator — safe program modification engine.

class ProgramMutator:
    def __init__(self, program, profile, strategy, volume_allocation, exercise_library):

    IMPLEMENT ALL 8 PRIMITIVE MUTATIONS (from the spec):
    1. swap_exercise(week, session, old_id, new_id, new_sets?, source, reason) → MutationResult
    2. add_exercise(week, session, exercise_id, sets, source, reason) → MutationResult
    3. remove_exercise(week, session, exercise_id, source, reason) → MutationResult
    4. add_sets(week, session, exercise_id, sets_delta, source, reason) → MutationResult
    5. remove_sets(week, session, exercise_id, sets_delta, source, reason) → MutationResult
    6. reorder_session(week, session, new_order, source, reason) → MutationResult
    7. move_exercise(week, from_session, to_session, exercise_id, source, reason) → MutationResult
    8. replace_prescription(week, session, exercise_id, new_sets_config, source, reason) → MutationResult

    IMPLEMENT ALL 5 COMPOUND MUTATIONS:
    1. fix_volume_deficit(week, muscle, target_sets, current_sets) → MutationResult
       - Tries in order: add sets to existing exercise → add new exercise → swap lowest-SFR exercise
    2. fix_volume_excess(week, muscle, target_sets, current_sets) → MutationResult
       - Remove sets from lowest-SFR exercise first
    3. fix_missing_movement_pattern(week, session, pattern) → MutationResult
       - Add a compound for the missing pattern. If no room, swap lowest-priority isolation.
    4. fix_push_pull_imbalance(week, push_sets, pull_sets) → MutationResult
       - Add pulling or pushing volume to restore balance
    5. redistribute_muscle_volume(week, muscle, from_session, to_session, sets) → MutationResult
       - Move volume between sessions when one is overloaded

    IMPLEMENT BATCH SYSTEM:
    def apply_mutation_batch(mutations: list[MutationRequest]) → list[MutationResult]:
       - Apply sequentially
       - Snapshot before each
       - Constraint check after each
       - Rollback any that cause violations

    CRITICAL: Every mutation must:
    - Recalculate volume accounting after the change (sum sets × volume_credit per muscle)
    - Check constraints (MEV/MRV, time cap, max exercises, axial limit)
    - Rollback if constraints fail (restore the snapshot)
    - Return a MutationResult with before/after volume snapshots

    HELPER FUNCTIONS (spec calls these "smart exercise finders"):
    - find_exercise_for_muscle(muscle, tier, exclude_ids, pattern_preference) → Exercise
    - find_exercise_for_pattern(pattern, tier, exclude_ids) → Exercise
    - find_non_axial_alternative(exercise, tier) → Exercise
    - calculate_session_volume(workout) → dict[str, float]  (muscle → total credit)
    - calculate_week_volume(week) → dict[str, float]
    - check_constraints(week, profile, volume_targets) → list[str]  (returns violation descriptions)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. layer5_validator.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Validation rules + auto-fix dispatch. LLM full-program review will be wired in Phase 5.

IMPLEMENT ALL 17 VALIDATION RULES from the spec (exact rule IDs):
  Volume: VOL_001, VOL_002
  Session: SES_001, SES_002, SES_003, SES_004, SES_005
  Variety: VAR_001, VAR_002
  Periodization: PER_001, PER_002, PER_003
  Goal-specific: GOAL_HYP_001, GOAL_STR_001, GOAL_POW_001, GOAL_POW_002
  Balance: BAL_001

Each rule has:
- check function that returns True/False + details
- severity: critical / major / warning
- auto_fix function that calls the appropriate mutator method

Main functions:

def run_all_validations(program, profile, strategy, volume_allocation) -> list[dict]:
    """Run all 17 rules. Return list of {id, severity, name, details, week, session}."""

def auto_fix_issue(mutator: ProgramMutator, issue: dict) -> MutationResult:
    """Map rule ID → specific mutator call. Implements the mapping from the spec."""
    # VOL_001 → mutator.fix_volume_deficit(...)
    # VOL_002 → mutator.fix_volume_excess(...)
    # SES_002 → mutator.swap_exercise() to replace axial with non-axial
    # PAT_001 → mutator.fix_missing_movement_pattern(...)
    # GOAL_HYP_001 → mutator.replace_prescription() with corrected reps
    # etc.

def validate_and_fix(program, profile, strategy, volume_allocation) -> tuple[BuiltProgram, list[dict]]:
    """The auto-fix loop from the spec:
    for iteration in range(3):
        issues = run_all_validations(...)
        critical + major → auto_fix_issue() for each
        if no critical/major: break
    return program, remaining_issues
    """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Test 1 — Run the validator on the test program from Phase 3:
  Generate the same 4-week test program, then validate it.
  Print all issues found (expect mostly clean if Phase 3 was correct).

Test 2 — Test auto-fix by deliberately breaking a program:
  Take the test program and manually remove all bicep exercises from Week 1.
  Run validate_and_fix. It should detect VOL_001 for biceps and auto-fix it.
  Print what the mutator did.

Test 3 — Test the mutator directly:
  Create a ProgramMutator for the test program.
  Call swap_exercise to replace barbell_back_squat with barbell_front_squat in Week 1.
  Print the MutationResult (volume_before, volume_after).
  The mutation should succeed (both are squat-pattern heavy compounds targeting quads/glutes).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPLEMENTATION SUMMARY — PRINT THIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 4 IMPLEMENTATION SUMMARY
================================

FILES CREATED:
- mutator.py: [X] lines — [description]
- layer5_validator.py: [X] lines — [description]

MUTATOR:
- Primitive mutations implemented: [list all 8]
- Compound mutations implemented: [list all 5]
- Batch system: [describe]
- Rollback mechanism: [describe how snapshots work]
- Volume recalculation: [describe when/how it triggers]

VALIDATOR:
- Rules implemented: [list all 17 rule IDs with severity]
- Auto-fix mappings: [list each rule ID → mutator method]
- Fix loop max iterations: [X]

TEST RESULTS:
1. Validation on clean program:
   - Critical issues: [X]
   - Major issues: [X]
   - Warnings: [X]
   - [list any issues found]

2. Auto-fix test (biceps removed):
   - Issue detected: [describe]
   - Fix applied: [describe what the mutator did]
   - Bicep volume after fix: [X] sets (target was [X])

3. Swap mutation test:
   - Swap: barbell_back_squat → barbell_front_squat
   - Success: [yes/no]
   - Volume change: [describe any differences]
   - Constraints passed: [yes/no]

DECISIONS MADE:
- [list any spec ambiguities and resolutions]
```

---
---

## PHASE 5: LLM Layers + Orchestrator (Wiring It All Together)

```
TASK: Implement Phase 5 — the remaining layers that use LLM calls, plus the main orchestrator.

SPEC LOCATION: Read docs/v5-program-generator-spec-FINAL.md — these sections:
- "Layer 1: Profile Builder"
- "Layer 2: Strategy Engine"
- "Layer 4 — Stage B" (LLM week review + applying suggestions via mutator)
- "Layer 5 — LLM Full-Program Review" (wiring LLM review into the validator)
- "Layer 6: Serializer"
- The main pipeline flow

EXISTING FILES (DO NOT MODIFY):
- All files from Phases 1-4

CREATE THESE FILES inside program_generator_v5/:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. layer1_profile_builder.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Two paths:
A) Structured input (from API/form) → deterministic profile construction. No LLM.
   def build_profile_from_structured(data: dict) -> AthleteProfile:
   - Validate all fields, apply defaults, compute derived fields

B) Natural language input (from voice agent) → LLM extraction.
   async def build_profile_from_natural_language(text: str, openai_client) -> AthleteProfile:
   - Use the PROFILE_EXTRACTION_PROMPT from prompts.py
   - Parse LLM JSON response into AthleteProfile
   - Validate the result, fill in defaults for missing fields

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. layer2_strategy_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rules engine for split + periodization selection, with LLM fallback for edge cases.

def build_strategy(profile: AthleteProfile, openai_client=None) -> ProgramStrategy:
  1. Select split via get_split_for_config() — deterministic
  2. Select periodization model:
     - hypertrophy → "volume_ramp"
     - strength → "linear_intensity"
     - power → "concurrent"
  3. Calculate mesocycle structure:
     - mesocycle_length: 3-4 weeks (3 for beginners, 4 for intermediate+)
     - num_mesocycles: program_duration_weeks / mesocycle_length
  4. Build WeekProfile for every week:
     - volume_multiplier ramps up within each mesocycle (from spec's periodization section)
     - intensity_modifier increases for strength, stays moderate for hypertrophy
     - Last week of each mesocycle is deload (is_deload=True, volume_multiplier=0.5)
     - EXCEPTION: last mesocycle may not need deload if program ends
  5. Apply sport adjustments if profile.sport is set
  6. If conflicting constraints detected (e.g., 2 days/week + power goal + advanced):
     - Try to resolve with rules
     - If can't resolve: call LLM with STRATEGY_RESOLUTION_PROMPT (if openai_client provided)
     - If no LLM available: use best-effort rules default

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. UPDATE layer4_program_builder.py — ADD Stage B
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Add the LLM week review (Stage B) to the existing Layer 4.

Add this function:
async def review_and_refine_program(
    program: BuiltProgram,
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    volume_allocation: VolumeAllocation,
    openai_client,
) -> BuiltProgram:
    """Stage B: Parallel LLM review of each week + apply suggestions via mutator."""
    
    async def review_single_week(week):
        prompt = format_week_review_prompt(week, profile, strategy)
        response = await openai_client.chat.completions.create(...)
        return parse_llm_response(response)
    
    # Fire all week reviews in PARALLEL
    reviews = await asyncio.gather(*[review_single_week(w) for w in program.weeks])
    
    # Apply suggestions through the mutator (not directly)
    mutator = ProgramMutator(program, profile, strategy, volume_allocation, EXERCISE_BY_ID)
    for week, review in zip(program.weeks, reviews):
        for suggestion in review.get("suggestions", []):
            mutation = parse_llm_suggestion_to_mutation(suggestion, week.week_number)
            if mutation:
                result = mutator.apply_mutation(mutation)
                # Log whether applied or rejected
    
    return program

Also add:
def parse_llm_suggestion_to_mutation(suggestion: dict, week_number: int) -> MutationRequest | None:
    """Convert LLM suggestion JSON to a MutationRequest. Return None if unparseable."""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. UPDATE layer5_validator.py — ADD LLM review
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Add the LLM full-program review to the existing validator.

Add:
async def llm_full_program_review(
    program: BuiltProgram,
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    openai_client,
) -> dict:
    """Send entire program to LLM for holistic quality review."""
    prompt = format_full_program_review_prompt(program)
    response = await openai_client.chat.completions.create(
        model="gpt-5.2",  # Higher-quality model for full review
        ...
    )
    return parse_review_response(response)

Update validate_and_fix to optionally run LLM review after deterministic fixes pass.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5. layer6_serializer.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Convert V5 BuiltProgram → V3 output format. 100% deterministic.

def serialize_to_v3(program: BuiltProgram) -> dict:
    """Convert BuiltProgram to the V3 CompletedProgram JSON format."""
    # Map V5 fields to V3 fields
    # Preserve all exercise details, sets, reps, RPE, rest, tempo
    # Output should be ready to store/return via the existing API

Note: Since we don't have the V3 schema files available, implement a clean JSON serialization that outputs a well-structured dict. Include a comment noting where V3 schema mapping would be plugged in.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6. main.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The async orchestrator — the entry point.

async def generate_program_v5(
    input_data: dict,
    openai_client = None,
    use_llm: bool = True,
) -> dict:
    """
    Full V5 pipeline:
    1. Layer 1: Build profile (structured or NL)
    2. Layer 2: Build strategy (rules + optional LLM)
    3. Layer 3: Calculate volume (deterministic)
    4. Layer 4A: Build program (deterministic)
    5. Layer 4B: LLM week review (parallel, if use_llm)
    6. Layer 5: Validate + auto-fix + LLM full review (if use_llm)
    7. Layer 6: Serialize to output format
    """
    # Time each step and log
    # If use_llm=False, skip all LLM calls (useful for testing)
    # Return the serialized program dict

Also add a synchronous wrapper:
def generate_program_v5_sync(input_data: dict, use_llm: bool = False) -> dict:
    """Synchronous version for testing (no LLM calls)."""
    return asyncio.run(generate_program_v5(input_data, use_llm=False))

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Test — Full pipeline WITHOUT LLM (deterministic only):
  from program_generator_v5.main import generate_program_v5_sync

  result = generate_program_v5_sync({
      "user_id": "test_001",
      "name": "Test Athlete",
      "training_goal": "hypertrophy",
      "training_level": "intermediate",
      "program_duration_weeks": 4,
      "training_days_per_week": 4,
      "session_duration_minutes": 60,
      "equipment_tier": 1,
  }, use_llm=False)

  # Print the full program
  # Verify it matches the Phase 3 test output quality

Test 2 — Profile builder from structured input:
  profile = build_profile_from_structured({same fields as above})
  # Verify all derived fields are computed

Test 3 — Strategy builder:
  strategy = build_strategy(profile)
  # Print: split selected, periodization model, week profiles
  # Verify: 4 weeks, volume_ramp, last week is deload

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPLEMENTATION SUMMARY — PRINT THIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 5 IMPLEMENTATION SUMMARY
================================

FILES CREATED:
- layer1_profile_builder.py: [X] lines
- layer2_strategy_engine.py: [X] lines
- layer6_serializer.py: [X] lines
- main.py: [X] lines

FILES MODIFIED:
- layer4_program_builder.py: added [X] lines (Stage B + LLM review)
- layer5_validator.py: added [X] lines (LLM full review)

LAYER 1 (Profile Builder):
- Structured input path: [describe]
- NL input path: [describe]
- Derived fields computed: [list]

LAYER 2 (Strategy Engine):
- Split selection: [describe decision tree]
- Periodization models: [list]
- Week profile generation: [describe ramp pattern]
- LLM fallback: [describe when it triggers]

LAYER 4 STAGE B:
- Parallel week review: [describe asyncio.gather setup]
- Suggestion → mutation parsing: [describe]
- Mutation application: [describe safeguards]

LAYER 5 LLM REVIEW:
- Model used: [X]
- Review output format: [describe]

LAYER 6 (Serializer):
- Output format: [describe structure]

MAIN ORCHESTRATOR:
- Pipeline steps: [list 1-7]
- Timing: [describe logging]
- LLM-free mode: [describe]

FULL PIPELINE TEST (deterministic, no LLM):
- Input: intermediate hypertrophy 4x/wk 4 weeks Tier 1
- Time to generate: [X] seconds
- Weeks generated: [X]
- Sessions per week: [X]
- Exercises per session: [range]
- Volume accuracy: [X]/[Y] muscles within ±2 sets
- Validation issues remaining: [X] critical, [X] major, [X] warnings
- Output format: [describe]

COMPLETE FILE INVENTORY:
program_generator_v5/
├── __init__.py
├── schemas.py: [X] lines
├── exercise_library.py: [X] lines (pre-existing, not modified)
├── volume_tables.py: [X] lines
├── split_templates.py: [X] lines
├── sport_mappings.py: [X] lines
├── scoring.py: [X] lines
├── utils.py: [X] lines
├── prompts.py: [X] lines
├── mutator.py: [X] lines
├── layer1_profile_builder.py: [X] lines
├── layer2_strategy_engine.py: [X] lines
├── layer3_volume_engine.py: [X] lines
├── layer4_program_builder.py: [X] lines
├── layer5_validator.py: [X] lines
├── layer6_serializer.py: [X] lines
└── main.py: [X] lines
Total: [X] lines across [X] files

DECISIONS MADE:
- [list any deviations or ambiguity resolutions]
```

---
---

## PHASE 6: Test Suite (Prove It Works)

```
TASK: Create a comprehensive test suite that runs all 7 test cases from the spec and validates program quality.

SPEC LOCATION: Read docs/v5-program-generator-spec-FINAL.md — the "Test Each Tier Independently" section lists the required test cases.

EXISTING FILES: All files from Phases 1-5.

CREATE: program_generator_v5/test_suite.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEST CASES (all from the spec):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Tier 1, beginner, hypertrophy, 3x/week, 45-min sessions, 4 weeks
2. Tier 1, intermediate, hypertrophy, 4x/week, 60-min sessions, 8 weeks (THE GOLD STANDARD)
3. Tier 2, intermediate, hypertrophy, 4x/week, 60-min sessions, 4 weeks
4. Tier 3, advanced, hypertrophy, 6x/week, 75-min sessions, 4 weeks
5. Tier 1, intermediate, strength, 4x/week, 60-min sessions, 8 weeks
6. Tier 1, intermediate, power, 4x/week, 60-min sessions, 4 weeks
7. Sport-specific: basketball, intermediate, 4x/week, 60-min sessions, 4 weeks

For EACH test case, generate the program (use_llm=False) and run these quality checks:

A) STRUCTURAL CHECKS:
   - Correct number of weeks generated
   - Correct sessions per week
   - Every session has 4-8 exercises
   - No empty sessions, no empty weeks

B) VOLUME CHECKS:
   - Every non-deload week: all muscles >= MEV (±1 set tolerance)
   - Every week: no muscle > MRV
   - Volume increases from Week 1 → Week 3 (or week before deload)
   - Deload weeks have ≤60% of Week 1 volume

C) EXERCISE QUALITY:
   - All exercises are available at the specified equipment tier
   - No avoided exercises appear
   - Heavy compounds first in every session
   - No isolation exercises below 8 reps in hypertrophy programs
   - Power/plyometric exercises first in power programs
   - At least one main lift (squat/bench/dead/OHP) per session in strength programs
   - No more than 2 axial-loading exercises per session

D) PRESCRIPTION QUALITY:
   - Rep ranges appropriate for exercise_type × goal
   - Rest periods appropriate (compounds > isolations)
   - RPE increases across weeks within mesocycle
   - Deload RPE is lower than Week 1

E) VARIETY CHECKS:
   - No two sessions in the same week are identical
   - Primary compounds are consistent within mesocycles
   - Exercise diversity across the full program (use at least 40% of available exercises)

F) TIMING CHECK:
   - Estimated session duration within ±10 min of target

Print a scorecard for each test case:
  TEST CASE [N]: [description]
  ✅/❌ Structural: [pass/fail details]
  ✅/❌ Volume: [pass/fail — worst muscle deviation]
  ✅/❌ Exercise quality: [pass/fail details]
  ✅/❌ Prescription: [pass/fail details]
  ✅/❌ Variety: [pass/fail details]
  ✅/❌ Timing: [avg duration vs target]
  GRADE: [A/B/C/D/F based on passes]

Also print the FULL PROGRAM for test case #2 (the gold standard) — every exercise, every set, every week.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPLEMENTATION SUMMARY — PRINT THIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 6 IMPLEMENTATION SUMMARY
================================

TEST RESULTS SCORECARD:
Test 1 (T1 beginner hyp 3x): [GRADE] — [pass count]/[total checks]
Test 2 (T1 intermediate hyp 4x): [GRADE] — [pass count]/[total checks]
Test 3 (T2 intermediate hyp 4x): [GRADE] — [pass count]/[total checks]
Test 4 (T3 advanced hyp 6x): [GRADE] — [pass count]/[total checks]
Test 5 (T1 intermediate str 4x): [GRADE] — [pass count]/[total checks]
Test 6 (T1 intermediate pow 4x): [GRADE] — [pass count]/[total checks]
Test 7 (basketball sport 4x): [GRADE] — [pass count]/[total checks]

OVERALL: [X]/7 tests at A or B grade

COMMON ISSUES ACROSS TESTS:
- [list any patterns of failure]

GOLD STANDARD PROGRAM (Test 2) — FULL OUTPUT:
[Print the complete 8-week program]

GENERATION PERFORMANCE:
- Average time per program: [X] seconds
- Slowest: [X] seconds (which test case)
- Fastest: [X] seconds (which test case)

KNOWN ISSUES:
- [list any remaining problems]
```
