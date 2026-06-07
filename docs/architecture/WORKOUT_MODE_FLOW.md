# Workout Mode Data Flow

## Visual Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          PROGRAM CREATION                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                     User completes questionnaire
                                    │
                                    ▼
                   ┌─────────────────────────────┐
                   │  LLM Generates Program      │
                   │  (4 weeks, 3x/week)        │
                   └─────────────────────────────┘
                                    │
                                    ▼
                   ┌─────────────────────────────┐
                   │  Save to Database           │
                   │  - UserGeneratedProgram     │
                   │  - Workouts (12)            │
                   │  - WorkoutExercises         │
                   │  - Sets                     │
                   └─────────────────────────────┘
                                    │
                    ✨ NEW FEATURE ✨
                                    ▼
                   ┌─────────────────────────────┐
                   │  create_schedule_for_       │
                   │  program()                  │
                   │  - Start: Next Monday       │
                   │  - Pattern: Mon/Wed/Fri     │
                   │  - Creates 12 Schedule      │
                   │    entries                  │
                   └─────────────────────────────┘
                                    │
                                    ▼
                          ✅ Program Ready

┌─────────────────────────────────────────────────────────────────────────┐
│                          WORKOUT DAY                                     │
└─────────────────────────────────────────────────────────────────────────┘

   User: "Start workout"
           │
           ▼
   ┌────────────────────────┐
   │  start_workout()       │
   │  Voice Agent Function  │
   └────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  get_todays_workout(user_id)       │
   │                                    │
   │  Query:                            │
   │  SELECT * FROM schedule            │
   │  WHERE user_id = ?                 │
   │    AND scheduled_date = TODAY      │
   │    AND completed = FALSE           │
   │                                    │
   │  Returns: Full workout structure   │
   │  - Workout metadata                │
   │  - All exercises (order preserved) │
   │  - All sets with targets          │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  WorkoutSession(                   │
   │    user_id,                        │
   │    schedule_id,                    │
   │    workout_data                    │
   │  )                                 │
   │                                    │
   │  Initializes:                      │
   │  - exercises: [ExerciseProgress]   │
   │  - current_exercise_index: 0       │
   │  - current_set_index: 0            │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  Store in AgentState               │
   │  state.set(                        │
   │    "workout.current_session",      │
   │    session.to_dict()               │
   │  )                                 │
   │                                    │
   │  Saved to:                         │
   │  .agent_state_{user_id}.json       │
   └────────────────────────────────────┘
           │
           ▼
   Nova: "Alright! Today's workout is Upper Push.
          First up: Bench Press - Set 1 of 5, 5 reps at 80%."

┌─────────────────────────────────────────────────────────────────────────┐
│                       DURING WORKOUT                                     │
└─────────────────────────────────────────────────────────────────────────┘

   [User performs set]
           │
   User: "Done" or Nova counts 5 reps
           │
           ▼
   ┌────────────────────────────────────┐
   │  complete_set(                     │
   │    reps=5,                         │
   │    weight=225,                     │
   │    rpe=8                           │
   │  )                                 │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  Load session from state           │
   │  session = WorkoutSession.         │
   │    from_dict(session_data)         │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  session.mark_set_complete(        │
   │    performed_reps=5,               │
   │    performed_weight=225,           │
   │    rpe=8                           │
   │  )                                 │
   │                                    │
   │  Updates:                          │
   │  - set.completed = True            │
   │  - set.performed_reps = 5          │
   │  - set.performed_weight = 225      │
   │  - set.actual_rpe = 8              │
   │  - set.completed_at = NOW          │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  session.advance_to_next_set()     │
   │                                    │
   │  Logic:                            │
   │  - More sets in exercise?          │
   │    → Increment set_index           │
   │  - Exercise done?                  │
   │    → Increment exercise_index      │
   │    → Reset set_index to 0          │
   │  - Workout done?                   │
   │    → Return False                  │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  Save updated session              │
   │  state.set(                        │
   │    "workout.current_session",      │
   │    session.to_dict()               │
   │  )                                 │
   │  state.save_state()                │
   └────────────────────────────────────┘
           │
           ▼
   Nova: "Awesome set! That's 5 reps at 225kg.
          Rest for 3:00. Next up: Set 2 of 5, 5 reps at 80%"

   [Repeat for all sets/exercises]

┌─────────────────────────────────────────────────────────────────────────┐
│                       END WORKOUT                                        │
└─────────────────────────────────────────────────────────────────────────┘

   User: "I'm done" or "End workout"
           │
           ▼
   ┌────────────────────────────────────┐
   │  end_workout()                     │
   │  Voice Agent Function              │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  Load session from state           │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  session.end_session()             │
   │  - is_active = False               │
   │  - end_time = NOW                  │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  Get completed sets                │
   │  completed_sets = session.         │
   │    get_completed_sets_for_         │
   │    logging()                       │
   │                                    │
   │  Returns: [                        │
   │    {set_id, reps, weight, rpe},    │
   │    {set_id, reps, weight, rpe},    │
   │    ...                             │
   │  ]                                 │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  For each completed set:           │
   │                                    │
   │  log_completed_set(                │
   │    db, user_id, set_id,            │
   │    reps, weight, rpe               │
   │  )                                 │
   │                                    │
   │  Creates ProgressLog entry:        │
   │  INSERT INTO progress_logs         │
   │  VALUES (...)                      │
   │  COMMIT                            │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  mark_workout_completed(           │
   │    db, schedule_id                 │
   │  )                                 │
   │                                    │
   │  UPDATE schedule                   │
   │  SET completed = TRUE              │
   │  WHERE id = schedule_id            │
   │  COMMIT                            │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  Clear session from state          │
   │  state.set(                        │
   │    "workout.current_session",      │
   │    None                            │
   │  )                                 │
   └────────────────────────────────────┘
           │
           ▼
   ┌────────────────────────────────────┐
   │  Switch to main menu               │
   │  state.switch_mode("main_menu")    │
   │  state.save_state()                │
   └────────────────────────────────────┘
           │
           ▼
   Nova: "Great work today! You crushed it.
          All your progress has been saved."

          ✅ Workout Complete!
