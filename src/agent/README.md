# agent/ -- Voice Agent Stack

Conversational voice agent for Nowva's real-time AI coaching system. This module
connects the biomechanics diagnosis pipeline to the user via WebRTC audio,
handling everything from onboarding through live workout coaching.

Formed by merging three previously separate directories (`agents/`, `core/`,
`services/`) into a single package with a strict dependency hierarchy.

## Directory Structure

### `core/` -- Infrastructure

Low-level building blocks with no upward dependencies.

| File | Purpose |
|---|---|
| `agent_state.py` | `AgentState` -- persistent state machine. Manages mode transitions (onboarding, main_menu, workout, program_creation), user data, and workout state. Persisted to `.agent_state_{user_id}.json` with atomic writes. Supports dot-notation access (`state.get("workout.current_session")`). |
| `ipc_communication.py` | `IPCServer` / `IPCClient` -- UNIX domain socket IPC with 4-byte length-prefix framing. Connects the voice agent process to the pose estimation process at `/tmp/nowva_coaching.sock`. |
| `session_manager.py` | `SessionManager` -- encrypted local session storage using Fernet symmetric encryption. Persists user credentials between launches. |
| `session_logger.py` | `SessionLogger` (singleton) -- cross-process CSV-based logging of all LLM calls, function tool calls, and conversation turns with token counts, cost tracking, and per-model usage aggregation. |
| `workout_session.py` | `WorkoutSession`, `ExerciseProgress`, `SetProgress` -- structured workout state. Tracks sets, reps, weights, RPE, velocity, and completion status. Serializable to/from dict for storage in `AgentState`. |
| `latency_tracker.py` | `LatencyTracker` (singleton) -- per-turn TTFT and end-to-end latency metrics with p50/p90/p99 percentiles. Detects progressive degradation in long sessions. |
| `token_estimator.py` | Token estimation via tiktoken when actual usage data is unavailable. Helpers for text, audio, and function call token counts. |
| `pricing_config.py` | Centralized per-model pricing tables (OpenAI, Google, Cartesia, Deepgram) and `calculate_cost()` utility. |

### `services/` -- Services Consumed by Agents

Depends on `core/`. No dependency on `agents/`.

| File | Purpose |
|---|---|
| `coaching_service.py` | `CoachingService` -- the central bridge between biomechanics and voice. Owns the IPC listener (background thread), the `CoachingOrchestrator`, and the `AudioCueService`. Dispatches incoming messages (`fault`, `rep_complete`, `set_complete`, `diagnosis_complete`, `calibration_complete`, etc.) to the orchestrator. Generates coaching speech via `session.generate_reply()`. |
| `coaching_orchestrator.py` | `CoachingOrchestrator` -- priority queue (`CuePriority`: FAULT_CUE > LLM_MOTIVATION > LLM_SET_RECAP > LLM_EXERCISE_RECAP > REP_COUNT_CUE > POSITIVE_CUE) that dispatches coaching events. Cached audio cues duck the LLM track. Handles per-set tracking, motivation triggers at set midpoint, set/exercise recaps with diagnosis data, and set report generation. |
| `audio_cue_service.py` | `AudioCueService` -- indexes pre-generated WAV files from `assets/cues/wav/` with random variant selection for natural-sounding playback. Falls back to runtime TTS (OpenAI `gpt-4o-mini-tts`) for missing cues. Rep counts play on a dedicated LiveKit audio track so they don't block agent speech. |
| `compaction_service.py` | `CompactionService` -- rolling background context summarization via GPT-4.1-mini. Maintains a 3-tier summary (HOT/WARM/COLD) that decays over time. Flushes cold context to `memory.md` on disk. Called by context pruning logic to prevent unbounded token growth. |
| `teaching_cues.py` | `SQUAT_TEACHING_CUES` -- registry of pre-cached audio cue keys and spoken text for the teaching flow ("Knees out.", "Chest up.", "Good.", etc.). |
| `email_service.py` | Sends workout programs to users via the Resend API. |
| `set_report.py` | `generate_set_report()` -- produces per-set PNG timeseries plots with joint angle data and annotated coaching cues at their exact timestamps. |
| `context_viewer.py` | `ContextViewer` -- debug HTTP server on port 8899 showing live LLM context, compaction tiers, and session stats. |
| `demo_narration.py` | LLM script generation for the choreographed coaching demo. Produces narration text synchronized with pose correction animations after a failed assessment. |
| `inline_task_runner.py` | Runs an `AgentTask` from non-inline contexts (e.g., IPC-triggered coaching demos) by injecting the task into the live `AgentSession`. |

### `agents/` -- LiveKit Voice Agents

Depends on both `core/` and `services/`.

All agents inherit from `BaseNovaAgent` (in `shared/base_agent.py`), which
extends LiveKit's `Agent` class and provides:

- Access to `AgentState` via `self.state` and `UserData` via `self.userdata`
- `self.user_id` / `self.user_name` properties
- `_say()` -- speak without being interrupted (suppresses turn detection)
- `_suppress_turn_detection()` / `_restore_turn_detection()` -- audio gating
- `_truncate_context_for_handoff()` -- compaction-aware context pruning
- `_log_function_call()` -- session logger integration

