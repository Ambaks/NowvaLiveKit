# V5 Program Generator — Complete Implementation Specification (FINAL)

## YOU ARE BUILDING THIS

Build V5 of our workout program generator. This is a Python backend system that generates periodized, multi-week training programs. It runs as a Celery task, uses LLM calls (OpenAI API) strategically for reasoning tasks, and deterministic engines for computation. The output is a structured program JSON that gets saved to the database and rendered as a PDF.

**Architecture philosophy: Deterministic foundation, LLM intelligence layer.** The deterministic engines guarantee mechanical correctness — volume targets are always hit, movement patterns are always balanced, periodization is always appropriate for the goal. The LLM adds coaching intelligence on top — interpreting complex user context, reviewing program coherence, catching qualitative issues that rules can't anticipate.

The existing codebase has V4 (8-layer architecture). You are creating V5 as a new module alongside V4 — do NOT modify V4 files. V5 should be a self-contained module that produces the same final `CompletedProgram` output format that the existing database saver and PDF generator expect.

---

## WHY V5 EXISTS — V4's CRITICAL FAILURES

V4 produces programs that no competent S&C coach would approve. Here are the specific failures you must prevent:

### Failure 1: Muscle groups below minimum effective volume
V4 generated a program where back got 3-4 direct sets per week for an intermediate hypertrophy program. The volume engine calculated 6-12 sets as the MEV-to-MAV range, but the exercise selector ignored these targets because it operated session-by-session with no weekly volume accounting. Triceps got ZERO direct sets for 2 entire weeks despite being flagged as an emphasis muscle.

### Failure 2: Wrong periodization model for the goal
V4 used block periodization with a "Realization" phase (6 reps @ 79%) for a hypertrophy program. Realization/peaking is a strength concept. Hypertrophy mesocycles should ramp VOLUME (not intensity) across weeks and end with a deload, not a peak.

### Failure 3: Uniform prescription across exercise types
Every exercise in a session got the same reps, intensity%, and rest period. Week 1: everything 12 reps @ 65% with 1 min rest. Week 4: everything 6 reps @ 79% with 2 min rest. This is wrong — barbell curls at 6 reps @ 79% with 2 min rest is nonsensical. Compounds and isolations need different prescriptions even within the same session.

### Failure 4: Junk volume from excessive same-exercise sets
8 sets of barbell bench press in a single session. Effective reps diminish significantly after ~5 hard sets of the same movement due to accumulated fatigue. Volume should be distributed across exercises, not stacked on one.

### Failure 5: Duplicate sessions
Week 4 Days 2 and 4 were identical — exact same exercises, sets, and reps. This wastes a training day and shows the variety system failed.

### Failure 6: Exercises in wrong session types
Lateral raises appeared on a lower body day. The exercise selector had no hard constraint preventing this.

### Failure 7: No vertical pulling in upper body sessions
Multiple upper body days had ZERO vertical pull movements (no pull-ups, no lat pulldowns). A balanced upper body session needs horizontal push, horizontal pull, vertical push, AND vertical pull patterns.

### Failure 8: Catastrophic generation speed
Layer 5 (exercise selection) took 574 of 611 total seconds (94%) because it made a separate LLM call for every single workout (16 calls for a 4-week program, would be 48+ for 12 weeks). Exercise selection from a constrained library is a scoring/constraint-satisfaction problem, not a reasoning problem.

---

## EQUIPMENT MODEL

There are exactly 3 equipment tiers. The system must produce excellent programs at ALL tiers, especially Tier 1 which is the default and most constrained.

### Tier 1: Barbell (DEFAULT)
- Olympic barbell (20kg/45lb) + plates (full range)
- A rack and adjustable bench are assumed — they come with the barbell. Do NOT treat rack or bench as separate equipment items.
- Pull-up bar (part of the rack)
- Floor space for bodyweight work

This is the default. If the user doesn't specify equipment, assume Tier 1.

### Tier 2: Barbell + Dumbbells
Everything in Tier 1 plus:
- Adjustable dumbbell set or dumbbell rack (full weight range)

### Tier 3: Barbell + Dumbbells + Bands
Everything in Tier 2 plus:
- Resistance bands (light, medium, heavy tensions)

**CRITICAL DESIGN RULE**: The exercise library must have enough exercises at EVERY tier to fill all muscle groups and movement patterns. If a tier cannot hit a muscle group with direct work, flag it at library design time — do not let it silently fail at generation time. The exercise library section below specifies minimum exercise counts per muscle group per tier.

---

## SUPPORTED PROGRAM GOALS

### 1. HYPERTROPHY (Muscle Growth)

**Programming Philosophy:**
- Primary driver of growth is VOLUME (hard sets near failure) accumulated over time
- Secondary driver is progressive overload (more weight or reps over weeks/mesocycles)
- Intensity stays moderate — most work at RPE 7-8.5 (RIR 1.5-3). Going to absolute failure is reserved for isolation movements on the last set of the last week before deload
- Variety matters — muscle fibers respond to different angles, grips, and resistance profiles
- Stretch-mediated hypertrophy is real — prioritize exercises that load the muscle at long lengths (incline curls, overhead tricep extensions, RDLs, flyes, sissy squats)

**Rep Ranges by Exercise Type:**
- Heavy compounds (squat, bench, deadlift, OHP): 6-10 reps
- Light compounds (rows, lunges, hip thrusts, pull-ups): 8-12 reps
- Isolations (curls, lateral raises, tricep extensions, flyes): 10-15 reps
- Small muscles / rear delts / calves / abs: 12-20 reps

**Periodization: Volume Ramping + Deload (MANDATORY for hypertrophy)**
This is the ONLY acceptable periodization model for hypertrophy goals. Do not use block periodization, do not use realization phases, do not use intensity peaking.

For a 4-week mesocycle:
- Week 1 (Introduction): Volume at MEV + ~10%. RPE 6-7. RIR 3-4. Purpose: establish movement patterns, begin stimulus.
- Week 2 (Building): Add 1-2 sets per muscle group vs Week 1. RPE 7-8. RIR 2-3. Purpose: overloading.
- Week 3 (Overreaching): Add 1-2 more sets, approaching MRV. RPE 8-9. RIR 1-2. Last sets of isolations can go to failure. Purpose: maximum stimulus before recovery.
- Week 4 (Deload): Volume drops to ~50% of Week 1. Intensity drops 10-15%. RPE 5-6. RIR 4+. Purpose: dissipate fatigue, allow supercompensation.

For programs longer than 4 weeks: run multiple mesocycles. Each subsequent mesocycle starts with slightly higher baseline volume (+1 set per muscle group at MEV) and can introduce new exercise variations.

**Rest Periods:**
- Heavy compounds: 120-180 seconds
- Light compounds: 90-120 seconds
- Isolations: 60-90 seconds
- Supersetted exercises: 60 seconds between exercises, full rest after completing both

**Volume Targets (weekly sets per muscle group for intermediate):**
These are the ranges the system must hit. MEV = minimum to see progress. MAV = optimal. MRV = maximum recoverable.

| Muscle Group | MEV | MAV | MRV | Notes |
|---|---|---|---|---|
| Chest | 8 | 14 | 20 | Split across flat, incline, decline angles |
| Back (lats) | 8 | 14 | 20 | Vertical + horizontal pulls |
| Back (upper/traps/rhomboids) | 4 | 8 | 14 | Rows, face pulls, shrugs |
| Side Delts | 6 | 12 | 20 | Isolation-heavy, can tolerate high frequency |
| Rear Delts | 6 | 10 | 18 | Often undertrained, high frequency tolerant |
| Front Delts | 0 | 0 | 6 | Get enough from pressing — direct work optional |
| Quads | 6 | 12 | 20 | Squat variations, lunges, leg press |
| Hamstrings | 4 | 10 | 16 | Hip hinge + knee flexion both needed |
| Glutes | 0 | 6 | 12 | Squats/deads contribute; add hip thrusts if priority |
| Biceps | 4 | 10 | 16 | Pulling contributes; add direct curl work |
| Triceps | 4 | 8 | 14 | Pressing contributes; add direct extension work |
| Calves | 4 | 8 | 14 | Stubborn muscle, high frequency helps |
| Abs/Core | 0 | 6 | 12 | Compounds contribute; add direct if priority |
| Forearms | 0 | 4 | 8 | Pulling/gripping contributes |

**CRITICAL VOLUME RULES FOR HYPERTROPHY:**
1. NO muscle group may fall below MEV in any non-deload week. This is a hard constraint, not a suggestion. If the exercise selector cannot fill MEV for a muscle group, the program is INVALID.
2. No single exercise should contribute more than 5 sets per session for the same muscle group. Distribute volume across 2-3 exercises per major muscle group.
3. Secondary muscle contributions count, but at a reduced rate: if bench press hits triceps as secondary, count it as 0.5× the set count for triceps. Do NOT count it as 1:1.
4. Each muscle group should be trained at least 2× per week for optimal frequency. Ideally no more than 10 direct sets per muscle group per session.

### 2. STRENGTH (Force Production)

**Programming Philosophy:**
- Primary driver is neural adaptation — training the nervous system to recruit more motor units and fire them faster
- Heavy loads (>80% 1RM) are essential for main lifts
- Lower volume than hypertrophy, but higher per-set intensity
- Specificity matters — if you want to get stronger at bench press, you bench press heavy. Variation is limited to addressing weak points.
- Accessory work exists to build muscle in areas that limit the main lifts, using hypertrophy-style parameters

**Rep Ranges by Exercise Type:**
- Main compound lifts (squat, bench, deadlift, OHP): 1-5 reps
- Close variations (pause bench, front squat, deficit deadlift): 3-6 reps
- Accessories (rows, curls, tricep work, etc.): 6-12 reps (hypertrophy parameters for muscle building)

**Periodization: Linear or Block with Intensity Ramping**
For a 4-week mesocycle:
- Week 1 (Accumulation): Main lifts 4×5 @ RPE 7. Accessories moderate volume.
- Week 2 (Intensification): Main lifts 4×4 @ RPE 7.5-8. Slightly heavier.
- Week 3 (Peak): Main lifts 5×3 @ RPE 8-8.5. Heaviest working week.
- Week 4 (Deload): Main lifts 3×3 @ RPE 6. Accessories halved.

For programs longer than 4 weeks: increase working weights each mesocycle. Can introduce variation lifts (e.g., switch from comp bench to close-grip bench for a mesocycle).

**Rest Periods:**
- Main lifts: 180-300 seconds (3-5 minutes)
- Close variations: 150-240 seconds
- Accessories: 90-120 seconds

**Volume is lower than hypertrophy** — typically 60-75% of hypertrophy volume for each muscle group. The intensity makes up for it.

### 3. POWER (Rate of Force Development)

**Programming Philosophy:**
- Power = force × velocity. Train BOTH components.
- Every session has 3 tiers: (1) explosive/power work FIRST, (2) strength work second, (3) accessory hypertrophy work last
- Power movements are done at submaximal loads (50-75% 1RM) for SPEED — compensatory acceleration
- Plyometrics are power exercises requiring zero equipment
- CNS fatigue management is critical — low volume, high quality, long rest

**Rep Ranges by Exercise Type:**
- Power/explosive movements: 1-3 reps (speed is the goal, stop before fatigue kills bar speed)
- Plyometrics: 3-5 reps (quality jumps, full reset between reps)
- Strength compounds: 3-5 reps @ 80-88%
- Accessories: 6-10 reps

**Periodization: Concurrent/Conjugate**
Every session has all three components. Across weeks:
- Week 1-2: Higher power volume (more explosive sets), moderate strength
- Week 3: Peak strength intensity, moderate power maintenance
- Week 4: Deload all components

**Rest Periods:**
- Power/plyometric movements: 180-300 seconds (full CNS recovery)
- Strength movements: 180-240 seconds
- Accessories: 60-90 seconds

**Available Power Exercises by Tier:**
- Tier 1 (barbell): Power cleans, hang cleans, push press, barbell jump squats (light), explosive barbell rows
- Tier 1 (bodyweight): Box jumps, broad jumps, depth jumps, clap push-ups, explosive pull-ups, sprints, bounds
- Tier 2 adds: DB snatches, DB clean & press, DB jump squats, DB swing
- Tier 3 adds: Band-resisted jumps, band-assisted plyometrics, accommodating resistance on compounds

### 4. SPORT-SPECIFIC (Maps to a Base Goal + Adjustments)

Sport-specific programs select one of the 3 base goals and apply sport-specific modifiers. The user provides their sport and the system determines the base + adjustments.

**Sport → Base Goal Mapping:**

| Sport Category | Base Goal | Key Adjustments |
|---|---|---|
| Basketball, Football (skill positions), Soccer, Volleyball | Power | Extra unilateral lower body, lateral movement prep, reduce upper body volume, add posterior chain emphasis |
| Football (linemen), Rugby, Wrestling | Strength + Power hybrid | Max strength emphasis, neck work, grip strength, heavy compound focus |
| Boxing, MMA, Martial Arts | Power | Rotational power, posterior chain, shoulder endurance, grip/forearm, reduced lower body hypertrophy volume |
| Swimming | Strength | Lat/shoulder emphasis, core anti-rotation, shoulder prehab (external rotation), reduced lower body |
| Running, Cycling, Endurance | Strength | Low volume, high intensity compounds for injury prevention, single-leg work, hip stability, NO power movements (save CNS for sport) |
| Baseball, Tennis, Golf | Power | Rotational power, unilateral emphasis, shoulder health, anti-rotation core |
| General Athleticism | Power | Balanced program with all movement patterns |

**Sport-Specific Adjustments Applied:**
- `volume_modifier`: 0.6-1.0 (endurance athletes need less gym volume to save recovery for sport)
- `emphasis_muscles`: list of muscles to prioritize (e.g., basketball → glutes, hamstrings, calves for jumping)
- `deemphasis_muscles`: list of muscles to reduce volume for (e.g., swimmers → quads)
- `mandatory_movement_patterns`: patterns that MUST be included (e.g., MMA → rotation, anti-rotation)
- `forbidden_exercises`: exercises contraindicated for the sport (e.g., behind-neck press for throwers)
- `injury_prevention_additions`: prehab exercises to include (e.g., external rotation for throwers, Nordic curls for sprinters)

---

## EXERCISE LIBRARY

### Schema

