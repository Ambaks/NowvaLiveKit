# Part 2: Service Wiring

## Goal
Let an agent register to receive `rep_complete` events from CoachingService, and add a coaching mode to the orchestrator that suppresses set-completion / motivation logic while the CoachingAgent is active.

## Files to modify

### `src/services/coaching_service.py`
- Add `_on_rep_complete_callback: Callable | None = None` to `__init__`
- Add `set_rep_complete_callback(fn)` and `clear_rep_complete_callback()` public methods
- In `_handle_message`, when `msg_type == "rep_complete"` and callback is set: call it with the full message dict
- Still forward to orchestrator (fault cues, rep counting should continue)
- Follows the same pattern as existing `_on_workout_complete_callback` and `_on_calibration_complete_callback`

### `src/services/coaching_orchestrator.py`
- Add `_coaching_mode: bool = False` to `__init__`
- Add `set_coaching_mode(enabled: bool)` method
- When `_coaching_mode is True` in `on_rep_complete()`: skip set completion check, motivation trigger, and positive cue enqueueing
- Fault cues and rep count cues continue normally (user still hears "knees out" during movement)
- When coaching mode is disabled, orchestrator resumes normal behavior

## Verification
- Set a mock callback, send a rep_complete IPC message, verify callback fires with full data
- Enable coaching mode, hit target reps — verify orchestrator does NOT trigger set recap or motivation
- Disable coaching mode, verify normal behavior resumes