```

## State Transitions

```
┌──────────────┐
│  ONBOARDING  │
└──────────────┘
       │
       ▼ (create_user completed)
┌──────────────┐
│  MAIN MENU   │◄─────────────┐
└──────────────┘              │
       │                      │
       ▼ (start_workout)      │
┌──────────────┐              │
│   WORKOUT    │              │
│   (Active)   │              │
└──────────────┘              │
       │                      │
       ▼ (end_workout)        │
       └──────────────────────┘
```

## Database Schema Relationships

```
┌─────────────────────┐
│  UserGenerated      │
│  Program            │
│  ┌───────────────┐  │
│  │ id            │  │
│  │ user_id       │  │
│  │ name          │  │
│  │ duration_wks  │  │
│  └───────────────┘  │
└─────────────────────┘
          │
          │ 1:N
          ▼
┌─────────────────────┐         ┌─────────────────────┐
│  Workout            │         │  Schedule           │
│  ┌───────────────┐  │         │  ┌───────────────┐  │
│  │ id            │◄─┼─────────┼──│ workout_id    │  │
│  │ program_id    │  │         │  │ user_id       │  │
│  │ week_number   │  │         │  │ scheduled_    │  │
│  │ day_number    │  │         │  │   date        │  │
│  │ name          │  │         │  │ completed     │  │
│  └───────────────┘  │         │  └───────────────┘  │
└─────────────────────┘         └─────────────────────┘
          │
          │ 1:N
          ▼
┌─────────────────────┐
│  WorkoutExercise    │
│  ┌───────────────┐  │
│  │ id            │  │
│  │ workout_id    │  │
│  │ exercise_id   │  │
│  │ order_number  │  │
│  └───────────────┘  │
└─────────────────────┘
          │
          │ 1:N
          ▼
┌─────────────────────┐         ┌─────────────────────┐
│  Set                │         │  ProgressLog        │
│  ┌───────────────┐  │         │  ┌───────────────┐  │
│  │ id            │◄─┼─────────┼──│ set_id        │  │
│  │ workout_ex_id │  │         │  │ user_id       │  │
│  │ set_number    │  │         │  │ performed_    │  │
│  │ reps (target) │  │         │  │   reps        │  │
│  │ intensity_%   │  │         │  │ performed_    │  │
│  │ rest_seconds  │  │         │  │   weight      │  │
│  └───────────────┘  │         │  │ rpe           │  │
└─────────────────────┘         │  │ completed_at  │  │
                                │  └───────────────┘  │
                                └─────────────────────┘
```

## Key Design Patterns

### 1. **State Machine Pattern**
- AgentState manages mode transitions
- Each mode has distinct function tools
- State persisted to JSON file

### 2. **Repository Pattern**
- `schedule_utils.py`: Schedule CRUD
- `progress_utils.py`: Progress CRUD
- Separates data access from business logic

### 3. **Session Pattern**
- WorkoutSession encapsulates workout state
- Serializable (to_dict / from_dict)
- Crash recovery via state persistence

### 4. **Strategy Pattern**
- Smart scheduling based on days_per_week
- Different patterns for 2/3/4/5+ days
- Extensible for muscle-group-aware scheduling

---

## Error Handling Strategy

1. **Non-blocking schedule creation**: Program generation succeeds even if schedule fails
2. **Graceful workout loading**: Clear message if no workout today
3. **Transaction safety**: Each set logged in separate transaction
4. **State recovery**: Session preserved in JSON file
5. **Try-catch at boundaries**: Voice agent functions never crash, return friendly messages

---

## Performance Considerations

- **Eager loading**: `joinedload()` prevents N+1 queries
- **Batch inserts**: Schedule entries created in single transaction
- **Index usage**: Foreign keys indexed, date queries efficient
- **File I/O**: JSON state minimal (< 50KB typical)

---

## Future Enhancements

1. **Pose Estimation Integration**:
   ```python
   # In voice_agent.py workout mode
   @function_tool
   async def rep_detected(velocity: float, depth: float):
       """Called by pose estimation on each rep"""
       session = load_session()
       current_set = session.get_current_set()
       current_set.measured_velocity = velocity
       # Auto-advance when target reps reached
   ```

2. **Auto-Regulation**:
   ```python
   # In workout_session.py
   def should_reduce_load(self) -> bool:
       """Check if velocity loss > 20%"""
       if velocity_loss > 0.20:
           return True
   ```

3. **Exercise Substitution**:
   ```python
   # In schedule_utils.py
   def substitute_exercise(workout_id, old_ex, new_ex, reason):
       """Swap exercise in workout"""
       # Update WorkoutExercise.exercise_id
   ```

---

Generated: October 27, 2025
