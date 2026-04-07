# Refactor: Collapse Website Agent to Single `submit_program` Tool

## Problem
The website voice agent has 15 `@function_tool` methods whose JSON schemas are serialized into every LLM call (~1,500-2,000 extra tokens). Each tool call also triggers another LLM inference round-trip. This causes 0.7-0.9s TTFT on Groq with llama-3.3-70b.

## Solution
Replace all 15 tools with a single `submit_program` tool. The LLM collects all info conversationally, then calls `submit_program` once at the end with all data. The tool handles validation, unit conversion, DB update, program generation API call, and room disconnect.

---

## Files to Change

### 1. `src/agents/website_voice_agent.py`

**Delete** all 15 `@function_tool` methods:
- `capture_name`
- `capture_height_weight`
- `capture_age_sex`
- `capture_goal`
- `capture_program_duration`
- `capture_training_frequency`
- `capture_session_duration`
- `capture_injury_history`
- `capture_specific_sport`
- `capture_training_season`
- `capture_games_per_week`
- `capture_user_notes`
- `capture_equipment_tier`
- `capture_fitness_level`
- `update_user_profile`
- `generate_workout_program`
- `end_conversation`

**Delete** the `_log_function_call` helper method (no longer needed with one tool).

**Add** one new `@function_tool` method: `submit_program`

```python
@function_tool
async def submit_program(
    self,
    context: RunContext,
    first_name: str,
    height: str,
    weight: str,
    age: int,
    sex: str,
    goal: str,
    duration_weeks: int,
    days_per_week: int,
    fitness_level: str,
    session_duration_minutes: int = 60,
    injuries: str = "none",
    sport: str = "none",
    training_season: str = None,
    games_per_week: int = 0,
    notes: str = None,
    equipment_tier: int = 2,
):
```

**Logic inside `submit_program`** (in order):
1. **Validate & normalize name** — strip, length check (1-50), reject placeholder names
2. **Convert height** — call `normalize_height_to_cm(height)`, validate 50-300cm range
3. **Convert weight** — call `normalize_weight_to_kg(weight)`, validate 30-300kg range
4. **Validate age** — 13-100 range
5. **Normalize sex** — map "m"/"male"/"man"/"boy" → "male", "f"/"female"/"woman"/"girl" → "female"
6. **Categorize goal** — call `categorize_goal(goal)`
7. **Validate duration_weeks** — clamp 2-52
8. **Validate days_per_week** — clamp 1-7
9. **Normalize fitness_level** — map to "beginner"/"intermediate"/"advanced"
10. **Validate optional fields** — clamp session_duration (30-180), equipment_tier (1-3), games_per_week (0-7), normalize training_season
11. **If any required field fails validation** — return a clear error string telling the LLM what was wrong (e.g., "Height could not be parsed. Ask the user for their height again in a format like 5'9 or 175cm, then call submit_program again with all fields.")
12. **Update DB** — same logic as current `update_user_profile()`: open `SessionLocal()`, query User by `self.state["user_id"]`, update name/height_cm/weight_kg/age/sex, commit
13. **Call program generation API** — same logic as current `generate_workout_program()`: POST to `{FASTAPI_URL}/api/programs/generate` with full payload, handle 202 response, publish LiveKit data message with job_id
14. **Disconnect** — same logic as current `end_conversation()`: `await context.session.room_io.room.disconnect()`
15. **Return** success message

**On validation failure**: return an error string describing what failed. The LLM will re-ask the user for the bad field(s) and call `submit_program` again with corrected values. This is the only case where the tool gets called more than once.

**Keep unchanged**:
- `__init__` method
- `on_enter` method
- The `entrypoint` function (including the new metrics_collected handler)
- All imports (add any needed, remove unused ones)

---

### 2. `src/agents/prompts/website_agent_prompt.py`

**Rewrite** `get_website_agent_prompt()` to return a much shorter prompt (~80-100 lines instead of ~224). Structure:

```
# NOVA - WEBSITE VOICE AGENT

You are Nova, an AI fitness coach helping website visitors create workout programs.

## RULES
- English only
- One question at a time, brief responses (1-2 sentences)
- Warm, professional, conversational tone
- Stay on topic — redirect off-topic questions back to program creation
- DO NOT answer general fitness questions

## CONVERSATION FLOW

1. Greet the user and ask for their first name
2. Spell out the name to confirm (e.g., "S-A-R-A-H, Sarah — is that right?")
   - If wrong, ask them to spell it letter by letter
3. Collect ALL of the following, one question at a time:

### Required:
- Height and weight (accept any format: "5'9 and 180lbs", "175cm 80kg", etc.)
- Age and sex
- Fitness goal (build muscle, get stronger, improve athleticism, etc.)
- Program duration in weeks (suggest 8-12 based on goal)
- Training days per week (1-7)
- Fitness level (beginner, intermediate, advanced)

### Optional (ask briefly, accept "none" / "skip"):
- Session duration in minutes (default 60)
- Injuries or limitations
- Specific sport (if yes → ask training season: off/pre/in/post-season)
  - If in-season → ask games per week
- Additional notes or preferences
- Equipment tier: 1 (barbell/rack/bench/pull-up bar/floor), 2 (+ dumbbells), 3 (+ bands). Default 2.

4. Once ALL info is collected, say an enthusiastic goodbye:
   - Thank them, tell them their program will arrive via email within 5 minutes
5. IMMEDIATELY call submit_program() with ALL collected data
   - Pass height and weight as raw strings (e.g., "5'9", "180 lbs") — the tool converts them
   - If the tool returns an error, re-ask ONLY the failed field, then call submit_program() again with everything
6. After submit_program succeeds, say nothing more — the session ends automatically
```

Key changes from current prompt:
- No per-tool instructions (no "call capture_X then immediately ask Question Y")
- No function-calling rules section (only one tool to call)
- Checklist-style data collection instead of rigid numbered sequence
- ~60% shorter

---

### 3. No changes needed
- `src/agents/shared/unit_conversion.py` — used as-is
- `entrypoint()` function — unchanged
- Imports from `unit_conversion` — already imported, keep them

---

## Summary of Impact

| Metric | Before | After |
|--------|--------|-------|
| Tool schemas per LLM call | 15 (~2,000 tokens) | 1 (~150 tokens) |
| LLM round-trips per conversation | ~15-20 | ~2-3 (1 normal + 1-2 if validation fails) |
| System prompt size | ~224 lines | ~80-100 lines |
| Total input tokens (baseline) | ~4,000-6,000 | ~1,500-2,500 |
| Expected TTFT improvement | 0.7-0.9s | ~0.3-0.5s |