```python
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional

class EquipmentTier(int, Enum):
    TIER_1 = 1  # Barbell (includes rack + bench)
    TIER_2 = 2  # + Dumbbells
    TIER_3 = 3  # + Bands

class MuscleRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    STABILIZER = "stabilizer"

class ExerciseType(str, Enum):
    HEAVY_COMPOUND = "heavy_compound"     # Squat, Bench, Deadlift, OHP
    LIGHT_COMPOUND = "light_compound"     # Rows, Lunges, Pull-ups, Hip Thrusts
    ISOLATION = "isolation"               # Curls, Lateral Raises, Extensions
    POWER = "power"                       # Cleans, Snatches, Explosive movements
    PLYOMETRIC = "plyometric"             # Jumps, Bounds, Clap Push-ups

class MovementPattern(str, Enum):
    HORIZONTAL_PUSH = "horizontal_push"   # Bench press, push-ups
    HORIZONTAL_PULL = "horizontal_pull"   # Rows
    VERTICAL_PUSH = "vertical_push"       # OHP, DB press
    VERTICAL_PULL = "vertical_pull"       # Pull-ups, lat pulldown
    HIP_HINGE = "hip_hinge"              # Deadlifts, RDL, Good mornings
    SQUAT = "squat"                       # Squats, lunges, leg press
    LUNGE = "lunge"                       # Lunges, split squats, step-ups
    ISOLATION_PUSH = "isolation_push"     # Tricep extensions, lateral raises
    ISOLATION_PULL = "isolation_pull"     # Curls, face pulls, rear delt work
    CORE = "core"                         # Planks, rollouts, crunches
    POWER_LOWER = "power_lower"           # Cleans, jumps, explosive squats
    POWER_UPPER = "power_upper"           # Push press, explosive rows, clap push-ups
    CARRY = "carry"                       # Farmer's carries, overhead carries
    ROTATION = "rotation"                 # Woodchops, rotational throws

class MuscleGroup(str, Enum):
    # Chest
    CHEST = "chest"                       # Pectoralis major (general)
    UPPER_CHEST = "upper_chest"           # Clavicular head
    LOWER_CHEST = "lower_chest"           # Sternal head

    # Back
    LATS = "lats"
    UPPER_BACK = "upper_back"             # Rhomboids, mid traps
    TRAPS = "traps"                       # Upper trapezius
    ERECTORS = "erectors"                 # Spinal erectors

    # Shoulders
    FRONT_DELTS = "front_delts"
    SIDE_DELTS = "side_delts"
    REAR_DELTS = "rear_delts"

    # Arms
    BICEPS = "biceps"
    TRICEPS = "triceps"
    FOREARMS = "forearms"

    # Lower Body
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    ADDUCTORS = "adductors"

    # Core
    ABS = "abs"
    OBLIQUES = "obliques"

class MuscleActivation(BaseModel):
    muscle: MuscleGroup
    role: MuscleRole
    # How much a set of this exercise "counts" toward volume for this muscle.
    # Primary = 1.0, Secondary = 0.5, Stabilizer = 0.0 (doesn't count toward volume)
    volume_credit: float = Field(ge=0.0, le=1.0)

class Exercise(BaseModel):
    id: str                                    # Unique snake_case ID: "bb_bench_press_flat"
    name: str                                  # Display name: "Barbell Bench Press (Flat)"
    equipment_tier: EquipmentTier              # Minimum tier required
    exercise_type: ExerciseType
    movement_pattern: MovementPattern
    muscle_activations: list[MuscleActivation]

    # Prescription constraints
    min_reps: int                              # Lowest reasonable rep count
    max_reps: int                              # Highest reasonable rep count
    min_sets_per_session: int = 2              # Don't program less than this (not worth the setup)
    max_sets_per_session: int = 5              # Hard cap per session (junk volume beyond this)

    # Fatigue profile
    is_axial_loading: bool = False             # Spinal compression (squat, deadlift, OHP, rows)
    systemic_fatigue: str = "moderate"         # "low", "moderate", "high"
    grip_intensive: bool = False               # Relevant for fatigue pairing

    # Difficulty & suitability
    difficulty: int = Field(ge=1, le=5)        # 1=beginner, 5=advanced
    requires_proficiency: bool = False         # True for Olympic lifts, advanced movements
    bilateral: bool = True                     # False for single-arm/leg (affects set count — double for unilateral)
    
    # SFR (Stimulus-to-Fatigue Ratio) — higher is better for hypertrophy
    sfr_rating: float = Field(ge=1.0, le=10.0, default=5.0)

    # Coaching
    cues: list[str] = []                       # Form cues for the voice agent
    common_mistakes: list[str] = []

    # Variation/rotation
    rotation_group: str                        # Exercises in the same group are interchangeable
    variation_tags: list[str] = []             # ["incline", "close_grip", "pause"] for specificity matching
```

### Minimum Exercise Requirements Per Tier

The exercise library MUST contain at least these many exercises for each muscle group at each tier.

**Tier 1 (Barbell + Bodyweight):**

| Muscle Group | Min Exercises | Examples |
|---|---|---|
| Chest | 5 | Flat bench, incline bench, close-grip bench (chest secondary), decline bench, push-up variations |
| Lats | 4 | Pull-ups, chin-ups, barbell row (underhand), barbell pendlay row |
| Upper Back | 3 | Barbell row (overhand), inverted rows, barbell shrugs |
| Side Delts | 2 | Barbell upright row, plate/barbell lateral raise |
| Rear Delts | 2 | Inverted row (wide grip, flared elbows), barbell face pull (wide grip high pull) |
| Front Delts | 2 | OHP, push press (also from pressing compounds) |
| Quads | 5 | Back squat, front squat, barbell lunges, barbell split squat, sissy squat (BW) |
| Hamstrings | 4 | Romanian deadlift, stiff-leg deadlift, good mornings, Nordic curls (BW) |
| Glutes | 3 | Barbell hip thrust, deep squats, barbell glute bridge |
| Biceps | 3 | Barbell curl, chin-ups (supinated), reverse grip barbell row |
| Triceps | 4 | Close-grip bench, skull crushers, overhead barbell extension, dips, diamond push-ups |
| Calves | 2 | Barbell calf raise (standing), barbell seated calf raise |
| Abs/Core | 4 | Barbell rollout, hanging leg raise, plank, dead bug |
| Forearms | 2 | Barbell wrist curl, behind-back barbell wrist curl |
| Adductors | 1 | Copenhagen plank (BW) |

**Tier 2 adds at minimum:**

| Muscle Group | Additional Exercises | Examples |
|---|---|---|
| Chest | +4 | DB flat press, DB incline press, DB flyes, DB incline flyes |
| Lats | +3 | DB row (single arm), DB pullover, DB chest-supported row |
| Upper Back | +2 | DB rear delt row, DB shrugs |
| Side Delts | +3 | DB lateral raise, DB Y-raise, DB Arnold press |
| Rear Delts | +2 | DB reverse flye, DB face pull (prone on incline bench) |
| Quads | +3 | DB goblet squat, DB Bulgarian split squat, DB step-up |
| Hamstrings | +2 | DB Romanian deadlift, DB single-leg RDL |
| Glutes | +2 | DB hip thrust, DB sumo squat |
| Biceps | +4 | DB curl, DB hammer curl, DB incline curl, DB concentration curl |
| Triceps | +3 | DB overhead extension, DB kickback, DB close-grip press |
| Calves | +1 | DB calf raise |

**Tier 3 adds at minimum:**

| Muscle Group | Additional Exercises | Examples |
|---|---|---|
| Side Delts | +1 | Band lateral raise |
| Rear Delts | +2 | Band pull-apart, band face pull |
| Biceps | +1 | Band curl |
| Triceps | +2 | Band pushdown, band overhead extension |
| Hamstrings | +1 | Band leg curl |
| Glutes | +1 | Band hip abduction |

### Exercise Library Population

Build the exercise library as a Python file (`exercise_library.py`) containing a list of `Exercise` objects. Include AT MINIMUM 80 exercises for Tier 1, 40 additional for Tier 2, and 15 additional for Tier 3 (135+ total). Each exercise must have fully populated muscle_activations with correct volume_credit values.

