# Nowva Main Application

This document describes the main Nowva application that orchestrates the voice agent and biomechanics pipeline processes.

## Architecture

The application consists of several key components:

1. **Main Orchestrator** ([src/main.py](src/main.py))
   - Entry point for the application
   - Manages session state and user onboarding
   - Coordinates voice agent and biomechanics pipeline subprocesses
   - Hosts both IPC servers (main + coaching)
   - Monitors mode changes via a pipe-based notification channel (no polling)
   - Optional flags: `--profile` (session profiler + HTML report on exit), `--simulate` (skip real pose estimation)
   - Set `NOWVA_LOG_CONSOLE=true` to mirror all console output to `session_logs/console_<timestamp>.log`

2. **Session Management** ([src/agent/core/session_manager.py](src/agent/core/session_manager.py))
   - Stores user sessions in encrypted local file (`.session.dat`)
   - Checks for existing sessions on startup
   - Creates and saves new sessions after onboarding

3. **State Management** ([src/agent/core/agent_state.py](src/agent/core/agent_state.py))
   - Manages agent modes: onboarding, main_menu, workout, program_creation
   - Tracks user information and workout state
   - Persistent state storage per user (`.agent_state_{user_id}.json`, atomic writes)
   - The voice agent signals state changes by writing to a notification pipe
     (`set_state_notify_fd()`); main.py `select()`s on the pipe and reloads state
     only when notified

4. **IPC Communication** ([src/agent/core/ipc_communication.py](src/agent/core/ipc_communication.py))
   - UNIX domain socket-based communication with 4-byte length-prefix framing
   - Two channels:
     - **Main IPC** (`/tmp/nowva_ipc.sock`) — biomechanics pipeline → main process
     - **Coaching IPC** (`/tmp/nowva_coaching.sock`) — main process ↔ voice agent
   - The coaching IPC server is bound eagerly at startup so the socket is ready
     before `WorkoutAgent.on_enter()` connects

5. **Voice Agent** ([src/agent/agents/voice_agent.py](src/agent/agents/voice_agent.py))
   - Cascade pipeline: Deepgram Nova-3 (STT), Gemini Flash Lite (LLM), Cartesia (TTS), Silero (VAD), semantic turn detection (MultilingualModel)
   - Mode-aware routing to OnboardingAgent / MainMenuAgent / WorkoutAgent / ProgramCreationAgent / ScheduleMaintenanceAgent
   - Function calling for structured data extraction
   - Runs continuously in background subprocess
   - Uploads EOU metrics to LiveKit Cloud for benchmarking (OTel pipeline)

6. **Voice Agent Launcher** ([src/agent/agents/console_launcher.py](src/agent/agents/console_launcher.py))
   - Spawns and monitors voice agent subprocess
   - Passes the state-notification pipe fd to the agent process
   - Manages agent process lifecycle

7. **Biomechanics Pipeline Process** ([src/biomechanics/pipeline_process.py](src/biomechanics/pipeline_process.py))
   - Runs the full layered pipeline (pose → IK → faults → rep counting → diagnosis)
   - Sends structured events to the main process via IPC
   - Supports `--preload`: loads models without opening the camera, then waits
     for a `start_capture` command — enables instant window display when the
     workout starts (native macOS fullscreen animation via `viz/window_anim.py`)
   - Supports `--calibration-mode` and `--calibration-file` for the
     assessment/calibration phases

8. **Session Profiler** ([src/profiler/](src/profiler/))
   - Enabled with `--profile` or `NOWVA_PROFILE=1`
   - Thread-safe event and resource collection across all processes
     (main, voice agent, pipeline)
   - Background CPU/memory/GPU sampling
   - Merges per-process JSON dumps into a self-contained HTML report
     (Chart.js) in `profiler_results/` on exit

## Flow Diagram

```
┌──────────────┐
│  Start App   │
└──────┬───────┘
       │
       ▼
  ┌─────────────────┐
  │ Check Session?  │
  └────┬────────┬───┘
       │        │
    No │        │ Yes
       │        │
       ▼        ▼
  ┌──────────────┐  ┌──────────────┐
  │ Voice Agent  │  │ Voice Agent  │
  │ (Onboarding) │  │ (Main Menu)  │
  └──────┬───────┘  └──────┬───────┘
         │                 │
         └────────┬────────┘
                  │
                  ▼
           ┌──────────────┐
           │  Main Menu   │
           │ (Voice Mode) │
           └──────┬───────┘
                  │
                  ▼
         ┌─────────────────────┐
         │  Start Workout      │
         │  (Voice Mode)       │
         ├─────────────────────┤
         │ • State → workout   │
         │ • Pipe notification │
         │ • Main IPC server   │
         │ • Pipeline process  │
         │ • Assessment +      │
         │   calibration phase │
         └─────────────────────┘
```

## Session Storage

Sessions are stored in encrypted `src/.session.dat`:

```json
{
  "user_id": "2f330a01-c50b-4a05-9dd8-1ab685c8f9ae",
  "username": "john_doe",
  "email": "john@example.com",
  "created_at": "2025-10-19T12:00:00"
}
```

## State Management

Agent state is stored per user in `.agent_state_{user_id}.json`:

```json
{
  "mode": "main_menu",
  "user": {
    "id": "2f330a01-c50b-4a05-9dd8-1ab685c8f9ae",
    "username": "john_doe",
    "name": "John",
    "email": "john@example.com",
    "first_time_main_menu": false
  },
  "workout": {
    "active": false,
    "current_session": null
  }
}
```

The main loop only launches the pipeline process once `mode == "workout"` AND
`workout.current_session` is set (configured by `confirm_quick_exercise` /
`start_workout` tools).

## IPC Communication

### Message Format

All IPC messages are JSON objects with a `type` field plus type-specific payload,
framed with a 4-byte big-endian length prefix.

### Message Types

**From Biomechanics Pipeline → Main Process (main IPC):**
- `rep_complete` — rep number, depth category, timing, faults
- `fault` — fault type + severity (MILD/MODERATE/SEVERE)
- `set_complete` — set number, total reps, per-set statistics
- `calibration_rep` / `calibration_complete` — calibration phase progress
- `assessment_rep` / `diagnosis_complete` — assessment phase + diagnosis results
- `cache_cues` / `play_cue` — audio cue pre-caching and playback requests
- `rest_complete` — rest timer expired

**From Voice Agent → Main Process (coaching IPC, forwarded to pipeline):**
- `rest_start` — begin rest timer with duration
- `workout_complete` — end the workout session
- `demo_start` / `demo_cue` / `demo_end` — choreographed coaching demo control

The main process relays events between the two channels: pipeline events are
forwarded to the voice agent for coaching delivery, and voice agent commands
are forwarded to the pipeline.

## Usage

### First Time Setup

1. **Setup Environment:**
   ```bash
   # Copy .env.example to .env and fill in your API keys
   cp .env.example .env

   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Run Main Application:**
   ```bash
   python src/main.py
   ```

3. **Voice Onboarding:**
   - Nova voice agent starts automatically
   - Speak your first name when prompted
   - Spell it out if needed for confirmation
   - Provide your email address
   - Confirm information
   - Agent transitions to main menu automatically

### Subsequent Runs

```bash
python src/main.py
```

The app will:
1. Detect existing session
2. Load user state
3. Reset to main_menu mode (safety feature)
4. Start voice agent in main menu mode
5. Greet returning user

### Starting a Workout

1. Tell Nova "start workout" or ask for a quick exercise
2. Nova collects exercise parameters (sets, reps, weight, rest) if needed
3. Nova switches state to workout mode and signals via the notification pipe
4. Main.py launches the biomechanics pipeline process
5. First-time exercises run a 2-rep form assessment + 5-rep calibration
6. Voice agent provides real-time coaching (cached cues + LLM speech)
7. Say "stop" or "I'm done" to end the workout

### Profiling a Session

```bash
python src/main.py --profile
```

On exit, an HTML report with per-turn latency, LLM usage, and CPU/memory/GPU
traces is written to `profiler_results/` and opened in the browser.

## Voice System

### Technology Stack

- **Deepgram Nova-3** — speech-to-text
- **Gemini Flash Lite** — conversational LLM (fast, low-cost)
- **Cartesia** — text-to-speech
- **Silero VAD + MultilingualModel** — voice activity and semantic turn detection
- **LiveKit Agents** — real-time communication framework
- **Function Calling** — structured data extraction and mode switching

### Mode-Specific Behavior

**Onboarding Mode:**
- AgentTask-based flow: collects first name and email with confirmation
- Creates user account in database
- Transitions to main menu

**Main Menu Mode:**
- Different greetings for first-time vs. returning users
- Voice commands: "start workout", quick exercise, program creation, schedule
- Natural conversation flow

**Workout Mode:**
- Real-time rep counting and fault cues (pre-cached audio, <50ms)
- LLM-generated set recaps with diagnosis data
- Choreographed coaching demo after a failed assessment
- "Stop" command to end workout

## Testing

### Test Voice Agent

```bash
PYTHONPATH=src python src/agent/agents/voice_agent.py console
```

### Run the Test Suite

```bash
PYTHONPATH=src pytest tests/ -x
```

## Notes

- Voice agent runs in console mode (no browser needed)
- IPC uses UNIX domain sockets (macOS/Linux only)
- Sessions are encrypted with Fernet symmetric encryption
- State files are JSON (per user) with atomic writes
- Mode changes are signaled over a pipe — main.py does not poll state files
- Pipeline process auto-starts/stops based on workout mode
- Safety feature: state always resets to main_menu on startup

## Safety Features

1. **Shutdown Cleanup**: Signal handlers reset state to main_menu
2. **Startup Reset**: Always reset to main_menu on app start
3. **State Persistence**: User data and preferences preserved
4. **Graceful Degradation**: Voice agent failure doesn't crash app
