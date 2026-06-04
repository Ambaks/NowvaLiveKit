# Part 5: Integration

## Goal
Wire CoachingAgent into the live system, make it invocable from WorkoutAgent, and handle edge cases.

## Files to modify

### `src/agents/workout_agent.py`
Add `start_form_coaching` function tool:
- Triggered by: "help me fix my form", "coach my form", "what am I doing wrong"
- Stops wake word system
- Truncates context
- Creates CoachingAgent with appropriate params (exercise from current workout session, max_iterations, etc.)
- Returns the agent for handoff via `session.update_agent()`

### Automatic invocation (future)
- CoachingService could detect persistent faults across multiple reps and suggest coaching
- First-time exercise detection: if user has never done this exercise, call CoachingAgent with `max_iterations=1` for a quick form check before calibration
- These are enhancements — the function tool is the MVP

## Edge cases to handle
- **Pipeline disconnects mid-coaching:** Add a timeout — if no rep event in 60s, prompt user or exit gracefully
- **User says nothing after cue:** Agent is conversational (not wake-word), so normal turn detection handles this
- **No faults on first rep:** Announce "form looks solid", finish immediately
- **Calibration after coaching:** CoachingAgent sets `calibration.active = True` in state, then hands to WorkoutAgent. WorkoutAgent's existing calibration flow picks it up naturally.
- **CoachingService not running:** Check `userdata.coaching_service` is not None before registering callback. If None, announce that biomechanics tracking isn't active and exit.

## End-to-end verification
1. Run pipeline + voice agent
2. Start a workout, say "hey nova, coach my form"
3. Perform reps — verify per-rep diagnosis + LLM cue with specific numbers
4. Verify fault cues still play during movement (orchestrator not broken)
5. Verify handoff back to WorkoutAgent is seamless (wake word resumes)
6. Test "move on" mid-coaching
7. Test with `run_calibration_after=True` — verify 5-rep calibration triggers after coaching