When building the library, use these volume_credit guidelines:
- Primary mover in the exercise: volume_credit = 1.0
- Significant secondary contributor: volume_credit = 0.5
- Minor secondary / stabilizer: volume_credit = 0.0 (don't count it)

Examples:
- Barbell Bench Press: chest PRIMARY 1.0, triceps SECONDARY 0.5, front_delts SECONDARY 0.5
- Barbell Row (overhand): upper_back PRIMARY 1.0, lats PRIMARY 1.0, biceps SECONDARY 0.5, rear_delts SECONDARY 0.5
- Barbell Curl: biceps PRIMARY 1.0, forearms SECONDARY 0.5
- Pull-up: lats PRIMARY 1.0, biceps SECONDARY 0.5, upper_back SECONDARY 0.5

---

## V5 ARCHITECTURE — HYBRID DETERMINISTIC + LLM

V5 has 6 layers. The core principle: **deterministic engines guarantee correctness, LLM calls add coaching intelligence.** The LLM is never asked to do math, search databases, or apply known rules — it's asked to reason, interpret, and judge.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        V5 PIPELINE                                  │
│                                                                     │
│  Layer 1: Profile Builder ───────── LLM for complex natural        │
│  (interpret user context)           language intake; deterministic   │
│                                     for structured API input        │
│                    │                                                │
│                    ▼                                                │
│  Layer 2: Strategy Engine ───────── Rules engine for 90% of cases; │
│  (split + periodization)            LLM for edge cases with        │
│                                     conflicting constraints         │
│                    │                                                │
│                    ▼                                                │
│  Layer 3: Volume Engine ─────────── 100% deterministic.            │
│  (set targets per muscle/session)   Pure math. No LLM.             │
│                                                                     │
│                    │                                                │
│                    ▼                                                │
│  Layer 4: Program Builder ───────── Deterministic scoring for      │
│  (exercise selection +               exercise selection; LLM for    │
│   prescription + ordering)          per-WEEK coherence review       │
│                                     (parallel calls)                │
│                    │                                                │
│                    ▼                                                │
│  Layer 5: Validator ─────────────── Deterministic rule checks +    │
│  (verify + auto-fix + review)       auto-fix; LLM for full-program │
│                                     qualitative review              │
│                    │                                                │
│                    ▼                                                │
│  Layer 6: Serializer ────────────── 100% deterministic.            │
│  (V5 → V3 format)                  Data mapping only.              │
│                                                                     │
│  TOTAL LLM CALLS: 3-9 (vs V4's 18-51)                             │
│  TOTAL TIME TARGET: 10-20 seconds (vs V4's 611 seconds)            │
└─────────────────────────────────────────────────────────────────────┘
```

### LLM USAGE SUMMARY

| Layer | LLM Calls | When | Model | Purpose |
|---|---|---|---|---|
| Layer 1 | 0-1 | Complex NL intake from voice agent | gpt-5-mini | Parse "I want to get toned but I had an ACL tear and play pickup basketball" into structured profile |
| Layer 2 | 0-1 | Conflicting/unusual constraints | gpt-5-mini | Resolve ambiguity that the rules engine can't handle |
| Layer 3 | 0 | Never | — | Pure math |
| Layer 4 | 1 per week (PARALLEL) | After building each week | gpt-5-mini | Review week's exercise selections for coaching coherence |
| Layer 5 | 1 | After full program built | gpt-5.2 | Holistic qualitative review of entire program |
| Layer 6 | 0 | Never | — | Data mapping |
| **Total** | **3-9** | | | **All LLM calls except Layer 4 are sequential; Layer 4 calls run in parallel** |

**CRITICAL RULE: LLM calls are ADVISORY, not authoritative.** The deterministic engines make the decisions. The LLM suggests improvements. If the LLM suggests something that violates a hard constraint (e.g., "add more back volume" when back is already at MRV), the suggestion is discarded. The LLM never overwrites the volume engine's math or the validator's rules.

---

### Layer 1: Profile Builder

**Input:** User data from the API (user profile, questionnaire answers, goal selection, equipment tier, sport if applicable). Can be structured (API/form) or unstructured (voice agent transcript).

**Output:** `AthleteProfile`

```python
class AthleteProfile(BaseModel):
    user_id: str
    name: str
    
    # Demographics
    age: Optional[int] = None
    sex: Optional[str] = None
    body_weight_kg: Optional[float] = None
    
    # Training context
    training_goal: str                         # "hypertrophy", "strength", "power"
    sport: Optional[str] = None                # "basketball", "mma", etc.
    training_level: str                        # "beginner", "intermediate", "advanced"
    training_age_years: Optional[float] = None
    
    # Program parameters
    program_duration_weeks: int
    training_days_per_week: int                # 2-6
    session_duration_minutes: int = 60
    
    # Equipment
    equipment_tier: EquipmentTier
    
    # Constraints
    injuries: list[dict] = []                  # [{"area": "left_shoulder", "avoid": ["overhead_press"]}]
    exercises_to_avoid: list[str] = []
    exercises_to_include: list[str] = []
    
    # Recovery
    recovery_capacity: str = "normal"          # "low", "normal", "high"
    
    # Emphasis
    weak_points: list[str] = []                # Muscle groups to prioritize
    
    # Derived (computed by Layer 1)
    effective_goal: str                        # After sport mapping
    sport_adjustments: Optional[dict] = None
    available_exercises: list[str] = []        # Exercise IDs available at this tier, minus injuries/avoids
    exercise_coverage_warnings: list[str] = [] # Any muscle groups with limited exercise options
```

**Logic:**

For STRUCTURED input (API/form where fields are already filled):
1. Directly populate the profile from provided fields
2. If `sport` is provided, look up the sport mapping table → set `effective_goal` and `sport_adjustments`
3. Filter exercise library: keep exercises where `equipment_tier <= user's tier`, remove `exercises_to_avoid`, remove exercises contraindicated by injuries
4. Validate coverage: for each muscle group, check that at least 2 exercises remain available. If fewer, add to `exercise_coverage_warnings`
5. **NO LLM call needed**

For UNSTRUCTURED input (voice agent transcript, free-text goal description):
1. **LLM CALL** — Send the raw text to the LLM with a structured output schema:

```python
PROFILE_EXTRACTION_PROMPT = """
You are extracting a structured athlete profile from a conversation transcript or free-text input.

Extract the following fields. If a field is not mentioned, set it to null.
Do not infer values that weren't stated or clearly implied.
If the user mentions a sport, identify the specific sport name.
If the user mentions injuries, extract the body area and what movements to avoid.
If the user mentions preferences ("I love deadlifts", "I hate leg press"), extract those.
If the user mentions weak points ("my arms are small", "I want bigger shoulders"), extract the muscle groups.

Return a JSON object matching this schema:
{
    "training_goal": "hypertrophy" | "strength" | "power" | null,
    "sport": string | null,
    "training_level": "beginner" | "intermediate" | "advanced" | null,
    "training_days_per_week": int | null,
    "session_duration_minutes": int | null,
    "injuries": [{"area": string, "avoid": [string]}],
    "exercises_to_avoid": [string],
    "exercises_to_include": [string],
    "weak_points": [string],  // muscle group names
    "recovery_notes": string | null,  // any mention of sleep, stress, recovery issues
    "additional_context": string | null  // anything else relevant
}
"""
```

2. Parse the LLM output into profile fields
3. Apply the same sport mapping, exercise filtering, and coverage validation as structured input
4. **1 LLM call, gpt-5-mini, ~1-2 seconds**

---

### Layer 2: Strategy Engine

**Input:** `AthleteProfile`

**Output:** `ProgramStrategy`

```python
class SessionTemplate(BaseModel):
    day_label: str                             # "Upper A", "Lower B", "Push", "Full Body"
    muscle_groups: list[MuscleGroup]
    required_movement_patterns: list[MovementPattern]
    optional_movement_patterns: list[MovementPattern]
    is_primary: bool = True                    # Primary sessions get more volume than light/secondary days

class SplitTemplate(BaseModel):
    split_id: str
    name: str
    sessions_per_week: list[SessionTemplate]
    suitable_levels: list[str]
    suitable_goals: list[str]

class WeekProfile(BaseModel):
    week_number: int
    mesocycle_number: int                      # Which mesocycle this week belongs to (1-indexed)
    week_in_mesocycle: int                     # Position within the mesocycle (1-4 typically)
    phase_name: str                            # "Introduction", "Building", "Overreaching", "Deload"
    volume_multiplier: float                   # Relative to mesocycle baseline. Week 1=1.0, Week 2=1.15, Week 3=1.25, Deload=0.5
    intensity_modifier: str                    # "light", "moderate", "moderate_heavy", "heavy", "deload"
    rpe_range: tuple[float, float]
    rir_range: tuple[int, int]
    is_deload: bool = False
    notes: str = ""

class ProgramStrategy(BaseModel):
    split: SplitTemplate
    week_profiles: list[WeekProfile]
    periodization_model: str                   # "volume_ramp", "linear_intensity", "concurrent"
    volume_modifier: float = 1.0               # Global scaling from sport adjustments
    emphasis_muscles: list[MuscleGroup] = []
    deemphasis_muscles: list[MuscleGroup] = []
    mesocycle_count: int                       # How many mesocycles in the program
```

**Split Selection Rules (deterministic):**

```
IF training_days_per_week == 2:
    IF training_level == "beginner": split = "full_body_2x"
    ELSE: split = "upper_lower_2x"

IF training_days_per_week == 3:
    IF training_level in ["beginner", "early_intermediate"]: split = "full_body_3x"
    ELIF effective_goal == "strength": split = "full_body_3x"  # frequency benefits strength
    ELSE: split = "push_pull_legs"

IF training_days_per_week == 4:
    split = "upper_lower_4x"  # Almost always optimal for 4 days
    Exception: IF effective_goal == "power" AND sport requires it: split = "concurrent_4x"

IF training_days_per_week == 5:
    IF effective_goal == "hypertrophy": split = "upper_lower_ppl_5x"
    ELSE: split = "upper_lower_plus_full_5x"

IF training_days_per_week == 6:
    split = "ppl_6x"  # Push/Pull/Legs 2x per week
```

**Week Profile Generation (deterministic by goal):**

For hypertrophy (volume_ramp):
```
mesocycle_length = 4
for each mesocycle m (1 to N):
    base_volume_bump = (m - 1) * 0.05  # Each meso starts 5% higher
    
    Week 1 (Introduction):
        volume_multiplier = 1.0 + base_volume_bump
        intensity_modifier = "moderate"
        rpe_range = (6.5, 7.5)
        rir_range = (3, 4)
    
    Week 2 (Building):
        volume_multiplier = 1.15 + base_volume_bump
        intensity_modifier = "moderate"
        rpe_range = (7.0, 8.0)
        rir_range = (2, 3)
    
    Week 3 (Overreaching):
        volume_multiplier = 1.25 + base_volume_bump
        intensity_modifier = "moderate_heavy"
        rpe_range = (8.0, 9.0)
        rir_range = (1, 2)
    
    Week 4 (Deload):
        volume_multiplier = 0.5
        intensity_modifier = "deload"
        rpe_range = (5.0, 6.0)
        rir_range = (4, 6)
        is_deload = True
```

For strength (linear_intensity):
```
mesocycle_length = 4
for each mesocycle m:
    Week 1 (Accumulation):
        volume_multiplier = 1.0
        intensity_modifier = "moderate_heavy"
        rpe_range = (7.0, 7.5)
        rir_range = (2, 3)
    
    Week 2 (Intensification):
        volume_multiplier = 0.95
        intensity_modifier = "heavy"
        rpe_range = (7.5, 8.0)
        rir_range = (2, 2)
    
    Week 3 (Peak):
        volume_multiplier = 0.85
        intensity_modifier = "very_heavy"
        rpe_range = (8.0, 8.5)
        rir_range = (1, 2)
    
    Week 4 (Deload):
        volume_multiplier = 0.5
        intensity_modifier = "deload"
        rpe_range = (5.0, 6.0)
        rir_range = (4, 6)
        is_deload = True
```

For power (concurrent):
```
mesocycle_length = 4
    Week 1-2: Higher power set counts, moderate strength
    Week 3: Peak strength intensity, power maintained
    Week 4: Deload
    (Power movements always present in every non-deload session)
```

**LLM Call (EDGE CASES ONLY):**

Only invoke if the rules engine detects genuinely conflicting constraints that it can't resolve:
- User wants 6 days/week but is a beginner (rules say beginners shouldn't do PPL 2x)
- User has shoulder + knee injuries that eliminate most compounds for both upper and lower
- User wants "hypertrophy" but also mentions "I need to peak for a powerlifting meet in 8 weeks"
- Sport-specific adjustments conflict with the user's stated preferences

```python
STRATEGY_RESOLUTION_PROMPT = """
You are an expert S&C coach resolving a conflict in program design.

The rules engine selected:
- Split: {rules_engine_split}
- Periodization: {rules_engine_periodization}

But there's a conflict:
{conflict_description}

The user's full profile:
{athlete_profile}

Your options for resolving:
1. Override the split to: {alternative_splits}
2. Override the periodization to: {alternative_periodizations}
3. Adjust constraints: {possible_adjustments}

Choose the best resolution and explain your reasoning in 2-3 sentences.

Return JSON:
{
    "resolution": "override_split" | "override_periodization" | "adjust_constraints",
    "value": string,  // the new split/periodization/adjustment
    "reasoning": string
}
"""
```

**Budget: 0-1 LLM calls, gpt-5-mini, ~1-2 seconds.** 90%+ of users will have zero LLM calls here.

---

### Layer 3: Volume Engine (100% Deterministic — NO LLM)

**Input:** `AthleteProfile`, `ProgramStrategy`

**Output:** `VolumeAllocation`

```python
class SessionVolumeTarget(BaseModel):
    day_label: str
    muscle_volumes: dict[str, int]             # {"chest": 4, "triceps": 3, "side_delts": 3, ...}
    total_sets: int
    movement_pattern_requirements: dict[str, int]  # {"horizontal_push": 4, "vertical_pull": 3, ...}

class WeekVolumeAllocation(BaseModel):
    week_number: int
    is_deload: bool
    sessions: list[SessionVolumeTarget]
    weekly_totals: dict[str, float]            # Total volume credit per muscle
    below_mev: list[str] = []                  # MUST be empty for non-deload weeks
    above_mrv: list[str] = []                  # MUST be empty always

class VolumeAllocation(BaseModel):
    weeks: list[WeekVolumeAllocation]
```

**Volume Calculation Algorithm:**

```
For each week:
    1. Get base MEV/MAV/MRV for training_level from volume_tables.py
    
    2. Compute prescribed volume per muscle:
       For hypertrophy (volume_ramp):
           base = MEV + (week_profile.volume_multiplier - 1.0) * (MAV - MEV) / 0.25
           # This maps: multiplier 1.0 → MEV, multiplier 1.25 → MAV
           # Clamped to [MEV, MRV]
       
       For strength:
           base = MEV + 0.3 * (MAV - MEV)  # Lower volume than hypertrophy
           base *= week_profile.volume_multiplier
       
       For power:
           base = MEV + 0.2 * (MAV - MEV)  # Even lower — save recovery for explosive work
           base *= week_profile.volume_multiplier
       
       For deload weeks:
           base = MEV * 0.5
    
    3. Apply modifiers:
       - sport volume_modifier (0.6-1.0): base *= volume_modifier
       - recovery_capacity: "low" → base *= 0.85, "high" → base *= 1.10
       - age: if age > 45 → base *= 0.85
       - emphasis_muscles: base *= 1.20 (capped at MRV)
       - deemphasis_muscles: base *= 0.80 (floored at MEV)
    
    4. Round to integers. Ensure >= MEV for non-deload, <= MRV always.
    
    5. Distribute across sessions:
       For each muscle group:
           sessions_targeting_this = [s for s in split.sessions if muscle in s.muscle_groups]
           sets_per_session = prescribed / len(sessions_targeting_this)
           # Distribute evenly, alternate ceiling/floor for odd numbers
           
           # Cap: no single session gets >10 direct sets for one muscle
           # Cap: total session sets <= session_duration_minutes / 3.5
    
    6. Derive movement pattern requirements:
       For each session, based on its assigned muscles:
           If session has chest volume → needs horizontal_push (and/or vertical_push for OHP)
           If session has lat volume → needs vertical_pull and/or horizontal_pull
           If session has quad volume → needs squat and/or lunge
           If session has hamstring volume → needs hip_hinge
           If session has side_delt volume → needs isolation_push
           If session has bicep volume → needs isolation_pull
           etc.
    
    7. VALIDATE:
       For each non-deload week:
           assert all muscle groups >= MEV
           assert all muscle groups <= MRV
           assert all session totals <= time cap
       If validation fails, redistribute. This MUST pass before proceeding.
```

**NO LLM calls. Pure computation.**

---

### Layer 4: Program Builder (Deterministic Core + LLM Coherence Review)

This is the most important layer. It has two sub-stages:

**Stage A: Deterministic Exercise Selection & Prescription** (no LLM)
**Stage B: LLM Coherence Review per week** (parallel calls)

```python
class PrescribedSet(BaseModel):
    set_number: int
    reps: int
    rpe: Optional[float] = None
    rir: Optional[int] = None
    intensity_percent: Optional[float] = None
    rest_seconds: int
    tempo: Optional[str] = None
    notes: str = ""

class PrescribedExercise(BaseModel):
    exercise_id: str
    exercise_name: str
    exercise_type: ExerciseType
    movement_pattern: MovementPattern
    sets: list[PrescribedSet]
    total_sets: int
    muscle_contributions: dict[str, float]     # {"chest": 3.0, "triceps": 1.5}
    superset_group: Optional[str] = None
    order_in_session: int
    rationale: str = ""

class BuiltWorkout(BaseModel):
    day_number: int
    day_label: str
    exercises: list[PrescribedExercise]
    total_sets: int
    estimated_duration_minutes: int
    volume_check: dict[str, float]
    warmup_notes: str
    
class BuiltWeek(BaseModel):
    week_number: int
    phase_name: str
    workouts: list[BuiltWorkout]
    weekly_volume_actual: dict[str, float]
    weekly_volume_target: dict[str, float]
    volume_adherence: dict[str, float]         # actual/target ratio (should be 0.85-1.15)

class BuiltProgram(BaseModel):
    profile: AthleteProfile
    strategy: ProgramStrategy
    weeks: list[BuiltWeek]
    unique_exercises_used: int
    total_sets: int
    total_workouts: int
    generation_time_seconds: float
```

#### Stage A: Exercise Selection Algorithm (DETERMINISTIC — NO LLM)

```
function select_exercises_for_session(session_template, volume_targets, week_number, 
                                       mesocycle_number, recently_used, available_exercises,
                                       program_goal):
    
    selected = []
    remaining_volume = copy(volume_targets.muscle_volumes)
    remaining_patterns = copy(volume_targets.movement_pattern_requirements)
    axial_count = 0
    grip_intensive_count = 0
    
    # ─── PHASE 1: Fill required movement patterns with compounds ───
    
    for pattern in sort_patterns_by_priority(remaining_patterns, program_goal):
        candidates = [ex for ex in available_exercises if
            ex.movement_pattern == pattern and
            ex.exercise_type in [HEAVY_COMPOUND, LIGHT_COMPOUND, POWER, PLYOMETRIC] and
            ex.id not in [s.exercise_id for s in selected] and
            ex.difficulty <= difficulty_cap_for_level(profile.training_level) and
            (not ex.requires_proficiency or profile.training_level in ["intermediate", "advanced"])
        ]
        
        if not candidates:
            continue  # Will be caught by validator
        
        for candidate in candidates:
            candidate._score = compute_exercise_score(
                exercise=candidate,
                remaining_volume=remaining_volume,
                recently_used=recently_used,
                mesocycle_number=mesocycle_number,
                week_number=week_number,
                axial_count=axial_count,
                grip_count=grip_intensive_count,
                program_goal=program_goal,
                user_preferences=profile.exercises_to_include,
            )
        
        candidates.sort(key=lambda x: -x._score)
        best = candidates[0]
        
        # Determine set count
        primary_muscles = [ma.muscle for ma in best.muscle_activations if ma.role == "primary"]
        max_needed = max(remaining_volume.get(m.value, 0) for m in primary_muscles) if primary_muscles else 3
        sets = min(best.max_sets_per_session, max(best.min_sets_per_session, round(max_needed)))
        
        # Update volume accounting
        for ma in best.muscle_activations:
            if ma.muscle.value in remaining_volume:
                remaining_volume[ma.muscle.value] -= sets * ma.volume_credit
        
        if best.is_axial_loading:
            axial_count += 1
        if best.grip_intensive:
            grip_intensive_count += 1
        
        remaining_patterns[pattern] -= 1
        selected.append((best, sets))
    
    # ─── PHASE 2: Fill remaining volume with isolations/accessories ───
    
    muscles_needing_volume = {m: v for m, v in remaining_volume.items() if v > 1.0}
    
    for muscle in sorted(muscles_needing_volume, key=lambda m: -remaining_volume[m]):
        candidates = [ex for ex in available_exercises if
            any(ma.muscle.value == muscle and ma.role == "primary" for ma in ex.muscle_activations) and
            ex.exercise_type in [ISOLATION, LIGHT_COMPOUND] and
            ex.id not in [s[0].id for s in selected]
        ]
        
        if not candidates:
            continue
        
        for candidate in candidates:
            candidate._score = compute_exercise_score(
                exercise=candidate,
                remaining_volume=remaining_volume,
                recently_used=recently_used,
                mesocycle_number=mesocycle_number,
                week_number=week_number,
                axial_count=axial_count,
                grip_count=grip_intensive_count,
                program_goal=program_goal,
                user_preferences=profile.exercises_to_include,
            )
        
        candidates.sort(key=lambda x: -x._score)
        best = candidates[0]
        
        needed = remaining_volume[muscle]
        sets = min(best.max_sets_per_session, max(best.min_sets_per_session, round(needed)))
        
        for ma in best.muscle_activations:
            if ma.muscle.value in remaining_volume:
                remaining_volume[ma.muscle.value] -= sets * ma.volume_credit
        
        selected.append((best, sets))
    
    # ─── PHASE 3: Validate and patch ───
    
    # Check for muscles still significantly short
    for muscle, remaining in remaining_volume.items():
        if remaining > 1.5:
            # Try adding 1-2 sets to an already-selected exercise that hits this muscle
            for (ex, sets) in selected:
                if any(ma.muscle.value == muscle for ma in ex.muscle_activations) and sets < ex.max_sets_per_session:
                    add = min(ex.max_sets_per_session - sets, round(remaining))
                    # update sets and remaining_volume
                    break
    
    # Check time cap
    estimated_time = estimate_session_duration(selected, program_goal)
    max_time = profile.session_duration_minutes * 1.1  # 10% grace
    while estimated_time > max_time and len(selected) > 4:
        # Remove the last isolation exercise (lowest priority)
        removed = selected.pop()
        # Re-add its volume to remaining
        estimated_time = estimate_session_duration(selected, program_goal)
    
    # Sort by exercise type priority
    type_order = {POWER: 0, PLYOMETRIC: 1, HEAVY_COMPOUND: 2, LIGHT_COMPOUND: 3, ISOLATION: 4}
    selected.sort(key=lambda x: type_order.get(x[0].exercise_type, 5))
    
    # Build superset pairs (for hypertrophy — pair antagonist isolations)
    if program_goal == "hypertrophy":
        selected = build_supersets(selected)
    
    return selected
```

**Scoring Function:**

```python
def compute_exercise_score(exercise, remaining_volume, recently_used, mesocycle_number,
                            week_number, axial_count, grip_count, program_goal, 
                            user_preferences):
    score = 0.0
    
    # 1. SFR rating (higher = more stimulus per unit of fatigue)
    #    More important for hypertrophy, less for strength
    if program_goal == "hypertrophy":
        score += exercise.sfr_rating * 12
    else:
        score += exercise.sfr_rating * 6
    
    # 2. Volume fill: how much remaining volume does this exercise address?
    #    Sum of (remaining_volume[muscle] × volume_credit) for each muscle
    volume_fill = 0
    for ma in exercise.muscle_activations:
        if ma.muscle.value in remaining_volume and remaining_volume[ma.muscle.value] > 0:
            volume_fill += min(remaining_volume[ma.muscle.value], exercise.max_sets_per_session) * ma.volume_credit
    score += volume_fill * 8
    
    # 3. Variety: penalize recently used, bonus for fresh exercises
    weeks_since_used = get_weeks_since_used(exercise.id, recently_used)
    if weeks_since_used == 0:  # Used this week already (different session)
        score -= 15  # Allow but discourage (compounds may appear 2x/week)
    elif weeks_since_used == 1:  # Last week
        score -= 5
    elif weeks_since_used is None:  # Never used in this mesocycle
        score += 10
    else:
        score += min(weeks_since_used * 3, 10)
    
    # 4. Rotation group freshness
    #    If this exercise's rotation group has been overused, penalize
    group_usage = get_rotation_group_usage(exercise.rotation_group, recently_used)
    score -= group_usage * 3
    
    # 5. Compound consistency within mesocycle
    #    Primary compounds should stay the same within a mesocycle for progressive overload
    #    Isolations should rotate for variety
    if exercise.exercise_type in [HEAVY_COMPOUND, LIGHT_COMPOUND]:
        if was_primary_compound_last_week(exercise.id, recently_used, week_number):
            score += 20  # Strong bonus for consistency
    elif exercise.exercise_type == ISOLATION:
        if weeks_since_used == 1:
            score -= 3  # Slight nudge to rotate isolations more
    
    # 6. Fatigue management
    if exercise.is_axial_loading and axial_count >= 2:
        score -= 25  # Strongly discourage >2 axial exercises per session
    if exercise.grip_intensive and grip_count >= 2:
        score -= 15
    if exercise.systemic_fatigue == "high":
        score -= 5  # Slight penalty — prefer lower fatigue exercises when options exist
    
    # 7. User preference
    if exercise.id in user_preferences:
        score += 20
    
    # 8. Stretch-position bonus for hypertrophy
    if program_goal == "hypertrophy" and "stretch" in exercise.variation_tags:
        score += 8  # Prefer exercises that load at long muscle lengths
    
    return score
```

**Variety Management (Deterministic):**

Within a mesocycle:
- Primary compounds for each movement pattern **stay the same** across all weeks. This ensures progressive overload tracking. If Week 1 Upper A starts with barbell bench press, so do Weeks 2 and 3.
- Isolation exercises **rotate** within their rotation group every 1-2 weeks. The scoring function handles this automatically through the variety bonus/penalty.

Between mesocycles:
- Primary compounds **rotate** to a different member of their rotation group. Mesocycle 1 → flat bench, Mesocycle 2 → incline bench, Mesocycle 3 → close-grip bench.
- This is driven by `mesocycle_number` in the scoring function — exercises used as primaries in the previous mesocycle get a penalty, fresh alternatives get a bonus.

**Prescription Engine (built into Layer 4, deterministic):**

After exercises are selected, each one gets prescribed differently based on **exercise type AND week profile**:

```python
def prescribe_exercise(exercise, total_sets, week_profile, program_goal):
    
    # ─── Determine rep range by exercise type + goal ───
    
    REP_RANGES = {
        "hypertrophy": {
            "heavy_compound":  (6, 10),
            "light_compound":  (8, 12),
            "isolation":       (10, 15),
            "power":           (3, 5),
            "plyometric":      (3, 5),
        },
        "strength": {
            "heavy_compound":  (1, 5),
            "light_compound":  (5, 8),
            "isolation":       (8, 12),
            "power":           (1, 3),
            "plyometric":      (3, 5),
        },
        "power": {
            "heavy_compound":  (3, 5),
            "light_compound":  (5, 8),
            "isolation":       (6, 10),
            "power":           (1, 3),
            "plyometric":      (3, 5),
        },
    }
    
    min_rep, max_rep = REP_RANGES[program_goal][exercise.exercise_type.value]
    
    # Clamp to exercise's own min/max
    min_rep = max(min_rep, exercise.min_reps)
    max_rep = min(max_rep, exercise.max_reps)
    
    # ─── Select reps within range based on week intensity ───
    
    INTENSITY_TO_REP_POSITION = {
        "deload":          1.0,    # Top of rep range (lightest)
        "light":           0.85,
        "moderate":        0.6,
        "moderate_heavy":  0.35,
        "heavy":           0.15,
        "very_heavy":      0.0,    # Bottom of rep range (heaviest)
    }
    
    position = INTENSITY_TO_REP_POSITION[week_profile.intensity_modifier]
    reps = round(min_rep + position * (max_rep - min_rep))
    reps = max(min_rep, min(max_rep, reps))
    
    # ─── Determine rest by exercise type + goal ───
    
    REST_SECONDS = {
        "hypertrophy": {
            "heavy_compound": 150, "light_compound": 100, "isolation": 75,
            "power": 240, "plyometric": 240,
        },
        "strength": {
            "heavy_compound": 240, "light_compound": 150, "isolation": 100,
            "power": 270, "plyometric": 240,
        },
        "power": {
            "heavy_compound": 210, "light_compound": 150, "isolation": 90,
            "power": 270, "plyometric": 270,
        },
    }
    
    rest = REST_SECONDS[program_goal][exercise.exercise_type.value]
    if week_profile.is_deload:
        rest = int(rest * 0.75)  # Shorter rest on deload — lighter loads, less recovery needed
    
    # ─── RPE/RIR from week profile, adjusted by exercise type ───
    
    base_rpe_low, base_rpe_high = week_profile.rpe_range
    base_rir_low, base_rir_high = week_profile.rir_range
    
    if exercise.exercise_type.value == "isolation":
        # Isolations can be pushed slightly harder (closer to failure) since less systemic fatigue
        rpe = round(base_rpe_high, 1)
        rir = base_rir_low
    elif exercise.exercise_type.value == "heavy_compound":
        # Compounds stay more conservative
        rpe = round(base_rpe_low, 1)
        rir = base_rir_high
    else:
        rpe = round((base_rpe_low + base_rpe_high) / 2, 1)
        rir = round((base_rir_low + base_rir_high) / 2)
    
    # ─── Tempo ───
    
    TEMPOS = {
        "hypertrophy": {
            "heavy_compound": "2-1-1-0",   # Controlled eccentric, brief pause, strong concentric
            "light_compound": "2-1-1-1",   # Slight squeeze at top
            "isolation":      "3-1-1-1",   # Slow eccentric for TUT
        },
        "strength": {
            "heavy_compound": "1-1-X-0",   # Controlled down, explosive up
            "light_compound": "2-0-1-0",
            "isolation":      "2-0-1-0",
        },
        "power": {
            "power":          "1-0-X-0",   # Explosive
            "plyometric":     "1-0-X-0",
            "heavy_compound": "1-1-X-0",
            "light_compound": "2-0-1-0",
            "isolation":      "2-0-1-0",
        },
    }
    
    tempo = TEMPOS.get(program_goal, {}).get(exercise.exercise_type.value, "2-0-1-0")
    
    # ─── Build sets ───
    
    sets = []
    for i in range(total_sets):
        set_notes = ""
        set_rpe = rpe
        set_rir = rir
        
        # Last set of last training week in mesocycle: push harder on isolations
        if (i == total_sets - 1 and 
            week_profile.week_in_mesocycle == 3 and  # Last hard week
            exercise.exercise_type.value == "isolation"):
            set_notes = "Push to failure on this set"
            set_rpe = 10.0
            set_rir = 0
        
        # First set warmup note for heavy compounds
        if i == 0 and exercise.exercise_type.value == "heavy_compound":
            set_notes = "Ramp up with 2-3 warm-up sets before working weight"
        
        sets.append(PrescribedSet(
            set_number=i + 1,
            reps=reps,
            rpe=set_rpe,
            rir=set_rir,
            rest_seconds=rest,
            tempo=tempo,
            notes=set_notes,
        ))
    
    return sets
```

**Time Estimation:**

```python
def estimate_session_duration(selected_exercises, program_goal):
    duration_seconds = 5 * 60  # 5 min warmup
    
    for i, (exercise, sets) in enumerate(selected_exercises):
        # Setup/transition time
        if i == 0:
            duration_seconds += 90  # First exercise setup
        else:
            duration_seconds += 45  # Transition between exercises
        
        for s in range(sets):
            # Execution time: reps × avg rep duration
            rep_duration = 4 if exercise.exercise_type.value in ["heavy_compound", "power"] else 3
            reps = 10  # rough average
            duration_seconds += reps * rep_duration
            
            # Rest time (skip after last set of exercise)
            if s < sets - 1:
                rest = REST_SECONDS[program_goal].get(exercise.exercise_type.value, 90)
                # Supersets reduce rest
                if hasattr(exercise, '_superset_group') and exercise._superset_group:
                    rest = int(rest * 0.6)
                duration_seconds += rest
    
    duration_seconds += 3 * 60  # 3 min cooldown
    return duration_seconds / 60  # Return minutes
```

#### Stage B: LLM Coherence Review (Per-Week, PARALLEL)

After the deterministic engine builds all workouts for a week, send the week to the LLM for a coaching coherence review. This catches qualitative issues that scoring can't detect.

**These calls run IN PARALLEL for all weeks simultaneously.** A 4-week program sends 4 LLM calls at once, not sequentially. Wall-clock time: ~3-5 seconds regardless of program length.

```python
WEEK_REVIEW_PROMPT = """
You are a world-class strength & conditioning coach reviewing one week of a {program_goal} training program.

The athlete: {training_level} level, {equipment_tier_description}, training {days_per_week}x/week.
{sport_context}

This is Week {week_number} ({phase_name}) of a {total_weeks}-week program.

Here is the week's training:

{formatted_week}
--- end of week ---

Weekly volume summary:
{volume_summary}

The volume targets and movement pattern balance have ALREADY been validated by a deterministic engine 
and are guaranteed correct. Do NOT comment on total volume, MEV/MRV compliance, or movement pattern coverage.

Instead, evaluate these QUALITATIVE aspects:

1. **Exercise synergy**: Do the selected exercises work well together within each session?
   Look for: redundant exercises hitting the same muscle at the same angle, missed opportunities 
   for complementary exercises, exercises that would fatigue each other poorly (e.g., heavy RDLs 
   immediately after heavy deadlifts).

2. **Session flow**: Does the exercise ordering make sense for training quality?
   Look for: grip-intensive exercises stacked back-to-back, exercises requiring the same equipment 
   creating logistical issues, poor superset pairings.

3. **Week-level coherence**: Do the sessions within the week complement each other?
   Look for: overemphasis on one movement angle across the week (e.g., all chest work is flat pressing, 
   no incline), lack of exercise variety between sessions with the same muscle groups.

4. **Coaching intuition**: Anything a good coach would change that isn't covered above?

Return a JSON object:
{
    "issues": [
        {
            "session_day": int,         // Which day has the issue (0 if week-level)
            "exercise_id": string|null,  // Specific exercise if applicable
            "issue": string,            // Brief description
            "suggestion": string,       // Specific replacement or reorder
            "confidence": "high" | "medium" | "low"
        }
    ],
    "overall_quality": "excellent" | "good" | "needs_work",
    "coaching_notes": string  // 1-2 sentence summary
}

If the week looks good, return empty issues array with "excellent" or "good" quality.
Only flag issues you're confident about. Max 3 issues per week.
"""
```

**Applying LLM Suggestions:**

The LLM's suggestions are ADVISORY. They go through a filter:

```python
def apply_week_review(built_week, llm_review, volume_targets, available_exercises):
    for issue in llm_review["issues"]:
        if issue["confidence"] == "low":
            continue  # Skip low-confidence suggestions
        
        if issue["suggestion"] contains an exercise swap:
            proposed_exercise = find_exercise(issue["suggestion"])
            
            # HARD CONSTRAINT CHECK: Does the swap maintain volume compliance?
            simulated_week = simulate_swap(built_week, issue["exercise_id"], proposed_exercise)
            new_volumes = calculate_week_volumes(simulated_week)
            
            for muscle, vol in new_volumes.items():
                if vol < MEV[muscle] or vol > MRV[muscle]:
                    # Swap would violate volume constraints — REJECT
                    log(f"Rejected LLM suggestion: {issue['issue']} — would break volume constraints")
                    continue
            
            # Swap is safe — apply it
            apply_swap(built_week, issue["exercise_id"], proposed_exercise)
            log(f"Applied LLM suggestion: {issue['issue']}")
        
        elif issue["suggestion"] contains a reorder:
            # Reordering is safe — apply it
            apply_reorder(built_week, issue)
    
    return built_week
```

**Budget: 1 call per week, gpt-5-mini, ALL IN PARALLEL. 4-week program = 4 parallel calls ≈ 3-5 seconds wall-clock. 12-week program = 12 parallel calls ≈ 3-5 seconds wall-clock (parallel means same time regardless of count).**

---

### Layer 5: Validator (Deterministic Rules + LLM Full-Program Review)

**Input:** `BuiltProgram` (after Layer 4's LLM suggestions have been applied)

**Output:** `ValidatedProgram`

#### Deterministic Validation Checks:

```python
VALIDATION_RULES = [
    # ─── Volume Checks ───
    {
        "id": "VOL_001", "severity": "critical",
        "name": "Weekly volume above MEV",
        "check": "For each non-deload week, every muscle group's actual volume credit >= MEV",
        "auto_fix": "Add sets of the highest-SFR exercise for the deficient muscle"
    },
    {
        "id": "VOL_002", "severity": "critical",
        "name": "Weekly volume below MRV",
        "check": "No muscle group exceeds MRV in any week",
        "auto_fix": "Remove sets from lowest-SFR exercise for the excess muscle"
    },
    {
        "id": "VOL_003", "severity": "major",
        "name": "Per-exercise set cap",
        "check": "No exercise exceeds its max_sets_per_session",
        "auto_fix": "Split excess sets into a second exercise for the same muscle"
    },
    {
        "id": "VOL_004", "severity": "major",
        "name": "Per-muscle session cap",
        "check": "No muscle group gets >10 direct sets in a single session",
        "auto_fix": "Redistribute to other sessions in the week"
    },
    {
        "id": "VOL_005", "severity": "warning",
        "name": "Volume adherence to target",
        "check": "actual/target ratio for each muscle is between 0.85 and 1.15",
        "auto_fix": "Adjust sets up or down by 1"
    },
    
    # ─── Movement Pattern Checks ───
    {
        "id": "PAT_001", "severity": "critical",
        "name": "Weekly movement pattern coverage",
        "check": "Each non-deload week has at least: 1 horizontal push, 1 horizontal pull, 1 vertical push, 1 vertical pull, 1 squat pattern, 1 hip hinge",
        "auto_fix": "Add a compound exercise for the missing pattern"
    },
    {
        "id": "PAT_002", "severity": "major",
        "name": "Push:Pull ratio",
        "check": "Weekly push volume within 0.7-1.3× of pull volume",
        "auto_fix": "Add pulling volume or reduce pushing volume"
    },
    {
        "id": "PAT_003", "severity": "major",
        "name": "Upper session has both push and pull",
        "check": "Every upper body or full body session contains at least one push AND one pull",
        "auto_fix": "Add a pull exercise to push-only sessions or vice versa"
    },
    
    # ─── Session Quality Checks ───
    {
        "id": "SES_001", "severity": "major",
        "name": "Exercise ordering",
        "check": "Within each session: power → heavy compound → light compound → isolation",
        "auto_fix": "Re-sort exercises by type"
    },
    {
        "id": "SES_002", "severity": "major",
        "name": "Axial load stacking",
        "check": "No session has >2 heavy axial-loading exercises",
        "auto_fix": "Swap one axial exercise for a non-axial alternative"
    },
    {
        "id": "SES_003", "severity": "warning",
        "name": "Session duration",
        "check": "Estimated duration within 110% of session_duration_minutes",
        "auto_fix": "Remove lowest-priority isolation or reduce sets"
    },
    {
        "id": "SES_004", "severity": "warning",
        "name": "Minimum exercises per session",
        "check": "Each session has at least 4 exercises (3 for sessions ≤45min)",
        "auto_fix": "Add an exercise"
    },
    {
        "id": "SES_005", "severity": "critical",
        "name": "No exercises on wrong day type",
        "check": "Isolation exercises only on days targeting their primary muscle. No lateral raises on leg day.",
        "auto_fix": "Move exercise to correct session or remove"
    },
    
    # ─── Variety Checks ───
    {
        "id": "VAR_001", "severity": "critical",
        "name": "No duplicate sessions in same week",
        "check": "No two sessions in the same week have identical exercise lists",
        "auto_fix": "Swap one exercise for a rotation group alternative"
    },
    {
        "id": "VAR_002", "severity": "warning",
        "name": "Program exercise diversity",
        "check": "Program uses at least 50% of available exercises over its full duration",
        "auto_fix": "Rotate in unused exercises in later mesocycles"
    },
    
    # ─── Periodization Checks ───
    {
        "id": "PER_001", "severity": "critical",
        "name": "Volume progression within mesocycle",
        "check": "In volume_ramp: total weekly volume increases week-over-week (except deload). In linear_intensity: intensity increases week-over-week.",
        "auto_fix": "Adjust to ensure monotonic progression"
    },
    {
        "id": "PER_002", "severity": "major",
        "name": "Deload volume reduction",
        "check": "Deload weeks have ≤60% of Week 1's volume",
        "auto_fix": "Reduce deload volume"
    },
    {
        "id": "PER_003", "severity": "critical",
        "name": "Correct periodization for goal",
        "check": "Hypertrophy uses volume_ramp. Strength uses linear_intensity. Power uses concurrent. No realization phase in hypertrophy.",
        "auto_fix": "This should never trigger if Layer 2 is correct. If it does, regenerate week profiles."
    },
    
    # ─── Goal-Specific Checks ───
    {
        "id": "GOAL_HYP_001", "severity": "major",
        "name": "Hypertrophy isolation rep floor",
        "check": "In hypertrophy programs, isolation exercises are never prescribed below 8 reps",
        "auto_fix": "Set isolation reps to minimum 8"
    },
    {
        "id": "GOAL_STR_001", "severity": "critical",
        "name": "Strength main lift presence",
        "check": "In strength programs, at least one main compound (squat/bench/deadlift/OHP) per session",
        "auto_fix": "Add main lift"
    },
    {
        "id": "GOAL_POW_001", "severity": "critical",
        "name": "Power exercise placement",
        "check": "In power programs, explosive/power/plyometric exercises are the first in every session",
        "auto_fix": "Re-sort to put power first"
    },
    {
        "id": "GOAL_POW_002", "severity": "critical",
        "name": "Power session completeness",
        "check": "In power programs, every non-deload session has at least one power or plyometric movement",
        "auto_fix": "Add a power movement from available exercises"
    },
]
```

**Auto-Fix Loop:**

```python
def validate_and_fix(program, profile, strategy, volume_allocation):
    max_iterations = 3
    
    for iteration in range(max_iterations):
        issues = run_all_validations(program, profile, strategy, volume_allocation)
        
        critical = [i for i in issues if i["severity"] == "critical"]
        major = [i for i in issues if i["severity"] == "major"]
        warnings = [i for i in issues if i["severity"] == "warning"]
        
        if not critical and not major:
            break
        
        # Fix critical first, then major
        for issue in critical + major:
            apply_auto_fix(program, issue, profile, volume_allocation)
        
        # Log what was fixed
        logger.info(f"  Validation iteration {iteration + 1}: fixed {len(critical)} critical, {len(major)} major issues")
    
    remaining_critical = [i for i in run_all_validations(program, ...) if i["severity"] == "critical"]
    if remaining_critical:
        logger.error(f"  ❌ {len(remaining_critical)} critical issues remain after {max_iterations} fix iterations!")
    
    return program, issues
```

#### LLM Full-Program Review (ONE call)

After deterministic validation passes, send the entire program to the LLM for a holistic quality review. This catches emergent patterns across weeks that per-week reviews and rule checks can't see.

```python
FULL_PROGRAM_REVIEW_PROMPT = """
You are a world-class S&C coach doing a final review of a complete {program_goal} training program.

Athlete: {training_level}, {equipment_tier_description}, {days_per_week}x/week, {duration_weeks} weeks.
{sport_context}
{weak_points_context}

The program has already passed all quantitative validation:
- ✅ Volume targets met for all muscle groups every week
- ✅ Movement pattern balance verified
- ✅ Push:pull ratios within range
- ✅ Periodization model correct for goal
- ✅ Exercise ordering correct
- ✅ No duplicate sessions

Your job is the FINAL coaching eye. Look for:

1. **Long-term exercise progression**: Does the exercise selection evolve sensibly across mesocycles? 
   Are there logical progressions (e.g., goblet squat → back squat → front squat)?

2. **Overuse patterns across weeks**: Any joint or tendon getting hammered with the same movement 
   pattern every session, every week? (e.g., always conventional grip bench, never neutral grip)

3. **Training experience quality**: Would this program be motivating and enjoyable to follow? 
   Is there enough variety to prevent boredom without being chaotic?

4. **Weak point addressing**: Given the athlete's stated weak points ({weak_points}), does the 
   program adequately prioritize those areas with both volume AND exercise selection?

5. **Red flags**: Anything that would make you, as a coach, uncomfortable prescribing this?

Here is the complete program:

{formatted_full_program}

Return JSON:
{
    "overall_grade": "A" | "B" | "C" | "D" | "F",
    "strengths": [string],     // 2-3 things the program does well
    "issues": [
        {
            "category": string,
            "description": string,
            "affected_weeks": [int],
            "suggested_fix": string,
            "confidence": "high" | "medium" | "low"
        }
    ],
    "coaching_summary": string  // 2-3 sentence overall assessment
}

Be honest but constructive. Only flag genuine issues. Max 5 issues.
"""
```

**Applying Full-Program Review:**

Same filtering as Layer 4's review — only apply high-confidence suggestions that don't violate volume constraints. The LLM's suggestions are treated as advice, not commands.

**Budget: 1 call, gpt-5.2 (higher quality model for this final review), ~5-8 seconds.**

---

### Layer 6: Serializer (100% Deterministic)

Converts `ValidatedProgram` → V3 `CompletedProgram` format for backward compatibility.

1. Map V5 `BuiltWeek` → V3 `GeneratedWeek`
2. Map V5 `BuiltWorkout` → V3 workout format
3. Map V5 `PrescribedExercise` → V3 exercise format with proper set notation
4. Generate workout names from split template day labels
5. Populate V3 metadata: total_workouts, total_exercises, generation_time, validation_pass_rate
6. Set validation_pass_rate based on validator results:
   - 0 critical + 0 major issues remaining = 100%
   - 0 critical + some warnings = 95%
   - Any remaining major = 85%
   - Any remaining critical = 70% (should not happen)

**NO LLM calls. Pure data mapping.**

---

## SPLIT TEMPLATES — COMPLETE DEFINITIONS

Define these as data structures in a `split_templates.py` file:

### Upper/Lower 4x (PRIMARY for most users)

```
Upper A (Horizontal Focus):
  muscle_groups: [chest, lats, upper_back, side_delts, rear_delts, biceps, triceps]
  required_patterns: [horizontal_push, horizontal_pull, vertical_pull, isolation_push, isolation_pull]
  optional_patterns: [vertical_push]
  notes: "Primary horizontal pressing day. Include a vertical pull for balance."
  
Lower A (Quad Focus):
  muscle_groups: [quads, hamstrings, glutes, calves, abs]
  required_patterns: [squat, hip_hinge]
  optional_patterns: [lunge, core]
  notes: "Squat variation as primary. Hip hinge secondary."

Upper B (Vertical Focus):
  muscle_groups: [chest, lats, upper_back, side_delts, rear_delts, biceps, triceps]
  required_patterns: [vertical_push, horizontal_pull, vertical_pull, isolation_push, isolation_pull]
  optional_patterns: [horizontal_push]
  notes: "Primary overhead pressing day. MUST use different primary compounds than Upper A."
  
Lower B (Hinge Focus):
  muscle_groups: [quads, hamstrings, glutes, calves, abs]
  required_patterns: [hip_hinge, squat]
  optional_patterns: [lunge, core]
  notes: "Deadlift/RDL variation as primary. Squat secondary. MUST use different exercises than Lower A."
```

### Push/Pull/Legs (3x or 6x)

```
Push:
  muscle_groups: [chest, front_delts, side_delts, triceps]
  required_patterns: [horizontal_push, vertical_push, isolation_push]
  optional_patterns: []
  notes: "All pressing + side delt isolation + tricep isolation."
  
Pull:
  muscle_groups: [lats, upper_back, rear_delts, biceps, forearms]
  required_patterns: [horizontal_pull, vertical_pull, isolation_pull]
  optional_patterns: []
  notes: "All pulling + rear delt isolation + bicep isolation."
  
Legs:
  muscle_groups: [quads, hamstrings, glutes, calves, abs]
  required_patterns: [squat, hip_hinge]
  optional_patterns: [lunge, core]
  notes: "Squat + hinge + isolation accessories."
```

### Full Body (2x or 3x)

```
Full Body A:
  muscle_groups: [ALL]
  required_patterns: [horizontal_push, horizontal_pull, squat, hip_hinge]
  optional_patterns: [isolation_push, isolation_pull, core]
  notes: "Compound-heavy. Limit isolations to 1-2 for time."

Full Body B:
  muscle_groups: [ALL]
  required_patterns: [vertical_push, vertical_pull, lunge, hip_hinge]
  optional_patterns: [isolation_push, isolation_pull, core]
  notes: "Different primary movements than A."

Full Body C (if 3x):
  muscle_groups: [ALL]
  required_patterns: [horizontal_push, horizontal_pull, squat, core]
  optional_patterns: [isolation_push, isolation_pull]
  notes: "Mix of A and B with different specific exercises."
```

### Concurrent/Power (4-5x)

```
Power + Upper:
  muscle_groups: [chest, lats, upper_back, shoulders, biceps, triceps]
  required_patterns: [power_upper, horizontal_push, horizontal_pull OR vertical_pull]
  optional_patterns: [isolation_push, isolation_pull]
  notes: "ALWAYS start with power/plyometric movement. Then strength. Then accessories."
  
Power + Lower:
  muscle_groups: [quads, hamstrings, glutes, calves]
  required_patterns: [power_lower, squat, hip_hinge]
  optional_patterns: [lunge, core]
  notes: "ALWAYS start with power/plyometric movement. Then strength. Then accessories."

Strength + Full (if 5x):
  muscle_groups: [ALL]
  required_patterns: [squat OR hip_hinge, horizontal_push OR vertical_push, horizontal_pull OR vertical_pull]
  optional_patterns: [core, isolation_push, isolation_pull]
  notes: "Heavy compound focus. Main lift + 2-3 accessories."
```

---

## FILE STRUCTURE

```
program_generator_v5/
├── __init__.py
├── main.py                    # Entry point: generate_program_v5()
├── schemas.py                 # All Pydantic models
├── exercise_library.py        # Complete exercise database (135+ exercises)
├── split_templates.py         # Split template definitions
├── volume_tables.py           # MEV/MAV/MRV tables per training level
├── sport_mappings.py          # Sport → goal + adjustments mapping table
├── layer1_profile_builder.py  # Profile construction (deterministic + optional LLM)
├── layer2_strategy_engine.py  # Split + periodization selection (rules + optional LLM)
├── layer3_volume_engine.py    # Volume calculation + distribution (deterministic)
├── layer4_program_builder.py  # Exercise selection + prescription + LLM week review
├── layer5_validator.py        # Validation + auto-fix + LLM full-program review
├── layer6_serializer.py       # V5 → V3 format conversion
├── scoring.py                 # Exercise scoring function
├── prompts.py                 # All LLM prompts in one place
└── utils.py                   # Time estimation, superset builder, helpers
```

## main.py ENTRY POINT

```python
import time
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

async def generate_program_v5(
    user_data: dict,
    exercise_library: list,
    openai_client,
    input_type: str = "structured",  # "structured" or "natural_language"
) -> CompletedProgram:
    """
    V5 Program Generator.
    
    Target: 10-20 seconds total.
    LLM calls: 3-9 (mostly parallel).
    """
    start_time = time.time()
    
    # ── Layer 1: Profile Builder ──
    logger.info("[Layer 1] Building athlete profile...")
    if input_type == "natural_language":
        profile = await build_profile_from_nl(user_data, exercise_library, openai_client)  # 1 LLM call
    else:
        profile = build_profile_structured(user_data, exercise_library)  # 0 LLM calls
    logger.info(f"  ✓ Goal: {profile.effective_goal}, Level: {profile.training_level}, Tier: {profile.equipment_tier}")
    logger.info(f"  ✓ Available exercises: {len(profile.available_exercises)}")
    if profile.exercise_coverage_warnings:
        logger.warning(f"  ⚠ Coverage warnings: {profile.exercise_coverage_warnings}")
    
    # ── Layer 2: Strategy Engine ──
    logger.info("[Layer 2] Determining program strategy...")
    strategy = determine_strategy(profile, openai_client)  # 0-1 LLM calls
    logger.info(f"  ✓ Split: {strategy.split.name}")
    logger.info(f"  ✓ Periodization: {strategy.periodization_model}")
    logger.info(f"  ✓ {strategy.mesocycle_count} mesocycle(s), {len(strategy.week_profiles)} weeks")
    
    # ── Layer 3: Volume Engine ──
    logger.info("[Layer 3] Calculating volume allocation...")
    volume = calculate_volume(profile, strategy)  # 0 LLM calls
    for week in volume.weeks:
        assert not week.below_mev, f"Week {week.week_number} below MEV for: {week.below_mev}"
        assert not week.above_mrv, f"Week {week.week_number} above MRV for: {week.above_mrv}"
    logger.info(f"  ✓ Volume allocated for {len(volume.weeks)} weeks")
    
    # ── Layer 4: Program Builder ──
    logger.info("[Layer 4] Building program...")
    
    # Stage A: Deterministic exercise selection + prescription (< 1 second)
    program = build_program_deterministic(profile, strategy, volume, exercise_library)
    logger.info(f"  ✓ Selected exercises: {program.unique_exercises_used} unique across {program.total_workouts} workouts")
    logger.info(f"  ✓ Total sets: {program.total_sets}")
    
    # Stage B: LLM coherence review (parallel calls, ~3-5 seconds wall-clock)
    logger.info(f"  🔍 Running LLM coherence review for {len(program.weeks)} weeks (parallel)...")
    program = await run_parallel_week_reviews(program, profile, strategy, openai_client)
    logger.info(f"  ✓ LLM review complete")
    
    # ── Layer 5: Validator ──
    logger.info("[Layer 5] Validating program...")
    
    # Stage A: Deterministic validation + auto-fix
    program, issues = validate_and_fix(program, profile, strategy, volume)
    critical_count = len([i for i in issues if i["severity"] == "critical"])
    major_count = len([i for i in issues if i["severity"] == "major"])
    warning_count = len([i for i in issues if i["severity"] == "warning"])
    logger.info(f"  ✓ Deterministic validation: {critical_count} critical, {major_count} major, {warning_count} warnings")
    
    # Stage B: LLM full-program review
    logger.info(f"  🔍 Running LLM full-program review...")
    program, llm_review = await run_full_program_review(program, profile, strategy, openai_client)
    logger.info(f"  ✓ LLM grade: {llm_review['overall_grade']}")
    logger.info(f"  ✓ {len(llm_review['issues'])} qualitative issues noted")
    
    # ── Layer 6: Serializer ──
    logger.info("[Layer 6] Serializing to V3 format...")
    completed = serialize_to_v3(program, profile, strategy, issues, llm_review)
    
    total_time = time.time() - start_time
    logger.info(f"\n✅ V5 Generation Complete!")
    logger.info(f"  Total Time: {total_time:.2f}s")
    logger.info(f"  LLM Grade: {llm_review['overall_grade']}")
    logger.info(f"  Coaching Notes: {llm_review['coaching_summary']}")
    
    return completed


async def run_parallel_week_reviews(program, profile, strategy, openai_client):
    """Run LLM week reviews in parallel for all weeks simultaneously."""
    
    async def review_single_week(week):
        prompt = format_week_review_prompt(week, profile, strategy)
        response = await openai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content)
    
    # Fire all week reviews simultaneously
    reviews = await asyncio.gather(*[review_single_week(week) for week in program.weeks])
    
    # Apply suggestions (respecting hard constraints)
    for week, review in zip(program.weeks, reviews):
        program = apply_week_review(week, review, profile, strategy)
    
    return program
```

---

## WHAT SUCCESS LOOKS LIKE

A successful V5 program for an intermediate hypertrophy user (Tier 1, 4x/week, 60min sessions) should look like:

**Week 1 Upper A (Introduction — RPE 6.5-7.5):**
1. Barbell Bench Press — 3×8-10 @ RPE 7, rest 150s, tempo 2-1-1-0
2. Pull-ups — 3×8-10 @ RPE 7, rest 120s, tempo 2-1-1-0
3. Barbell Overhead Press — 3×8-10 @ RPE 7, rest 120s, tempo 2-1-1-0
4. Barbell Upright Row — 3×12-15 @ RPE 7.5, rest 75s, tempo 3-1-1-1
5. Barbell Curl — 2×10-12 @ RPE 7.5, rest 75s, tempo 2-0-1-0
6. Skull Crushers — 2×10-12 @ RPE 7.5, rest 75s, tempo 3-1-1-0

**Week 1 Lower A (Introduction — RPE 6.5-7.5):**
1. Barbell Back Squat — 3×8-10 @ RPE 7, rest 150s, tempo 2-1-1-0
2. Barbell Romanian Deadlift — 3×8-10 @ RPE 7, rest 120s, tempo 2-1-1-0
3. Barbell Walking Lunges — 3×10-12 @ RPE 7, rest 90s, tempo 2-0-1-0
4. Barbell Calf Raise — 3×12-15 @ RPE 7.5, rest 60s, tempo 2-1-1-1
5. Hanging Leg Raise — 2×12-15 @ RPE 7, rest 60s

**Week 3 Upper A (Overreaching — RPE 8-9, more volume):**
1. Barbell Bench Press — 4×6-8 @ RPE 8.5, rest 150s ← Same exercise, more sets, lower reps, higher RPE
2. Pull-ups — 4×8-10 @ RPE 8, rest 120s ← More sets
3. Barbell Overhead Press — 3×8-10 @ RPE 8.5, rest 120s
4. Barbell Upright Row — 4×12-15 @ RPE 9, rest 75s ← More sets
5. Barbell Curl — 3×10-12 @ RPE 9, rest 75s, notes: "Last set to failure" ← More sets
6. Skull Crushers — 3×10-12 @ RPE 9, rest 75s, notes: "Last set to failure" ← More sets

Notice: compounds and isolations have DIFFERENT rep ranges, rest periods, and RPE targets in the same session. Volume increases week over week. Exercises stay consistent within the mesocycle for progressive overload. Every upper session has push AND pull. Every muscle group gets adequate volume.

---

## CRITICAL IMPLEMENTATION NOTES

### 1. Exercise Library is the Foundation
Spend 40% of development time on a complete, accurate exercise library. Every exercise needs correct muscle_activations with proper volume_credit values. Test by running the selector at each tier and verifying coverage.

### 2. Volume Credit Accounting Must Be Exact
The #1 V4 failure was bad volume tracking. Every exercise's contribution is `sets × volume_credit`. Track it precisely, validate it at multiple points (Layer 3 outputs, Layer 4 post-selection, Layer 5 validation).

### 3. LLM Calls Are Advisory, Not Authoritative
The deterministic engine makes the decisions. The LLM reviews and suggests improvements. If a suggestion would violate a hard constraint (volume below MEV, wrong exercise ordering, etc.), it's rejected. The LLM never overwrites the volume engine's math.

### 4. Test Each Tier Independently
Generate test programs for:
- Tier 1 beginner hypertrophy 3x/week
- Tier 1 intermediate hypertrophy 4x/week (MOST COMMON)
- Tier 2 intermediate hypertrophy 4x/week
- Tier 3 advanced hypertrophy 6x/week
- Tier 1 intermediate strength 4x/week
- Tier 1 intermediate power 4x/week
- Sport-specific: basketball power 4x/week

### 5. Parallel LLM Calls
Layer 4's per-week reviews MUST run in parallel using asyncio.gather. A 12-week program should take the same wall-clock time as a 4-week program for the LLM review stage.

### 6. The Validator is a Safety Net, Not a Crutch
If the validator regularly catches critical issues, Layer 4 has bugs. Fix the generator. The validator should mostly see clean programs.

### 7. Backward Compatibility
V3 `CompletedProgram` format MUST be preserved. Layer 6 handles the conversion. Do not modify V3 schemas.

---

## PROGRAM MUTATOR — THE FIX ENGINE

Both Layer 4 (LLM week review suggestions) and Layer 5 (deterministic auto-fixes + LLM full-program suggestions) need to modify the built program. They both call into a shared **Program Mutator** module (`mutator.py`) that performs safe mutations while maintaining constraint integrity.

The mutator is the single source of truth for "how do you change a program after it's been built." No layer should directly modify `BuiltProgram` fields — always go through the mutator.

### Core Principle: Every Mutation Recalculates Volume

After ANY mutation (swap, add, remove, adjust sets, reorder), the mutator recalculates the affected session's and week's volume accounting. If the mutation would cause a constraint violation, it either adjusts to stay in bounds or rejects the mutation entirely.

### Mutator Schema

```python
class MutationResult(BaseModel):
    success: bool
    mutation_type: str                         # "swap", "add", "remove", "add_sets", "remove_sets", "reorder", "move"
    description: str                           # Human-readable: "Swapped bb_bench_press for bb_incline_bench in Week 2 Upper A"
    volume_before: dict[str, float]            # Weekly volume per muscle BEFORE mutation
    volume_after: dict[str, float]             # Weekly volume per muscle AFTER mutation
    constraint_violations: list[str]           # Any new violations introduced (should be empty on success)
    rollback_applied: bool = False             # True if mutation was attempted but rolled back

class MutationRequest(BaseModel):
    """A single requested change to the program."""
    mutation_type: str                         # "swap_exercise", "add_exercise", "remove_exercise", 
                                               # "add_sets", "remove_sets", "reorder_session", 
                                               # "move_exercise", "replace_prescription"
    week_number: int
    session_day: int                           # Which day in the week (1-indexed)
    exercise_id: Optional[str] = None          # Target exercise (for swap, remove, add_sets, remove_sets)
    new_exercise_id: Optional[str] = None      # Replacement exercise (for swap, add)
    new_exercise_sets: Optional[int] = None    # Sets for the new/added exercise
    sets_delta: Optional[int] = None           # +/- sets (for add_sets, remove_sets)
    new_order: Optional[list[str]] = None      # New exercise ID order (for reorder)
    target_session_day: Optional[int] = None   # Destination session (for move_exercise)
    source: str = "unknown"                    # "validator_auto_fix", "llm_week_review", "llm_full_review"
    reason: str = ""                           # Why this mutation is being requested
```

### Mutator Functions

```python
class ProgramMutator:
    """
    Safely mutates a BuiltProgram while maintaining volume and constraint integrity.
    Used by Layer 4 (LLM review application) and Layer 5 (auto-fix engine).
    """
    
    def __init__(self, program: BuiltProgram, profile: AthleteProfile, 
                 strategy: ProgramStrategy, volume_allocation: VolumeAllocation,
                 exercise_library: dict[str, Exercise]):
        self.program = program
        self.profile = profile
        self.strategy = strategy
        self.volume = volume_allocation
        self.library = exercise_library  # {exercise_id: Exercise}
    
    # ─────────────────────────────────────────────
    # PRIMITIVE MUTATIONS
    # ─────────────────────────────────────────────
    
    def swap_exercise(self, week_num: int, session_day: int, 
                      old_exercise_id: str, new_exercise_id: str,
                      new_sets: int = None, source: str = "", reason: str = "") -> MutationResult:
        """
        Replace one exercise with another in a specific session.
        
        Used by:
        - Layer 4 LLM review: "swap bb_bench_press for bb_incline_bench for angle variety"
        - Layer 5 auto-fix SES_002: "swap a 3rd axial exercise for a non-axial alternative"
        - Layer 5 auto-fix VAR_001: "swap one exercise for rotation group alternative to avoid duplicate sessions"
        
        Logic:
        1. Find the old exercise in the specified session
        2. Calculate volume that will be REMOVED (old exercise sets × volume_credits)
        3. Calculate volume that will be ADDED (new exercise sets × volume_credits)
        4. If new_sets is None, use the same set count as the old exercise
        5. Simulate the swap: compute new weekly volumes
        6. Check constraints:
           - No muscle below MEV? (for non-deload weeks)
           - No muscle above MRV?
           - New exercise available at user's equipment tier?
           - New exercise not in exercises_to_avoid?
           - New exercise difficulty appropriate for training level?
        7. If constraints pass: apply swap, recalculate volumes, return success
        8. If constraints fail: try adjusting sets (±1-2) to fix. If still fails: reject, return failure
        """
        pass  # IMPLEMENT FULLY
    
    def add_exercise(self, week_num: int, session_day: int,
                     exercise_id: str, sets: int,
                     source: str = "", reason: str = "") -> MutationResult:
        """
        Add a new exercise to a session.
        
        Used by:
        - Layer 5 auto-fix VOL_001: add exercise when muscle is below MEV
        - Layer 5 auto-fix PAT_001: add compound when movement pattern is missing
        - Layer 5 auto-fix GOAL_STR_001: add main lift to strength session
        - Layer 5 auto-fix GOAL_POW_002: add power movement to power session
        
        Logic:
        1. Verify exercise is available (tier, not avoided, not already in session)
        2. Verify sets >= exercise.min_sets_per_session
        3. Calculate volume that will be added
        4. Check: would any muscle exceed MRV?
        5. Check: would session duration exceed time cap? 
           If yes: try removing the lowest-priority existing isolation first, then add
        6. Apply: add exercise, prescribe sets/reps using prescription engine, 
           insert at correct position (by exercise_type ordering)
        7. Recalculate session and week volumes
        """
        pass  # IMPLEMENT FULLY
    
    def remove_exercise(self, week_num: int, session_day: int,
                        exercise_id: str,
                        source: str = "", reason: str = "") -> MutationResult:
        """
        Remove an exercise from a session entirely.
        
        Used by:
        - Layer 5 auto-fix SES_003: remove lowest-priority exercise when session exceeds time cap
        - Layer 5 auto-fix SES_005: remove exercise that's on the wrong day type
        
        Logic:
        1. Find the exercise in the session
        2. Calculate volume that will be lost
        3. Check: would any muscle fall below MEV after removal?
           If yes: can we add sets to another existing exercise that targets the same muscle?
           If still below MEV: reject removal (or flag that a replacement is needed)
        4. Apply: remove exercise, recalculate volumes
        """
        pass  # IMPLEMENT FULLY
    
    def add_sets(self, week_num: int, session_day: int,
                 exercise_id: str, sets_to_add: int,
                 source: str = "", reason: str = "") -> MutationResult:
        """
        Add sets to an existing exercise in a session.
        
        Used by:
        - Layer 5 auto-fix VOL_001: when a muscle is slightly below MEV, add 1-2 sets 
          to an existing exercise rather than adding a whole new exercise
        - Layer 4 Phase 3 (post-selection patching): fill remaining volume gaps
        
        Logic:
        1. Find the exercise
        2. Check: would new total exceed exercise.max_sets_per_session? If yes: cap at max
        3. Check: would any muscle exceed MRV?
        4. Check: would session duration exceed time cap?
        5. Apply: add sets with same prescription as existing sets, recalculate volumes
        """
        pass  # IMPLEMENT FULLY
    
    def remove_sets(self, week_num: int, session_day: int,
                    exercise_id: str, sets_to_remove: int,
                    source: str = "", reason: str = "") -> MutationResult:
        """
        Remove sets from an existing exercise.
        
        Used by:
        - Layer 5 auto-fix VOL_002: muscle above MRV, reduce sets on lowest-SFR exercise
        - Layer 5 auto-fix VOL_003: exercise exceeds max_sets_per_session cap
        - Layer 5 auto-fix SES_003: session too long, reduce sets before removing exercises
        
        Logic:
        1. Find the exercise
        2. Check: would remaining sets be < exercise.min_sets_per_session? 
           If yes: remove the whole exercise instead (call remove_exercise)
        3. Check: would any muscle fall below MEV?
        4. Apply: remove last N sets, recalculate volumes
        """
        pass  # IMPLEMENT FULLY
    
    def reorder_session(self, week_num: int, session_day: int,
                        new_exercise_order: list[str],
                        source: str = "", reason: str = "") -> MutationResult:
        """
        Reorder exercises within a session.
        
        Used by:
        - Layer 5 auto-fix SES_001: enforce power → heavy compound → light compound → isolation
        - Layer 5 auto-fix GOAL_POW_001: move power exercises to first position
        - Layer 4 LLM review: "move face pulls before curls for better session flow"
        
        Logic:
        1. Verify all exercise IDs in new_order match existing exercises
        2. Reorder exercises
        3. Update order_in_session field for each exercise
        4. No volume changes — this is always safe
        """
        pass  # IMPLEMENT FULLY
    
    def move_exercise(self, week_num: int, from_session_day: int, to_session_day: int,
                      exercise_id: str,
                      source: str = "", reason: str = "") -> MutationResult:
        """
        Move an exercise from one session to another within the same week.
        
        Used by:
        - Layer 5 auto-fix SES_005: lateral raises on leg day → move to upper body day
        - Layer 5 auto-fix VOL_004: muscle has >10 sets in one session → redistribute
        
        Logic:
        1. Remove exercise from source session (calculate volume loss)
        2. Check: does destination session target this muscle group? 
           If not: this is probably wrong, reject
        3. Check: would destination session exceed time cap?
        4. Add exercise to destination session at correct position
        5. Recalculate both sessions' and the week's volumes
        """
        pass  # IMPLEMENT FULLY
    
    def replace_prescription(self, week_num: int, session_day: int,
                             exercise_id: str, new_sets: list[PrescribedSet],
                             source: str = "", reason: str = "") -> MutationResult:
        """
        Replace the set/rep/rest prescription for an exercise without changing the exercise itself.
        
        Used by:
        - Layer 5 auto-fix GOAL_HYP_001: isolation has <8 reps in hypertrophy → represcribe with 10-12
        - Layer 5 auto-fix PER_002: deload volume too high → represcribe with fewer sets
        
        Logic:
        1. Find the exercise
        2. Replace its sets with new_sets
        3. Recalculate volume (set count may have changed)
        4. Validate constraints
        """
        pass  # IMPLEMENT FULLY

    # ─────────────────────────────────────────────
    # COMPOUND MUTATIONS (combine primitives)
    # ─────────────────────────────────────────────
    
    def redistribute_muscle_volume(self, week_num: int, muscle: str, 
                                    from_session_day: int, to_session_day: int,
                                    sets_to_move: int,
                                    source: str = "", reason: str = "") -> MutationResult:
        """
        Move volume for a specific muscle from one session to another.
        Either by moving an exercise or by adjusting set counts.
        
        Used by:
        - Layer 5 auto-fix VOL_004: muscle has >10 sets in one session
        
        Logic:
        1. Find exercises in source session that target this muscle
        2. Pick the one with the most sets (or lowest priority)
        3. If moving all its sets: move_exercise to destination
        4. If moving partial sets: remove_sets from source, add_sets to an exercise 
           in destination that targets the same muscle (or add_exercise if none exists)
        """
        pass  # IMPLEMENT FULLY
    
    def fix_volume_deficit(self, week_num: int, muscle: str, deficit: float,
                           source: str = "", reason: str = "") -> MutationResult:
        """
        Fix a muscle group that's below MEV for a given week.
        This is the most important compound mutation — it's what prevents V4's 
        "back getting 3 sets" failure.
        
        Used by:
        - Layer 5 auto-fix VOL_001
        
        Strategy (in order of preference):
        1. ADD SETS to an existing exercise in the week that targets this muscle
           - Find all exercises across all sessions this week that have this muscle as PRIMARY
           - Pick the one with highest SFR that isn't already at max_sets_per_session
           - Add enough sets to fill the deficit
           - If this exceeds max_sets_per_session, add what we can and continue to step 2
        
        2. ADD A NEW EXERCISE in the session with the most room (fewest total sets)
           - Find the highest-SFR exercise for this muscle from available_exercises
           - That isn't already used this week
           - Add it with enough sets to fill remaining deficit (min: min_sets_per_session)
           - Prescribe it using the prescription engine with the week's profile
        
        3. If the session is at time cap: SWAP a low-priority exercise
           - Find the exercise in the week with the lowest priority (lowest SFR, isolation, 
             non-emphasis muscle) that we can sacrifice
           - Swap it for the muscle-targeting exercise
        
        Return: MutationResult with details of what was done
        """
        pass  # IMPLEMENT FULLY
    
    def fix_volume_excess(self, week_num: int, muscle: str, excess: float,
                          source: str = "", reason: str = "") -> MutationResult:
        """
        Fix a muscle group that's above MRV for a given week.
        
        Used by:
        - Layer 5 auto-fix VOL_002
        
        Strategy:
        1. Find exercises targeting this muscle, sorted by SFR ascending (remove lowest quality first)
        2. Remove sets from the lowest-SFR exercise until excess is eliminated
        3. If that drops below min_sets_per_session, remove the exercise entirely
        4. Recalculate and verify
        """
        pass  # IMPLEMENT FULLY
    
    def fix_missing_movement_pattern(self, week_num: int, missing_pattern: str,
                                      source: str = "", reason: str = "") -> MutationResult:
        """
        Add an exercise to cover a missing movement pattern in a week.
        
        Used by:
        - Layer 5 auto-fix PAT_001: missing horizontal_pull, vertical_pull, etc.
        
        Strategy:
        1. Find the session in the week that should have this pattern 
           (based on split template required_patterns)
        2. Find the best compound exercise for this pattern from available_exercises
        3. If session is at time cap: find the lowest-priority exercise that can be swapped
           (prefer swapping an isolation for the same muscle group the compound would hit)
        4. Add/swap the exercise
        5. Prescribe using prescription engine
        """
        pass  # IMPLEMENT FULLY
    
    def fix_push_pull_imbalance(self, week_num: int, push_volume: float, pull_volume: float,
                                 source: str = "", reason: str = "") -> MutationResult:
        """
        Fix push:pull ratio being outside 0.7-1.3 range.
        
        Used by:
        - Layer 5 auto-fix PAT_002
        
        Strategy:
        If push-heavy (ratio > 1.3):
            - Add pulling volume: add sets to existing pull exercises or add a new pull exercise
            - Or reduce pushing volume: remove sets from lowest-SFR push isolation
        If pull-heavy (ratio < 0.7):
            - Add pushing volume or reduce pulling volume (same logic, reversed)
        """
        pass  # IMPLEMENT FULLY
    
    # ─────────────────────────────────────────────
    # VOLUME ACCOUNTING (called after every mutation)
    # ─────────────────────────────────────────────
    
    def recalculate_session_volume(self, week_num: int, session_day: int) -> dict[str, float]:
        """
        Recalculate the actual volume credit for each muscle group in a session.
        
        For each exercise in the session:
            For each muscle_activation in the exercise:
                volume_credit[muscle] += exercise.total_sets × activation.volume_credit
        
        Update the session's volume_check field.
        Return the new volume dict.
        """
        pass  # IMPLEMENT FULLY
    
    def recalculate_week_volume(self, week_num: int) -> dict[str, float]:
        """
        Sum all session volumes for the week.
        Update the week's weekly_volume_actual and volume_adherence fields.
        Return the new weekly volume dict.
        """
        pass  # IMPLEMENT FULLY
    
    def check_constraints_after_mutation(self, week_num: int) -> list[str]:
        """
        After a mutation, verify all hard constraints still hold for the affected week.
        Returns a list of violation descriptions (empty = all good).
        
        Checks:
        - Every muscle >= MEV (non-deload) or skip (deload)
        - Every muscle <= MRV
        - No exercise > max_sets_per_session
        - No muscle > 10 direct sets per session
        - Session durations within cap
        - Movement pattern requirements still met
        - Exercise ordering still correct
        """
        pass  # IMPLEMENT FULLY
    
    # ─────────────────────────────────────────────
    # SMART EXERCISE FINDER (used by compound mutations)
    # ─────────────────────────────────────────────
    
    def find_best_exercise_for_muscle(self, muscle: str, week_num: int, session_day: int,
                                       exclude_ids: list[str] = []) -> Optional[Exercise]:
        """
        Find the best available exercise that targets a specific muscle group.
        Used when we need to ADD an exercise to fix a deficit.
        
        Scoring:
        - Must have muscle as PRIMARY
        - Must be available at user's equipment tier
        - Must not be in exclude_ids (already in session or week)
        - Must not be in exercises_to_avoid
        - Prefer highest SFR
        - Prefer exercises not used recently (variety)
        - Prefer exercises appropriate for the session type (isolations for filling gaps, 
          compounds for pattern coverage)
        """
        pass  # IMPLEMENT FULLY
    
    def find_lowest_priority_exercise(self, week_num: int, session_day: int,
                                       protect_muscles: list[str] = []) -> Optional[str]:
        """
        Find the exercise in a session that is safest to remove or swap.
        Used when we need to make room for a more important exercise.
        
        Priority (lowest = most removable):
        1. Isolation exercises for non-emphasis, non-weak-point muscles
        2. Isolation exercises for non-emphasis muscles
        3. Light compound exercises (only if not the sole exercise for a movement pattern)
        4. NEVER remove: heavy compounds, power exercises, or the only exercise for a required pattern
        
        protect_muscles: muscles that are at or near MEV — don't remove exercises targeting them
        """
        pass  # IMPLEMENT FULLY
    
    # ─────────────────────────────────────────────
    # BATCH MUTATION (for applying multiple LLM suggestions)
    # ─────────────────────────────────────────────
    
    def apply_mutation_batch(self, mutations: list[MutationRequest]) -> list[MutationResult]:
        """
        Apply a batch of mutations in sequence, rolling back any that cause violations.
        
        Used by:
        - Layer 4: applying all LLM week review suggestions for a week
        - Layer 5: applying all LLM full-program review suggestions
        
        Logic:
        1. Sort mutations by priority: critical fixes first, then major, then suggestions
        2. For each mutation:
            a. Snapshot current state
            b. Apply mutation
            c. Check constraints
            d. If constraints violated: rollback to snapshot, mark as failed
            e. If constraints pass: keep, move to next
        3. Return list of results (which succeeded, which failed, why)
        """
        results = []
        for mutation in sorted(mutations, key=lambda m: mutation_priority(m)):
            # Snapshot
            snapshot = self._snapshot_week(mutation.week_number)
            
            # Apply
            result = self._apply_single_mutation(mutation)
            
            if not result.success:
                results.append(result)
                continue
            
            # Check constraints
            violations = self.check_constraints_after_mutation(mutation.week_number)
            
            if violations:
                # Rollback
                self._restore_snapshot(mutation.week_number, snapshot)
                result.success = False
                result.rollback_applied = True
                result.constraint_violations = violations
                logger.info(f"  ↩ Rolled back mutation: {result.description} — would cause: {violations}")
            else:
                logger.info(f"  ✓ Applied mutation: {result.description}")
            
            results.append(result)
        
        return results
    
    def _snapshot_week(self, week_num: int) -> dict:
        """Deep copy of a week's state for rollback."""
        week = self.program.weeks[week_num - 1]
        return week.model_copy(deep=True)
    
    def _restore_snapshot(self, week_num: int, snapshot) -> None:
        """Restore a week from snapshot."""
        self.program.weeks[week_num - 1] = snapshot
```

### How Layers Use the Mutator

#### Layer 4 — Applying LLM Week Review Suggestions

```python
async def apply_week_review(program, week, llm_review, profile, strategy, volume, exercise_library):
    """
    Take LLM week review output and convert to MutationRequests, then apply via mutator.
    """
    mutator = ProgramMutator(program, profile, strategy, volume, exercise_library)
    mutations = []
    
    for issue in llm_review.get("issues", []):
        if issue["confidence"] == "low":
            continue  # Skip low-confidence suggestions
        
        mutation = parse_llm_suggestion_to_mutation(issue, week.week_number)
        if mutation:
            mutations.append(mutation)
    
    results = mutator.apply_mutation_batch(mutations)
    
    applied = [r for r in results if r.success]
    rejected = [r for r in results if not r.success]
    
    if rejected:
        logger.info(f"  Week {week.week_number}: Applied {len(applied)}/{len(mutations)} LLM suggestions. "
                     f"Rejected {len(rejected)} (would violate constraints).")
    
    return program


def parse_llm_suggestion_to_mutation(issue: dict, week_number: int) -> Optional[MutationRequest]:
    """
    Parse an LLM suggestion into a concrete MutationRequest.
    
    The LLM returns suggestions like:
    - "swap bb_bench_press for bb_incline_bench for angle variety"
    - "move db_lateral_raise from day 2 to day 1"  
    - "reorder day 3: put pull-ups before rows for better energy management"
    
    This function pattern-matches the suggestion text and extracts:
    - mutation_type
    - exercise IDs involved
    - session days involved
    
    If the suggestion is too vague to parse into a concrete mutation, return None.
    
    IMPORTANT: The LLM should be prompted to return structured suggestions (see prompts.py).
    The week review prompt should ask for:
    {
        "suggestion_type": "swap" | "reorder" | "move" | "add" | "remove",
        "exercise_id": string | null,
        "replacement_exercise_id": string | null,
        "session_day": int,
        "target_session_day": int | null,  // for moves
        "reason": string
    }
    
    This makes parsing trivial — just map the fields to a MutationRequest.
    """
    pass  # IMPLEMENT FULLY
```

#### Layer 5 — Deterministic Auto-Fix Implementation

```python
def auto_fix_issue(program, issue, profile, strategy, volume, exercise_library):
    """
    Apply the appropriate auto-fix for a validation issue.
    Each validation rule ID maps to a specific fix strategy using the mutator.
    """
    mutator = ProgramMutator(program, profile, strategy, volume, exercise_library)
    
    # ─── VOL_001: Muscle below MEV ───
    if issue["id"] == "VOL_001":
        # issue["details"] contains: {"week": 2, "muscle": "lats", "actual": 5.0, "mev": 8}
        week_num = issue["details"]["week"]
        muscle = issue["details"]["muscle"]
        deficit = issue["details"]["mev"] - issue["details"]["actual"]
        
        return mutator.fix_volume_deficit(
            week_num=week_num, muscle=muscle, deficit=deficit,
            source="validator_auto_fix", reason=f"VOL_001: {muscle} is {deficit:.1f} sets below MEV"
        )
    
    # ─── VOL_002: Muscle above MRV ───
    elif issue["id"] == "VOL_002":
        week_num = issue["details"]["week"]
        muscle = issue["details"]["muscle"]
        excess = issue["details"]["actual"] - issue["details"]["mrv"]
        
        return mutator.fix_volume_excess(
            week_num=week_num, muscle=muscle, excess=excess,
            source="validator_auto_fix", reason=f"VOL_002: {muscle} is {excess:.1f} sets above MRV"
        )
    
    # ─── VOL_003: Exercise exceeds max_sets_per_session ───
    elif issue["id"] == "VOL_003":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        exercise_id = issue["details"]["exercise_id"]
        current_sets = issue["details"]["current_sets"]
        max_sets = issue["details"]["max_sets"]
        excess_sets = current_sets - max_sets
        
        # Strategy: reduce sets on this exercise AND add a new exercise for the same muscle
        result1 = mutator.remove_sets(
            week_num=week_num, session_day=session_day, exercise_id=exercise_id,
            sets_to_remove=excess_sets,
            source="validator_auto_fix", reason=f"VOL_003: {exercise_id} has {current_sets} sets (max {max_sets})"
        )
        
        # Find primary muscles of the excess exercise and add a new exercise for them
        exercise = exercise_library[exercise_id]
        primary_muscles = [ma.muscle.value for ma in exercise.muscle_activations if ma.role == "primary"]
        if primary_muscles:
            new_ex = mutator.find_best_exercise_for_muscle(
                primary_muscles[0], week_num, session_day, 
                exclude_ids=[exercise_id]
            )
            if new_ex:
                result2 = mutator.add_exercise(
                    week_num=week_num, session_day=session_day,
                    exercise_id=new_ex.id, sets=excess_sets,
                    source="validator_auto_fix", reason=f"VOL_003: redistributing {excess_sets} sets to {new_ex.name}"
                )
        
        return result1
    
    # ─── VOL_004: Muscle >10 direct sets in one session ───
    elif issue["id"] == "VOL_004":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        muscle = issue["details"]["muscle"]
        excess = issue["details"]["actual"] - 10
        
        # Find another session in the week that targets this muscle
        week = program.weeks[week_num - 1]
        other_sessions = [s for s in week.workouts if s.day_number != session_day 
                          and muscle in [mg.value for mg in strategy.split.sessions_per_week[s.day_number - 1].muscle_groups]]
        
        if other_sessions:
            target_session = other_sessions[0].day_number
            return mutator.redistribute_muscle_volume(
                week_num=week_num, muscle=muscle,
                from_session_day=session_day, to_session_day=target_session,
                sets_to_move=round(excess),
                source="validator_auto_fix", reason=f"VOL_004: {muscle} has >10 sets in session {session_day}"
            )
        else:
            # No other session targets this muscle — just reduce
            return mutator.fix_volume_excess(week_num, muscle, excess, 
                                             source="validator_auto_fix", reason="VOL_004: no redistribution target")
    
    # ─── PAT_001: Missing movement pattern ───
    elif issue["id"] == "PAT_001":
        week_num = issue["details"]["week"]
        missing_pattern = issue["details"]["missing_pattern"]
        
        return mutator.fix_missing_movement_pattern(
            week_num=week_num, missing_pattern=missing_pattern,
            source="validator_auto_fix", reason=f"PAT_001: {missing_pattern} missing in week {week_num}"
        )
    
    # ─── PAT_002: Push:Pull imbalance ───
    elif issue["id"] == "PAT_002":
        week_num = issue["details"]["week"]
        push_vol = issue["details"]["push_volume"]
        pull_vol = issue["details"]["pull_volume"]
        
        return mutator.fix_push_pull_imbalance(
            week_num=week_num, push_volume=push_vol, pull_volume=pull_vol,
            source="validator_auto_fix", reason=f"PAT_002: push:pull ratio {push_vol/pull_vol:.2f}"
        )
    
    # ─── PAT_003: Upper session missing push or pull ───
    elif issue["id"] == "PAT_003":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        missing = issue["details"]["missing"]  # "push" or "pull"
        
        if missing == "pull":
            pattern = "horizontal_pull"  # Default to adding a row
        else:
            pattern = "horizontal_push"  # Default to adding a press
        
        return mutator.fix_missing_movement_pattern(
            week_num=week_num, missing_pattern=pattern,
            source="validator_auto_fix", reason=f"PAT_003: session {session_day} has no {missing}"
        )
    
    # ─── SES_001: Wrong exercise ordering ───
    elif issue["id"] == "SES_001":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        correct_order = issue["details"]["correct_order"]  # list of exercise_ids in proper order
        
        return mutator.reorder_session(
            week_num=week_num, session_day=session_day, new_exercise_order=correct_order,
            source="validator_auto_fix", reason="SES_001: incorrect exercise ordering"
        )
    
    # ─── SES_002: >2 axial-loading exercises ───
    elif issue["id"] == "SES_002":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        axial_exercises = issue["details"]["axial_exercise_ids"]
        
        # Keep the 2 with highest SFR, swap the rest
        sorted_by_sfr = sorted(axial_exercises, key=lambda eid: exercise_library[eid].sfr_rating, reverse=True)
        for exercise_to_swap in sorted_by_sfr[2:]:  # Swap the 3rd, 4th, etc.
            # Find a non-axial alternative for the same muscle
            exercise = exercise_library[exercise_to_swap]
            primary_muscles = [ma.muscle.value for ma in exercise.muscle_activations if ma.role == "primary"]
            alternatives = [ex for ex in exercise_library.values() 
                           if not ex.is_axial_loading 
                           and any(ma.muscle.value in primary_muscles and ma.role == "primary" for ma in ex.muscle_activations)
                           and ex.equipment_tier.value <= profile.equipment_tier.value]
            
            if alternatives:
                best_alt = max(alternatives, key=lambda x: x.sfr_rating)
                mutator.swap_exercise(week_num, session_day, exercise_to_swap, best_alt.id,
                                      source="validator_auto_fix", reason="SES_002: too many axial exercises")
    
    # ─── SES_003: Session too long ───
    elif issue["id"] == "SES_003":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        
        # Find lowest-priority exercise and remove or reduce sets
        lowest = mutator.find_lowest_priority_exercise(week_num, session_day)
        if lowest:
            return mutator.remove_exercise(
                week_num=week_num, session_day=session_day, exercise_id=lowest,
                source="validator_auto_fix", reason="SES_003: session exceeds time cap"
            )
    
    # ─── SES_005: Exercise on wrong day type ───
    elif issue["id"] == "SES_005":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        exercise_id = issue["details"]["exercise_id"]
        
        # Find the correct session for this exercise
        exercise = exercise_library[exercise_id]
        primary_muscles = [ma.muscle.value for ma in exercise.muscle_activations if ma.role == "primary"]
        
        # Find a session that targets this muscle
        week = program.weeks[week_num - 1]
        for workout in week.workouts:
            if workout.day_number != session_day:
                session_muscles = [mg.value for mg in strategy.split.sessions_per_week[workout.day_number - 1].muscle_groups]
                if any(m in session_muscles for m in primary_muscles):
                    return mutator.move_exercise(
                        week_num=week_num, from_session_day=session_day, 
                        to_session_day=workout.day_number, exercise_id=exercise_id,
                        source="validator_auto_fix", reason=f"SES_005: {exercise_id} on wrong day"
                    )
        
        # No suitable session found — just remove it
        return mutator.remove_exercise(
            week_num=week_num, session_day=session_day, exercise_id=exercise_id,
            source="validator_auto_fix", reason="SES_005: no suitable session, removing"
        )
    
    # ─── VAR_001: Duplicate sessions ───
    elif issue["id"] == "VAR_001":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["duplicate_session_day"]  # The second (duplicate) session
        exercise_to_swap = issue["details"]["exercise_to_differentiate"]  # An exercise to swap for variety
        
        # Find a rotation group alternative
        exercise = exercise_library[exercise_to_swap]
        alternatives = [ex for ex in exercise_library.values()
                       if ex.rotation_group == exercise.rotation_group 
                       and ex.id != exercise_to_swap
                       and ex.equipment_tier.value <= profile.equipment_tier.value]
        
        if alternatives:
            alt = alternatives[0]  # Pick first alternative in rotation group
            return mutator.swap_exercise(
                week_num=week_num, session_day=session_day,
                old_exercise_id=exercise_to_swap, new_exercise_id=alt.id,
                source="validator_auto_fix", reason="VAR_001: duplicate session differentiation"
            )
    
    # ─── GOAL_HYP_001: Isolation reps too low ───
    elif issue["id"] == "GOAL_HYP_001":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        exercise_id = issue["details"]["exercise_id"]
        
        # Represcribe with proper hypertrophy isolation rep range
        week_profile = strategy.week_profiles[week_num - 1]
        exercise = exercise_library[exercise_id]
        existing_ex = find_exercise_in_session(program, week_num, session_day, exercise_id)
        
        new_sets = prescribe_exercise(exercise, existing_ex.total_sets, week_profile, "hypertrophy")
        # This will give 10-15 reps since it's an isolation in hypertrophy
        
        return mutator.replace_prescription(
            week_num=week_num, session_day=session_day, exercise_id=exercise_id,
            new_sets=new_sets,
            source="validator_auto_fix", reason="GOAL_HYP_001: isolation reps below 8"
        )
    
    # ─── GOAL_STR_001: Missing main lift ───
    elif issue["id"] == "GOAL_STR_001":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        
        # Add a main compound (squat, bench, deadlift, or OHP)
        main_lifts = [ex for ex in exercise_library.values()
                     if ex.exercise_type.value == "heavy_compound"
                     and ex.equipment_tier.value <= profile.equipment_tier.value
                     and ex.id not in [e.exercise_id for e in program.weeks[week_num-1].workouts[session_day-1].exercises]]
        
        if main_lifts:
            best = max(main_lifts, key=lambda x: x.sfr_rating)
            return mutator.add_exercise(
                week_num=week_num, session_day=session_day,
                exercise_id=best.id, sets=4,
                source="validator_auto_fix", reason="GOAL_STR_001: no main lift in session"
            )
    
    # ─── GOAL_POW_001: Power exercises not first ───
    elif issue["id"] == "GOAL_POW_001":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        correct_order = issue["details"]["correct_order"]
        
        return mutator.reorder_session(
            week_num=week_num, session_day=session_day, new_exercise_order=correct_order,
            source="validator_auto_fix", reason="GOAL_POW_001: power movements must be first"
        )
    
    # ─── GOAL_POW_002: No power movement in session ───
    elif issue["id"] == "GOAL_POW_002":
        week_num = issue["details"]["week"]
        session_day = issue["details"]["session_day"]
        
        power_exercises = [ex for ex in exercise_library.values()
                          if ex.exercise_type.value in ["power", "plyometric"]
                          and ex.equipment_tier.value <= profile.equipment_tier.value]
        
        if power_exercises:
            best = max(power_exercises, key=lambda x: x.sfr_rating)
            return mutator.add_exercise(
                week_num=week_num, session_day=session_day,
                exercise_id=best.id, sets=3,
                source="validator_auto_fix", reason="GOAL_POW_002: no power movement in session"
            )
    
    # ─── PER_001: Volume not progressing ───
    elif issue["id"] == "PER_001":
        week_num = issue["details"]["week"]
        prev_volume = issue["details"]["previous_week_volume"]
        current_volume = issue["details"]["current_week_volume"]
        
        # Need to add total volume to this week
        deficit = prev_volume - current_volume + 2  # Need to exceed previous, not just match
        
        # Add sets to the highest-SFR exercises across the week
        week = program.weeks[week_num - 1]
        for workout in week.workouts:
            if deficit <= 0:
                break
            for ex in workout.exercises:
                if ex.total_sets < exercise_library[ex.exercise_id].max_sets_per_session:
                    mutator.add_sets(
                        week_num=week_num, session_day=workout.day_number,
                        exercise_id=ex.exercise_id, sets_to_add=1,
                        source="validator_auto_fix", reason="PER_001: volume not progressing"
                    )
                    deficit -= 1
                    if deficit <= 0:
                        break
    
    # ─── PER_002: Deload volume too high ───
    elif issue["id"] == "PER_002":
        week_num = issue["details"]["week"]
        target_max = issue["details"]["target_max_volume"]
        current = issue["details"]["current_volume"]
        excess = current - target_max
        
        # Remove sets across the week evenly
        week = program.weeks[week_num - 1]
        while excess > 0:
            # Find exercise with most sets that can be reduced
            all_exercises = [(w.day_number, ex) for w in week.workouts for ex in w.exercises]
            all_exercises.sort(key=lambda x: -x[1].total_sets)
            
            for session_day, ex in all_exercises:
                if ex.total_sets > exercise_library[ex.exercise_id].min_sets_per_session:
                    mutator.remove_sets(
                        week_num=week_num, session_day=session_day,
                        exercise_id=ex.exercise_id, sets_to_remove=1,
                        source="validator_auto_fix", reason="PER_002: deload volume too high"
                    )
                    excess -= 1
                    break
            else:
                break  # No more sets can be removed
    
    return MutationResult(success=False, mutation_type="unknown", 
                          description=f"No auto-fix implemented for {issue['id']}")
```

#### Layer 5 Full Auto-Fix Loop

```python
def validate_and_fix(program, profile, strategy, volume, exercise_library):
    """
    Run validation → auto-fix → re-validate loop.
    Returns the fixed program and any remaining issues.
    """
    max_iterations = 3
    all_results = []
    
    for iteration in range(max_iterations):
        issues = run_all_validations(program, profile, strategy, volume, exercise_library)
        
        critical = [i for i in issues if i["severity"] == "critical"]
        major = [i for i in issues if i["severity"] == "major"]
        warnings = [i for i in issues if i["severity"] == "warning"]
        
        logger.info(f"  Validation pass {iteration + 1}: "
                     f"{len(critical)} critical, {len(major)} major, {len(warnings)} warnings")
        
        if not critical and not major:
            logger.info(f"  ✓ All critical/major issues resolved after {iteration + 1} pass(es)")
            break
        
        # Fix in priority order: critical first, then major
        for issue in critical + major:
            result = auto_fix_issue(program, issue, profile, strategy, volume, exercise_library)
            all_results.append(result)
            
            if result.success:
                logger.info(f"    ✓ Fixed {issue['id']}: {result.description}")
            else:
                logger.warning(f"    ✗ Could not fix {issue['id']}: {result.description}")
                if result.constraint_violations:
                    logger.warning(f"      Violations: {result.constraint_violations}")
    
    # Final validation pass
    final_issues = run_all_validations(program, profile, strategy, volume, exercise_library)
    remaining_critical = [i for i in final_issues if i["severity"] == "critical"]
    
    if remaining_critical:
        logger.error(f"  ❌ {len(remaining_critical)} CRITICAL issues remain after {max_iterations} fix iterations!")
        for issue in remaining_critical:
            logger.error(f"    - {issue['id']}: {issue['description']}")
    
    return program, final_issues, all_results
```

### Mutation Logging

Every mutation is logged with full context for debugging:

```python
class MutationLog(BaseModel):
    """Stored with the program for debugging and auditing."""
    mutations: list[MutationResult]
    total_attempted: int
    total_applied: int
    total_rejected: int
    total_rolled_back: int
    fix_iterations: int
    
    @property
    def summary(self) -> str:
        return (f"{self.total_applied}/{self.total_attempted} mutations applied, "
                f"{self.total_rejected} rejected, {self.total_rolled_back} rolled back "
                f"over {self.fix_iterations} iteration(s)")
```

This gets serialized and stored alongside the program so you can debug why a specific program looks the way it does — every change has a paper trail.

---

## UPDATED FILE STRUCTURE

```
program_generator_v5/
├── __init__.py
├── main.py                    # Entry point: generate_program_v5()
├── schemas.py                 # All Pydantic models (including MutationResult, MutationRequest)
├── exercise_library.py        # Complete exercise database (135+ exercises)
├── split_templates.py         # Split template definitions
├── volume_tables.py           # MEV/MAV/MRV tables per training level
├── sport_mappings.py          # Sport → goal + adjustments mapping table
├── layer1_profile_builder.py  # Profile construction (deterministic + optional LLM)
├── layer2_strategy_engine.py  # Split + periodization selection (rules + optional LLM)
├── layer3_volume_engine.py    # Volume calculation + distribution (deterministic)
├── layer4_program_builder.py  # Exercise selection + prescription + LLM week review
├── layer5_validator.py        # Validation rules + auto-fix dispatch + LLM full-program review
├── layer6_serializer.py       # V5 → V3 format conversion
├── mutator.py                 # ← NEW: Program Mutator — safe program modification engine
├── scoring.py                 # Exercise scoring function
├── prompts.py                 # All LLM prompts in one place
└── utils.py                   # Time estimation, superset builder, helpers
```

---

## NOW BUILD IT.

Implementation order:
1. `schemas.py` — All Pydantic models (including mutation schemas)
2. `exercise_library.py` — 135+ exercises with accurate metadata
3. `volume_tables.py` — MEV/MAV/MRV tables for beginner/intermediate/advanced
4. `split_templates.py` — All split definitions
5. `sport_mappings.py` — Sport → goal + adjustments
6. `prompts.py` — All LLM prompts
7. `scoring.py` — Exercise scoring function
8. `utils.py` — Time estimation, superset builder, helpers
9. `mutator.py` — Program Mutator with ALL primitive + compound mutations fully implemented
10. `layer3_volume_engine.py` — Volume calculation and distribution
11. `layer4_program_builder.py` — Exercise selection + prescription + LLM week review
12. `layer2_strategy_engine.py` — Rules engine for split/periodization + LLM fallback
13. `layer1_profile_builder.py` — Profile construction
14. `layer5_validator.py` — Validation rules + auto-fix dispatch (using mutator) + LLM full review
15. `layer6_serializer.py` — V3 adapter
16. `main.py` — Async orchestrator with parallel LLM calls
17. Test with all 7 test cases

Generate the COMPLETE implementation. Do not stub functions. Do not leave TODOs. Every function should be fully implemented and working.
