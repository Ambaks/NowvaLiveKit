# Nowva Main Application

This document describes the main Nowva application that orchestrates the voice agent and pose estimation processes.

## Architecture

The application consists of several key components:

1. **Main Orchestrator** ([src/main.py](src/main.py))
   - Entry point for the application
   - Manages session state and user onboarding
   - Coordinates voice agent and pose estimation processes
   - Handles IPC communication setup

2. **Session Management** ([src/session_manager.py](src/session_manager.py))
   - Stores user sessions in local JSON file
   - Checks for existing sessions on startup
   - Creates and saves new sessions after onboarding

3. **IPC Communication** ([src/ipc_communication.py](src/ipc_communication.py))
   - UNIX domain socket-based communication
   - Server runs in main process
   - Client runs in pose estimation process
   - Exchanges JSON messages (rep counts, form feedback, etc.)

4. **Voice Agent** ([src/Agent.py](src/Agent.py))
   - Handles all user communication
   - Manages states: onboarding, main_menu, workout
   - Provides conversational AI for coaching and instructions

5. **Pose Estimation Process** ([src/pose_estimation_process.py](src/pose_estimation_process.py))
   - Runs stereo pose estimation with two cameras
   - Uses calibrations from `biomechanics/week2_stereo/`
   - Sends data to main process via IPC
   - Currently sends placeholder data (rep counts, form feedback)

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
  ┌─────────┐  ┌──────────────┐
  │Onboarding│  │  Main Menu   │
  └────┬────┘  └──────┬───────┘
       │              │
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐
       │  Main Menu   │
       │              │
       │ 1. Workout   │
       │ 2. Questions │
       │ 3. Exit      │
       └──────┬───────┘
              │
              ▼
       ┌─────────────────┐
       │  Start Workout  │
       ├─────────────────┤
       │ • IPC Server    │
       │ • Pose Process  │
       │ • Voice Agent   │
       └─────────────────┘
```

## Session Storage

Sessions are stored in `src/.session.json`:

```json
{
  "user_id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "created_at": "2025-10-18T12:00:00"
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

1. **Initialize Database:**
   ```bash
   cd src
   python db/setup_db.py
   ```

2. **Run Main Application:**
   ```bash
   python src/main.py
   ```

3. **Onboarding:**
   - Enter username when prompted
   - Enter email when prompted
   - User is created in database
   - Session is saved locally

### Subsequent Runs

```bash
python src/main.py
```

The app will detect the existing session and skip onboarding.

### Starting a Workout

1. Select option `1` from main menu
2. IPC server starts in background
3. Pose estimation process launches
4. Two camera feeds appear in OpenCV window
5. Placeholder data flows through IPC:
   - Rep count increments every ~1 second
   - Form feedback sent every 3 reps
6. Press `Ctrl+C` to stop workout

## Testing

### Test IPC Communication

```bash
cd src
python test_ipc.py
```

This test verifies:
- Server and client can connect
- Messages flow bidirectionally
- JSON serialization works correctly

Expected output:
```
✓ Test PASSED: IPC communication working correctly
```

## Current Status

### ✅ Implemented
- Session management with JSON storage
- Database integration for user management
- IPC communication (UNIX domain sockets)
- Basic onboarding flow
- Pose estimation process with stereo cameras
- Main orchestrator script

### 🚧 Placeholder/Simplified
- Onboarding uses text input (voice agent integration pending)
- Main menu uses text input (voice agent integration pending)
- Pose estimation sends dummy data (real metrics pending)
- Voice agent states defined but not fully integrated

### 📋 TODO
- Integrate voice agent for onboarding conversation
- Extract username/email from voice conversation
- Integrate voice agent for main menu
- Send real pose metrics through IPC (joint angles, depth, etc.)
- Implement actual rep counting logic
- Implement form analysis (knees caving, back angle, etc.)
- Add workout programs and exercise tracking
- Persist workout data to database

## File Structure

```
src/
├── main.py                      # Main orchestrator
├── session_manager.py           # Session management
├── ipc_communication.py         # IPC server/client
├── pose_estimation_process.py   # Pose estimation wrapper
├── Agent.py                     # Voice agent with states
├── test_ipc.py                 # IPC test script
├── .session.json               # User session (created at runtime)
├── db/                         # Database module
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   └── setup_db.py
└── biomechanics/               # Pose estimation
    └── week2_stereo/
        ├── stereo_triangulation.py
        └── stereo_calibration.npz
```

## Dependencies

See [src/requirements.txt](src/requirements.txt) and [src/biomechanics/requirements.txt](src/biomechanics/requirements.txt)

Key dependencies:
- LiveKit (voice agent)
- OpenCV (pose estimation)
- SQLAlchemy (database)
- NumPy (pose calculations)

## Notes

- IPC uses UNIX domain sockets (macOS/Linux only)
- Pose estimation requires two cameras (cam0, cam1)
- MPS device required for pose model (Apple Silicon)
- Session file is stored in `src/.session.json`
- Database SQLite file location defined in `.env`
