# Nowva Main Application

This document describes the main Nowva application that orchestrates the voice agent and pose estimation processes.

## Architecture

The application consists of several key components:

1. **Main Orchestrator** ([src/main.py](src/main.py))
   - Entry point for the application
   - Manages session state and user onboarding
   - Coordinates voice agent and pose estimation processes
   - Handles IPC communication setup
   - Monitors state changes to control pose estimation

2. **Session Management** ([src/core/session_manager.py](src/core/session_manager.py))
   - Stores user sessions in encrypted local file (`.session.dat`)
   - Checks for existing sessions on startup
   - Creates and saves new sessions after onboarding

3. **State Management** ([src/core/agent_state.py](src/core/agent_state.py))
   - Manages agent modes: onboarding, main_menu, workout
   - Tracks user information and workout state
   - Persistent state storage per user
   - Enables smooth mode transitions

4. **IPC Communication** ([src/core/ipc_communication.py](src/core/ipc_communication.py))
   - UNIX domain socket-based communication
   - Server runs in main process
   - Client runs in pose estimation process
   - Exchanges JSON messages (rep counts, form feedback, etc.)

5. **Voice Agent** ([src/agents/voice_agent.py](src/agents/voice_agent.py))
   - Mode-aware conversational AI using GPT-4 Realtime API
   - Handles onboarding, main menu, and workout modes
   - Function calling for structured data extraction
   - Runs continuously in background subprocess

6. **Voice Agent Launcher** ([src/agents/console_launcher.py](src/agents/console_launcher.py))
   - Spawns and monitors voice agent subprocess
   - Captures onboarding data from agent output
   - Manages agent process lifecycle

7. **Pose Estimation Process** ([src/pose/pose_estimation_process.py](src/pose/pose_estimation_process.py))
   - Runs stereo pose estimation with cameras
   - Sends data to main process via IPC
   - Controlled by workout mode state

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
         ┌─────────────────┐
         │  Start Workout  │
         │  (Voice Mode)   │
         ├─────────────────┤
         │ • State → workout│
         │ • IPC Server    │
         │ • Pose Process  │
         │ • Voice Agent   │
         └─────────────────┘
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

Agent state is stored per user in `src/.agent_state_{user_id}.json`:

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
    "exercise": null,
    "reps": 0
  }
}
```

## IPC Communication

### Message Format

All IPC messages are JSON objects with `type` and `value` fields:

```json
{
  "type": "rep_count",
  "value": 5
}
```

### Message Types

**From Pose Estimation → Main Process:**
- `rep_count`: Integer rep count
- `feedback`: String form feedback (e.g., "knees caving", "back folding")
- `status`: Status updates (e.g., "initialized", "calibrating")
- `error`: Error messages

**From Main Process → Pose Estimation:**
- `command`: Control commands (e.g., "start", "stop", "pause")

### Socket Location

UNIX domain socket: `/tmp/nowva_ipc.sock`

## Usage

### First Time Setup

1. **Setup Environment:**
   ```bash
   # Copy .env.example to .env and fill in your API keys
   cp src/.env.example src/.env

   # Install dependencies
   pip install -r src/requirements.txt
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

1. Tell Nova "start workout" or "let's work out"
2. Nova switches to workout mode
3. Main.py detects state change
4. IPC server starts in background
5. Pose estimation process launches
6. Voice agent provides real-time coaching
7. Say "stop" or "I'm done" to end workout

## Voice System

### Technology Stack

- **GPT-4 Realtime API**: Integrated STT + LLM + TTS
- **LiveKit Agents**: Real-time communication framework
- **Function Calling**: Structured data extraction and mode switching

### Mode-Specific Behavior

**Onboarding Mode:**
- Collects first name and email
- Confirms spelling letter-by-letter
- Creates user account in database
- Transitions to main menu

**Main Menu Mode:**
- Different greetings for first-time vs. returning users
- Voice commands: "start workout", "view progress", "settings"
- Natural conversation flow

**Workout Mode:**
- Real-time rep counting feedback
- Form correction coaching
- Encouragement and motivation
- "Stop" command to end workout

## Testing

### Test Voice Agent

```bash
cd src/agents
python voice_agent.py console
```

### Test IPC Communication

```bash
cd src/tests
python test_ipc.py
```

Expected output:
```
✓ Test PASSED: IPC communication working correctly
```

## Current Status

### ✅ Implemented
- Session management with encrypted storage
- Database integration (PostgreSQL via Neon)
- State management with mode switching
- IPC communication (UNIX domain sockets)
- Voice onboarding with GPT-4 Realtime
- Voice main menu navigation
- Voice workout coaching
- Pose estimation integration
- Automatic state-based process control

### 🚧 In Progress
- Real pose metrics (currently placeholder data)
- Actual rep counting logic
- Form analysis algorithms
- Workout program tracking

### 📋 TODO
- Send real pose metrics through IPC (joint angles, depth, etc.)
- Implement squat rep detection from pose data
- Implement form analysis (knee valgus, back angle, etc.)
- Add workout programs and exercise library
- Persist workout data to database
- Progress tracking and analytics

## File Structure

```
src/
├── main.py                          # Main orchestrator
├── agents/
│   ├── voice_agent.py              # Mode-aware voice agent
│   └── console_launcher.py         # Agent subprocess launcher
├── core/
│   ├── session_manager.py          # Session management
│   ├── agent_state.py              # State management
│   └── ipc_communication.py        # IPC server/client
├── pose/
│   └── pose_estimation_process.py  # Pose estimation wrapper
├── auth/
│   └── user_management.py          # User account creation
├── db/                             # Database module
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   └── setup_db.py
└── biomechanics/                   # Pose estimation
    └── week2_stereo/
        ├── stereo_triangulation.py
        └── stereo_calibration.npz
```

## Dependencies

See [src/requirements.txt](src/requirements.txt)

Key dependencies:
- **livekit-agents**: Real-time voice framework
- **livekit-plugins-openai**: GPT-4 Realtime API integration
- **OpenCV**: Pose estimation and camera capture
- **SQLAlchemy**: Database ORM
- **NumPy**: Pose calculations
- **cryptography**: Session encryption

## Environment Variables

Required in `src/.env`:

```bash
# OpenAI (for GPT-4 Realtime API)
OPENAI_API_KEY=your_openai_key

# Database (Neon PostgreSQL)
DATABASE_URL=postgresql://...

# Optional: LiveKit credentials (for remote deployment)
LIVEKIT_URL=wss://...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
```

## Notes

- Voice agent runs in console mode (no browser needed)
- IPC uses UNIX domain sockets (macOS/Linux only)
- Sessions are encrypted with Fernet symmetric encryption
- State files are JSON (per user)
- Main.py monitors state files for mode changes
- Pose estimation auto-starts/stops based on workout mode
- Safety feature: State always resets to main_menu on startup

## Safety Features

1. **Shutdown Cleanup**: Signal handlers reset state to main_menu
2. **Startup Reset**: Always reset to main_menu on app start
3. **State Persistence**: User data and preferences preserved
4. **Graceful Degradation**: Voice agent failure doesn't crash app