| File | Purpose |
|---|---|
| `voice_agent.py` | Entrypoint. Sets up the cascade pipeline (Deepgram STT, Gemini LLM, Cartesia TTS, Silero VAD), initializes compaction and context viewer, then routes to the correct agent based on `AgentState.mode`. Integrates `SessionProfiler` for per-session instrumentation and uploads EOU metrics to LiveKit Cloud. Uses pipe-based state notification (`set_state_notify_fd`) instead of polling to detect mode transitions from the main process. |
| `onboarding_agent.py` | `OnboardingAgent` -- new user flow using AgentTask-based architecture. Delegates to discrete tasks (e.g., name/email collection) and hands off to main menu on completion. |
| `main_menu_agent.py` | `MainMenuAgent` -- primary interaction hub. Routes to workout, program creation, schedule, teaching, or quick exercise flows. |
| `workout_agent.py` | `WorkoutAgent` -- active workout sessions. Creates and starts `CoachingService`, manages wake word system ("hey Nova"), handles verbal set termination via `force_end_current_set()`. |
| `StartQuickExerciseAgent.py` | `CollectExerciseInfoTask` -- an `AgentTask` that collects quick-exercise parameters (sets, reps, weight, rest) then checks calibration status and hands off to calibration or workout. |
| `calibration_agent.py` | `CalibrationAgent` -- handles the calibration phase before a workout. Guides the user through the 2-rep form assessment and 5-rep calibration, relaying coaching orchestrator analysis data. |
| `coaching_demo_task.py` | `CoachingDemoTask` -- an `AgentTask` that delivers the choreographed coaching demo after a failed assessment. Coordinates synced narration + yoyo pose animation. |
| `program_creation_agent.py` | `ProgramCreationAgent` -- multi-step data collection (height, weight, age, goals, schedule) for generating personalized training programs. |
| `schedule_agent.py` | `ScheduleMaintenanceAgent` -- schedule viewing and modification. |
| `teaching_agent.py` | `TeachingAgent` -- guided squat instruction with phased progression. |
| `teaching_phases.py` | Phase definitions and transition logic for the teaching flow. |
| `website_voice_agent.py` | Website-facing voice agent (demo/landing page). |
| `website_voice_agent_v2.py` | Revised website agent with step-based prompting. |
| `console_launcher.py` | Launches the voice agent in console mode for local development. |

**Prompts** live in `agents/prompts/` -- one file per agent, exporting a
`get_<agent>_prompt()` function.

**Shared utilities** in `agents/shared/`:
- `userdata.py` -- `UserData` dataclass for ephemeral session state across handoffs
- `helpers.py` -- common agent helpers
- `unit_conversion.py` -- metric/imperial conversion utilities

## Dependency Rule

```
agents/  -->  services/  -->  core/
```

`core/` has zero upward dependencies. `services/` imports from `core/` only.
`agents/` imports from both. No circular imports.

## How It Runs

1. `main.py` starts the FastAPI backend and pose estimation as subprocesses.
2. The voice agent launches via LiveKit's worker framework. The entrypoint is
   `agents/voice_agent.py:entrypoint()`, which receives a `JobContext` from
   LiveKit when a user connects via WebRTC.
3. The entrypoint builds a cascade pipeline (Deepgram STT, Gemini LLM,
   Cartesia TTS) and creates an `AgentSession`. It then hands off to the
   appropriate `BaseNovaAgent` subclass based on persisted mode.
4. Agent handoffs (e.g., onboarding -> main menu -> workout) happen via
   LiveKit's agent transfer mechanism with context truncation.

## Key Data Flow

During an active workout set:

```
Biomechanics Pipeline (pose estimation process)
    |
    |  UNIX socket IPC (/tmp/nowva_coaching.sock)
    |  Message types: fault, rep_complete, frame_data,
    |                 diagnosis_complete, calibration_complete, ...
    v
CoachingService._handle_message()
    |
    |  Dispatches to CoachingOrchestrator
    v
CoachingOrchestrator (priority queue)
    |
    |-- FAULT_CUE (p1) ---------> AudioCueService.play_cue()
    |                              Pre-cached WAV, random variant
    |
    |-- LLM_MOTIVATION (p2) ----> session.generate_reply()
    |                              2-5 word mid-set push
    |
    |-- LLM_SET_RECAP (p3) -----> session.generate_reply()
    |                              Post-set feedback with diagnosis data
    |
    |-- LLM_EXERCISE_RECAP (p4) > session.generate_reply()
    |                              End-of-exercise summary
    |
    |-- REP_COUNT_CUE (p5) -----> Dedicated audio track (non-blocking)
    |
    |-- POSITIVE_CUE (p6) ------> AudioCueService.play_cue()
    |
    v
User hears coaching via WebRTC audio track
```

Cached audio cues always take priority over LLM-generated speech.
When a cached cue fires, the LLM audio track is ducked so the cue
is heard clearly.
